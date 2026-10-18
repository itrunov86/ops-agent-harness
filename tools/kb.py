#!/usr/bin/env python3
"""
kb.py — поиск, каталог и проверка базы знаний (paths.kb_root из конфига agent-harness) для людей и ИИ-агентов.

    python3 tools/kb.py search "payments latency rollback"   # разделы + строки, читать только их
    python3 tools/kb.py list --service vault --since 2026-10-01
    python3 tools/kb.py lint [--json] [--strict]
    python3 tools/kb.py meta duty/OPS-1234-payments-latency-2026-10-13.md
    python3 tools/kb.py catalog        # пишет catalog.md (в .gitignore) для чтения глазами и Obsidian

Метаданные документа берутся из frontmatter, а если его нет — выводятся из пути, имени
файла и шапки. Ручные навигационные таблицы для поиска не нужны. Индекс строится в памяти
при каждом вызове. Только стандартная библиотека.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_config import CONFIG  # noqa: E402

ROOT = CONFIG.kb_root
GLOSSARY = ROOT / "navigation" / "glossary.md"
# Документы с этой даты обязаны иметь frontmatter (см. AGENTS.md).
CUTOVER = "2026-10-16"

TYPES = ("rca", "request", "runbook", "plan", "decision", "review", "reference",
         "snapshot", "finding", "task", "nav")
LIFECYCLES = ("current", "historical", "superseded", "draft")
CONTENT_DIRS = {"alerts", "duty", "tasks", "review", "release", "s3", "terragrunt", "decisions", "reference"}
SKIP_DIRS = {".git", "tools", "__pycache__", "node_modules", ".obsidian", ".trash"}
NAV_DIRS = {"navigation", "exports"}
ROOT_NAV_FILES = {"AGENTS.md", "CLAUDE.md", "documentation-navigation-map.md", "catalog.md"}
TOP_DIR_TYPE = {
    "alerts": "rca", "incidents": "rca", "postmortems": "rca",
    "duty": "request", "s3": "request",
    "findings": "finding", "runbooks": "runbook",
    "services": "reference", "patterns": "reference", "reference": "reference", "terragrunt": "reference", "wiki": "reference",
    "review": "review", "release": "plan", "plans": "plan", "decisions": "decision",
    "tasks": "task", "navigation": "nav", "tickets": "reference", "exports": "reference",
}
CURRENT_TYPES = {"runbook", "reference", "decision", "nav"}

DATE_RE = re.compile(r"(20\d\d)-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
COMPACT_DATE_RE = re.compile(r"(?<!\d)(20\d\d)(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)")
TICKET_RE = CONFIG.ticket_re(6)
HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$")
NAV_PATH_RE = re.compile(
    r"`((?:alerts|duty|release|review|s3|terragrunt|wiki|tasks|navigation)/[^`]+\.(?:md|sh))`")
MD_LINK_RE = re.compile(r"\]\((?!https?:|mailto:|#)([^)\s]+?\.md)(?:#[^)]*)?\)")

# --------------------------------------------------------------------------------------------
# Морфология: стеммер Портера для русского, лёгкая нормализация английского
# --------------------------------------------------------------------------------------------

_RU_PERFECTIVE = re.compile(r"((ив|ивши|ившись|ыв|ывши|ывшись)|((?<=[ая])(в|вши|вшись)))$")
_RU_REFLEXIVE = re.compile(r"(с[яь])$")
_RU_ADJECTIVE = re.compile(r"(ее|ие|ые|ое|ими|ыми|ей|ий|ый|ой|ем|им|ым|ом|его|ого|ему|ому|их|ых|"
                           r"ую|юю|ая|яя|ою|ею)$")
_RU_PARTICIPLE = re.compile(r"((ивш|ывш|ующ)|((?<=[ая])(ем|нн|вш|ющ|щ)))$")
_RU_VERB = re.compile(r"((ила|ыла|ена|ейте|уйте|ите|или|ыли|ей|уй|ил|ыл|им|ым|ен|ило|ыло|ено|ят|"
                      r"ует|уют|ит|ыт|ены|ить|ыть|ишь|ую|ю)|((?<=[ая])(ла|на|ете|йте|ли|й|л|ем|н|"
                      r"ло|но|ет|ют|ны|ть|ешь|нно)))$")
_RU_NOUN = re.compile(r"(а|ев|ов|ие|ье|е|иями|ями|ами|еи|ии|и|ией|ей|ой|ий|й|иям|ям|ием|ем|ам|ом|"
                      r"о|у|ах|иях|ях|ы|ь|ию|ью|ю|ия|ья|я)$")
_RU_RV = re.compile(r"^(.*?[аеиоуыэюя])(.*)$")
_RU_DERIVATIONAL = re.compile(r".*[^аеиоуыэюя]+[аеиоуыэюя].*ость?$")
_RU_DER = re.compile(r"ость?$")
_RU_SUPERLATIVE = re.compile(r"(ейше|ейш)$")


def stem_ru(word: str) -> str:
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
        rv = _RU_DER.sub("", rv, 1)
    temp = re.sub(r"ь$", "", rv, 1)
    if temp == rv:
        rv = _RU_SUPERLATIVE.sub("", rv, 1)
        rv = re.sub(r"нн$", "н", rv, 1)
    else:
        rv = temp
    return pre + rv


def stem_en(word: str) -> str:
    if len(word) <= 4:
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("sses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


STOP = set("""
и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее мне было вот
от меня еще нет о из ему теперь когда даже ну ли если уже или ни быть был него до вас там потом себя
ей может они тут где есть надо ней для мы тебя их чем была сам без чего раз тоже себе под будет ж тогда
кто этот того потому этого какой ним здесь этом один почти тем чтобы нее сейчас были куда зачем всех
можно при об другой хоть после над больше тот через эти нас про всего них какая много эту свою этой
перед лучше том нельзя такой им более всегда между это также либо
the a an of to in and or is are was were be been for on with as by at from it its this that these those
not no if then than into via per
""".split())

_WORD_RE = re.compile(r"[0-9a-zа-я]+(?:[-_./:][0-9a-zа-я]+)*")
_SPLIT_RE = re.compile(r"[-_./:]")
_HAS_CYR = re.compile(r"[а-я]")
_stem_cache: dict[str, str] = {}


def stem(tok: str) -> str:
    out = _stem_cache.get(tok)
    if out is None:
        if _HAS_CYR.search(tok):
            out = stem_ru(tok)
        elif tok.isalpha():
            out = stem_en(tok)
        else:
            out = tok
        _stem_cache[tok] = out
    return out


def analyze(text: str) -> list[str]:
    """Токены для поиска: составные (payments-prod, ops-1234) целиком и по частям, слова — по основе."""
    out: list[str] = []
    for m in _WORD_RE.finditer(text.lower().replace("ё", "е")):
        w = m.group(0)
        parts = _SPLIT_RE.split(w)
        if len(parts) > 1:
            out.append(w)
            out.extend(stem(p) for p in parts if len(p) >= 2 and p not in STOP)
        elif len(w) >= 2 and w not in STOP:
            out.append(stem(w))
    return out


def phrase_tokens(text: str, split_compounds: bool) -> list[str]:
    """Последовательность токенов для сопоставления фраз из глоссария."""
    out: list[str] = []
    for m in _WORD_RE.finditer(text.lower().replace("ё", "е")):
        w = m.group(0)
        parts = _SPLIT_RE.split(w)
        if len(parts) > 1 and not split_compounds:
            out.append(w)
        else:
            out.extend(stem(p) for p in parts if p)
    return out


# --------------------------------------------------------------------------------------------
# Глоссарий: канонические имена сервисов и синонимы (navigation/glossary.md)
# --------------------------------------------------------------------------------------------

class Glossary:
    def __init__(self, path: Path = GLOSSARY) -> None:
        self.aliases: dict[str, list[str]] = {}
        self._phrases: dict[str, list[tuple[tuple[str, ...], str]]] = defaultdict(list)
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                m = re.match(r"^\s*[-*]\s*`?([a-z0-9][a-z0-9._-]*)`?\s*:\s*(.+)$", line)
                if not m:
                    continue
                canon = m.group(1)
                names = [canon] + [a.strip().strip("`") for a in m.group(2).split(",") if a.strip()]
                self.aliases[canon] = names
                for name in names:
                    for split in (False, True):
                        toks = tuple(phrase_tokens(name, split))
                        if toks:
                            self._phrases[toks[0]].append((toks, canon))

    def match(self, text: str) -> Counter:
        found: Counter = Counter()
        for split in (False, True):
            toks = phrase_tokens(text, split)
            for i, t in enumerate(toks):
                for phrase, canon in self._phrases.get(t, ()):
                    if tuple(toks[i:i + len(phrase)]) == phrase:
                        found[canon] += 1
        return found

    def canonical(self, value: str) -> str:
        hit = self.match(value)
        return hit.most_common(1)[0][0] if hit else value.strip().lower()

    def expand(self, query: str) -> Counter:
        """Токены синонимов для найденных в запросе сервисов (с пониженным весом)."""
        extra: Counter = Counter()
        for canon in self.match(query):
            for name in self.aliases.get(canon, ()):
                for t in analyze(name):
                    extra[t] = 0.4
        return extra


# --------------------------------------------------------------------------------------------
# Документы и метаданные
# --------------------------------------------------------------------------------------------

def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        return v[1:-1]
    return v


def _parse_value(v: str):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        return [_unquote(x) for x in v[1:-1].split(",") if x.strip()]
    if v in ("null", "~", "None"):
        return None
    if v[:1] not in "'\"":
        v = re.sub(r"\s+#.*$", "", v)
    return _unquote(v)


def parse_frontmatter(lines: list[str]) -> tuple[dict, int, bool]:
    """(meta, индекс первой строки тела, frontmatter не закрыт)."""
    if not lines or lines[0].strip() != "---":
        return {}, 0, False
    meta: dict = {}
    key = None
    for i in range(1, min(len(lines), 120)):
        line = lines[i]
        if line.strip() == "---":
            return meta, i + 1, False
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key = m.group(1)
            meta[key] = _parse_value(m.group(2)) if m.group(2).strip() else []
            continue
        m = re.match(r"^\s+-\s+(.*)$", line)
        if m and key is not None:
            cur = meta.get(key)
            if not isinstance(cur, list):
                cur = [] if cur in (None, "") else [cur]
            cur.append(_unquote(m.group(1)))
            meta[key] = cur
    return {}, 0, True


def as_list(v) -> list[str]:
    if v is None:
        return []
    items = v if isinstance(v, list) else re.split(r"[,;]\s*", str(v))
    return [str(s).strip() for s in items
            if str(s).strip() and str(s).strip().lower() not in ("null", "none", "~")]


@dataclass
class Doc:
    path: Path
    rel: str
    top: str
    lines: list[str]
    meta: dict
    body_start: int
    fm_broken: bool
    title: str = ""
    type: str = ""
    lifecycle: str = ""
    status: str = ""
    date: str = ""
    tickets: list[str] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    summary: str = ""
    field_tf: Counter = field(default_factory=Counter)

    @property
    def has_fm(self) -> bool:
        return bool(self.meta)


def _infer_type(top: str, rel: str, root_level: bool) -> str:
    name = Path(rel).name.lower()
    if root_level:
        return "nav"
    if "runbook" in name:
        return "runbook"
    if re.search(r"(^|[-_])adr([-_.]|$)|decision", name):
        return "decision"
    if "review" in name:
        return "review"
    base = TOP_DIR_TYPE.get(top, "reference")
    if base in ("rca", "request", "finding", "nav"):
        return base
    if re.search(r"plan|migration|upgrade", name):
        return "plan"
    if top == "tasks" and re.search(r"summary|inventory|snapshot|audit|report|collection|current-state|map", name):
        return "snapshot"
    return base


def _infer_lifecycle(type_: str, status: str) -> str:
    s = status.lower()
    if re.search(r"deprecat|supersed|obsolete|устар|заменён|заменен", s):
        return "superseded"
    if re.search(r"\bdraft\b|черновик", s):
        return "draft"
    return "current" if type_ in CURRENT_TYPES else "historical"


def _infer_date(meta: dict, rel: str, head: list[str]) -> str:
    for v in as_list(meta.get("date")):
        m = DATE_RE.search(v)
        if m:
            return m.group(0)
    found = DATE_RE.findall(Path(rel).name)
    if found:
        return "-".join(found[-1])
    m = COMPACT_DATE_RE.search(rel)
    if m:
        return "-".join(m.groups())
    for line in head:
        if re.search(r"дата|date|сформир|обновл", line, re.I):
            m = DATE_RE.search(line)
            if m:
                return m.group(0)
    for line in head[:15]:
        m = DATE_RE.search(line)
        if m:
            return m.group(0)
    return ""


_SKIP_SUMMARY = re.compile(r"^(\||```|---|>?\s*$|[-*]\s*$|(дата|date|status|статус|ticket|тикет|"
                           r"сервис|service|owner|scope|freshness)\b)", re.I)


def _infer_summary(meta: dict, head: list[str]) -> str:
    s = meta.get("summary")
    if isinstance(s, list):
        s = " ".join(s)
    if s:
        return str(s).strip()
    for line in head:
        m = re.match(r"^\s*(?:\*\*)?(read this when|кратко|tl;dr|итог|суть)(?:\*\*)?\s*[:—-]\s*(.+)$",
                     line, re.I)
        if m:
            return m.group(2).strip()[:240]
    for line in head:
        t = line.strip()
        if not t or t.startswith("#") or _SKIP_SUMMARY.match(t):
            continue
        return re.sub(r"\s+", " ", t)[:240]
    return ""


def load_doc(path: Path, base: Path, glossary: Glossary) -> Doc:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    meta, body_start, broken = parse_frontmatter(lines)
    try:
        rel = path.relative_to(ROOT).as_posix()
    except ValueError:
        rel = str(path).replace(str(Path.home()), "~", 1)
    rel_in_base = path.relative_to(base)
    root_level = len(rel_in_base.parts) == 1
    top = rel_in_base.parts[0] if not root_level else ""
    d = Doc(path=path, rel=rel, top=top, lines=lines, meta=meta, body_start=body_start, fm_broken=broken)

    head = lines[body_start:body_start + 40]
    title = str(meta.get("title") or "")
    if not title:
        for line in head:
            m = re.match(r"^#\s+(.+)$", line)
            if m:
                title = m.group(1).strip()
                break
    d.title = title or path.stem

    status = meta.get("status")
    if isinstance(status, list):
        status = "; ".join(status)
    if not status:
        for line in head[:30]:
            m = re.match(r"^\s*(?:\*\*)?(?:status|статус)(?:\*\*)?\s*:\s*(.+)$", line, re.I)
            if m:
                status = m.group(1)
                break
    d.status = str(status or "").strip()

    t = str(meta.get("type") or "").strip().lower()
    d.type = t if t in TYPES else _infer_type(top, rel, root_level)
    lc = str(meta.get("lifecycle") or "").strip().lower()
    d.lifecycle = lc if lc in LIFECYCLES else _infer_lifecycle(d.type, d.status)
    d.date = _infer_date(meta, rel, head)

    tickets = as_list(meta.get("tickets")) + as_list(meta.get("ticket")) + as_list(meta.get("incident"))
    if not tickets:
        tickets = [m.group(0) for m in TICKET_RE.finditer(path.name + " " + d.title)]
    d.tickets = list(dict.fromkeys(x.upper() for x in tickets))
    d.tags = as_list(meta.get("tags"))

    weights: Counter = Counter()
    for v in as_list(meta.get("services")) + as_list(meta.get("service")):
        weights[glossary.canonical(v)] += 10
    probe = " ".join([path.stem.replace("_", " "), d.title, " ".join(d.tags)])
    for canon, n in glossary.match(probe).items():
        weights[canon] += 3 * n
    headings = " ".join(m.group(2) for line in lines[body_start:]
                        for m in [HEADING_RE.match(line)] if m)
    for canon, n in glossary.match(headings).items():
        weights[canon] += n
    d.services = [c for c, w in weights.most_common() if w >= 2][:5]
    d.summary = _infer_summary(meta, head)

    d.field_tf = Counter(analyze(d.title) * 3
                         + analyze(path.stem) * 2
                         + analyze(" ".join(d.tags + d.tickets + d.services)) * 3
                         + analyze(d.summary) * 2)
    return d


def iter_md(base: Path, include_nav: bool):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(x for x in dirnames if x not in SKIP_DIRS and not x.startswith("."))
        rel_dir = Path(dirpath).relative_to(base)
        if not include_nav and rel_dir.parts and rel_dir.parts[0] in NAV_DIRS:
            continue
        for fn in sorted(filenames):
            if not fn.endswith(".md"):
                continue
            if not include_nav and not rel_dir.parts and fn in ROOT_NAV_FILES:
                continue
            yield Path(dirpath) / fn


def load_docs(roots: list[Path], include_nav: bool) -> list[Doc]:
    glossary = Glossary()
    docs = []
    for base in roots:
        for p in iter_md(base, include_nav):
            docs.append(load_doc(p, base, glossary))
    return docs


def extra_roots(args) -> list[Path]:
    roots = [ROOT]
    env = os.environ.get("KB_EXTRA_ROOTS", "")
    for r in list(getattr(args, "root", None) or []) + [x for x in env.split(":") if x]:
        p = Path(r).expanduser().resolve()
        if p.is_dir() and p not in roots:
            roots.append(p)
    return roots


def filter_docs(docs: list[Doc], args) -> list[Doc]:
    out = []
    for d in docs:
        if args.type and d.type not in args.type:
            continue
        if args.lifecycle and d.lifecycle not in args.lifecycle:
            continue
        if args.service and not set(s.lower() for s in args.service) & set(d.services):
            continue
        if args.ticket and not set(t.upper() for t in args.ticket) & set(d.tickets):
            continue
        if args.since and (not d.date or d.date < args.since):
            continue
        if args.path and not any(re.search(p, d.rel) for p in args.path):
            continue
        out.append(d)
    return out


# --------------------------------------------------------------------------------------------
# Поиск: BM25 по разделам + поля документа (title, имя файла, теги, тикеты, сервисы, summary)
# --------------------------------------------------------------------------------------------

@dataclass
class Section:
    doc: Doc
    start: int
    end: int
    heading: str
    tf: Counter
    length: int


def split_sections(d: Doc, max_lines: int = 120, window: int = 80) -> list[tuple[int, int, str]]:
    bounds: list[tuple[int, str]] = [(d.body_start, "")]
    in_code = False
    for i in range(d.body_start, len(d.lines)):
        line = d.lines[i]
        if line.startswith("```"):
            in_code = not in_code
            continue
        if not in_code:
            m = HEADING_RE.match(line)
            if m:
                bounds.append((i, m.group(2)))
    out = []
    for k, (start, head) in enumerate(bounds):
        end = bounds[k + 1][0] if k + 1 < len(bounds) else len(d.lines)
        if end <= start:
            continue
        if end - start <= max_lines:
            out.append((start, end, head))
        else:
            for s in range(start, end, window):
                out.append((s, min(s + window, end), head))
    return out


def bm25(tf: Counter, dl: int, avgdl: float, df: Counter, n: int, q: dict[str, float],
         k1: float = 1.2, b: float = 0.75) -> float:
    score = 0.0
    for t, qw in q.items():
        f = tf.get(t)
        if not f:
            continue
        idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
        score += qw * idf * f * (k1 + 1) / (f + k1 * (1 - b + b * dl / avgdl))
    return score


def run_search(docs: list[Doc], query: str, limit: int, per_doc: int = 2) -> list[dict]:
    base_terms = list(dict.fromkeys(analyze(query)))
    if not base_terms:
        return []
    q: dict[str, float] = {t: 1.0 for t in base_terms}
    for t, w in Glossary().expand(query).items():
        q.setdefault(t, w)

    sections: list[Section] = []
    for d in docs:
        for s, e, head in split_sections(d):
            toks = analyze(head) * 2 + analyze("\n".join(d.lines[s:e]))
            if toks:
                sections.append(Section(d, s, e, head, Counter(toks), len(toks)))
    if not sections:
        return []
    sec_df: Counter = Counter()
    for s in sections:
        sec_df.update(s.tf.keys())
    doc_df: Counter = Counter()
    for d in docs:
        doc_df.update(d.field_tf.keys())
    avg_sec = sum(s.length for s in sections) / len(sections)
    avg_doc = (sum(sum(d.field_tf.values()) for d in docs) / len(docs)) or 1.0

    doc_score: dict[int, float] = {}
    for d in docs:
        doc_score[id(d)] = bm25(d.field_tf, sum(d.field_tf.values()) or 1, avg_doc, doc_df, len(docs), q)

    today = date.today()
    scored: list[tuple[float, Section]] = []
    for s in sections:
        sec = bm25(s.tf, s.length, avg_sec, sec_df, len(sections), q)
        dsc = doc_score[id(s.doc)]
        if sec <= 0 and dsc <= 0:
            continue
        matched = sum(1 for t in base_terms if t in s.tf or t in s.doc.field_tf)
        coverage = matched / len(base_terms)
        score = (sec + 0.6 * dsc) * (0.4 + 0.6 * coverage)
        if s.doc.date:
            try:
                age = (today - date.fromisoformat(s.doc.date)).days
                score *= 1 + 0.15 * max(0.0, 1 - age / 365)
            except ValueError:
                pass
        if s.doc.lifecycle == "superseded":
            score *= 0.5
        elif s.doc.lifecycle == "draft":
            score *= 0.8
        scored.append((score, s))
    scored.sort(key=lambda x: -x[0])

    picked: dict[int, list[tuple[float, Section]]] = {}
    order: list[int] = []
    for score, s in scored:
        key = id(s.doc)
        if key not in picked:
            if len(order) >= limit:
                continue
            picked[key] = []
            order.append(key)
        hits = picked[key]
        if len(hits) < per_doc and (not hits or score >= 0.6 * hits[0][0]):
            hits.append((score, s))

    results = []
    for key in order:
        hits = picked[key]
        d = hits[0][1].doc
        results.append({
            "path": d.rel, "title": d.title, "type": d.type, "lifecycle": d.lifecycle,
            "date": d.date, "tickets": d.tickets, "services": d.services,
            "score": round(hits[0][0], 2),
            "sections": [_section_view(s, base_terms) for _, s in hits],
        })
    return results


def _section_view(s: Section, terms: list[str]) -> dict:
    # Лучшая строка раздела по числу совпавших терминов; заголовок — только если больше нечего показать.
    best_line, best_hits = s.start, -1
    tset = set(terms)
    for i in range(s.start, s.end):
        line = s.doc.lines[i]
        if not line.strip() or (line.startswith("#") and i != s.start):
            continue
        hits = len(tset & set(analyze(line))) - (0.5 if line.startswith("#") else 0)
        if hits > best_hits:
            best_line, best_hits = i, hits
    snippet = re.sub(r"\s+", " ", s.doc.lines[best_line].strip())
    if len(snippet) > 200:
        snippet = snippet[:197] + "…"
    heading = "" if s.heading == s.doc.title else s.heading
    return {"heading": heading, "lines": [s.start + 1, s.end], "line": best_line + 1, "snippet": snippet}


# --------------------------------------------------------------------------------------------
# Команды
# --------------------------------------------------------------------------------------------

def _meta_line(d: Doc) -> str:
    parts = [d.type, d.lifecycle, d.date or "без даты"]
    if d.tickets:
        parts.append(", ".join(d.tickets[:3]))
    if d.services:
        parts.append(", ".join(d.services))
    return " · ".join(parts)


def cmd_search(args) -> int:
    docs = filter_docs(load_docs(extra_roots(args), args.all), args)
    results = run_search(docs, " ".join(args.query), args.limit)
    if args.json:
        print(json.dumps({"root": str(ROOT), "results": results}, ensure_ascii=False, indent=1))
        return 0
    if not results:
        print("Ничего не найдено. Уточни сервис/симптом/тикет или ослабь фильтры.")
        return 1
    print(f"root: {ROOT} · {len(results)} док. · читай только указанные строки: sed -n 'A,Bp' <path>")
    for i, r in enumerate(results, 1):
        print(f"\n{i}. {r['path']}")
        print(f"   {' · '.join(x for x in [r['type'], r['lifecycle'], r['date'] or 'без даты', ', '.join(r['tickets'][:3]), ', '.join(r['services'])] if x)}")
        print(f"   {r['title'][:140]}")
        for s in r["sections"]:
            head = f"§ {s['heading'][:70]} " if s["heading"] else "§ (начало) "
            print(f"   {head}L{s['lines'][0]}-{s['lines'][1]} · L{s['line']}: {s['snippet']}")
    return 0


def cmd_list(args) -> int:
    docs = filter_docs(load_docs(extra_roots(args), args.all), args)
    docs.sort(key=lambda d: (d.date or "0000", d.rel), reverse=True)
    if args.stats:
        by_type = Counter(d.type for d in docs)
        by_lc = Counter(d.lifecycle for d in docs)
        by_service = Counter(s for d in docs for s in d.services)
        print(f"документов: {len(docs)}; с frontmatter: {sum(d.has_fm for d in docs)}")
        print("type: " + ", ".join(f"{k} {v}" for k, v in by_type.most_common()))
        print("lifecycle: " + ", ".join(f"{k} {v}" for k, v in by_lc.most_common()))
        print("services: " + ", ".join(f"{k} {v}" for k, v in by_service.most_common(40)))
        return 0
    shown = docs[:args.limit] if args.limit else docs
    if args.json:
        print(json.dumps([{"path": d.rel, "title": d.title, "type": d.type, "lifecycle": d.lifecycle,
                           "date": d.date, "tickets": d.tickets, "services": d.services,
                           "summary": d.summary} for d in shown], ensure_ascii=False, indent=1))
        return 0
    print(f"root: {ROOT} · показано {len(shown)} из {len(docs)}")
    for d in shown:
        print(f"{d.date or '----------'} {d.type:<9} {d.lifecycle:<10} {d.rel}")
        extra = ", ".join(d.tickets[:3] + d.services)
        print(f"           {d.title[:110]}{'  [' + extra + ']' if extra else ''}")
    return 0


def cmd_meta(args) -> int:
    docs = load_docs(extra_roots(args), True)
    want = [x.rstrip("/") for x in args.paths]
    for d in docs:
        if any(d.rel == w or d.rel.endswith("/" + w) or str(d.path) == str(Path(w).expanduser().resolve())
               for w in want):
            print(json.dumps({"path": d.rel, "title": d.title, "type": d.type, "lifecycle": d.lifecycle,
                              "status": d.status, "date": d.date, "tickets": d.tickets,
                              "services": d.services, "tags": d.tags, "summary": d.summary,
                              "frontmatter": bool(d.meta)}, ensure_ascii=False, indent=1))
    return 0


def cmd_catalog(args) -> int:
    docs = load_docs([ROOT], False)
    docs.sort(key=lambda d: (d.date or "0000", d.rel), reverse=True)
    out = ["# Каталог документации",
           "",
           "Сгенерирован `python3 tools/kb.py catalog`; не править руками и не коммитить "
           "(файл в .gitignore). Агентам удобнее `kb.py search` и `kb.py list`.",
           ""]
    for t in TYPES:
        group = [d for d in docs if d.type == t]
        if not group:
            continue
        out += [f"## {t} ({len(group)})", "", "| Дата | Документ | Тикеты | Сервисы | Кратко |",
                "| --- | --- | --- | --- | --- |"]
        for d in group:
            summary = d.summary.replace("|", "\\|")[:160]
            out.append(f"| {d.date} | [{d.title.replace('|', '/')[:90]}]({d.rel}) | {', '.join(d.tickets[:3])} | "
                       f"{', '.join(d.services)} | {summary} |")
        out.append("")
    (ROOT / "catalog.md").write_text("\n".join(out), encoding="utf-8")
    print(f"catalog.md: {len(docs)} документов")
    return 0


def cmd_lint(args) -> int:
    glossary = Glossary()
    docs = load_docs([ROOT], True)
    errors: list[str] = []
    warnings: list[str] = []
    legacy = 0
    for d in docs:
        if d.fm_broken:
            errors.append(f"{d.rel}: frontmatter без закрывающей строки ---")
        if d.has_fm:
            t = str(d.meta.get("type") or "").lower()
            if t and t not in TYPES:
                errors.append(f"{d.rel}: type={t!r}, допустимо: {', '.join(TYPES)}")
            lc = str(d.meta.get("lifecycle") or "").lower()
            if lc and lc not in LIFECYCLES:
                errors.append(f"{d.rel}: lifecycle={lc!r}, допустимо: {', '.join(LIFECYCLES)}")
            for v in as_list(d.meta.get("date")):
                if not DATE_RE.fullmatch(v):
                    errors.append(f"{d.rel}: date={v!r}, нужен формат YYYY-MM-DD")
            for target in as_list(d.meta.get("superseded_by")):
                if not (ROOT / target).exists():
                    errors.append(f"{d.rel}: superseded_by указывает на несуществующий {target}")
            for v in as_list(d.meta.get("services")) + as_list(d.meta.get("service")):
                if glossary.canonical(v) not in glossary.aliases:
                    warnings.append(f"{d.rel}: сервиса {v!r} нет в navigation/glossary.md")
        if d.top in CONTENT_DIRS:
            if d.date and d.date >= CUTOVER:
                missing = [k for k in ("type", "date", "summary") if not d.meta.get(k)]
                if d.type in ("rca", "request") and not (d.meta.get("tickets") or d.meta.get("ticket")):
                    missing.append("tickets")
                if missing:
                    errors.append(f"{d.rel}: документ с {CUTOVER} без полей frontmatter: {', '.join(missing)}")
            elif not d.has_fm:
                legacy += 1
        for m in MD_LINK_RE.finditer("\n".join(d.lines)):
            target = (d.path.parent / m.group(1)).resolve()
            if not target.exists():
                warnings.append(f"{d.rel}: битая ссылка {m.group(1)}")

    nav_files = [ROOT / "documentation-navigation-map.md", ROOT / "AGENTS.md"] + sorted((ROOT / "navigation").glob("*.md"))
    broken: list[str] = []
    for f in nav_files:
        if not f.exists():
            continue
        for m in NAV_PATH_RE.finditer(f.read_text(encoding="utf-8", errors="ignore")):
            rel = m.group(1)
            if "*" in rel or "..." in rel or rel in broken:
                continue
            if not (ROOT / rel).exists():
                broken.append(rel)
    errors += [f"навигация ссылается на несуществующий {b}" for b in broken]

    # Папка tasks/ только с сырыми данными видна поиску, лишь если на неё ссылается какой-то документ.
    corpus = "\n".join("\n".join(d.lines) for d in docs)
    tasks_without_md = []
    tdir = ROOT / "tasks"
    if tdir.is_dir():
        for entry in sorted(tdir.iterdir()):
            if entry.is_dir() and not any(entry.rglob("*.md")) and f"tasks/{entry.name}" not in corpus:
                tasks_without_md.append(f"tasks/{entry.name}")
    warnings += [f"{t}: только сырые данные, и ни один документ на них не ссылается" for t in tasks_without_md]

    ok = not errors and (not args.strict or not warnings)
    if args.json:
        print(json.dumps({
            "ok": ok, "errors": errors, "warnings": warnings,
            "stats": {"docs": len(docs), "with_frontmatter": sum(d.has_fm for d in docs),
                      "legacy_without_frontmatter": legacy},
            # совместимость со старым check_navigation.py
            "orphan_files": [], "orphan_task_folders": [], "broken_links": broken,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"Документов: {len(docs)}, с frontmatter: {sum(d.has_fm for d in docs)}, "
              f"старых без frontmatter: {legacy} (допустимо, метаданные выводятся).")
        for e in errors:
            print(f"ОШИБКА  {e}")
        for w in warnings:
            print(f"warn    {w}")
        print("OK" if ok else "ЕСТЬ ОШИБКИ")
    return 0 if ok else 1


VAULT = ROOT  # заметки Obsidian живут в этом же репозитории


def cmd_hook(args) -> int:
    """UserPromptSubmit-хук Claude Code и Codex: по тикетам из запроса — что уже есть в базе.

    Читает JSON с полем `prompt` из stdin, печатает hookSpecificOutput.additionalContext.
    Молчит, если тикетов нет или ничего не найдено; никогда не падает, чтобы не мешать запросу.
    """
    try:
        payload = json.load(sys.stdin)
        keys = list(dict.fromkeys(m.group(0).upper() for m in TICKET_RE.finditer(str(payload.get("prompt", "")))))[:3]
        if not keys:
            return 0
        roots = [ROOT]
        docs = load_docs(roots, False)
        lines = []
        for key in keys:
            hits = sorted((d for d in docs if key in d.tickets and d.top != "tickets"),
                          key=lambda d: d.date or "", reverse=True)
            hub = VAULT / "tickets" / f"{key}.md"
            if not hits and not hub.exists():
                continue
            lines.append(f"{key}: в базе знаний уже есть ({len(hits)} док.):")
            if hub.exists():
                lines.append(f"- хаб: tickets/{key}.md")
            for d in hits[:3]:
                lines.append(f"- {d.date or '----------'} {d.type}/{d.lifecycle}: {d.rel} — {d.title[:90]}")
        if lines:
            lines.append(f"Подробнее: kb_search или python3 {Path(__file__).resolve()} search \"<KEY>\"; "
                         "читать только выданные разделы.")
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                     "additionalContext": "\n".join(lines)}}, ensure_ascii=False))
    except Exception:  # noqa: BLE001 — хук не должен ломать отправку запроса
        pass
    return 0


def cmd_eval(args) -> int:
    """Прогон золотых вопросов: место ожидаемого документа и размер выдачи."""
    rows = [l.split("\t") for l in Path(args.file).read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#")]
    roots = [ROOT]
    docs = load_docs(roots, False)
    ranks, sizes = [], []
    for query, expected in rows:
        res = run_search(docs, query, args.limit)
        rank = next((i for i, r in enumerate(res, 1) if re.search(expected.strip(), r["path"], re.I)), None)
        ranks.append(rank)
        sizes.append(len(json.dumps(res, ensure_ascii=False)))
        print(f"{'—' if rank is None else rank:>2}  {query}")
    n = len(rows)
    hit1 = sum(r == 1 for r in ranks) / n
    hit3 = sum(r is not None and r <= 3 for r in ranks) / n
    print(f"\nвопросов {n}: hit@1 {hit1:.0%}, hit@3 {hit3:.0%}, hit@{args.limit} "
          f"{sum(r is not None for r in ranks) / n:.0%}; выдача в среднем {sum(sizes) // n} символов")
    return 0 if hit3 >= args.min_hit3 else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=f"Поиск, каталог и проверка {ROOT}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def filters(p):
        p.add_argument("--type", action="append", choices=TYPES)
        p.add_argument("--lifecycle", action="append", choices=LIFECYCLES)
        p.add_argument("--service", action="append", help="каноническое имя из navigation/glossary.md")
        p.add_argument("--ticket", action="append")
        p.add_argument("--since", help="YYYY-MM-DD")
        p.add_argument("--path", action="append", help="regex по пути")
        p.add_argument("--root", action="append", help="доп. каталог с .md")
        p.add_argument("--all", action="store_true", help="включить navigation/ и корневые файлы")
        p.add_argument("--json", action="store_true")

    p = sub.add_parser("search", help="найти разделы документов")
    p.add_argument("query", nargs="+")
    p.add_argument("-n", "--limit", type=int, default=6)
    filters(p)
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("list", help="каталог документов, новые сверху")
    p.add_argument("-n", "--limit", type=int, default=40, help="0 — без ограничения")
    p.add_argument("--stats", action="store_true")
    filters(p)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("meta", help="метаданные документа")
    p.add_argument("paths", nargs="+")
    p.add_argument("--root", action="append")
    p.set_defaults(func=cmd_meta)

    p = sub.add_parser("catalog", help="записать catalog.md")
    p.set_defaults(func=cmd_catalog)

    p = sub.add_parser("eval", help="прогон золотых вопросов (navigation/golden-questions.tsv)")
    p.add_argument("file", nargs="?", default=str(ROOT / "navigation" / "golden-questions.tsv"))
    p.add_argument("-n", "--limit", type=int, default=6)
    p.add_argument("--min-hit3", type=float, default=0.8, help="ниже — exit 1")
    p.set_defaults(func=cmd_eval)

    p = sub.add_parser("hook", help="UserPromptSubmit-хук: контекст по тикетам из запроса (stdin JSON)")
    p.set_defaults(func=cmd_hook)

    p = sub.add_parser("lint", help="проверка frontmatter и ссылок")
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true", help="предупреждения тоже считаются ошибками")
    p.set_defaults(func=cmd_lint)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
