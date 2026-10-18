from __future__ import annotations

import asyncio
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from urllib.parse import quote, urlsplit

import httpx
from mcp.server.fastmcp import FastMCP


_DURATION_PART = re.compile(r"(?P<value>\d+(?:\.\d+)?)(?P<unit>ms|s|m|h|d|w|y)")
_DURATION_MULTIPLIER = {
    "ms": 0.001,
    "s": 1.0,
    "m": 60.0,
    "h": 3600.0,
    "d": 86400.0,
    "w": 604800.0,
    "y": 31536000.0,
}


@dataclass(frozen=True)
class _QueryTarget:
    """Resolved destination for one request: the configured base URL only.

    URLs, credentials and tenants come from config.yaml, never from a tool
    argument; `headers` carries per-request headers such as VictoriaLogs
    AccountID chosen from a server-side allowlist.
    """

    base_url: str
    client_factory: Callable[[], Any]
    headers: dict[str, str] | None = None

    def endpoint(self, path: str) -> str:
        return f"{self.base_url}{path}"


def _parse_duration(value: Any) -> float | None:
    """Parse a Prometheus-style duration or a number of seconds."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None
    try:
        parsed = float(text)
        return parsed if math.isfinite(parsed) else None
    except ValueError:
        pass

    position = 0
    total = 0.0
    for match in _DURATION_PART.finditer(text):
        if match.start() != position:
            return None
        total += float(match.group("value")) * _DURATION_MULTIPLIER[match.group("unit")]
        position = match.end()
    if position != len(text):
        return None
    return total


def _parse_timestamp(value: Any) -> float | None:
    """Parse an RFC3339 timestamp or a Prometheus Unix timestamp."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None
    try:
        parsed = float(text)
        return parsed if math.isfinite(parsed) else None
    except ValueError:
        pass

    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.timestamp()


def _duration_limit(limits: dict[str, Any], *names: str, default: float) -> float:
    for name in names:
        if name not in limits:
            continue
        parsed = _parse_duration(limits.get(name))
        if parsed is not None and parsed > 0:
            return parsed
    return default


def _int_limit(limits: dict[str, Any], name: str, default: int) -> int:
    try:
        value = int(limits.get(name, default))
    except (TypeError, ValueError):
        return default
    return max(1, value)


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    except (TypeError, ValueError):
        return 2**63 - 1


