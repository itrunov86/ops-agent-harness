from __future__ import annotations

import importlib.util
import json
import math
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

# <agent-harness>/mcp/sre-toolbox/tools/obsidian.py -> <agent-harness>/tools/kb.py
DEFAULT_KB_TOOL = Path(__file__).resolve().parents[3] / "tools" / "kb.py"

# --- Морфология: стеммер Портера для русского, лёгкая нормализация английского.
# Та же логика, что в tools/kb.py agent-harness, чтобы «переезд/переезда/переезде» совпадали.
_RU_PERFECTIVE = re.compile(r"((ив|ивши|ившись|ыв|ывши|ывшись)|((?<=[ая])(в|вши|вшись)))$")
_RU_REFLEXIVE = re.compile(r"(с[яь])$")
_RU_ADJECTIVE = re.compile(r"(ее|ие|ые|ое|ими|ыми|ей|ий|ый|ой|ем|им|ым|ом|его|ого|ему|ому|их|ых|ую|юю|ая|яя|ою|ею)$")
_RU_PARTICIPLE = re.compile(r"((ивш|ывш|ующ)|((?<=[ая])(ем|нн|вш|ющ|щ)))$")
_RU_VERB = re.compile(r"((ила|ыла|ена|ейте|уйте|ите|или|ыли|ей|уй|ил|ыл|им|ым|ен|ило|ыло|ено|ят|ует|уют|ит|ыт|ены|ить|"
                      r"ыть|ишь|ую|ю)|((?<=[ая])(ла|на|ете|йте|ли|й|л|ем|н|ло|но|ет|ют|ны|ть|ешь|нно)))$")
_RU_NOUN = re.compile(r"(а|ев|ов|ие|ье|е|иями|ями|ами|еи|ии|и|ией|ей|ой|ий|й|иям|ям|ием|ем|ам|ом|о|у|ах|иях|ях|ы|ь|"
                      r"ию|ью|ю|ия|ья|я)$")
_RU_RV = re.compile(r"^(.*?[аеиоуыэюя])(.*)$")
_RU_DERIVATIONAL = re.compile(r".*[^аеиоуыэюя]+[аеиоуыэюя].*ость?$")
_STEM_CACHE: dict[str, str] = {}


def _stem_ru(word: str) -> str:
    m = _RU_RV.match(word)
    if not m:
        return word
    pre, rv = m.groups()
    temp = _RU_PERFECTIVE.sub("", rv, 1)
    if temp == rv:
        rv = _RU_REFLEXIVE.sub("", rv, 1)
        temp = _RU_ADJECTIVE.sub("", rv, 1)
        if temp != rv:
            rv = _RU_PARTICIPLE.sub("", temp, 1)
        else:
            temp = _RU_VERB.sub("", rv, 1)
            rv = _RU_NOUN.sub("", rv, 1) if temp == rv else temp
    else:
        rv = temp
    rv = re.sub(r"и$", "", rv, 1)
    if _RU_DERIVATIONAL.match(rv):
        rv = re.sub(r"ость?$", "", rv, 1)
    temp = re.sub(r"ь$", "", rv, 1)
    if temp == rv:
        rv = re.sub(r"(ейше|ейш)$", "", rv, 1)
        rv = re.sub(r"нн$", "н", rv, 1)
    else:
        rv = temp
    return pre + rv


def _stem(tok: str) -> str:
    out = _STEM_CACHE.get(tok)
    if out is None:
        if re.search(r"[а-я]", tok):
            out = _stem_ru(tok)
        elif tok.isalpha() and len(tok) > 4 and tok.endswith("s") and not tok.endswith(("ss", "us", "is")):
            out = tok[:-1]
        else:
            out = tok
        _STEM_CACHE[tok] = out
    return out


def _terms(text: str) -> list[str]:
    """Основы слов длиной от 2 символов; составные (payments-prod, ops-1234) — целиком и по частям."""
    out: list[str] = []
    for m in re.finditer(r"[0-9a-zа-я]+(?:[-_.][0-9a-zа-я]+)*", text.lower().replace("ё", "е")):
        w = m.group(0)
        parts = re.split(r"[-_.]", w)
        if len(parts) > 1:
            out.append(w)
        out.extend(_stem(x) for x in parts if len(x) >= 2)
    return out



