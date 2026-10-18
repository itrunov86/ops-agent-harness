from __future__ import annotations

import json
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
        return bool(cfg.get("url"))

    def _base() -> str:
        return cfg["url"].rstrip("/")

    def _api(path: str) -> str:
        ver = str(cfg.get("api_version", "2"))
        return f"{_base()}/rest/api/{ver}{path}"

    def _agile(path: str) -> str:
        return f"{_base()}/rest/agile/1.0{path}"

    def _writes_enabled() -> bool:
        return bool(cfg.get("allow_writes", False))

    def _project_allowed(project_key: str | None) -> bool:
        allow = cfg.get("allow_projects") or []
        if not allow:
            return True
        if not project_key:
            return False
        return project_key.upper() in [p.upper() for p in allow]

    def _key_project(issue_key: str) -> str:
        # JIRA-123 -> JIRA
        return issue_key.split("-", 1)[0] if "-" in issue_key else issue_key

    def _trim(value: Any, max_chars: int) -> Any:
        if isinstance(value, str) and len(value) > max_chars:
            return value[:max_chars] + f"…(+{len(value) - max_chars} chars)"
        return value

    def _default_fields() -> list[str]:
        fields = limits.get("default_fields") or [
            "summary", "status", "priority", "assignee", "reporter",
            "issuetype", "labels", "created", "updated",
        ]
        return list(fields)

    def _compact_issue(
        issue: dict[str, Any],
        include_comments: bool = False,
    ) -> dict[str, Any]:
        """Сжимает Jira issue до минимально полезной формы для модели."""
        f = issue.get("fields", {}) or {}
        max_chars = int(limits.get("max_field_chars", 4000))

        def _user(u: Any) -> Any:
            if not isinstance(u, dict):
                return None
            return u.get("displayName") or u.get("name") or u.get("emailAddress")

        def _name(x: Any) -> Any:
            return x.get("name") if isinstance(x, dict) else None

        out: dict[str, Any] = {
            "key": issue.get("key"),
            "id": issue.get("id"),
            "summary": _trim(f.get("summary"), max_chars),
            "status": _name(f.get("status")),
            "priority": _name(f.get("priority")),
            "issuetype": _name(f.get("issuetype")),
            "assignee": _user(f.get("assignee")),
            "reporter": _user(f.get("reporter")),
            "labels": f.get("labels") or [],
            "components": [_name(c) for c in (f.get("components") or [])],
            "fix_versions": [_name(v) for v in (f.get("fixVersions") or [])],
            "created": f.get("created"),
            "updated": f.get("updated"),
            "duedate": f.get("duedate"),
            "url": f"{_base()}/browse/{issue.get('key')}" if issue.get("key") else None,
        }
        if f.get("description"):
            out["description"] = _trim(f["description"], max_chars)

        if include_comments:
            max_comments = int(limits.get("max_comments_in_issue", 5))
            if max_comments > 0:
                comments_field = f.get("comment", {}) or {}
                comments = comments_field.get("comments") or []
                tail = comments[-max_comments:]
                out["comments"] = [
                    {
                        "author": _user(c.get("author")),
                        "created": c.get("created"),
                        "body": _trim(c.get("body"), max_chars),
                    }
                    for c in tail
                ]
                out["comments_total"] = comments_field.get("total", len(comments))
        return out

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    @mcp.tool()
    async def jira_get_issue(
        key: str,
        fields: list[str] | None = None,
        with_comments: bool = False,
    ) -> dict[str, Any]:
        """
        Получить одну задачу Jira по ключу (например 'OPS-123').

        Возвращает компактную форму: ключевые поля + URL. Длинные строки
        обрезаются до limits.max_field_chars (экономия токенов).

        Args:
            key:           ключ задачи, например 'OPS-123'.
            fields:        список полей. None — список по умолчанию из конфига.
            with_comments: подмешать последние N комментариев (N из конфига).
        """
        if not _configured():
            return {"error": "jira не сконфигурирован в config.yaml"}
        if not _project_allowed(_key_project(key)):
            return {"error": f"проект {_key_project(key)} не в allow_projects"}

        fl = fields or _default_fields()
        # description нужен почти всегда — добавляем, если пользователь не передал свой список.
        if fields is None and "description" not in fl:
            fl = list(fl) + ["description"]
        params: dict[str, str] = {"fields": ",".join(fl)}
        if with_comments:
            # При expand=changelog приходит история; нам нужны только комментарии.
            params["fields"] = params["fields"] + ",comment"

        async with client_factory() as c:
            r = await c.get(_api(f"/issue/{key}"), params=params)
            if r.status_code == 404:
                return {"error": f"issue {key} не найден"}
            r.raise_for_status()
            data = r.json()

        payload = {"issue": redactor.scrub_any(_compact_issue(data, with_comments))}
        audit_fn("jira_get_issue", {"key": key, "fields": fl, "with_comments": with_comments},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def jira_search(
        jql: str,
        fields: list[str] | None = None,
        limit: int = 20,
        start_at: int = 0,
    ) -> dict[str, Any]:
        """
        Поиск задач Jira по JQL (Jira Query Language).

        Примеры JQL:
            project = OPS AND status = "In Progress" ORDER BY updated DESC
            assignee = currentUser() AND resolution = Unresolved
            sprint in openSprints() AND project = OPS

        Args:
            jql:      JQL-выражение.
            fields:   список полей (по умолчанию из конфига — компактный набор).
            limit:    максимум задач в ответе (потолок limits.max_issues_returned).
            start_at: пагинация (offset).

        Returns:
            {total, returned, truncated, issues: [{key, summary, status, ...}]}
        """
        if not _configured():
            return {"error": "jira не сконфигурирован в config.yaml"}

        cap = int(limits.get("max_issues_returned", 50))
        limit = min(max(1, limit), cap)
        fl = fields or _default_fields()

        body = {
            "jql": jql,
            "startAt": int(start_at),
            "maxResults": limit,
            "fields": fl,
        }
        async with client_factory() as c:
            r = await c.post(_api("/search"), content=json.dumps(body))
            if r.status_code >= 400:
                try:
                    err = r.json()
                except json.JSONDecodeError:
                    err = {"raw": r.text[:500]}
                return {"error": "jira error", "status": r.status_code, "details": err}
            data = r.json()

        issues_raw = data.get("issues", []) or []
        # Дополнительная пост-фильтрация allow_projects (на случай если JQL шире).
        issues = [
            _compact_issue(i) for i in issues_raw
            if _project_allowed(_key_project(i.get("key", "")))
        ]
        payload = {
            "total": data.get("total"),
            "returned": len(issues),
            "truncated": (data.get("total") or 0) > (start_at + len(issues)),
            "issues": redactor.scrub_any(issues),
        }
        audit_fn("jira_search", {"jql": jql, "limit": limit, "start_at": start_at, "fields": fl},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def jira_create_issue(
        project: str,
        issue_type: str,
        summary: str,
        description: str | None = None,
        assignee: str | None = None,
        labels: list[str] | None = None,
        priority: str | None = None,
        parent_key: str | None = None,
        epic_key: str | None = None,
        extra_fields: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Создать новую задачу в Jira.

        Включается через jira.allow_writes: true. Allowlist по проектам тоже
        применяется. По умолчанию — read-only.

        Args:
            project:      project key, например 'OPS'.
            issue_type:   название типа: 'Task', 'Bug', 'Story', 'Sub-task',
                          'Epic' и т.п.
            summary:      заголовок.
            description:  тело (Jira wiki markup или текст).
            assignee:     username исполнителя (Jira Server использует name,
                          не accountId).
            labels:       список лейблов.
            priority:     название приоритета: 'High', 'Medium' и т.п.
            parent_key:   для подзадач — ключ родителя.
            epic_key:     ключ эпика для привязки через Agile API после создания
                          (например 'OPS-1000'). Надёжнее, чем customfield_10008/10014,
                          которые часто не доступны на экране создания.
            extra_fields: произвольные дополнительные поля fields в формате Jira REST.
                          Нужно для customfield'ов (например Epic Name — его customfield_NNNNN
                          зависит от инстанса, — обязателен при создании Epic).
                          Эти поля смерджатся в верхний уровень fields поверх
                          именованных параметров.
        """
        if not _configured():
            return {"error": "jira не сконфигурирован в config.yaml"}
        if not _writes_enabled():
            return {"error": "запись в jira отключена; jira.allow_writes=true в config.yaml"}
        if not _project_allowed(project):
            return {"error": f"проект {project} не в allow_projects"}

        fields: dict[str, Any] = {
            "project": {"key": project},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }
        if description:
            fields["description"] = description
        if assignee:
            fields["assignee"] = {"name": assignee}
        if labels:
            fields["labels"] = labels
        if priority:
            fields["priority"] = {"name": priority}
        if parent_key:
            fields["parent"] = {"key": parent_key}
        if extra_fields:
            fields.update(extra_fields)

        body = {"fields": fields}
        async with client_factory() as c:
            r = await c.post(_api("/issue"), content=json.dumps(body))
            if r.status_code >= 400:
                try:
                    err = r.json()
                except json.JSONDecodeError:
                    err = {"raw": r.text[:500]}
                return {"error": "jira error", "status": r.status_code, "details": err}
            data = r.json()

        issue_key = data.get("key")
        payload: dict[str, Any] = {
            "created": True,
            "key": issue_key,
            "id": data.get("id"),
            "url": f"{_base()}/browse/{issue_key}" if issue_key else None,
        }

        if epic_key and issue_key and _project_allowed(_key_project(epic_key)):
            async with client_factory() as c:
                er = await c.post(
                    _agile(f"/epic/{epic_key}/issue"),
                    content=json.dumps({"issues": [issue_key]}),
                )
            payload["epic_linked"] = er.status_code in (200, 204)
            if not payload["epic_linked"]:
                payload["epic_link_error"] = er.text[:200]

        audit_fn("jira_create_issue",
                 {"project": project, "issue_type": issue_type, "summary": summary,
                  "epic_key": epic_key},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def jira_update_issue(
        key: str,
        fields: dict[str, Any] | None = None,
        summary: str | None = None,
        description: str | None = None,
        assignee: str | None = None,
        labels: list[str] | None = None,
        priority: str | None = None,
    ) -> dict[str, Any]:
        """
        Обновить поля задачи Jira.

        Можно передать либо готовый словарь fields (как требует Jira REST),
        либо отдельные удобные параметры — они смерджатся.

        Args:
            key:         ключ задачи (например 'OPS-123').
            fields:      сырая структура fields в формате Jira REST.
            summary:     новый заголовок.
            description: новое описание.
            assignee:    новый исполнитель (username; null строкой 'null' для unassign не работает —
                         передайте fields={"assignee": null}).
            labels:      полный новый список лейблов.
            priority:    новый приоритет (например 'High').
        """
        if not _configured():
            return {"error": "jira не сконфигурирован в config.yaml"}
        if not _writes_enabled():
            return {"error": "запись в jira отключена; jira.allow_writes=true в config.yaml"}
        if not _project_allowed(_key_project(key)):
            return {"error": f"проект {_key_project(key)} не в allow_projects"}

        merged: dict[str, Any] = dict(fields or {})
        if summary is not None:
            merged["summary"] = summary
        if description is not None:
            merged["description"] = description
        if assignee is not None:
            merged["assignee"] = {"name": assignee}
        if labels is not None:
            merged["labels"] = labels
        if priority is not None:
            merged["priority"] = {"name": priority}

        if not merged:
            return {"error": "нечего обновлять — задайте fields или хотя бы одно поле"}

        body = {"fields": merged}
        async with client_factory() as c:
            r = await c.put(_api(f"/issue/{key}"), content=json.dumps(body))
            if r.status_code >= 400:
                try:
                    err = r.json()
                except json.JSONDecodeError:
                    err = {"raw": r.text[:500]}
                return {"error": "jira error", "status": r.status_code, "details": err}

        payload = {"updated": True, "key": key, "fields_changed": list(merged.keys())}
        audit_fn("jira_update_issue", {"key": key, "fields_changed": list(merged.keys())},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def jira_transition_issue(
        key: str,
        transition: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        """
        Перевести задачу Jira в другой статус (workflow transition).

        Jira принимает не имя статуса, а ID транзишена. Этот tool сам ищет
        подходящий ID по имени транзишена (например 'In Progress', 'Done').

        Args:
            key:        ключ задачи (например 'OPS-123').
            transition: имя транзишена (Jira UI -> кнопка перехода).
            comment:    опциональный комментарий, добавляется атомарно с transition.
        """
        if not _configured():
            return {"error": "jira не сконфигурирован в config.yaml"}
        if not _writes_enabled():
            return {"error": "запись в jira отключена; jira.allow_writes=true в config.yaml"}
        if not _project_allowed(_key_project(key)):
            return {"error": f"проект {_key_project(key)} не в allow_projects"}

        async with client_factory() as c:
            # 1. Получаем список доступных транзишенов.
            r = await c.get(_api(f"/issue/{key}/transitions"))
            if r.status_code >= 400:
                return {"error": "jira error", "status": r.status_code, "details": r.text[:500]}
            trs = (r.json().get("transitions") or [])
            match = next(
                (t for t in trs if (t.get("name") or "").lower() == transition.lower()),
                None,
            )
            if not match:
                available = [t.get("name") for t in trs]
                return {"error": f"transition '{transition}' недоступен", "available": available}

            body: dict[str, Any] = {"transition": {"id": match["id"]}}
            if comment:
                body["update"] = {"comment": [{"add": {"body": comment}}]}

            r2 = await c.post(
                _api(f"/issue/{key}/transitions"),
                content=json.dumps(body),
            )
            if r2.status_code >= 400:
                try:
                    err = r2.json()
                except json.JSONDecodeError:
                    err = {"raw": r2.text[:500]}
                return {"error": "jira transition error", "status": r2.status_code, "details": err}

        payload = {
            "transitioned": True,
            "key": key,
            "to": match.get("to", {}).get("name") or match.get("name"),
        }
        audit_fn("jira_transition_issue", {"key": key, "transition": transition, "with_comment": bool(comment)},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def jira_add_comment(key: str, body: str) -> dict[str, Any]:
        """
        Добавить комментарий к задаче Jira.

        Args:
            key:  ключ задачи (например 'OPS-123').
            body: тело комментария (Jira wiki markup или текст).
        """
        if not _configured():
            return {"error": "jira не сконфигурирован в config.yaml"}
        if not _writes_enabled():
            return {"error": "запись в jira отключена; jira.allow_writes=true в config.yaml"}
        if not _project_allowed(_key_project(key)):
            return {"error": f"проект {_key_project(key)} не в allow_projects"}

        async with client_factory() as c:
            r = await c.post(
                _api(f"/issue/{key}/comment"),
                content=json.dumps({"body": body}),
            )
            if r.status_code >= 400:
                try:
                    err = r.json()
                except json.JSONDecodeError:
                    err = {"raw": r.text[:500]}
                return {"error": "jira error", "status": r.status_code, "details": err}
            data = r.json()

        payload = {
            "commented": True,
            "key": key,
            "id": data.get("id"),
            "created": data.get("created"),
        }
        audit_fn("jira_add_comment", {"key": key, "body_chars": len(body)}, len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def jira_set_epic(
        issue_key: str,
        epic_key: str,
    ) -> dict[str, Any]:
        """
        Привязать задачу к эпику через Jira Agile API.

        Использует POST /rest/agile/1.0/epic/{epicKey}/issue — работает там,
        где customfield_10008 не доступен на экране создания/редактирования.

        Args:
            issue_key: ключ задачи (например 'OPS-1234').
            epic_key:  ключ эпика (например 'OPS-1000').
        """
        if not _configured():
            return {"error": "jira не сконфигурирован в config.yaml"}
        if not _writes_enabled():
            return {"error": "запись в jira отключена; jira.allow_writes=true в config.yaml"}
        if not _project_allowed(_key_project(issue_key)):
            return {"error": f"проект {_key_project(issue_key)} не в allow_projects"}
        if not _project_allowed(_key_project(epic_key)):
            return {"error": f"проект {_key_project(epic_key)} не в allow_projects"}

        body = {"issues": [issue_key]}
        async with client_factory() as c:
            r = await c.post(_agile(f"/epic/{epic_key}/issue"), content=json.dumps(body))
            if r.status_code >= 400:
                try:
                    err = r.json()
                except json.JSONDecodeError:
                    err = {"raw": r.text[:500]}
                return {"error": "jira agile error", "status": r.status_code, "details": err}

        payload = {"linked": True, "issue_key": issue_key, "epic_key": epic_key}
        audit_fn("jira_set_epic", {"issue_key": issue_key, "epic_key": epic_key}, len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def jira_list_projects(limit: int = 50) -> dict[str, Any]:
        """
        Список проектов Jira (или подмножество, если задан jira.allow_projects).

        Args:
            limit: максимум проектов в ответе.
        """
        if not _configured():
            return {"error": "jira не сконфигурирован в config.yaml"}

        async with client_factory() as c:
            r = await c.get(_api("/project"))
            if r.status_code >= 400:
                return {"error": "jira error", "status": r.status_code, "details": r.text[:500]}
            raw = r.json() or []

        out = []
        for p in raw:
            key = p.get("key")
            if not _project_allowed(key):
                continue
            out.append({
                "key": key,
                "name": p.get("name"),
                "id": p.get("id"),
                "lead": (p.get("lead") or {}).get("displayName")
                if isinstance(p.get("lead"), dict) else None,
                "url": f"{_base()}/browse/{key}" if key else None,
            })
            if len(out) >= limit:
                break

        payload = {"count": len(out), "projects": redactor.scrub_any(out)}
        audit_fn("jira_list_projects", {"limit": limit}, len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def jira_list_boards(
        project: str | None = None,
        board_type: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Список Agile-досок Jira (Scrum / Kanban).

        Args:
            project:    фильтр по project key.
            board_type: 'scrum' или 'kanban'.
            limit:      потолок результатов.
        """
        if not _configured():
            return {"error": "jira не сконфигурирован в config.yaml"}
        if project and not _project_allowed(project):
            return {"error": f"проект {project} не в allow_projects"}

        params: dict[str, str] = {"maxResults": str(min(limit, 100))}
        if project:
            params["projectKeyOrId"] = project
        if board_type:
            params["type"] = board_type

        async with client_factory() as c:
            r = await c.get(_agile("/board"), params=params)
            if r.status_code >= 400:
                return {"error": "jira agile error", "status": r.status_code, "details": r.text[:500]}
            data = r.json()

        boards = [
            {
                "id": b.get("id"),
                "name": b.get("name"),
                "type": b.get("type"),
                "project_key": (b.get("location", {}) or {}).get("projectKey"),
            }
            for b in (data.get("values") or [])
        ]
        payload = {"count": len(boards), "boards": boards}
        audit_fn("jira_list_boards", {"project": project, "type": board_type}, len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def jira_list_sprints(
        board_id: int,
        state: str | None = "active",
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Список спринтов для доски Jira (Scrum).

        Args:
            board_id: id Agile-доски (см. jira_list_boards).
            state:    'active' / 'future' / 'closed' / None (все).
            limit:    потолок результатов.
        """
        if not _configured():
            return {"error": "jira не сконфигурирован в config.yaml"}

        params: dict[str, str] = {"maxResults": str(min(limit, 100))}
        if state:
            params["state"] = state

        async with client_factory() as c:
            r = await c.get(_agile(f"/board/{board_id}/sprint"), params=params)
            if r.status_code >= 400:
                return {"error": "jira agile error", "status": r.status_code, "details": r.text[:500]}
            data = r.json()

        sprints = [
            {
                "id": s.get("id"),
                "name": s.get("name"),
                "state": s.get("state"),
                "start_date": s.get("startDate"),
                "end_date": s.get("endDate"),
                "goal": s.get("goal"),
            }
            for s in (data.get("values") or [])
        ]
        payload = {"count": len(sprints), "sprints": sprints}
        audit_fn("jira_list_sprints", {"board_id": board_id, "state": state}, len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def jira_sprint_issues(
        sprint_id: int,
        jql: str | None = None,
        fields: list[str] | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """
        Список задач в спринте Jira (Agile API).

        Args:
            sprint_id: id спринта (см. jira_list_sprints).
            jql:       дополнительный JQL для фильтрации (например 'assignee = currentUser()').
            fields:    список полей (по умолчанию из конфига).
            limit:     потолок задач.
        """
        if not _configured():
            return {"error": "jira не сконфигурирован в config.yaml"}

        cap = int(limits.get("max_issues_returned", 50))
        limit = min(max(1, limit), cap)
        fl = fields or _default_fields()

        params: dict[str, str] = {
            "maxResults": str(limit),
            "fields": ",".join(fl),
        }
        if jql:
            params["jql"] = jql

        async with client_factory() as c:
            r = await c.get(_agile(f"/sprint/{sprint_id}/issue"), params=params)
            if r.status_code >= 400:
                return {"error": "jira agile error", "status": r.status_code, "details": r.text[:500]}
            data = r.json()

        issues = [
            _compact_issue(i) for i in (data.get("issues") or [])
            if _project_allowed(_key_project(i.get("key", "")))
        ]
        payload = {
            "total": data.get("total"),
            "returned": len(issues),
            "issues": redactor.scrub_any(issues),
        }
        audit_fn("jira_sprint_issues", {"sprint_id": sprint_id, "jql": jql, "limit": limit},
                 len(json.dumps(payload)))
        return payload
