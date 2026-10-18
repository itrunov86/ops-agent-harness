from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

import httpx
from mcp.server.fastmcp import FastMCP


def register(
    mcp: FastMCP,
    cfg: dict[str, Any],
    client_factory: Callable[[], httpx.AsyncClient],
    redactor: Any,
    audit_fn: Callable[[str, dict, int], None],
) -> None:
    limits = cfg.get("limits", {}) or {}

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    def _configured() -> bool:
        return bool(cfg and cfg.get("url"))

    def _base() -> str:
        return cfg["url"].rstrip("/")

    def _api(path: str) -> str:
        return f"{_base()}{path}"

    def _trim(value: Any, max_chars: int) -> Any:
        """Обрезает строку до max_chars с суффиксом о количестве отброшенных символов."""
        if isinstance(value, str) and len(value) > max_chars:
            return value[:max_chars] + f"…(+{len(value) - max_chars} chars)"
        return value

    def _compact_dashboard_meta(item: dict[str, Any]) -> dict[str, Any]:
        """Из ответа /api/search или meta-части /api/dashboards/uid/{uid}."""
        return {
            "uid": item.get("uid"),
            "title": item.get("title"),
            "type": item.get("type"),  # 'dash-db' / 'dash-folder'
            "folder_title": item.get("folderTitle") or item.get("folder_title"),
            "folder_uid": item.get("folderUid") or item.get("folder_uid"),
            "tags": item.get("tags") or [],
            "url": f"{_base()}{item.get('url')}" if item.get("url") else None,
            "uri": item.get("uri"),
        }

    def _compact_panel(p: dict[str, Any], max_chars: int) -> dict[str, Any]:
        """Из массива dashboard.panels — оставляем только метаданные, без полных
        queries (они длинные и обычно не нужны для быстрой инспекции)."""
        targets = p.get("targets") or []
        target_summary = []
        for t in targets:
            # PromQL / LogsQL / SQL — поле зависит от datasource.
            expr = t.get("expr") or t.get("query") or t.get("rawSql") or ""
            target_summary.append({
                "refId": t.get("refId"),
                "datasource": (t.get("datasource") or {}).get("uid")
                    if isinstance(t.get("datasource"), dict)
                    else t.get("datasource"),
                "expr": _trim(expr, max_chars),
            })
        ds = p.get("datasource")
        return {
            "id": p.get("id"),
            "type": p.get("type"),
            "title": p.get("title"),
            "datasource": (ds.get("uid") if isinstance(ds, dict) else ds),
            "targets": target_summary,
        }

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    @mcp.tool()
    async def grafana_search(
        query: str | None = None,
        type: str | None = None,
        tag: str | None = None,
        folder_uid: str | None = None,
        limit: int = 30,
    ) -> dict[str, Any]:
        """
        Поиск дашбордов и папок в Grafana.

        Args:
            query:      текстовая строка (фрагмент названия). None — без фильтра.
            type:       'dash-db' (только дашборды) или 'dash-folder' (только папки).
                        None — оба типа.
            tag:        фильтр по тегу.
            folder_uid: ограничить поиск папкой (по UID). None — без ограничения.
            limit:      максимум результатов (потолок limits.max_dashboards_returned).
        """
        if not _configured():
            return {"error": "grafana не сконфигурирован в config.yaml"}

        cap = int(limits.get("max_dashboards_returned", 50))
        limit = min(max(1, limit), cap)

        params: dict[str, Any] = {"limit": str(limit)}
        if query:
            params["query"] = query
        if type:
            params["type"] = type
        if tag:
            params["tag"] = tag
        if folder_uid:
            params["folderUIDs"] = folder_uid

        async with client_factory() as c:
            r = await c.get(_api("/api/search"), params=params)
            if r.status_code >= 400:
                return {"error": "grafana error", "status": r.status_code,
                        "details": r.text[:500]}
            data = r.json() or []

        items = [_compact_dashboard_meta(it) for it in data]
        payload = {
            "returned": len(items),
            "results": redactor.scrub_any(items),
        }
        audit_fn("grafana_search",
              {"query": query, "type": type, "tag": tag, "folder_uid": folder_uid,
               "limit": limit},
              len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def grafana_get_dashboard(uid: str) -> dict[str, Any]:
        """
        Получить дашборд по UID. Возвращает мета-инфу и компактный список панелей
        (id/type/title/datasource/targets с обрезанными query).

        Полный JSON-дашборд не возвращаем — он бывает огромным и для большинства
        задач не нужен. Если нужен — открой Grafana по url.

        Args:
            uid: UID дашборда (виден в URL Grafana и в результатах grafana_search).
        """
        if not _configured():
            return {"error": "grafana не сконфигурирован в config.yaml"}

        async with client_factory() as c:
            r = await c.get(_api(f"/api/dashboards/uid/{uid}"))
            if r.status_code == 404:
                return {"error": f"дашборд {uid} не найден"}
            if r.status_code >= 400:
                return {"error": "grafana error", "status": r.status_code,
                        "details": r.text[:500]}
            data = r.json() or {}

        meta = data.get("meta", {}) or {}
        dash = data.get("dashboard", {}) or {}
        panels = dash.get("panels") or []
        max_chars = int(limits.get("max_field_chars", 4000))
        cap = int(limits.get("max_panels_returned", 100))
        truncated = len(panels) > cap
        compact_panels = [_compact_panel(p, max_chars) for p in panels[:cap]]

        payload = {
            "uid": uid,
            "title": dash.get("title"),
            "tags": dash.get("tags") or [],
            "folder_title": meta.get("folderTitle"),
            "folder_uid": meta.get("folderUid"),
            "version": dash.get("version"),
            "schema_version": dash.get("schemaVersion"),
            "url": f"{_base()}{meta.get('url')}" if meta.get("url") else None,
            "total_panels": len(panels),
            "returned_panels": len(compact_panels),
            "truncated_panels": truncated,
            "panels": redactor.scrub_any(compact_panels),
        }
        audit_fn("grafana_get_dashboard", {"uid": uid},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def grafana_list_datasources() -> dict[str, Any]:
        """
        Список datasources, подключённых к Grafana.

        Используется чтобы понять, какие источники метрик/логов/трейсов смотрит
        Grafana — Prometheus, Loki, VictoriaMetrics, Tempo и т.д.

        Args:
        """
        if not _configured():
            return {"error": "grafana не сконфигурирован в config.yaml"}

        async with client_factory() as c:
            r = await c.get(_api("/api/datasources"))
            if r.status_code >= 400:
                return {"error": "grafana error", "status": r.status_code,
                        "details": r.text[:500]}
            data = r.json() or []

        items = [
            {
                "id": d.get("id"),
                "uid": d.get("uid"),
                "name": d.get("name"),
                "type": d.get("type"),
                "url": d.get("url"),
                "is_default": d.get("isDefault"),
                "access": d.get("access"),
            }
            for d in data
        ]
        payload = {
            "returned": len(items),
            "datasources": redactor.scrub_any(items),
        }
        audit_fn("grafana_list_datasources", {},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def grafana_get_annotations(
        from_ts: int | None = None,
        to_ts: int | None = None,
        tags: list[str] | None = None,
        dashboard_uid: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """
        Аннотации Grafana за окно времени — релизы, инциденты, ручные пометки.

        Полезно для корреляции: что в это время катилось, какие были ручные
        маркеры на дашбордах.

        Args:
            from_ts:        unix-время в ms. None = now - 24h.
            to_ts:          unix-время в ms. None = now.
            tags:           фильтр по тегам (например ['deploy', 'incident']).
            dashboard_uid:  ограничить аннотациями конкретного дашборда.
            limit:          максимум (потолок limits.max_annotations_returned).
        """
        if not _configured():
            return {"error": "grafana не сконфигурирован в config.yaml"}

        cap = int(limits.get("max_annotations_returned", 200))
        limit = min(max(1, limit), cap)

        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        if to_ts is None:
            to_ts = now_ms
        if from_ts is None:
            from_ts = now_ms - 24 * 3600 * 1000

        params: dict[str, Any] = {
            "from": str(from_ts),
            "to": str(to_ts),
            "limit": str(limit),
        }
        if dashboard_uid:
            params["dashboardUID"] = dashboard_uid
        # httpx принимает list для повторяющихся параметров.
        if tags:
            params["tags"] = list(tags)

        async with client_factory() as c:
            r = await c.get(_api("/api/annotations"), params=params)
            if r.status_code >= 400:
                return {"error": "grafana error", "status": r.status_code,
                        "details": r.text[:500]}
            data = r.json() or []

        max_chars = int(limits.get("max_field_chars", 4000))
        items = [
            {
                "id": a.get("id"),
                "dashboard_uid": a.get("dashboardUID"),
                "panel_id": a.get("panelId"),
                "time": a.get("time"),
                "time_end": a.get("timeEnd"),
                "text": _trim(a.get("text") or "", max_chars),
                "tags": a.get("tags") or [],
                "login": a.get("login"),
            }
            for a in data
        ]
        payload = {
            "from_ms": from_ts,
            "to_ms": to_ts,
            "returned": len(items),
            "annotations": redactor.scrub_any(items),
        }
        audit_fn("grafana_get_annotations",
              {"from_ts": from_ts, "to_ts": to_ts, "tags": tags,
               "dashboard_uid": dashboard_uid, "limit": limit},
              len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def grafana_list_alert_rules(
        folder_uid: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Список alert rules (Grafana Unified Alerting). Используется чтобы понять,
        что сейчас алертится в кластере, какие пороги и где определены правила.

        Использует /api/v1/provisioning/alert-rules — требует роль Editor/Admin
        или Service Account с правом alert.rules:read.

        Args:
            folder_uid: ограничить папкой. None — все правила.
            limit:      максимум (потолок limits.max_alert_rules_returned).
        """
        if not _configured():
            return {"error": "grafana не сконфигурирован в config.yaml"}

        cap = int(limits.get("max_alert_rules_returned", 100))
        limit = min(max(1, limit), cap)

        async with client_factory() as c:
            r = await c.get(_api("/api/v1/provisioning/alert-rules"))
            if r.status_code == 403:
                return {
                    "error": "недостаточно прав. Нужна роль Editor/Admin или Service Account с alert.rules:read.",
                }
            if r.status_code >= 400:
                return {"error": "grafana error", "status": r.status_code,
                        "details": r.text[:500]}
            data = r.json() or []

        max_chars = int(limits.get("max_field_chars", 4000))
        items = []
        for rule in data:
            if folder_uid and rule.get("folderUID") != folder_uid:
                continue
            # Сводим условия и query в краткую форму.
            d = rule.get("data") or []
            exprs = []
            for query in d:
                model = query.get("model") or {}
                expr = model.get("expr") or model.get("expression") or ""
                if expr:
                    exprs.append({
                        "refId": query.get("refId"),
                        "datasource": (query.get("datasourceUid")
                                       or (query.get("datasource") or {}).get("uid")),
                        "expr": _trim(expr, max_chars),
                    })
            items.append({
                "uid": rule.get("uid"),
                "title": rule.get("title"),
                "folder_uid": rule.get("folderUID"),
                "rule_group": rule.get("ruleGroup"),
                "condition": rule.get("condition"),
                "for": rule.get("for"),
                "no_data_state": rule.get("noDataState"),
                "exec_err_state": rule.get("execErrState"),
                "labels": rule.get("labels") or {},
                "annotations": {k: _trim(str(v), max_chars)
                                for k, v in (rule.get("annotations") or {}).items()},
                "queries": exprs,
            })
            if len(items) >= limit:
                break

        payload = {
            "returned": len(items),
            "alert_rules": redactor.scrub_any(items),
        }
        audit_fn("grafana_list_alert_rules",
              {"folder_uid": folder_uid, "limit": limit},
              len(json.dumps(payload)))
        return payload
