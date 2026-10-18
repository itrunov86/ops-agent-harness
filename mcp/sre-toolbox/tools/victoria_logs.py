from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from dataclasses import replace
from typing import Any, Callable

import httpx
from mcp.server.fastmcp import FastMCP

from tools.victoria_metrics import (
    _QueryTarget,
    _error,
    _finish,
    _int_limit,
    _json_size,
    _parse_timestamp,
    _request_timeout,
    _resolve_target,
)


def _header_kwargs(target: _QueryTarget) -> dict[str, Any]:
    return {"headers": dict(target.headers)} if target.headers else {}


def _tenant_map(cfg: dict[str, Any]) -> dict[str, str]:
    """Server-side map of VictoriaLogs tenant name -> AccountID."""
    raw = cfg.get("tenants") or {}
    if not isinstance(raw, dict):
        return {}
    return {
        str(name).strip(): str(account_id).strip()
        for name, account_id in raw.items()
        if str(name).strip() and str(account_id).strip().isdigit()
    }


def _apply_tenant(
    cfg: dict[str, Any],
    tenants: dict[str, str],
    target: _QueryTarget,
    tenant: str | None,
) -> tuple[_QueryTarget, str | None, str | None]:
    """Pin the request to one allowlisted tenant via AccountID header.

    Returns (target, tenant_name, error).
    """
    requested = (tenant or "").strip() or (str(cfg.get("default_tenant") or "").strip() or None)
    if requested is None:
        return target, None, None
    if not tenants:
        return target, None, "tenant routing is not configured for VictoriaLogs"

    if requested in tenants:
        name = requested
    else:
        name = next((n for n, account_id in tenants.items() if account_id == requested), "")
    if not name:
        return target, None, (
            f"unknown tenant: {requested}; available: {', '.join(sorted(tenants))}"
        )
    headers = {**(target.headers or {}), "AccountID": tenants[name], "ProjectID": "0"}
    return replace(target, headers=headers), name, None


