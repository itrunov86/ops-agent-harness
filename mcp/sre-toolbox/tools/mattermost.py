from __future__ import annotations

import json
import re
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

    def _team_allowed(team_name: str | None) -> bool:
        allow = cfg.get("allow_teams") or []
        if not allow:
            return True
        if not team_name:
            return False
        return team_name in allow

    def _channel_write_allowed(channel_id: str | None) -> bool:
        allow = cfg.get("allow_channels") or []
        if not allow:
            return True
        if not channel_id:
            return False
        return channel_id in allow

    def _trim(value: Any, max_chars: int) -> Any:
        """Обрезает строку до max_chars с суффиксом о количестве отброшенных символов."""
        if isinstance(value, str) and len(value) > max_chars:
            return value[:max_chars] + f"…(+{len(value) - max_chars} chars)"
        return value

    async def _resolve_team_id(client: httpx.AsyncClient, team: str) -> tuple[str | None, dict[str, Any] | None]:
        """Принимает name или id. Если выглядит как id (26 символов id Mattermost) —
        возвращаем как есть. Иначе резолвим по имени через /teams/name/{name}.
        Возвращает (team_id, None) при успехе или (None, error_dict)."""
        if len(team) == 26 and team.isalnum():
            return team, None
        r = await client.get(_api(f"/teams/name/{_urlquote(team, safe='')}"))
        if r.status_code == 404:
            return None, {"error": f"team '{team}' не найдена"}
        if r.status_code >= 400:
            return None, {"error": "mattermost error", "status": r.status_code,
                          "details": r.text[:500]}
        data = r.json()
        return data.get("id"), None

    def _compact_team(t: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": t.get("id"),
            "name": t.get("name"),
            "display_name": t.get("display_name"),
            "description": t.get("description"),
            "type": t.get("type"),
        }

    def _compact_channel(c: dict[str, Any]) -> dict[str, Any]:
        max_chars = int(limits.get("max_field_chars", 4000))
        return {
            "id": c.get("id"),
            "name": c.get("name"),
            "display_name": c.get("display_name"),
            "type": c.get("type"),  # O=public, P=private, D=direct, G=group
            "team_id": c.get("team_id"),
            "header": _trim(c.get("header") or "", max_chars),
            "purpose": _trim(c.get("purpose") or "", max_chars),
            "total_msg_count": c.get("total_msg_count"),
            "last_post_at": c.get("last_post_at"),
        }

    def _compact_post(p: dict[str, Any]) -> dict[str, Any]:
        max_chars = int(limits.get("max_field_chars", 4000))
        return {
            "id": p.get("id"),
            "channel_id": p.get("channel_id"),
            "user_id": p.get("user_id"),
            "root_id": p.get("root_id") or None,
            "create_at": p.get("create_at"),
            "edit_at": p.get("edit_at"),
            "message": _trim(p.get("message") or "", max_chars),
            "type": p.get("type"),
            "has_reactions": p.get("has_reactions"),
        }

    _PERMALINK_RE = re.compile(r"/(?P<team>[^/]+)/pl/(?P<post>[a-z0-9]+)")

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------

    @mcp.tool()
    async def mm_list_teams() -> dict[str, Any]:
        """
        Список команд (teams) Mattermost, в которых я состою.
        """
        if not _configured():
            return {"error": "mattermost не сконфигурирован в config.yaml"}

        async with client_factory() as c:
            r = await c.get(_api("/users/me/teams"))
            if r.status_code >= 400:
                return {"error": "mattermost error", "status": r.status_code,
                        "details": r.text[:500]}
            data = r.json() or []

        teams = [_compact_team(t) for t in data
                 if _team_allowed(t.get("name"))]
        payload = {"returned": len(teams), "teams": redactor.scrub_any(teams)}
        audit_fn("mm_list_teams", {}, len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def mm_list_channels(team: str, limit: int = 50) -> dict[str, Any]:
        """
        Каналы внутри команды, в которые я состою.

        Args:
            team:  name или id команды.
            limit: максимум каналов (потолок limits.max_channels_returned).
        """
        if not _configured():
            return {"error": "mattermost не сконфигурирован в config.yaml"}

        cap = int(limits.get("max_channels_returned", 100))
        limit = min(max(1, limit), cap)

        async with client_factory() as c:
            team_id, err = await _resolve_team_id(c, team)
            if err:
                return err
            if not _team_allowed(team):
                # Дополнительная проверка по name (если team пришёл как id).
                t2 = await c.get(_api(f"/teams/{team_id}"))
                if t2.status_code < 400 and not _team_allowed(t2.json().get("name")):
                    return {"error": f"team '{team}' не в allow_teams"}

            r = await c.get(_api(f"/users/me/teams/{team_id}/channels"))
            if r.status_code >= 400:
                return {"error": "mattermost error", "status": r.status_code,
                        "details": r.text[:500]}
            data = r.json() or []

        channels = [_compact_channel(ch) for ch in data[:limit]]
        payload = {
            "team_id": team_id,
            "returned": len(channels),
            "truncated": len(data) > limit,
            "channels": redactor.scrub_any(channels),
        }
        audit_fn("mm_list_channels", {"team": team, "limit": limit},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def mm_list_channel_posts(
        channel_id: str,
        since_ms: int | None = None,
        before: str | None = None,
        after: str | None = None,
        page: int = 0,
        per_page: int = 60,
    ) -> dict[str, Any]:
        """
        Список постов в канале с пагинацией. Для аналитики/дайджестов поверх
        канала (поиск через mm_search_posts режется на limits.max_search_results).

        Поддерживает три режима выборки (взаимоисключающие):
          - since_ms: посты, изменённые после unix-времени в ms.
          - before:   посты ДО указанного post_id (более старые) — для пагинации назад.
          - after:    посты ПОСЛЕ указанного post_id (более новые) — для пагинации вперёд.
          - (без фильтров): последние per_page постов, начиная со страницы `page`.

        Args:
            channel_id: id канала (узнать через mm_list_channels).
            since_ms:   unix-время в ms. None = без фильтра по времени.
            before:     post_id для пагинации назад. None = не использовать.
            after:      post_id для пагинации вперёд. None = не использовать.
            page:       номер страницы (0-based), используется если не задан since/before/after.
            per_page:   размер страницы (потолок limits.max_posts_returned, Mattermost макс 200).
        """
        if not _configured():
            return {"error": "mattermost не сконфигурирован в config.yaml"}

        cap = int(limits.get("max_posts_returned", 200))
        per_page = min(max(1, per_page), cap)

        params: dict[str, str] = {"per_page": str(per_page)}
        # Mattermost API: режимы since / before / after / page взаимоисключающие.
        if since_ms is not None:
            params["since"] = str(since_ms)
        elif before:
            params["before"] = before
        elif after:
            params["after"] = after
        else:
            params["page"] = str(page)

        async with client_factory() as c:
            r = await c.get(_api(f"/channels/{channel_id}/posts"), params=params)
            if r.status_code >= 400:
                return {"error": "mattermost error", "status": r.status_code,
                        "details": r.text[:500]}
            data = r.json() or {}

        order = data.get("order") or []
        posts_map = data.get("posts") or {}
        ordered = [
            _compact_post(posts_map[pid]) for pid in order if pid in posts_map
        ]

        payload = {
            "channel_id": channel_id,
            "returned": len(ordered),
            "next_post_id": data.get("next_post_id") or None,
            "prev_post_id": data.get("prev_post_id") or None,
            "posts": redactor.scrub_any(ordered),
        }
        audit_fn("mm_list_channel_posts",
                 {"channel_id": channel_id, "since_ms": since_ms,
                  "before": before, "after": after,
                  "page": page, "per_page": per_page},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def mm_get_post(post_id: str) -> dict[str, Any]:
        """
        Получить один пост по его id (тот самый id из URL пермалинки).

        Возвращает сам пост + краткую инфу про канал и автора (чтобы было
        понятно, что это и куда).

        Args:
            post_id: id поста (последний сегмент в URL пермалинки).
        """
        if not _configured():
            return {"error": "mattermost не сконфигурирован в config.yaml"}

        async with client_factory() as c:
            r = await c.get(_api(f"/posts/{post_id}"))
            if r.status_code == 404:
                return {"error": f"пост {post_id} не найден"}
            if r.status_code >= 400:
                return {"error": "mattermost error", "status": r.status_code,
                        "details": r.text[:500]}
            post = r.json()

            out: dict[str, Any] = {"post": _compact_post(post)}

            # Канал — для контекста.
            ch_r = await c.get(_api(f"/channels/{post.get('channel_id')}"))
            if ch_r.status_code < 400:
                out["channel"] = _compact_channel(ch_r.json())

            # Автор — username важнее, чем user_id.
            u_r = await c.get(_api(f"/users/{post.get('user_id')}"))
            if u_r.status_code < 400:
                u = u_r.json()
                out["author"] = {
                    "id": u.get("id"),
                    "username": u.get("username"),
                    "first_name": u.get("first_name"),
                    "last_name": u.get("last_name"),
                }

        payload = redactor.scrub_any(out)
        audit_fn("mm_get_post", {"post_id": post_id}, len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def mm_get_thread(post_id: str) -> dict[str, Any]:
        """
        Тред: корневой пост + все ответы.

        Принимает id любого поста в треде — Mattermost возвращает весь тред.

        Args:
            post_id: id любого поста треда.
        """
        if not _configured():
            return {"error": "mattermost не сконфигурирован в config.yaml"}

        cap = int(limits.get("max_posts_returned", 50))

        async with client_factory() as c:
            r = await c.get(_api(f"/posts/{post_id}/thread"))
            if r.status_code == 404:
                return {"error": f"пост {post_id} не найден"}
            if r.status_code >= 400:
                return {"error": "mattermost error", "status": r.status_code,
                        "details": r.text[:500]}
            data = r.json() or {}

        order = data.get("order") or []
        posts_map = data.get("posts") or {}
        ordered_posts = [_compact_post(posts_map[pid]) for pid in order if pid in posts_map]
        truncated = len(ordered_posts) > cap
        if truncated:
            ordered_posts = ordered_posts[:cap]

        payload = {
            "thread_id": post_id,
            "returned": len(ordered_posts),
            "truncated": truncated,
            "posts": redactor.scrub_any(ordered_posts),
        }
        audit_fn("mm_get_thread", {"post_id": post_id}, len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def mm_search_posts(
        team: str,
        terms: str,
        is_or_search: bool = False,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        Поиск постов внутри команды.

        Args:
            team:         name или id команды, в которой ищем.
            terms:        поисковая строка (поддерживает модификаторы из=…, in=…,
                          after:YYYY-MM-DD и т.д. — как в UI Mattermost).
            is_or_search: если true — OR между терминами вместо AND.
            limit:        максимум результатов (потолок limits.max_search_results).
        """
        if not _configured():
            return {"error": "mattermost не сконфигурирован в config.yaml"}

        cap = int(limits.get("max_search_results", 30))
        limit = min(max(1, limit), cap)

        async with client_factory() as c:
            team_id, err = await _resolve_team_id(c, team)
            if err:
                return err

            body = {"terms": terms, "is_or_search": is_or_search}
            r = await c.post(_api(f"/teams/{team_id}/posts/search"),
                             content=json.dumps(body))
            if r.status_code >= 400:
                return {"error": "mattermost error", "status": r.status_code,
                        "details": r.text[:500]}
            data = r.json() or {}

        order = data.get("order") or []
        posts_map = data.get("posts") or {}
        ordered = [_compact_post(posts_map[pid]) for pid in order[:limit] if pid in posts_map]

        payload = {
            "team_id": team_id,
            "terms": terms,
            "returned": len(ordered),
            "truncated": len(order) > limit,
            "posts": redactor.scrub_any(ordered),
        }
        audit_fn("mm_search_posts", {"team": team, "terms": terms, "limit": limit},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def mm_resolve_permalink(url: str) -> dict[str, Any]:
        """
        Разобрать URL пермалинки Mattermost и вернуть пост с контекстом.

        Принимает URL вида 'https://<base>/<team_name>/pl/<post_id>'.
        Делает то же, что mm_get_post, но удобнее когда пользователь скинул
        голую ссылку из чата.

        Args:
            url: URL пермалинки.
        """
        if not _configured():
            return {"error": "mattermost не сконфигурирован в config.yaml"}

        m = _PERMALINK_RE.search(url)
        if not m:
            return {"error": "не похоже на пермалинку Mattermost",
                    "expected": "https://<base>/<team>/pl/<post_id>"}
        team = m.group("team")
        post_id = m.group("post")

        if not _team_allowed(team):
            return {"error": f"team '{team}' не в allow_teams"}

        # Дальше как в mm_get_post, но возвращаем ещё и team.
        async with client_factory() as c:
            r = await c.get(_api(f"/posts/{post_id}"))
            if r.status_code == 404:
                return {"error": f"пост {post_id} не найден",
                        "team_hint": team}
            if r.status_code >= 400:
                return {"error": "mattermost error", "status": r.status_code,
                        "details": r.text[:500]}
            post = r.json()

            out: dict[str, Any] = {
                "url": url,
                "team_name": team,
                "post": _compact_post(post),
            }

            ch_r = await c.get(_api(f"/channels/{post.get('channel_id')}"))
            if ch_r.status_code < 400:
                out["channel"] = _compact_channel(ch_r.json())

            u_r = await c.get(_api(f"/users/{post.get('user_id')}"))
            if u_r.status_code < 400:
                u = u_r.json()
                out["author"] = {
                    "id": u.get("id"),
                    "username": u.get("username"),
                    "first_name": u.get("first_name"),
                    "last_name": u.get("last_name"),
                }

        payload = redactor.scrub_any(out)
        audit_fn("mm_resolve_permalink", {"url": url, "team": team, "post_id": post_id},
                 len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def mm_create_post(
        channel_id: str,
        message: str,
        root_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Отправить сообщение в канал Mattermost.

        Включается через mattermost.allow_writes: true. Если задан
        mattermost.allow_channels — постить можно только в эти каналы.

        Args:
            channel_id: id канала (не имя). Узнать можно через mm_list_channels.
            message:    текст сообщения (поддерживает Markdown).
            root_id:    id корневого поста — если ответ в тред. None — новое сообщение.
        """
        if not _configured():
            return {"error": "mattermost не сконфигурирован в config.yaml"}
        if not _writes_enabled():
            return {"error": "запись в mattermost отключена; mattermost.allow_writes=true в config.yaml"}
        if not _channel_write_allowed(channel_id):
            return {"error": f"канал {channel_id} не в allow_channels"}

        body: dict[str, Any] = {"channel_id": channel_id, "message": message}
        if root_id:
            body["root_id"] = root_id

        async with client_factory() as c:
            r = await c.post(_api("/posts"), content=json.dumps(body))
            if r.status_code >= 400:
                return {"error": "mattermost error", "status": r.status_code,
                        "details": r.text[:500]}
            data = r.json()

        # Соберём URL для удобства (team нужен — возьмём из канала).
        permalink: str | None = None
        async with client_factory() as c:
            ch_r = await c.get(_api(f"/channels/{channel_id}/teams"))
            # Старые API не поддерживают этот ep — пробуем достать team по другому пути.
            if ch_r.status_code < 400:
                teams = ch_r.json() or []
                if teams:
                    tn = teams[0].get("name")
                    if tn:
                        permalink = f"{_base()}/{tn}/pl/{data.get('id')}"

        payload = {
            "created": True,
            "id": data.get("id"),
            "create_at": data.get("create_at"),
            "channel_id": channel_id,
            "root_id": data.get("root_id") or None,
            "url": permalink,
        }
        audit_fn("mm_create_post",
                 {"channel_id": channel_id, "root_id": root_id,
                  "message_length": len(message)},
                 len(json.dumps(payload)))
        return payload
