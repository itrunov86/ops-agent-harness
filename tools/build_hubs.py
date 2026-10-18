#!/usr/bin/env python3
"""Пересобирает списки заметок в хабах базы знаний (agent-harness).

Хаб — заметка в services/ или tickets/ с frontmatter `hub_match: <regex>`. Скрипт находит заметки,
где regex встречается в заголовке, имени файла, тегах, полях `services`/`tickets` или ссылках [[…]],
и переписывает блок между маркерами
<!-- hub:notes --> и <!-- /hub:notes --> (новые сверху). Остальной текст хаба не трогает.

    python3 tools/build_hubs.py               # база — paths.kb_root из конфига
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_config import CONFIG  # noqa: E402

ROOT = CONFIG.kb_root
START, END = "<!-- hub:notes -->", "<!-- /hub:notes -->"
LIMIT = 30


def title_of(text: str, stem: str) -> str:
    m = re.search(r"(?m)^#\s+(.+)$", text)
    return m.group(1).strip() if m else stem


def main() -> int:
    skip = {"navigation", "exports", "tools"}
    notes = {p: p.read_text(encoding="utf-8") for p in ROOT.rglob("*.md")
             if not any(x.startswith(".") for x in p.relative_to(ROOT).parts)
             and p.relative_to(ROOT).parts[0] not in skip and len(p.relative_to(ROOT).parts) > 1}
    hubs = [p for p, t in notes.items() if re.search(r"(?m)^hub_match:", t)]
    stems = [p.stem for p in notes]
    # Неуникальное имя (все журналы — handoff.md) Obsidian не разрешит: ссылаемся путём от корня.
    target = {p: (p.stem if stems.count(p.stem) == 1 else str(p.relative_to(ROOT).with_suffix(""))) for p in notes}
    for hub in hubs:
        text = notes[hub]
        pattern = re.search(r"(?m)^hub_match:\s*['\"]?(.+?)['\"]?\s*$", text).group(1)
        rx = re.compile(pattern, re.I)
        found = []
        for p, t in notes.items():
            if p == hub or p in hubs:
                continue
            meta = re.findall(r"(?m)^(?:tags|services|tickets):.*$", t.split("\n---", 1)[0] if t.startswith("---") else "")
            hay = " ".join([title_of(t, p.stem), p.stem, *meta, " ".join(re.findall(r"\[\[([^\]]+)\]\]", t))])
            if rx.search(hay):
                date = re.search(r"(?m)^date:\s*(\S+)", t) or re.search(r"(20\d\d-\d\d-\d\d)", p.name)
                found.append(((date.group(1) if date else ""), target[p], title_of(t, p.stem)))
        found.sort(reverse=True)
        lines = [f"- {d} [[{stem}|{title}]]" for d, stem, title in found[:LIMIT]]
        if len(found) > LIMIT:
            lines.append(f"- … ещё {len(found) - LIMIT}: `python3 {Path(__file__).resolve().parent}/kb.py search \"<тема>\"`")
        block = f"{START}\n" + ("\n".join(lines) or "- пока нет") + f"\n{END}"
        new = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
        if new != text:
            hub.write_text(new, encoding="utf-8")
        print(f"{hub.relative_to(ROOT)}: {len(found)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
