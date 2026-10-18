from __future__ import annotations

import json
import re
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
        return f"{_base()}/rest/api{path}"

    def _writes_enabled() -> bool:
        return bool(cfg.get("allow_writes", False))

    def _space_allowed(space_key: str | None) -> bool:
        allow = cfg.get("allow_spaces") or []
        if not allow:
            return True
        if not space_key:
            return False
        return space_key.upper() in [s.upper() for s in allow]

    async def _convert_to_storage(
        client: httpx.AsyncClient, content: str, source_format: str
    ) -> tuple[str | None, dict[str, Any] | None]:
        """
        Сконвертировать тело страницы из wiki/editor в storage (XHTML).
        Нужен для append, где новый контент склеивается с уже существующим
        storage-телом. Возвращает (storage_value, None) при успехе или
        (None, error_dict) — при ошибке.
        """
        if source_format == "storage":
            return content, None
        payload = {"value": content, "representation": source_format}
        r = await client.post(
            _api("/contentbody/convert/storage"),
            content=json.dumps(payload),
        )
        if r.status_code >= 400:
            return None, {
                "error": "confluence convert error",
                "status": r.status_code,
                "details": r.text[:500],
            }
        return r.json().get("value") or "", None

    # Простая HTML -> text конвертация без внешних зависимостей.
    _HTML_BLOCK_TAGS = re.compile(
        r"</?(?:p|div|br|li|ul|ol|tr|table|thead|tbody|h[1-6]|pre|blockquote)\b[^>]*>",
        re.IGNORECASE,
    )
    _HTML_ANY_TAG = re.compile(r"<[^>]+>")
    _HTML_ENTITIES = {
        "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&apos;": "'",
    }

    def _html_to_text(html: str, max_chars: int) -> tuple[str, bool]:
        if not html:
            return "", False
        # Превращаем блочные теги в переносы.
        txt = _HTML_BLOCK_TAGS.sub("\n", html)
        # Удаляем все остальные теги.
        txt = _HTML_ANY_TAG.sub("", txt)
        # Раскрываем основные entity.
        for ent, ch in _HTML_ENTITIES.items():
            txt = txt.replace(ent, ch)
        # Numeric entities &#1234;
        txt = re.sub(r"&#(\d+);", lambda m: chr(int(m.group(1))), txt)
        # Схлопываем пустые строки и пробелы.
        txt = re.sub(r"[ \t]+", " ", txt)
        txt = re.sub(r"\n{3,}", "\n\n", txt)
        txt = txt.strip()
        truncated = len(txt) > max_chars
        if truncated:
            txt = txt[:max_chars] + f"…(+{len(txt) - max_chars} chars)"
        return txt, truncated

    def _compact_page(
        page: dict[str, Any],
        include_body: bool = True,
    ) -> dict[str, Any]:
        space = (page.get("space") or {})
        version = (page.get("version") or {})
        out: dict[str, Any] = {
            "id": page.get("id"),
            "type": page.get("type"),
            "title": page.get("title"),
            "space_key": space.get("key"),
            "space_name": space.get("name"),
            "version": version.get("number"),
            "last_modified": version.get("when") or version.get("friendlyWhen"),
            "last_modified_by": (version.get("by") or {}).get("displayName"),
            "url": f"{_base()}{(page.get('_links', {}) or {}).get('webui', '')}"
            if (page.get("_links", {}) or {}).get("webui")
            else None,
        }
        if include_body:
            body = ((page.get("body") or {}).get("storage") or {}).get("value") or ""
            max_chars = int(limits.get("max_page_chars", 12000))
            text, truncated = _html_to_text(body, max_chars)
            out["body"] = text
            out["truncated"] = truncated
        return out

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    @mcp.tool()
    async def confluence_get_page(
        page_id: str | None = None,
        space: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """
        Получить страницу Confluence — либо по id, либо по паре (space, title).

        Тело возвращается как обычный текст (storage XHTML → plain text), обрезается
        до limits.max_page_chars. Это удобно для чтения квартальных планов,
        architecture decisions, описаний процессов и т.п.

        Args:
            page_id: id страницы (если знаешь).
            space:   space key, например 'TEAM'.
            title:   точное название страницы (учитывается регистр).
        """
        if not _configured():
            return {"error": "confluence не сконфигурирован в config.yaml"}
        if not page_id and not (space and title):
            return {"error": "укажите page_id ИЛИ пару (space, title)"}

        params = {"expand": "body.storage,version,space"}

        async with client_factory() as c:
            if page_id:
                r = await c.get(_api(f"/content/{page_id}"), params=params)
                if r.status_code == 404:
                    return {"error": f"страница {page_id} не найдена"}
                if r.status_code >= 400:
                    return {"error": "confluence error", "status": r.status_code, "details": r.text[:500]}
                page = r.json()
            else:
                r = await c.get(_api("/content"), params={
                    **params,
                    "spaceKey": space,
                    "title": title,
                    "type": "page",
                    "limit": "1",
                })
                if r.status_code >= 400:
                    return {"error": "confluence error", "status": r.status_code, "details": r.text[:500]}
                results = (r.json().get("results") or [])
                if not results:
                    return {"error": f"страница space={space} title={title!r} не найдена"}
                page = results[0]

        payload = {"page": redactor.scrub_any(_compact_page(page, include_body=True))}
        audit_fn("confluence_get_page",
                 {"page_id": page_id, "space": space, "title": title},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def confluence_search(
        cql: str,
        limit: int = 10,
        include_body: bool = False,
    ) -> dict[str, Any]:
        """
        Поиск страниц Confluence по CQL (Confluence Query Language).

        Примеры CQL:
            space = TEAM AND type = page AND title ~ "Quarterly"
            text ~ "SLO" AND lastModified > "2026-01-01"
            ancestor = 1234567

        Args:
            cql:          CQL-выражение.
            limit:        максимум результатов (потолок limits.max_search_results).
            include_body: подмешать ли тело страниц (затратно по токенам — обычно нет).
        """
        if not _configured():
            return {"error": "confluence не сконфигурирован в config.yaml"}

        cap = int(limits.get("max_search_results", 25))
        limit = min(max(1, limit), cap)

        expand_parts = ["version", "space"]
        if include_body:
            expand_parts.append("body.storage")

        params = {"cql": cql, "limit": str(limit), "expand": ",".join(expand_parts)}
        async with client_factory() as c:
            r = await c.get(_api("/content/search"), params=params)
            if r.status_code >= 400:
                return {"error": "confluence error", "status": r.status_code, "details": r.text[:500]}
            data = r.json()

        results = [
            _compact_page(p, include_body=include_body)
            for p in (data.get("results") or [])
        ]
        payload = {
            "count": len(results),
            "total": data.get("totalSize") or data.get("size"),
            "results": redactor.scrub_any(results),
        }
        audit_fn("confluence_search",
                 {"cql": cql, "limit": limit, "include_body": include_body},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def confluence_get_page_children(
        page_id: str,
        limit: int = 20,
        include_body: bool = False,
    ) -> dict[str, Any]:
        """
        Дочерние страницы для заданной страницы Confluence (хлебные крошки вниз).

        Полезно: 'дай квартальный план и все его разделы' → сначала
        confluence_get_page, потом confluence_get_page_children по тому же id.

        Args:
            page_id:      id родительской страницы.
            limit:        максимум child-страниц (потолок limits.max_children).
            include_body: подмешать тело каждой child (обычно избыточно).
        """
        if not _configured():
            return {"error": "confluence не сконфигурирован в config.yaml"}

        cap = int(limits.get("max_children", 50))
        limit = min(max(1, limit), cap)

        expand_parts = ["version", "space"]
        if include_body:
            expand_parts.append("body.storage")

        params = {"limit": str(limit), "expand": ",".join(expand_parts)}
        async with client_factory() as c:
            r = await c.get(
                _api(f"/content/{page_id}/child/page"),
                params=params,
            )
            if r.status_code == 404:
                return {"error": f"страница {page_id} не найдена"}
            if r.status_code >= 400:
                return {"error": "confluence error", "status": r.status_code, "details": r.text[:500]}
            data = r.json()

        children = [
            _compact_page(p, include_body=include_body)
            for p in (data.get("results") or [])
        ]
        payload = {"parent_id": page_id, "count": len(children),
                   "children": redactor.scrub_any(children)}
        audit_fn("confluence_get_page_children",
                 {"page_id": page_id, "limit": limit, "include_body": include_body},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def confluence_get_bookmark(name: str) -> dict[str, Any]:
        """
        Получить страницу Confluence по алиасу из confluence.bookmarks в config.yaml.

        Удобно для регулярно используемых документов — например 'квартальный план':
            confluence:
              bookmarks:
                quarterly_plan:
                  space: "TEAM"
                  title: "Quarterly Plan Q3 2026"

        Тогда из Claude можно сказать просто: confluence_get_bookmark("quarterly_plan").

        Args:
            name: ключ закладки из конфига.
        """
        if not _configured():
            return {"error": "confluence не сконфигурирован в config.yaml"}

        bookmarks = cfg.get("bookmarks") or {}
        entry = bookmarks.get(name)
        if not entry:
            return {
                "error": f"закладка '{name}' не найдена",
                "available": list(bookmarks.keys()),
            }

        if isinstance(entry, str):
            return await confluence_get_page(page_id=entry)  # type: ignore[arg-type]
        if isinstance(entry, dict):
            if entry.get("page_id") or entry.get("id"):
                return await confluence_get_page(
                    page_id=str(entry.get("page_id") or entry.get("id"))
                )
            return await confluence_get_page(
                space=entry.get("space"), title=entry.get("title")
            )
        return {"error": f"некорректный формат закладки '{name}'"}

    @mcp.tool()
    async def confluence_create_page(
        space: str,
        title: str,
        content: str,
        parent_id: str | None = None,
        content_format: str = "wiki",
    ) -> dict[str, Any]:
        """
        Создать новую страницу в Confluence.

        Включается через confluence.allow_writes: true. Если задан
        confluence.allow_spaces — пишем только в перечисленные space keys.
        По умолчанию — read-only.

        Args:
            space:           space key, например 'ARCH'.
            title:           заголовок страницы (должен быть уникален в space).
            content:         тело страницы.
            parent_id:       id родительской страницы. Если задан — страница
                             создастся как child этой страницы.
            content_format:  формат content: 'wiki' (Jira/Confluence wiki markup,
                             по умолчанию), 'storage' (XHTML) или 'editor'.
        """
        if not _configured():
            return {"error": "confluence не сконфигурирован в config.yaml"}
        if not _writes_enabled():
            return {"error": "запись в confluence отключена; confluence.allow_writes=true в config.yaml"}
        if not _space_allowed(space):
            return {"error": f"space {space} не в allow_spaces"}
        if content_format not in {"wiki", "storage", "editor"}:
            return {"error": "content_format должен быть 'wiki', 'storage' или 'editor'"}

        body_payload: dict[str, Any] = {
            "type": "page",
            "title": title,
            "space": {"key": space},
            "body": {
                "storage": {
                    "value": content,
                    "representation": content_format,
                }
            },
        }
        if parent_id:
            body_payload["ancestors"] = [{"id": str(parent_id)}]

        async with client_factory() as c:
            r = await c.post(
                _api("/content"),
                content=json.dumps(body_payload),
            )
            if r.status_code >= 400:
                try:
                    err = r.json()
                except json.JSONDecodeError:
                    err = {"raw": r.text[:500]}
                return {"error": "confluence error", "status": r.status_code, "details": err}
            data = r.json()

        webui = (data.get("_links", {}) or {}).get("webui")
        payload = {
            "created": True,
            "id": data.get("id"),
            "title": data.get("title"),
            "space": (data.get("space") or {}).get("key"),
            "version": (data.get("version") or {}).get("number"),
            "url": f"{_base()}{webui}" if webui else None,
        }
        audit_fn("confluence_create_page",
                 {"space": space, "title": title, "parent_id": parent_id,
                  "content_format": content_format},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def confluence_update_page(
        page_id: str,
        content: str | None = None,
        title: str | None = None,
        content_format: str = "wiki",
        append: bool = False,
    ) -> dict[str, Any]:
        """
        Обновить существующую страницу Confluence.

        По умолчанию полностью ЗАМЕНЯЕТ тело. С append=True — дописывает content
        в конец к существующему телу (удобно, чтобы добавить новую секцию на
        страницу квартального плана, не трогая старые).

        Включается через confluence.allow_writes: true.

        Args:
            page_id:        id страницы.
            content:        новое тело. Если append=False — заменяет полностью;
                            если append=True — дописывается в конец. Если None и
                            задан title — обновляется только заголовок.
            title:          новый заголовок (опционально).
            content_format: формат content: 'wiki' (по умолчанию), 'storage' или 'editor'.
            append:         если True — добавить content в конец текущего тела
                            вместо замены.
        """
        if not _configured():
            return {"error": "confluence не сконфигурирован в config.yaml"}
        if not _writes_enabled():
            return {"error": "запись в confluence отключена; confluence.allow_writes=true в config.yaml"}
        if content is None and title is None:
            return {"error": "укажите content или title"}
        if content_format not in {"wiki", "storage", "editor"}:
            return {"error": "content_format должен быть 'wiki', 'storage' или 'editor'"}

        async with client_factory() as c:
            r = await c.get(
                _api(f"/content/{page_id}"),
                params={"expand": "body.storage,version,space"},
            )
            if r.status_code == 404:
                return {"error": f"страница {page_id} не найдена"}
            if r.status_code >= 400:
                return {"error": "confluence error", "status": r.status_code, "details": r.text[:500]}
            current = r.json()

            space_key = (current.get("space") or {}).get("key")
            if not _space_allowed(space_key):
                return {"error": f"space {space_key} не в allow_spaces"}

            current_version = ((current.get("version") or {}).get("number")) or 0
            current_body = ((current.get("body") or {}).get("storage") or {}).get("value") or ""
            new_title = title or current.get("title")

            if content is not None:
                if append:
                    new_storage, err = await _convert_to_storage(
                        c, content, content_format
                    )
                    if err:
                        return err
                    new_body_value = current_body + (new_storage or "")
                    new_body_format = "storage"
                else:
                    new_body_value = content
                    new_body_format = content_format
            else:
                new_body_value = current_body
                new_body_format = "storage"

            update_payload = {
                "id": str(page_id),
                "type": current.get("type") or "page",
                "title": new_title,
                "version": {"number": current_version + 1},
                "body": {
                    "storage": {
                        "value": new_body_value,
                        "representation": new_body_format,
                    }
                },
            }

            r = await c.put(
                _api(f"/content/{page_id}"),
                content=json.dumps(update_payload),
            )
            if r.status_code >= 400:
                try:
                    err = r.json()
                except json.JSONDecodeError:
                    err = {"raw": r.text[:500]}
                return {"error": "confluence error", "status": r.status_code, "details": err}
            data = r.json()

        webui = (data.get("_links", {}) or {}).get("webui")
        payload = {
            "updated": True,
            "id": data.get("id"),
            "title": data.get("title"),
            "version": (data.get("version") or {}).get("number"),
            "url": f"{_base()}{webui}" if webui else None,
            "append": append,
        }
        audit_fn("confluence_update_page",
                 {"page_id": page_id, "append": append,
                  "content_format": content_format,
                  "title_changed": title is not None},
                 len(json.dumps(payload)))
        return payload
