from __future__ import annotations

import json
from typing import Any, Callable
from urllib.parse import quote as _urlquote

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
        return f"{_base()}/api/v4{path}"

    def _writes_enabled() -> bool:
        return bool(cfg.get("allow_writes", False))

    def _normalize_path(project: str | int) -> str:
        """'group/subgroup/project' → 'group/subgroup/project' (без квотинга,
        для проверки в allowlist и логов); числовой id остаётся строкой."""
        return str(project).strip("/")

    def _project_allowed(project: str | int | None) -> bool:
        allow = cfg.get("allow_projects") or []
        if not allow:
            return True
        if project is None:
            return False
        p = _normalize_path(project)
        return p in [_normalize_path(x) for x in allow]

    def _project_id_for_url(project: str | int) -> str:
        """URL-encoded форма project identifier'а для подстановки в путь.
        Числовой id остаётся как есть; путь — url-quote с safe=''."""
        s = _normalize_path(project)
        if s.isdigit():
            return s
        return _urlquote(s, safe="")

    def _trim(value: Any, max_chars: int) -> Any:
        if isinstance(value, str) and len(value) > max_chars:
            return value[:max_chars] + f"…(+{len(value) - max_chars} chars)"
        return value

    def _compact_project(p: dict[str, Any]) -> dict[str, Any]:
        max_chars = int(limits.get("max_field_chars", 4000))
        return {
            "id": p.get("id"),
            "path_with_namespace": p.get("path_with_namespace"),
            "name": p.get("name"),
            "description": _trim(p.get("description") or "", max_chars),
            "default_branch": p.get("default_branch"),
            "visibility": p.get("visibility"),
            "web_url": p.get("web_url"),
            "last_activity_at": p.get("last_activity_at"),
            "archived": p.get("archived"),
        }

    def _compact_mr(m: dict[str, Any]) -> dict[str, Any]:
        max_chars = int(limits.get("max_field_chars", 4000))
        return {
            "iid": m.get("iid"),
            "project_id": m.get("project_id"),
            "title": m.get("title"),
            "state": m.get("state"),
            "draft": m.get("draft", m.get("work_in_progress")),
            "author": (m.get("author") or {}).get("username"),
            "assignees": [(a or {}).get("username") for a in (m.get("assignees") or [])],
            "reviewers": [(r or {}).get("username") for r in (m.get("reviewers") or [])],
            "source_branch": m.get("source_branch"),
            "target_branch": m.get("target_branch"),
            "merge_status": m.get("merge_status") or m.get("detailed_merge_status"),
            "labels": m.get("labels"),
            "created_at": m.get("created_at"),
            "updated_at": m.get("updated_at"),
            "merged_at": m.get("merged_at"),
            "web_url": m.get("web_url"),
            "description": _trim(m.get("description") or "", max_chars),
        }

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    @mcp.tool()
    async def gitlab_list_projects(
        search: str | None = None,
        owned: bool = False,
        membership: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Список проектов GitLab.

        Args:
            search:     текстовый поиск по имени / пути.
            owned:      только проекты, владельцем которых я являюсь.
            membership: только проекты, где я состою участником.
            limit:      максимум проектов в ответе (потолок limits.max_projects_returned).
        """
        if not _configured():
            return {"error": "gitlab не сконфигурирован в config.yaml"}

        cap = int(limits.get("max_projects_returned", 50))
        limit = min(max(1, limit), cap)

        params: dict[str, Any] = {
            "per_page": str(limit),
            "order_by": "last_activity_at",
            "sort": "desc",
            "simple": "true",
        }
        if search:
            params["search"] = search
        if owned:
            params["owned"] = "true"
        if membership:
            params["membership"] = "true"

        async with client_factory() as c:
            r = await c.get(_api("/projects"), params=params)
            if r.status_code >= 400:
                return {"error": "gitlab error", "status": r.status_code, "details": r.text[:500]}
            data = r.json()

        projects = [
            _compact_project(p) for p in (data or [])
            if _project_allowed(p.get("path_with_namespace"))
        ]
        payload = {
            "returned": len(projects),
            "projects": redactor.scrub_any(projects),
        }
        audit_fn("gitlab_list_projects",
                 {"search": search, "owned": owned, "membership": membership, "limit": limit},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def gitlab_get_project(project: str) -> dict[str, Any]:
        """
        Получить один проект GitLab по id или полному пути 'group/subgroup/project'.

        Args:
            project: числовой id или путь с namespace.
        """
        if not _configured():
            return {"error": "gitlab не сконфигурирован в config.yaml"}
        if not _project_allowed(project):
            return {"error": f"проект {project} не в allow_projects"}

        pid = _project_id_for_url(project)
        async with client_factory() as c:
            r = await c.get(_api(f"/projects/{pid}"))
            if r.status_code == 404:
                return {"error": f"проект {project} не найден"}
            if r.status_code >= 400:
                return {"error": "gitlab error", "status": r.status_code, "details": r.text[:500]}
            data = r.json()

        payload = {"project": redactor.scrub_any(_compact_project(data))}
        audit_fn("gitlab_get_project", {"project": _normalize_path(project)},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def gitlab_list_mrs(
        project: str | None = None,
        state: str = "opened",
        author: str | None = None,
        assignee: str | None = None,
        reviewer: str | None = None,
        labels: str | None = None,
        search: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Список merge requests — либо в одном проекте, либо по всему инстансу.

        Args:
            project:  id/path проекта. None — поиск по всему GitLab.
            state:    'opened' / 'closed' / 'merged' / 'all'.
            author:   username автора.
            assignee: username исполнителя (любой из).
            reviewer: username ревьюера (любой из).
            labels:   список лейблов через запятую (точное совпадение).
            search:   текстовый поиск по title/description.
            limit:    максимум MR (потолок limits.max_mrs_returned).
        """
        if not _configured():
            return {"error": "gitlab не сконфигурирован в config.yaml"}
        if project is not None and not _project_allowed(project):
            return {"error": f"проект {project} не в allow_projects"}

        cap = int(limits.get("max_mrs_returned", 50))
        limit = min(max(1, limit), cap)

        params: dict[str, Any] = {
            "per_page": str(limit),
            "state": state,
            "order_by": "updated_at",
            "sort": "desc",
            "scope": "all",
        }
        if author:
            params["author_username"] = author
        if assignee:
            params["assignee_username"] = assignee
        if reviewer:
            params["reviewer_username"] = reviewer
        if labels:
            params["labels"] = labels
        if search:
            params["search"] = search

        if project:
            pid = _project_id_for_url(project)
            url = _api(f"/projects/{pid}/merge_requests")
        else:
            url = _api("/merge_requests")

        async with client_factory() as c:
            r = await c.get(url, params=params)
            if r.status_code >= 400:
                return {"error": "gitlab error", "status": r.status_code, "details": r.text[:500]}
            data = r.json()

        mrs = [_compact_mr(m) for m in (data or [])]
        payload = {
            "returned": len(mrs),
            "merge_requests": redactor.scrub_any(mrs),
        }
        audit_fn("gitlab_list_mrs",
                 {"project": _normalize_path(project) if project else None,
                  "state": state, "limit": limit},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def gitlab_get_mr(
        project: str,
        mr_iid: int,
        with_diff: bool = False,
        with_comments: bool = False,
    ) -> dict[str, Any]:
        """
        Получить один MR по project + iid (внутренний номер в проекте).

        Args:
            project:       id/path проекта.
            mr_iid:        internal id MR'а в этом проекте (число из URL).
            with_diff:     подмешать список изменённых файлов и diff'ы (обрезанные).
            with_comments: подмешать дискуссии (notes).
        """
        if not _configured():
            return {"error": "gitlab не сконфигурирован в config.yaml"}
        if not _project_allowed(project):
            return {"error": f"проект {project} не в allow_projects"}

        pid = _project_id_for_url(project)
        out: dict[str, Any] = {}

        async with client_factory() as c:
            r = await c.get(_api(f"/projects/{pid}/merge_requests/{mr_iid}"))
            if r.status_code == 404:
                return {"error": f"MR {project}!{mr_iid} не найден"}
            if r.status_code >= 400:
                return {"error": "gitlab error", "status": r.status_code, "details": r.text[:500]}
            out["mr"] = _compact_mr(r.json())

            if with_diff:
                r2 = await c.get(_api(f"/projects/{pid}/merge_requests/{mr_iid}/diffs"))
                if r2.status_code < 400:
                    diffs = r2.json() or []
                    cap_files = int(limits.get("max_diff_files", 25))
                    cap_chars = int(limits.get("max_field_chars", 4000))
                    truncated_files = len(diffs) > cap_files
                    compact_diffs = []
                    for d in diffs[:cap_files]:
                        compact_diffs.append({
                            "old_path": d.get("old_path"),
                            "new_path": d.get("new_path"),
                            "new_file": d.get("new_file"),
                            "deleted_file": d.get("deleted_file"),
                            "renamed_file": d.get("renamed_file"),
                            "diff": _trim(d.get("diff") or "", cap_chars),
                        })
                    out["diff"] = {
                        "files": compact_diffs,
                        "truncated_files": truncated_files,
                        "total_files": len(diffs),
                    }

            if with_comments:
                r3 = await c.get(_api(f"/projects/{pid}/merge_requests/{mr_iid}/notes"),
                                 params={"sort": "asc", "per_page": "100"})
                if r3.status_code < 400:
                    notes = r3.json() or []
                    cap_chars = int(limits.get("max_field_chars", 4000))
                    compact_notes = [
                        {
                            "id": n.get("id"),
                            "author": (n.get("author") or {}).get("username"),
                            "system": n.get("system"),
                            "created_at": n.get("created_at"),
                            "body": _trim(n.get("body") or "", cap_chars),
                        }
                        for n in notes
                    ]
                    out["comments"] = compact_notes

        payload = redactor.scrub_any(out)
        audit_fn("gitlab_get_mr",
                 {"project": _normalize_path(project), "mr_iid": mr_iid,
                  "with_diff": with_diff, "with_comments": with_comments},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def gitlab_get_file(
        project: str,
        file_path: str,
        ref: str = "HEAD",
    ) -> dict[str, Any]:
        """
        Прочитать файл из репозитория проекта.

        Args:
            project:   id/path проекта.
            file_path: путь к файлу от корня репо, например 'src/main.py'.
            ref:       branch / tag / commit SHA. По умолчанию 'HEAD'.
        """
        if not _configured():
            return {"error": "gitlab не сконфигурирован в config.yaml"}
        if not _project_allowed(project):
            return {"error": f"проект {project} не в allow_projects"}

        pid = _project_id_for_url(project)
        fp = _urlquote(file_path.lstrip("/"), safe="")

        async with client_factory() as c:
            r = await c.get(_api(f"/projects/{pid}/repository/files/{fp}/raw"),
                            params={"ref": ref})
            if r.status_code == 404:
                return {"error": f"файл {file_path}@{ref} не найден в {project}"}
            if r.status_code >= 400:
                return {"error": "gitlab error", "status": r.status_code, "details": r.text[:500]}
            text = r.text

        cap = int(limits.get("max_file_chars", 12000))
        truncated = len(text) > cap
        if truncated:
            text = text[:cap] + f"…(+{len(r.text) - cap} chars)"

        payload = {
            "project": _normalize_path(project),
            "file_path": file_path,
            "ref": ref,
            "content": redactor.scrub(text),
            "truncated": truncated,
            "url": f"{_base()}/{_normalize_path(project)}/-/blob/{ref}/{file_path.lstrip('/')}",
        }
        audit_fn("gitlab_get_file",
                 {"project": _normalize_path(project), "file_path": file_path,
                  "ref": ref},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def gitlab_search(
        search: str,
        scope: str = "blobs",
        project: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Поиск по GitLab — глобально или внутри проекта.

        Args:
            search:  поисковая строка.
            scope:   'blobs' (код) / 'issues' / 'merge_requests' / 'projects' /
                     'users' / 'commits' / 'wiki_blobs' / 'milestones'.
            project: id/path проекта — поиск внутри проекта. None — глобально.
            limit:   максимум результатов (потолок limits.max_search_results).
        """
        if not _configured():
            return {"error": "gitlab не сконфигурирован в config.yaml"}
        if project is not None and not _project_allowed(project):
            return {"error": f"проект {project} не в allow_projects"}

        cap = int(limits.get("max_search_results", 30))
        limit = min(max(1, limit), cap)

        params = {"scope": scope, "search": search, "per_page": str(limit)}

        if project:
            pid = _project_id_for_url(project)
            url = _api(f"/projects/{pid}/search")
        else:
            url = _api("/search")

        async with client_factory() as c:
            r = await c.get(url, params=params)
            if r.status_code >= 400:
                return {"error": "gitlab error", "status": r.status_code, "details": r.text[:500]}
            data = r.json() or []

        cap_chars = int(limits.get("max_field_chars", 4000))
        compact: list[dict[str, Any]] = []
        for item in data:
            if scope == "blobs" or scope == "wiki_blobs":
                compact.append({
                    "path": item.get("path"),
                    "ref": item.get("ref"),
                    "project_id": item.get("project_id"),
                    "startline": item.get("startline"),
                    "data": _trim(item.get("data") or "", cap_chars),
                })
            elif scope == "issues":
                compact.append({
                    "iid": item.get("iid"),
                    "title": item.get("title"),
                    "state": item.get("state"),
                    "project_id": item.get("project_id"),
                    "labels": item.get("labels"),
                    "web_url": item.get("web_url"),
                    "description": _trim(item.get("description") or "", cap_chars),
                })
            elif scope == "merge_requests":
                compact.append(_compact_mr(item))
            elif scope == "projects":
                compact.append(_compact_project(item))
            elif scope == "commits":
                compact.append({
                    "id": (item.get("id") or "")[:12],
                    "title": item.get("title"),
                    "author_name": item.get("author_name"),
                    "created_at": item.get("created_at"),
                    "project_id": item.get("project_id"),
                    "web_url": item.get("web_url"),
                })
            else:
                compact.append(item)

        payload = {
            "scope": scope,
            "returned": len(compact),
            "results": redactor.scrub_any(compact),
        }
        audit_fn("gitlab_search",
                 {"scope": scope, "search": search,
                  "project": _normalize_path(project) if project else None,
                  "limit": limit},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def gitlab_create_mr_note(
        project: str,
        mr_iid: int,
        body: str,
    ) -> dict[str, Any]:
        """
        Оставить комментарий (note) в merge request.

        Включается через gitlab.allow_writes: true. Allowlist по проектам тоже
        применяется.

        Args:
            project: id/path проекта.
            mr_iid:  internal id MR'а в этом проекте.
            body:    текст комментария (поддерживает GitLab Flavored Markdown).
        """
        if not _configured():
            return {"error": "gitlab не сконфигурирован в config.yaml"}
        if not _writes_enabled():
            return {"error": "запись в gitlab отключена; gitlab.allow_writes=true в config.yaml"}
        if not _project_allowed(project):
            return {"error": f"проект {project} не в allow_projects"}

        pid = _project_id_for_url(project)
        body_payload = {"body": body}

        async with client_factory() as c:
            r = await c.post(
                _api(f"/projects/{pid}/merge_requests/{mr_iid}/notes"),
                content=json.dumps(body_payload),
            )
            if r.status_code >= 400:
                return {"error": "gitlab error", "status": r.status_code,
                        "details": r.text[:500]}
            data = r.json()

        payload = {
            "created": True,
            "id": data.get("id"),
            "author": (data.get("author") or {}).get("username"),
            "created_at": data.get("created_at"),
            "url": f"{_base()}/{_normalize_path(project)}/-/merge_requests/{mr_iid}#note_{data.get('id')}",
        }
        audit_fn("gitlab_create_mr_note",
                 {"project": _normalize_path(project), "mr_iid": mr_iid,
                  "body_length": len(body)},
                 len(json.dumps(payload)))
        return payload