def register(
    mcp: FastMCP,
    cfg: dict[str, Any],
    redactor: Any,
    audit_fn: Callable[[str, dict, int], None],
) -> None:
    limits = cfg.get("limits", {}) or {}

    # -------------------------------------------------------------------------
    # Internal index class
    # -------------------------------------------------------------------------

    class ObsidianIndex:
        """Простой in-memory поисковый индекс по Obsidian vault."""

        def __init__(self, vault_path: Path) -> None:
            self.vault_path = vault_path
            # rel_path -> {mtime, content, tokens (Counter), title}
            self.notes: dict[str, dict[str, Any]] = {}
            self.refresh()

        @staticmethod
        def _tokenize(text: str) -> Counter[str]:
            return Counter(_terms(text))

        @staticmethod
        def _title_from(content: str, fallback: str) -> str:
            # Берём первый # H1 или имя файла
            for line in content.splitlines()[:30]:
                m = re.match(r"#\s+(.+)", line)
                if m:
                    return m.group(1).strip()
            return fallback

        def refresh(self) -> None:
            if not self.vault_path.exists():
                return
            seen: set[str] = set()
            for path in self.vault_path.rglob("*.md"):
                # Пропускаем системные папки Obsidian
                if any(p.startswith(".") for p in path.relative_to(self.vault_path).parts):
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                rel = path.relative_to(self.vault_path).as_posix()
                seen.add(rel)
                if rel in self.notes and self.notes[rel]["mtime"] == stat.st_mtime:
                    continue
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                self.notes[rel] = {
                    "mtime": stat.st_mtime,
                    "content": content,
                    "tokens": self._tokenize(content),
                    "title": self._title_from(content, path.stem),
                }
            # Удаляем заметки, которых уже нет на диске
            for stale in [k for k in self.notes if k not in seen]:
                self.notes.pop(stale, None)

        def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
            """BM25 по основам слов + бонус за совпадение в заголовке/имени файла."""
            q_terms = list(dict.fromkeys(_terms(query)))
            if not q_terms or not self.notes:
                return []
            n_docs = len(self.notes)
            df = Counter()
            for note in self.notes.values():
                df.update(t for t in q_terms if t in note["tokens"])
            avgdl = sum(sum(n["tokens"].values()) for n in self.notes.values()) / n_docs or 1.0
            k1, b = 1.2, 0.75
            scored: list[tuple[float, str]] = []
            for rel, note in self.notes.items():
                tokens: Counter[str] = note["tokens"]
                dl = sum(tokens.values()) or 1
                head = set(_terms(note["title"] + " " + rel))
                score = 0.0
                matched = 0
                for term in q_terms:
                    f = tokens.get(term, 0)
                    if f:
                        matched += 1
                        idf = math.log(1 + (n_docs - df[term] + 0.5) / (df[term] + 0.5))
                        score += idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / avgdl))
                    if term in head:
                        score += 2.0
                if score > 0:
                    scored.append((score * (0.4 + 0.6 * matched / len(q_terms)), rel))
            scored.sort(reverse=True)
            results: list[dict[str, Any]] = []
            max_snippet = int(limits.get("snippet_chars", 400))
            for score, rel in scored[:top_k]:
                note = self.notes[rel]
                results.append({
                    "path": rel,
                    "title": note["title"],
                    "score": round(score, 2),
                    "snippet": self._snippet(note["content"], query, max_snippet),
                })
            return results

        @staticmethod
        def _snippet(content: str, query: str, max_chars: int) -> str:
            lower = content.lower().replace("ё", "е")
            terms = sorted(set(_terms(query)), key=len, reverse=True)
            for term in terms:
                idx = lower.find(term)
                if idx != -1:
                    start = max(0, idx - max_chars // 3)
                    end = min(len(content), idx + (max_chars * 2) // 3)
                    prefix = "…" if start > 0 else ""
                    suffix = "…" if end < len(content) else ""
                    return prefix + content[start:end] + suffix
            return content[:max_chars] + ("…" if len(content) > max_chars else "")

    # -------------------------------------------------------------------------
    # Build index
    # -------------------------------------------------------------------------

    import logging
    log = logging.getLogger(__name__)

    obsidian: ObsidianIndex | None = None
    if cfg.get("vault_path"):
        try:
            vault = Path(cfg["vault_path"]).expanduser()
            if vault.exists() and vault.is_dir():
                obsidian = ObsidianIndex(vault)
                log.info("obsidian vault loaded: %d notes from %s",
                         len(obsidian.notes), vault)
            else:
                log.warning("obsidian vault_path '%s' not found, skipping", vault)
        except Exception as e:  # noqa: BLE001
            log.error("failed to load obsidian vault: %s", e)

    # -------------------------------------------------------------------------
    # Tools
    # -------------------------------------------------------------------------


    # -------------------------------------------------------------------------
    # База знаний (+ этот vault) через kb.py из agent-harness
    # -------------------------------------------------------------------------

    # obsidian.kb_tool — путь к kb.py. По умолчанию — копия в этом репозитории
    # (<agent-harness>/tools/kb.py, на три уровня выше tools/ этого сервера).
    # Корень базы kb.py берёт из своего конфига (paths.kb_root agent-harness).
    # Устаревший ключ obsidian.kb_root (<kb_root>/tools/kb.py) поддерживается.
    if cfg.get("kb_tool"):
        kb_tool = Path(str(cfg["kb_tool"])).expanduser()
    elif cfg.get("kb_root"):
        kb_tool = Path(str(cfg["kb_root"])).expanduser() / "tools" / "kb.py"
    else:
        kb_tool = DEFAULT_KB_TOOL
    _kb_cache: dict[str, Any] = {}

    def _kb_module():
        """Грузит kb.py по пути obsidian.kb_tool; перечитывает, если файл изменился."""
        path = kb_tool
        if not path.exists():
            return None
        mtime = path.stat().st_mtime
        if _kb_cache.get("mtime") != mtime:
            spec = importlib.util.spec_from_file_location("harness_kb", path)
            mod = importlib.util.module_from_spec(spec)
            sys.modules["harness_kb"] = mod  # dataclass с отложенными аннотациями ищет модуль здесь
            spec.loader.exec_module(mod)
            _kb_cache.update(mtime=mtime, mod=mod)
        return _kb_cache["mod"]

    def _kb_docs(mod, include_obsidian: bool, service, ticket, doc_type, since):
        roots = [mod.ROOT]
        if include_obsidian and obsidian is not None and obsidian.vault_path.resolve() != Path(mod.ROOT).resolve():
            roots.append(obsidian.vault_path.resolve())
        f = SimpleNamespace(type=[doc_type] if doc_type else None, lifecycle=None,
                            service=[service] if service else None, ticket=[ticket] if ticket else None,
                            since=since, path=None)
        return mod.filter_docs(mod.load_docs(roots, False), f)

    @mcp.tool()
    async def kb_search(query: str, limit: int = 6, service: str | None = None, ticket: str | None = None,
                        doc_type: str | None = None, include_obsidian: bool = True) -> dict[str, Any]:
        """
        Поиск по базе знаний: документы базы (RCA, обращения, runbook-и, решения) и заметки Obsidian.

        ВЫЗЫВАЙ ПЕРВЫМ при разборе алерта, обращения или вопроса о сервисе/тикете — до дорогих
        походов в логи и метрики. Возвращает разделы с диапазоном строк, а не документы целиком:
        дальше читай только эти строки (sed -n 'A,Bp' или obsidian_read_note).

        Args:
            query:     симптом, сервис, алерт, тикет ("nexus квота восстановление", "OPS-1234").
            limit:     сколько документов вернуть (по умолчанию 6, потолок 15).
            service:   каноническое имя из navigation/glossary.md базы (vault, harbor, payments…).
            ticket:    ключ задачи (OPS-1234, INC-42).
            doc_type:  rca | request | runbook | plan | decision | review | reference | snapshot | finding | task.
            include_obsidian: искать и в заметках vault, если vault — отдельная папка (по умолчанию да).
        """
        mod = _kb_module()
        if mod is None:
            return {"error": f"kb.py не найден: {kb_tool} — задайте obsidian.kb_tool в config.yaml"}
        docs = _kb_docs(mod, include_obsidian, service, ticket, doc_type, None)
        results = mod.run_search(docs, query, min(max(1, limit), 15))
        payload = {"root": str(mod.ROOT), "count": len(results), "results": redactor.scrub_any(results)}
        audit_fn("kb_search", {"query": query, "limit": limit}, len(json.dumps(payload, ensure_ascii=False)))
        return payload

    @mcp.tool()
    async def kb_list(service: str | None = None, ticket: str | None = None, doc_type: str | None = None,
                      since: str | None = None, limit: int = 20, include_obsidian: bool = False) -> dict[str, Any]:
        """
        Каталог базы знаний (новые сверху) с фильтрами — обзор без поискового запроса:
        «что есть по vault», «все runbook-и», «что появилось с 2026-10-01», «всё по OPS-1234».

        Args:
            service, ticket, doc_type: фильтры как в kb_search.
            since:  YYYY-MM-DD — только документы с этой даты.
            limit:  максимум строк (по умолчанию 20, потолок 100).
            include_obsidian: добавить заметки vault.
        """
        mod = _kb_module()
        if mod is None:
            return {"error": f"kb.py не найден: {kb_tool}"}
        docs = _kb_docs(mod, include_obsidian, service, ticket, doc_type, since)
        docs.sort(key=lambda d: (d.date or "0000", d.rel), reverse=True)
        rows = [{"path": d.rel, "title": d.title, "type": d.type, "lifecycle": d.lifecycle, "date": d.date,
                 "tickets": d.tickets, "services": d.services, "summary": d.summary[:200]}
                for d in docs[:min(max(1, limit), 100)]]
        payload = {"root": str(mod.ROOT), "total": len(docs), "results": redactor.scrub_any(rows)}
        audit_fn("kb_list", {"service": service, "ticket": ticket, "type": doc_type}, len(json.dumps(payload, ensure_ascii=False)))
        return payload

    @mcp.tool()
    async def obsidian_search(query: str, top_k: int = 5) -> dict[str, Any]:
        """
        Поиск в локальном vault Obsidian (runbooks, постмортемы, описания сервисов).

        ВЫЗЫВАЙ ЭТОТ TOOL ПЕРВЫМ при разборе инцидента. Часто нужный runbook
        или описание похожего прошлого инцидента уже есть в заметках — это
        экономит десятки тысяч токенов по сравнению с походами в продакшн.

        Args:
            query: ключевые слова — название алерта, имя сервиса, симптом
                   (например "HighErrorRate checkout" или "оплата таймаут").
            top_k: сколько лучших совпадений вернуть (по умолчанию 5, потолок 20).

        Returns:
            {count, vault_size, results: [{path, title, score, snippet}]}
        """
        if obsidian is None:
            return {"error": "obsidian не сконфигурирован — задайте obsidian.vault_path в config.yaml"}
        obsidian.refresh()  # cheap: только mtime-проверки
        top_k = min(max(1, top_k), 20)
        results = obsidian.search(query, top_k)
        payload = {
            "count": len(results),
            "vault_size": len(obsidian.notes),
            "results": redactor.scrub_any(results),
        }
        audit_fn("obsidian_search", {"query": query, "top_k": top_k}, len(json.dumps(payload)))
        return payload

    @mcp.tool()
    async def obsidian_read_note(path: str) -> dict[str, Any]:
        """
        Прочитать конкретную заметку из vault Obsidian целиком.

        Используй после obsidian_search, когда найден релевантный runbook и
        нужно получить его полностью.

        Args:
            path: относительный путь от корня vault, например
                  'runbooks/payment-timeout.md' (как вернул obsidian_search).
        """
        if obsidian is None:
            return {"error": "obsidian не сконфигурирован"}

        # Защита от path traversal
        try:
            target = (obsidian.vault_path / path).resolve()
            if not str(target).startswith(str(obsidian.vault_path.resolve())):
                return {"error": "path traversal заблокирован"}
        except (ValueError, OSError) as e:
            return {"error": f"bad path: {e}"}

        if not target.exists() or not target.is_file():
            return {"error": f"note not found: {path}"}

        max_chars = int(limits.get("max_note_chars", 8000))
        content = target.read_text(encoding="utf-8", errors="replace")
        truncated = len(content) > max_chars
        payload = {
            "path": path,
            "title": ObsidianIndex._title_from(content, target.stem),
            "content": redactor.scrub(content[:max_chars]),
            "size_chars": len(content),
            "truncated": truncated,
        }
        audit_fn("obsidian_read_note", {"path": path}, len(json.dumps(payload)))
        return payload

    def _inject_wikilinks(content: str, related: list[str], title_to_stem: dict[str, str]) -> tuple[str, list[str]]:
        """
        Вставляет [[wikilinks]] в контент:
        1. Явные ссылки из related — добавляются в секцию ## Связанные заметки.
        2. Авто-ссылки: первое упоминание каждого заголовка vault в тексте
           оборачивается в ссылку.
        Obsidian находит заметку по имени файла, а файлы называются slug-ом с датой,
        поэтому ссылка на существующую заметку пишется как [[имя-файла|Заголовок]].
        Заголовок без заметки (сервис, тикет) остаётся [[Заголовок]] — будущий хаб.
        Возвращает (новый контент, список заголовков, на которые поставлены ссылки).
        """
        def link(title: str, shown: str | None = None) -> str:
            stem = title_to_stem.get(title.lower())
            shown = shown or title
            return f"[[{stem}|{shown}]]" if stem and stem != shown else f"[[{shown}]]"

        linked: list[str] = []
        for vault_title in sorted({k for k in title_to_stem}, key=len, reverse=True):
            if len(vault_title) < 4:
                continue
            pattern = r"(?<![\[|])" + re.escape(vault_title) + r"(?![\]|])"
            m = re.search(pattern, content, flags=re.IGNORECASE)
            if m:
                content = content[:m.start()] + link(vault_title, m.group(0)) + content[m.end():]
                linked.append(m.group(0))

        explicit = [r for r in related if r.lower() not in {x.lower() for x in linked}]
        all_links = linked + explicit
        if all_links and "## Связанные заметки" not in content:
            content = content.rstrip() + "\n\n## Связанные заметки\n\n" + "\n".join(
                f"- {link(l)}" for l in all_links) + "\n"
        return content, all_links

    @mcp.tool()
    async def obsidian_append_finding(
        title: str,
        content: str,
        folder: str = "findings",
        tags: list[str] | None = None,
        related_notes: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Записать новую заметку в Obsidian vault — итог разбора инцидента, найденную
        закономерность, временный workaround и т.п. Так vault накапливает память
        команды, и следующий похожий инцидент найдётся через obsidian_search.

        Включается через obsidian.allow_writes: true в config.yaml.

        Args:
            title:         заголовок заметки (станет H1 и частью имени файла).
            content:       тело заметки в markdown.
            folder:        подпапка vault (по умолчанию 'findings').
            tags:          список тегов для frontmatter.
            related_notes: заголовки связанных заметок для [[wikilinks]].
                           Передавай заголовки из obsidian_search результатов —
                           они будут добавлены в секцию «Связанные заметки»
                           и найдены в тексте для inline-ссылок.
        """
        if obsidian is None:
            return {"error": "obsidian не сконфигурирован"}
        if not cfg.get("allow_writes", False):
            return {"error": "запись в obsidian отключена; включите obsidian.allow_writes в config.yaml"}

        # slug для имени файла
        safe = re.sub(r"[^\w\s\-А-Яа-яёЁ]", "", title).strip()
        safe = re.sub(r"[\s_-]+", "-", safe).lower()[:80] or "note"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        filename = f"{ts}-{safe}.md"

        try:
            target_dir = (obsidian.vault_path / folder).resolve()
            if not str(target_dir).startswith(str(obsidian.vault_path.resolve())):
                return {"error": "folder traversal заблокирован"}
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return {"error": f"cannot create folder: {e}"}

        target_file = target_dir / filename
        tag_list = tags or ["auto", "finding"]
        fm_tags = ", ".join(tag_list)

        # Вставляем wikilinks: авто (из vault) + явные (из related_notes)
        title_to_stem = {n["title"].lower(): Path(rel).stem for rel, n in obsidian.notes.items()}
        linked_content, all_links = _inject_wikilinks(
            content,
            related=related_notes or [],
            title_to_stem=title_to_stem,
        )

        body = (
            f"---\n"
            f"date: {ts}\n"
            f"tags: [{fm_tags}]\n"
            f"aliases: [{json.dumps(title, ensure_ascii=False)}]\n"
            f"source: claude-mcp\n"
            f"---\n\n"
            f"# {title}\n\n"
            f"{linked_content}\n"
        )
        target_file.write_text(body, encoding="utf-8")
        # Пересобрать списки заметок в хабах services/ и tickets/, если в vault есть сборщик.
        hubs_script = next((s for s in (obsidian.vault_path / "tools" / "build_hubs.py",
                                        obsidian.vault_path / ".scripts" / "build_hubs.py") if s.exists()), None)
        if hubs_script:
            try:
                subprocess.run([sys.executable, "-I", str(hubs_script)], cwd=obsidian.vault_path,
                               capture_output=True, timeout=20, check=False)
            except (OSError, subprocess.SubprocessError) as e:
                log.warning("build_hubs failed: %s", e)
        obsidian.refresh()

        payload = {
            "path": f"{folder}/{filename}",
            "written_chars": len(body),
            "tags": tag_list,
            "wikilinks_added": all_links,
        }
        audit_fn("obsidian_append_finding",
                 {"title": title, "folder": folder, "tags": tag_list, "wikilinks": len(all_links)},
                 len(json.dumps(payload)))
        return payload