async def _fetch_ndjson(
    target: _QueryTarget,
    path: str,
    params: dict[str, Any],
    timeout_seconds: float,
    max_input_bytes: int,
) -> tuple[list[dict[str, Any]], bool, dict[str, Any] | None]:
    """Read a bounded VictoriaLogs NDJSON response through the resolved target."""

    async def read_response(response: Any) -> tuple[list[dict[str, Any]], bool, dict[str, Any] | None]:
        if response.status_code >= 400:
            return [], False, {
                "error": "logs upstream request failed",
                "status": response.status_code,
            }

        lines: list[dict[str, Any]] = []
        bytes_read = 0
        truncated_input = False
        async for raw_line in response.aiter_lines():
            if not raw_line:
                continue
            bytes_read += len(raw_line.encode("utf-8", errors="replace")) + 1
            if bytes_read > max_input_bytes:
                truncated_input = True
                break
            try:
                obj = json.loads(raw_line)
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(obj, dict):
                lines.append(obj)
        return lines, truncated_input, None

    async def request() -> tuple[list[dict[str, Any]], bool, dict[str, Any] | None]:
        async with target.client_factory() as client:
            async with client.stream(
                "GET", target.endpoint(path), params=params, **_header_kwargs(target)
            ) as response:
                return await read_response(response)

    try:
        return await asyncio.wait_for(request(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return [], False, {"error": "logs request timed out"}
    except httpx.TimeoutException:
        return [], False, {"error": "logs request timed out"}
    except httpx.RequestError:
        return [], False, {"error": "logs request failed"}


async def _fetch_json(
    target: _QueryTarget,
    path: str,
    params: dict[str, Any],
    timeout_seconds: float,
) -> tuple[Any, dict[str, Any] | None]:
    """Fetch a bounded JSON response without exposing upstream response text."""

    async def request() -> tuple[Any, dict[str, Any] | None]:
        async with target.client_factory() as client:
            response = await client.get(
                target.endpoint(path), params=params, **_header_kwargs(target)
            )
        if response.status_code >= 400:
            return None, {
                "error": "logs upstream request failed",
                "status": response.status_code,
            }
        try:
            return response.json(), None
        except (TypeError, ValueError):
            # VictoriaLogs versions may return streams as newline-delimited JSON.
            raw_text = str(getattr(response, "text", "") or "")
            values: list[Any] = []
            for raw_line in raw_text.splitlines():
                try:
                    values.append(json.loads(raw_line))
                except (TypeError, json.JSONDecodeError):
                    continue
            if values:
                return values, None
            return None, {"error": "logs upstream returned invalid JSON"}

    try:
        return await asyncio.wait_for(request(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        return None, {"error": "logs request timed out"}
    except httpx.TimeoutException:
        return None, {"error": "logs request timed out"}
    except httpx.RequestError:
        return None, {"error": "logs request failed"}


def _validate_window(start: str, end: str, limits: dict[str, Any]) -> str | None:
    start_seconds = _parse_timestamp(start)
    end_seconds = _parse_timestamp(end)
    if start_seconds is None or end_seconds is None:
        return "start and end must be RFC3339 or Unix timestamps"
    if end_seconds <= start_seconds:
        return "end must be greater than start"

    try:
        max_window_hours = float(limits.get("max_query_window_hours", 24))
    except (TypeError, ValueError):
        max_window_hours = 24.0
    max_window_hours = max(0.001, max_window_hours)
    if end_seconds - start_seconds > max_window_hours * 3600:
        return f"query window exceeds max_query_window_hours ({max_window_hours:g} hours)"
    return None


def register(
    mcp: FastMCP,
    cfg: dict[str, Any],
    client_factory: Callable[[], httpx.AsyncClient],
    redactor: Any,
    audit_fn: Callable[[str, dict, int], None],
    allowlist_fn: Callable[[str], str | None] | None = None,
) -> None:
    limits = cfg.get("limits", {}) or {}
    tenants = _tenant_map(cfg)

    def finish(payload: dict[str, Any]) -> dict[str, Any]:
        return _finish(payload, redactor, limits)

    def resolve(tenant: str | None) -> tuple[_QueryTarget | None, str | None, dict[str, Any] | None]:
        target, error = _resolve_target(cfg, client_factory, backend_name="VictoriaLogs")
        if error:
            return None, None, error
        assert target is not None
        target, tenant_name, tenant_error = _apply_tenant(cfg, tenants, target, tenant)
        if tenant_error:
            return None, None, _error(tenant_error)
        return target, tenant_name, None

    @mcp.tool()
    async def vl_query(
        logsql: str,
        start: str,
        end: str,
        limit: int | None = None,
        mode: str | None = None,
        tenant: str | None = None,
    ) -> dict[str, Any]:
        """
        LogsQL-запрос к VictoriaLogs одного тенанта.

        Args:
            logsql: LogsQL-выражение, например '_stream:{service="api"} error'.
            start: RFC3339 timestamp начала окна.
            end: RFC3339 timestamp конца окна.
            limit: максимум строк (потолок из конфига).
            mode: 'patterns' (по умолчанию — кластеризация) или 'lines'.
            tenant: тенант логов (имя из server-side карты,
                    например payments-prod, infra, k8s-prod, или его
                    AccountID). None — default_tenant из конфига. Неизвестное
                    имя вернёт список доступных.

        Returns:
            При mode='patterns': {total_lines, unique_patterns, top_patterns}
            При mode='lines': {count, lines}
        """
        target, tenant_name, selection_error = resolve(tenant)
        if selection_error:
            return finish(selection_error)
        assert target is not None
        tenant_context = {"tenant": tenant_name} if tenant_name else {}

        if allowlist_fn:
            if err := allowlist_fn(logsql):
                return finish(_error(err))

        default_limit = _int_limit(limits, "default_limit", 100)
        max_lines = _int_limit(limits, "max_lines_returned", 500)
        selected_mode = mode or limits.get("default_mode", "patterns")
        if selected_mode not in ("patterns", "lines"):
            return finish(_error(
                "unknown mode; use 'patterns' or 'lines'",
            ))
        try:
            requested_limit = default_limit if limit is None else int(limit)
        except (TypeError, ValueError):
            return finish(_error(
                "limit must be a positive integer",
            ))
        if requested_limit <= 0:
            return finish(_error(
                "limit must be a positive integer",
            ))
        line_limit = min(requested_limit, max_lines)

        if validation_error := _validate_window(start, end, limits):
            return finish(_error(validation_error))

        try:
            max_response_bytes = _int_limit(limits, "max_response_bytes", 262_144)
        except (TypeError, ValueError):
            max_response_bytes = 262_144
        max_input_bytes = _int_limit(
            limits,
            "max_input_bytes",
            max(1_048_576, max_response_bytes * 8),
        )
        params = {
            "query": logsql,
            "start": start,
            "end": end,
            "limit": str(line_limit),
        }
        raw_events, truncated_input, request_error = await _fetch_ndjson(
            target,
            "/select/logsql/query",
            params,
            _request_timeout(cfg, limits),
            max_input_bytes,
        )
        if request_error:
            return finish(_error(
                request_error.pop("error", "logs request failed"),
                **request_error,
            ))

        lines: list[str] = []
        for obj in raw_events[:line_limit]:
            msg = obj.get("_msg")
            if msg is None:
                msg = json.dumps(obj, ensure_ascii=False)
            lines.append(str(msg))

        if selected_mode == "lines":
            payload = {
                **tenant_context,
                "count": len(lines),
                "truncated_input": truncated_input,
                "lines": lines,
            }
            result = finish(payload)
            audit_fn(
                "vl_query",
                {
                    "logsql": logsql,
                    "start": start,
                    "end": end,
                    "limit": line_limit,
                    "mode": selected_mode,
                    "tenant": tenant_name,
                },
                _json_size(result),
            )
            return result

        def normalize(value: str) -> str:
            value = re.sub(r"\b[0-9a-fA-F]{8,}\b", "<HEX>", value)
            value = re.sub(r"\d+", "<N>", value)
            value = re.sub(r'"[^"]{12,}"', '"<STR>"', value)
            value = re.sub(r"\s+", " ", value).strip()
            return value[:240]

        counter: Counter[str] = Counter(normalize(line) for line in lines)
        top_n = _int_limit(limits, "pattern_cluster_top", 30)
        payload = {
            **tenant_context,
            "total_lines": len(lines),
            "unique_patterns": len(counter),
            "truncated_input": truncated_input,
            "top_patterns": [
                {"pattern": pattern, "count": count}
                for pattern, count in counter.most_common(top_n)
            ],
        }
        result = finish(payload)
        audit_fn(
            "vl_query",
            {
                "logsql": logsql,
                "start": start,
                "end": end,
                "limit": line_limit,
                "mode": selected_mode,
                "tenant": tenant_name,
            },
            _json_size(result),
        )
        return result

    @mcp.tool()
    async def vl_streams(
        query: str = "*",
        limit: int = 50,
        tenant: str | None = None,
    ) -> dict[str, Any]:
        """
        Список потоков (_stream) в VictoriaLogs одного тенанта.

        Args:
            query: LogsQL-выражение для фильтрации (по умолчанию '*').
            limit: максимум потоков в ответе.
            tenant: тенант логов (имя из server-side карты
                    или AccountID). None — default_tenant из конфига.
        """
        target, tenant_name, selection_error = resolve(tenant)
        if selection_error:
            return finish(selection_error)
        assert target is not None
        tenant_context = {"tenant": tenant_name} if tenant_name else {}

        if allowlist_fn:
            if err := allowlist_fn(query):
                return finish(_error(err))

        max_streams = _int_limit(limits, "max_streams_returned", 200)
        try:
            requested_limit = int(limit)
        except (TypeError, ValueError):
            return finish(_error(
                "limit must be a positive integer",
            ))
        if requested_limit <= 0:
            return finish(_error(
                "limit must be a positive integer",
            ))
        stream_limit = min(requested_limit, max_streams)
        data, request_error = await _fetch_json(
            target,
            "/select/logsql/streams",
            {"query": query, "limit": str(stream_limit)},
            _request_timeout(cfg, limits),
        )
        if request_error:
            return finish(_error(
                request_error.pop("error", "logs request failed"),
                **request_error,
            ))

        if isinstance(data, dict):
            # VictoriaLogs returns {"values": [{"value": ..., "hits": ...}]}
            # for this endpoint. Keep compatibility with older wrappers that
            # used `streams` or `data` as the collection key.
            streams = data.get("values")
            if streams is None:
                streams = data.get("streams")
            if streams is None:
                streams = data.get("data")
        else:
            streams = data
        if not isinstance(streams, list):
            return finish(_error(
                "logs upstream returned an invalid streams response",
            ))

        payload = {
            **tenant_context,
            "count": min(len(streams), max_streams),
            "truncated": len(streams) > max_streams,
            "streams": streams[:max_streams],
        }
        result = finish(payload)
        audit_fn(
            "vl_streams",
            {
                "query": query,
                "limit": stream_limit,
                "tenant": tenant_name,
            },
            _json_size(result),
        )
        return result