def _bounded_response(payload: dict[str, Any], max_bytes: int) -> dict[str, Any]:
    """Keep a redacted response below the configured serialized-size limit."""
    if _json_size(payload) <= max_bytes:
        return payload

    out = dict(payload)
    out["truncated_response"] = True

    # First reduce nested point arrays, then the number of series/results.
    for key in ("series", "results", "values"):
        collection = out.get(key)
        if not isinstance(collection, list):
            continue
        while _json_size(out) > max_bytes and collection:
            changed_nested = False
            if key == "series":
                for item in collection:
                    if not isinstance(item, dict):
                        continue
                    values = item.get("values")
                    if isinstance(values, list) and len(values) > 1:
                        item["values"] = values[: max(1, len(values) // 2)]
                        changed_nested = True
            if changed_nested:
                continue
            collection = collection[: max(0, len(collection) // 2)]
            out[key] = collection

    if _json_size(out) <= max_bytes:
        return out

    # A single result can still contain unusually large labels. Keep only
    # stable context fields rather than returning an over-sized payload.
    minimal = {
        key: out[key]
        for key in ("error", "tenant", "truncated_response")
        if key in out
    }
    minimal["truncated_response"] = True
    if _json_size(minimal) <= max_bytes:
        return minimal
    return {"error": "response exceeds configured max_response_bytes", "truncated_response": True}


def _finish(
    payload: dict[str, Any],
    redactor: Any,
    limits: dict[str, Any],
) -> dict[str, Any]:
    redacted = redactor.scrub_any(payload)
    # Keep enough room for context/error metadata even if an invalid config
    # accidentally sets a tiny value. The configured limit is still enforced
    # for all practical response sizes.
    max_bytes = max(1024, _int_limit(limits, "max_response_bytes", 262_144))
    return _bounded_response(redacted, max_bytes)


def _error(message: str, **extra: Any) -> dict[str, Any]:
    return {"error": message, **extra}


def _base_url(section: dict[str, Any]) -> str | None:
    raw = str(section.get("url") or "").strip().rstrip("/")
    try:
        parsed = urlsplit(raw)
    except ValueError:
        return None
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return None
    return raw


def _resolve_target(
    cfg: dict[str, Any],
    client_factory: Callable[[], httpx.AsyncClient],
    backend_name: str = "VictoriaMetrics",
) -> tuple[_QueryTarget | None, dict[str, Any] | None]:
    base_url = _base_url(cfg)
    if base_url is None:
        return None, _error(f"invalid {backend_name} URL configuration")
    return _QueryTarget(base_url=base_url, client_factory=client_factory), None


def _request_timeout(cfg: dict[str, Any], limits: dict[str, Any]) -> float:
    default = cfg.get("timeout_seconds", 15)
    try:
        configured = float(limits.get("request_timeout_seconds", default))
    except (TypeError, ValueError):
        configured = 15.0
    try:
        maximum = float(limits.get("max_timeout_seconds", 30))
    except (TypeError, ValueError):
        maximum = 30.0
    return min(max(0.1, configured), max(0.1, maximum))


async def _fetch_json(
    target: _QueryTarget,
    path: str,
    params: dict[str, Any],
    timeout_seconds: float,
) -> tuple[Any, dict[str, Any] | None]:
    try:
        async with target.client_factory() as client:
            response = await asyncio.wait_for(
                client.get(target.endpoint(path), params=params),
                timeout=timeout_seconds,
            )
    except asyncio.TimeoutError:
        return None, {"error": "metrics request timed out"}
    except httpx.TimeoutException:
        return None, {"error": "metrics request timed out"}
    except httpx.RequestError:
        return None, {"error": "metrics request failed"}

    if response.status_code >= 400:
        return None, {"error": "metrics upstream request failed", "status": response.status_code}
    try:
        return response.json(), None
    except (TypeError, ValueError):
        return None, {"error": "metrics upstream returned invalid JSON"}


def _api_error(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "metrics upstream returned an invalid response"
    if data.get("status") == "success":
        return None
    # Do not echo the upstream error: some Prometheus-compatible backends
    # include the full query or backend URL in it.
    return "metrics upstream returned an error"


def _validate_range(
    start: str,
    end: str,
    step: str,
    limits: dict[str, Any],
) -> str | None:
    start_seconds = _parse_timestamp(start)
    end_seconds = _parse_timestamp(end)
    if start_seconds is None or end_seconds is None:
        return "start and end must be RFC3339 or Unix timestamps"
    if end_seconds <= start_seconds:
        return "end must be greater than start"

    range_seconds = end_seconds - start_seconds
    max_range = _duration_limit(
        limits,
        "max_range_seconds",
        "max_range",
        default=30 * 86400,
    )
    if range_seconds > max_range:
        return f"requested range exceeds max_range ({int(max_range)} seconds)"

    step_seconds = _parse_duration(step)
    if step_seconds is None or step_seconds <= 0:
        return "step must be a positive Prometheus duration"
    min_step = _duration_limit(limits, "min_step_seconds", "min_step", default=1)
    max_step = _duration_limit(limits, "max_step_seconds", "max_step", default=3600)
    if step_seconds < min_step:
        return f"step is below min_step ({min_step:g} seconds)"
    if step_seconds > max_step:
        return f"step exceeds max_step ({max_step:g} seconds)"

    max_points = _int_limit(limits, "max_points_requested", 100_000)
    if math.ceil(range_seconds / step_seconds) + 1 > max_points:
        return f"requested points exceed max_points_requested ({max_points})"
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

    def finish(payload: dict[str, Any]) -> dict[str, Any]:
        return _finish(payload, redactor, limits)

    @mcp.tool()
    async def vm_query(
        promql: str,
        time_: str | None = None,
    ) -> dict[str, Any]:
        """
        Instant PromQL-запрос в хаб VictoriaMetrics (все тенанты сразу).

        Кластер выбирается label vm_account_id (например 100 — prod,
        200 — staging; список — vm_label_values('vm_account_id')).

        Args:
            promql: PromQL-выражение.
            time_: RFC3339 timestamp, по умолчанию now.
        """
        target, selection_error = _resolve_target(cfg, client_factory)
        if selection_error:
            return finish(selection_error)
        assert target is not None

        if allowlist_fn:
            if err := allowlist_fn(promql):
                return finish(_error(err))

        params: dict[str, str] = {"query": promql}
        if time_:
            params["time"] = time_
        data, request_error = await _fetch_json(
            target,
            "/api/v1/query",
            params,
            _request_timeout(cfg, limits),
        )
        if request_error:
            return finish(_error(
                request_error.pop("error", "metrics request failed"),
                **request_error,
            ))
        if error_message := _api_error(data):
            return finish(_error(error_message))

        raw = ((data.get("data") or {}).get("result") or []) if isinstance(data, dict) else []
        if not isinstance(raw, list):
            return finish(_error("metrics upstream returned an invalid result"))

        cap = _int_limit(limits, "max_series_returned", 30)
        truncated = len(raw) > cap
        results = []
        for item in raw[:cap]:
            try:
                value = float(item["value"][1])
            except (KeyError, IndexError, ValueError, TypeError):
                continue
            results.append({"labels": item.get("metric", {}), "value": value})

        payload = {
            "count": len(results),
            "truncated": truncated,
            "results": results,
        }
        result = finish(payload)
        audit_fn(
            "vm_query",
            {
                "promql": promql,
                "time": time_,
            },
            _json_size(result),
        )
        return result

    @mcp.tool()
    async def vm_query_range(
        promql: str,
        start: str,
        end: str,
        step: str = "60s",
        summarize: bool | None = None,
    ) -> dict[str, Any]:
        """
        Range PromQL-запрос в хаб VictoriaMetrics; кластер — label vm_account_id.

        Args:
            promql: PromQL-выражение.
            start, end: RFC3339 timestamps или Unix timestamps.
            step: шаг, например 30s, 1m или 5m; проверяется конфигурационным
                  min/max и лимитом расчётных точек.
            summarize: если True — min/max/avg/p50/p95/p99 вместо точек.
        """
        target, selection_error = _resolve_target(cfg, client_factory)
        if selection_error:
            return finish(selection_error)
        assert target is not None

        if allowlist_fn:
            if err := allowlist_fn(promql):
                return finish(_error(err))
        if validation_error := _validate_range(start, end, step, limits):
            return finish(_error(validation_error))

        if summarize is None:
            summarize = bool(limits.get("summarize_by_default", True))

        params: dict[str, str] = {
            "query": promql,
            "start": start,
            "end": end,
            "step": step,
        }
        data, request_error = await _fetch_json(
            target,
            "/api/v1/query_range",
            params,
            _request_timeout(cfg, limits),
        )
        if request_error:
            return finish(_error(
                request_error.pop("error", "metrics request failed"),
                **request_error,
            ))
        if error_message := _api_error(data):
            return finish(_error(error_message))

        raw_series = ((data.get("data") or {}).get("result") or []) if isinstance(data, dict) else []
        if not isinstance(raw_series, list):
            return finish(_error("metrics upstream returned an invalid result"))

        series_cap = _int_limit(limits, "max_series_returned", 30)
        point_cap = _int_limit(limits, "max_points_per_series", 120)
        out: list[dict[str, Any]] = []
        for series in raw_series[:series_cap]:
            try:
                values = [float(value[1]) for value in series.get("values", [])]
            except (KeyError, IndexError, ValueError, TypeError):
                continue
            if not values:
                continue
            if summarize:
                sorted_values = sorted(values)
                count = len(sorted_values)
                out.append({
                    "labels": series.get("metric", {}),
                    "min": sorted_values[0],
                    "max": sorted_values[-1],
                    "avg": sum(values) / count,
                    "p50": sorted_values[count // 2],
                    "p95": sorted_values[min(count - 1, int(count * 0.95))],
                    "p99": sorted_values[min(count - 1, int(count * 0.99))],
                    "points": count,
                })
            else:
                stride = max(1, math.ceil(len(values) / point_cap))
                out.append({
                    "labels": series.get("metric", {}),
                    "values": values[::stride][:point_cap],
                })

        payload = {
            "series": out,
            "truncated_series": len(raw_series) > series_cap,
            "summarize": summarize,
        }
        result = finish(payload)
        audit_fn(
            "vm_query_range",
            {
                "promql": promql,
                "start": start,
                "end": end,
                "step": step,
                "summarize": summarize,
            },
            _json_size(result),
        )
        return result

    @mcp.tool()
    async def vm_label_values(
        label: str,
        match: str | None = None,
    ) -> dict[str, Any]:
        """
        Список значений лейбла в хабе VictoriaMetrics.

        Args:
            label: имя лейбла, например __name__, job, service или vm_account_id.
            match: опциональный селектор для фильтрации.
        """
        target, selection_error = _resolve_target(cfg, client_factory)
        if selection_error:
            return finish(selection_error)
        assert target is not None
        if not label.strip():
            return finish(_error("label must not be empty"))

        params: dict[str, str] = {}
        if match:
            params["match[]"] = match
        data, request_error = await _fetch_json(
            target,
            f"/api/v1/label/{quote(label.strip(), safe='')}/values",
            params,
            _request_timeout(cfg, limits),
        )
        if request_error:
            return finish(_error(
                request_error.pop("error", "metrics request failed"),
                **request_error,
            ))
        if isinstance(data, dict) and data.get("status") not in (None, "success"):
            return finish(_error(
                "metrics upstream returned an error",
            ))

        values = data.get("data", []) if isinstance(data, dict) else []
        if not isinstance(values, list):
            return finish(_error("metrics upstream returned an invalid label response"))
        cap = _int_limit(limits, "max_label_values_returned", 500)
        payload = {
            "count": min(len(values), cap),
            "truncated": len(values) > cap,
            "values": values[:cap],
        }
        result = finish(payload)
        audit_fn(
            "vm_label_values",
            {
                "label": label,
                "match": match,
            },
            _json_size(result),
        )
        return result
