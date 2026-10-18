#!/usr/bin/env python3
"""Проверка, что в репозиторий не попали секреты и данные конкретного места работы.

    python3 scripts/check_sanitized.py            # все файлы под git (или все, если git ещё нет)
    python3 scripts/check_sanitized.py path ...   # только эти файлы

Общие правила — ниже: приватные ключи, токены, внутренние IP, личные домашние пути, почта не на example.*.
Личный стоп-лист — `.sanitize-denylist` в корне репозитория (в .gitignore): по одной регулярке на строку,
например название компании, внутренние домены, логины. Код выхода 1, если что-то найдено.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip"}

RULES = [
    ("приватный ключ", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY")),
    ("JWT", re.compile(r"\beyJ[\w-]{20,}\.[\w-]{20,}")),
    ("Vault token", re.compile(r"\bhvs\.[\w-]{20,}")),
    ("GitLab token", re.compile(r"\bglpat-[\w-]{20}")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("AWS key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Yandex Cloud key/token", re.compile(r"\bAQVN[\w-]{30,}|\bt1\.[\w-]{40,}|\by[0-3]_[\w-]{40,}")),
    ("Slack token", re.compile(r"\bxox[abpr]-[\w-]{10,}")),
    ("внутренний IP", re.compile(r"\b(?:10\.(?!0\.0\.0\b)\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}"
                                 r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b")),
    ("домашний путь", re.compile(r"/(?:Users|home)/(?!<|\{|\$|you\b|user\b|me\b)[A-Za-z0-9._-]+")),
    ("почта", re.compile(r"\b[\w.+-]+@(?!example\.(?:com|org|net)\b)[\w-]+\.[\w.-]+\b")),
]
# Шаблоны в коде самой проверки и примерах секретов в тестах — не утечка.
ALLOW = {
    "scripts/check_sanitized.py": {"приватный ключ", "JWT", "Vault token", "GitLab token", "GitHub token",
                                   "AWS key", "Yandex Cloud key/token", "Slack token", "внутренний IP"},
    "tools/agent_session.py": {"приватный ключ", "JWT", "Vault token", "GitLab token", "AWS key",
                               "Yandex Cloud key/token"},
    "tests/test_agent_session.py": {"Vault token"},
}


def files(args: list[str]) -> list[Path]:
    if args:
        return [Path(a).resolve() for a in args]
    try:
        out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-co", "--exclude-standard"],
                             capture_output=True, text=True, check=True).stdout.split("\n")
        return [REPO / f for f in out if f]
    except (OSError, subprocess.CalledProcessError):
        return [p for p in REPO.rglob("*") if p.is_file() and ".git" not in p.parts]


def denylist() -> list[re.Pattern]:
    path = REPO / ".sanitize-denylist"
    if not path.exists():
        return []
    return [re.compile(line.strip(), re.I) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def main(argv: list[str]) -> int:
    deny = denylist()
    found = 0
    for f in files(argv):
        if not f.is_file() or f.suffix in SKIP_SUFFIXES or f.name == ".sanitize-denylist":
            continue
        rel = f.relative_to(REPO).as_posix() if f.is_relative_to(REPO) else str(f)
        allowed = ALLOW.get(rel, set())
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(lines, 1):
            for name, rx in RULES:
                if name not in allowed and (m := rx.search(line)):
                    print(f"{rel}:{n}: {name}: {m.group(0)[:60]}")
                    found += 1
            for rx in deny:
                if m := rx.search(line):
                    print(f"{rel}:{n}: стоп-лист /{rx.pattern}/: {m.group(0)[:60]}")
                    found += 1
    # Авторы коммитов публикуются вместе с репозиторием: рабочая почта выдаёт место работы.
    try:
        authors = set(subprocess.run(["git", "-C", str(REPO), "log", "--format=%an <%ae>%n%cn <%ce>"],
                                     capture_output=True, text=True, check=True).stdout.splitlines())
    except (OSError, subprocess.CalledProcessError):
        authors = set()
    for author in sorted(a for a in authors if a):
        if any(rx.search(author) for rx in deny):
            print(f"git log: автор/коммиттер из стоп-листа: {author}")
            found += 1
    print(f"{'Найдено: ' + str(found) if found else 'Чисто'}; стоп-лист: {len(deny)} правил")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
