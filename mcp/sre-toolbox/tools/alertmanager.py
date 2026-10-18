from __future__ import annotations

import json
from typing import Any, Callable

import httpx
from mcp.server.fastmcp import FastMCP


_SHARED_KEYS = {"instances", "default_instance", "auth", "headers", "limits"}


def _instance_configs(cfg: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Alertmanager instances: `instances` map, or legacy single `url` as "default".

    Top-level settings (timeout, verify_ssl, auth, headers) are defaults that an
    instance overrides.
    """
    if not cfg:
        return {}
    raw = cfg.get("instances") or {}
    if not raw:
        return {"default": dict(cfg)} if cfg.get("url") else {}
    shared = {k: v for k, v in cfg.items() if k not in _SHARED_KEYS}
    instances: dict[str, dict[str, Any]] = {}
    for name, instance_cfg in raw.items():
        if not isinstance(instance_cfg, dict) or not instance_cfg.get("url"):
            continue
        merged = {**shared, **instance_cfg}
        merged["auth"] = {**(cfg.get("auth") or {}), **(instance_cfg.get("auth") or {})}
        merged["headers"] = {**(cfg.get("headers") or {}), **(instance_cfg.get("headers") or {})}
        merged["url"] = str(instance_cfg["url"]).rstrip("/")
        instances[str(name)] = merged
    return instances


def register(
    mcp: FastMCP,
    cfg: dict[str, Any],
    client_factory: Callable[[dict[str, Any]], httpx.AsyncClient],
    redactor: Any,
    audit_fn: Callable[[str, dict, int], None],
) -> None:
    limits = cfg.get("limits", {}) or {}
    instances = _instance_configs(cfg)

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _select(instance: str | None) -> tuple[str | None, dict[str, Any] | None, str | None]:
        if not instances:
            return None, None, "alertmanager не сконфигурирован в config.yaml"
        requested = (instance or "").strip() or None
        if requested is None:
            configured = str(cfg.get("default_instance") or "").strip()
            name = configured if configured in instances else next(iter(instances))
            return name, instances[name], None
        if requested in instances:
            return requested, instances[requested], None
        for name, instance_cfg in instances.items():
            if requested in [str(a) for a in (instance_cfg.get("aliases") or [])]:
                return name, instance_cfg, None
        return requested, None, (
            f"unknown Alertmanager instance: {requested}; available: {', '.join(sorted(instances))}"
        )

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    @mcp.tool()
    async def am_active_alerts(
        severity: str | None = None,
        service: str | None = None,
        limit: int = 50,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """
        Активные алерты из Alertmanager (/api/v2/alerts).

        Args:
            severity: фильтр по label severity (critical/warning/info).
            service:  фильтр по label service (или job, если в вашей разметке так).
            limit:    максимум алертов в ответе (потолок 200).
            instance: Alertmanager из server-side списка (например primary, secondary).
                      None — default_instance из конфига.

        Returns:
            {instance, count, alerts: [{name, severity, service, started_at, summary, runbook}]}
        """
        name, am_cfg, error = _select(instance)
        if error:
            return {"instance": name, "error": error}
        assert am_cfg is not None

        cap = int(limits.get("max_alerts_returned", 200))
        limit = min(limit, cap)

        async with client_factory(am_cfg) as c:
            r = await c.get(f"{am_cfg['url']}/api/v2/alerts")
            r.raise_for_status()
            raw = r.json()

        out: list[dict[str, Any]] = []
        for a in raw:
            labels = a.get("labels", {}) or {}
            if severity and labels.get("severity") != severity:
                continue
            if service and (
                labels.get("service") != service
                and labels.get("job") != service
            ):
                continue
            annotations = a.get("annotations", {}) or {}
            out.append({
                "name": labels.get("alertname"),
                "severity": labels.get("severity"),
                "service": labels.get("service") or labels.get("job"),
                "started_at": a.get("startsAt"),
                "summary": annotations.get("summary") or annotations.get("description"),
                "runbook": annotations.get("runbook_url") or annotations.get("runbook"),
                "status": (a.get("status", {}) or {}).get("state"),
            })
            if len(out) >= limit:
                break

        payload = {
            "instance": name,
            "count": len(out),
            "alerts": redactor.scrub_any(out),
        }
        audit_fn("am_active_alerts",
                 {"severity": severity, "service": service, "limit": limit, "instance": name},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def am_silences(
        active_only: bool = True,
        instance: str | None = None,
    ) -> dict[str, Any]:
        """
        Список silence-ов в Alertmanager (/api/v2/silences).

        Args:
            active_only: если True, возвращает только активные.
            instance: Alertmanager из server-side списка (например primary, secondary).
                      None — default_instance из конфига.
        """
        name, am_cfg, error = _select(instance)
        if error:
            return {"instance": name, "error": error}
        assert am_cfg is not None

        async with client_factory(am_cfg) as c:
            r = await c.get(f"{am_cfg['url']}/api/v2/silences")
            r.raise_for_status()
            raw = r.json()

        out = []
        for s in raw:
            state = (s.get("status", {}) or {}).get("state")
            if active_only and state != "active":
                continue
            out.append({
                "id": s.get("id"),
                "state": state,
                "matchers": [
                    f"{m.get('name')}{'=~' if m.get('isRegex') else '='}{m.get('value')}"
                    for m in s.get("matchers", [])
                ],
                "starts_at": s.get("startsAt"),
                "ends_at": s.get("endsAt"),
                "comment": s.get("comment"),
                "created_by": s.get("createdBy"),
            })

        payload = {"instance": name, "count": len(out), "silences": redactor.scrub_any(out)}
        audit_fn("am_silences", {"active_only": active_only, "instance": name},
                 len(json.dumps(payload)))
        return payload
