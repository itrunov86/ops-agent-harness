#!/usr/bin/env python3
"""
agent_session.py — журнал длинной задачи и хуки, которые не дают агенту терять контекст (agent-harness).

    python3 tools/agent_session.py start OPS-1234 [slug]   # завести/найти tasks/<KEY>-<slug>/handoff.md
    python3 tools/agent_session.py hook                    # обработчик хуков Claude Code и Codex (stdin JSON)

Хук делает три вещи:
- SessionStart (compact/resume/clear/startup): подставляет журнал активной задачи в контекст;
- UserPromptSubmit/PostToolUse: при заполнении контекста на 50% и 75% (один раз на порог) просит обновить журнал;
- PostCompact (Claude): сохраняет резюме сжатия в ~/.agents/state/compact/;
- PreToolUse/PostToolUse/Stop: автокоммит базы знаний — файлы, изменённые чатом (любым инструментом), коммитятся
  в конце ответа, только свои; файл, который за последний час правил другой чат, или файл с похожим на секрет
  значением не коммитится, пользователь получает предупреждение. Репозитории с кодом не трогаются.

Активная задача: ключ Jira в имени git-ветки рабочей папки, иначе журнал, к которому привязан чат, иначе папка,
зарегистрированная командой `start` (только если в её пути есть ключ). Чат привязывается, когда пользователь
начинает сообщение с ключа или пишет «работаем по OPS-…» / «working on OPS-…», и когда агент заводит журнал
(`start`) или пишет в него.
Хук никогда не падает и ничего не блокирует. Только стандартная библиотека.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_config import CONFIG  # noqa: E402

ROOT = CONFIG.kb_root
STATE = CONFIG.state_dir
ACTIVE = STATE / "active-tasks.json"
KEY_RE = CONFIG.ticket_re()
SESSIONS = STATE / "session-tasks.json"
_KEY = f"({CONFIG.ticket_group})"
# Явное «работаем над задачей»: ключ в начале сообщения или фраза перед ключом (русская или английская).
PROMPT_KEY_RE = re.compile(
    rf"^\W*{_KEY}\b"
    rf"|(?:работаем|продолжа\w*|переключ\w*)\s+(?:по|на|с)?\s*(?:задач\w*\s+)?{_KEY}\b"
    rf"|\b(?:working\s+on|work\s+on|continu\w*(?:\s+with)?|resum\w*|switch\w*\s+to)\s+(?:the\s+)?(?:task\s+|ticket\s+)?{_KEY}\b",
    re.I)
START_RE = re.compile(rf"(?:^|[;&|\n(])\s*(?:cd\s+\S+\s*&&\s*)?(?:python3?\s+(?:-I\s+)?)?\S*agent_session\.py\s+start\s+{_KEY}",
                      re.I)
HANDOFF_PATH_RE = re.compile(rf"tasks/{_KEY}[^/\"\s]*/handoff\.md", re.I)
WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "apply_patch"}
THRESHOLDS = [int(x) for x in os.environ.get("AGENT_HANDOFF_THRESHOLDS", ",".join(map(str, CONFIG.handoff_thresholds))).split(",")]
MAX_INJECT = 8000

TEMPLATE = """---
type: task
lifecycle: draft
date: {today}
tickets: [{key}]
services: []
status: "в работе"
summary: "{key}: <цель в одну фразу>"
---

# {key}: журнал задачи

Журнал для продолжения после сжатия контекста или в новой сессии. Ведётся по скиллу `handoff`: разделы «Сейчас»
перезаписываются, «Решения», «Сделано», «Грабли» и «Уроки» дополняются.

## Цель и критерий готовности

## Сейчас

- Где остановились:
- Следующий шаг (одно действие):
- Ждём от пользователя:

## Решения

## Сделано

## Грабли

## Уроки
"""


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def _branch_key(cwd: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", cwd, "branch", "--show-current"], capture_output=True,
                             text=True, timeout=2).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = KEY_RE.search(out)
    return m.group(0).upper() if m else None


def _handoff_for_key(key: str) -> Path | None:
    hits = sorted((ROOT / "tasks").glob(f"{key}*/handoff.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    return hits[0] if hits else None


def find_active(cwd: str, sid: str = "") -> Path | None:
    """Журнал задачи: ключ в git-ветке папки, иначе привязка чата, иначе привязка папки."""
    key = _branch_key(cwd) if cwd else None
    if key and (p := _handoff_for_key(key)):
        return p
    for registry, name in ((SESSIONS, sid), (ACTIVE, str(Path(cwd).resolve()) if cwd else "")):
        entry = _load(registry, {}).get(name) if name else None
        if entry and Path(entry["path"]).exists():
            return Path(entry["path"])
    return None


def bind_session(sid: str, path: Path) -> bool:
    """Привязать чат к журналу; True, если привязка изменилась. Привязки старше 30 дней выбрасываются."""
    sessions = _load(SESSIONS, {})
    if not sid or sessions.get(sid, {}).get("path") == str(path):
        return False
    cutoff = time.time() - 30 * 86400
    sessions = {k: v for k, v in sessions.items() if v.get("updated", 0) > cutoff}
    m = KEY_RE.search(path.parent.name)
    sessions[sid] = {"path": str(path), "key": m.group(0).upper() if m else "", "updated": int(time.time())}
    _save(SESSIONS, sessions)
    return True


def _prompt_journal(prompt: str) -> Path | None:
    """Журнал задачи, которую пользователь явно назвал: ключ в начале сообщения или «работаем по OPS-…»."""
    m = PROMPT_KEY_RE.search(prompt)
    key = next((g for g in m.groups() if g), "") if m else ""
    return _handoff_for_key(key.upper()) if key else None


def _tool_journal(payload: dict) -> Path | None:
    """Журнал, который агент только что завёл командой start или записал в tasks/<KEY>-*/handoff.md."""
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    if isinstance(command, list):                       # Codex: ["bash", "-lc", "<команда>"]
        command = command[-1] if command else ""
    if m := START_RE.search(str(command)):              # только запуск, а не упоминание внутри echo/JSON
        return _handoff_for_key(m.group(1).upper())
    text = json.dumps(tool_input, ensure_ascii=False)
    if payload.get("tool_name") in WRITE_TOOLS and (m := HANDOFF_PATH_RE.search(text)):
        return _handoff_for_key(m.group(1).upper())
    return None


def _inject(handoff: Path, lead: str) -> str:
    body = handoff.read_text(encoding="utf-8", errors="replace")
    if len(body) > MAX_INJECT:
        body = body[:MAX_INJECT] + "\n… (обрезано, полный журнал — в файле)"
    stamp = datetime.fromtimestamp(handoff.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    return (f"{lead}Журнал активной задачи {handoff} (обновлён {stamp}). Продолжай с «Следующий шаг», "
            f"сначала сверь его с git status и текущим состоянием; журнал веди по скиллу handoff.\n\n{body}")


def cmd_start(key: str, slug: str | None) -> int:
    key = key.upper()
    path = _handoff_for_key(key)
    if path is None:
        folder = next(iter(sorted((ROOT / "tasks").glob(f"{key}*/"))), None)
        if folder is None:
            folder = ROOT / "tasks" / (f"{key}-{slug}" if slug else key)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / "handoff.md"
        path.write_text(TEMPLATE.format(today=date.today().isoformat(), key=key), encoding="utf-8")
    # Папку привязываем, только если она своя у задачи (ключ в пути): общая папка чатов подсунула бы
    # журнал всем параллельным чатам. Сам чат привязывает хук PostToolUse, увидев эту команду.
    cwd = Path.cwd().resolve()
    if key.lower() in str(cwd).lower():
        active = _load(ACTIVE, {})
        active[str(cwd)] = {"path": str(path), "key": key, "updated": int(time.time())}
        _save(ACTIVE, active)
    print(path)
    return 0


# --------------------------------------------------------------------------------------------
# Заполненность контекста
# --------------------------------------------------------------------------------------------

def _tail_lines(path: Path, size: int = 400_000) -> list[str]:
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - size))
        return fh.read().decode("utf-8", errors="ignore").splitlines()


def context_usage(transcript: str, model: str = "") -> tuple[int, int] | None:
    """(занято токенов, размер окна) по последнему ответу модели в транскрипте Claude Code или Codex."""
    try:
        lines = _tail_lines(Path(transcript))
    except OSError:
        return None
    for line in reversed(lines):
        if '"token_count"' in line:                                  # Codex
            try:
                info = json.loads(line)["payload"]["info"]
                return int(info["last_token_usage"]["input_tokens"]), int(info["model_context_window"])
            except (ValueError, KeyError, TypeError):
                continue
        if '"usage"' in line and '"assistant"' in line:              # Claude Code
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("isSidechain"):
                continue
            msg = o.get("message") or {}
            u = msg.get("usage") or {}
            used = sum(int(u.get(k) or 0) for k in
                       ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            if not used:
                continue
            name = f"{msg.get('model', '')} {model}"
            env = os.environ.get("AGENT_CONTEXT_WINDOW")
            window = int(env) if env else (1_000_000 if re.search(r"opus-5|fable|\[1m\]", name) or used > 200_000
                                            else 200_000)
            return used, window
    return None


def _pressure(payload: dict) -> str | None:
    usage = context_usage(payload.get("transcript_path") or "", payload.get("model") or "")
    if not usage:
        return None
    used, window = usage
    pct = int(100 * used / window)
    sid = payload.get("session_id") or "unknown"
    state_file = STATE / "pressure" / f"{sid}.json"
    fired = set(_load(state_file, []))
    fired = {t for t in fired if pct >= t - 10}        # после сжатия пороги снова взводятся
    due = [t for t in THRESHOLDS if pct >= t and t not in fired]
    _save(state_file, sorted(fired | set(due)))
    if not due:
        return None
    level = max(due)
    handoff = find_active(payload.get("cwd") or "", sid)
    where = (f"обнови журнал задачи {handoff}" if handoff else
             f"заведи журнал: python3 {Path(__file__).resolve()} start <KEY> <slug>, затем заполни его")
    text = f"Контекст заполнен на {pct}% ({used // 1000}K из {window // 1000}K). По скиллу handoff {where}."
    if level >= max(THRESHOLDS):
        text += (" Заверши текущий шаг, обнови журнал и предложи пользователю /compact с пометкой, что сохранить:"
                 " после сжатия журнал подставится сам.")
    return text


# --------------------------------------------------------------------------------------------
# Хук
# --------------------------------------------------------------------------------------------

# --------------------------------------------------------------------------------------------
# Автокоммит базы знаний: файлы, изменённые чатом, коммитятся в конце его ответа
# --------------------------------------------------------------------------------------------

AUTO = STATE / "autocommit"
OWNERS = AUTO / "owners.json"            # путь → {session_id: время последней правки}
OWNER_TTL = 3600                         # чат, не правивший файл час, не мешает коммиту другого
GIT_BUSY = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply")
SECRET_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY|\beyJ[\w-]{20,}\.[\w-]{20,}|\bhvs\.[\w-]{20,}|\bglpat-[\w-]{20}"
                       r"|\bAKIA[0-9A-Z]{16}\b|\bAQVN[\w-]{30,}|\bt1\.[\w-]{40,}")


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=10)


def _dirty() -> dict[str, list | None]:
    """Незакоммиченные файлы базы: путь → [mtime_ns, size], удалённые → None."""
    entries = _git("status", "--porcelain", "-z", "--untracked-files=all").stdout.split("\0")
    res: dict[str, list | None] = {}
    i = 0
    while i < len(entries):
        entry = entries[i]
        i += 1
        if len(entry) < 4:
            continue
        if "R" in entry[:2] or "C" in entry[:2]:
            i += 1                                       # за переименованием идёт старое имя
        path = entry[3:]
        try:
            st = (ROOT / path).stat()
            res[path] = [st.st_mtime_ns, st.st_size]
        except OSError:
            res[path] = None
    return res


def _track(event: str, payload: dict, sid: str) -> None:
    """PreToolUse — снимок; PostToolUse — какие файлы базы поменял этот вызов (любой инструмент, и bash тоже)."""
    if not CONFIG.autocommit or not (ROOT / ".git").exists():
        return
    pre_file = AUTO / f"{sid}.pre.json"
    if event == "PreToolUse":
        _save(pre_file, _dirty())
        return
    now = _dirty()
    pre = _load(pre_file, None)
    changed = {p for p, sig in now.items() if pre.get(p, "absent") != sig} if pre is not None else set()
    target = (payload.get("tool_input") or {}).get("file_path") if isinstance(payload.get("tool_input"), dict) else None
    if target:
        try:
            rel = str(Path(target).resolve().relative_to(ROOT))
            if rel in now:
                changed.add(rel)
        except ValueError:
            pass
    if not changed:
        return
    touched_file = AUTO / f"{sid}.json"
    _save(touched_file, sorted(set(_load(touched_file, [])) | changed))
    owners = _load(OWNERS, {})
    for p in changed:
        owners.setdefault(p, {})[sid] = int(time.time())
    _save(OWNERS, owners)


def _commit_key(sid: str, paths: list[str]) -> str:
    if key := _load(SESSIONS, {}).get(sid, {}).get("key"):
        return key
    keys = [m.group(0).upper() for p in paths for m in KEY_RE.finditer(p)]
    return max(set(keys), key=keys.count) if keys else ""


def _autocommit(sid: str) -> str | None:
    """Stop: закоммитить файлы этого чата. Чужие (другой чат правил их за последний час) и с секретами — пропустить."""
    touched_file = AUTO / f"{sid}.json"
    touched = set(_load(touched_file, []))
    if not touched or not CONFIG.autocommit:
        return None
    if any((ROOT / ".git" / name).exists() for name in GIT_BUSY):
        return f"Автокоммит {ROOT} отложен: в репозитории идёт merge/rebase."
    now, owners, cutoff = _dirty(), _load(OWNERS, {}), time.time() - OWNER_TTL
    paths, shared, secret = [], [], []
    for p in sorted(touched & set(now)):                 # уже закоммиченное или откаченное выпадает само
        if any(s != sid and ts > cutoff for s, ts in owners.get(p, {}).items()):
            shared.append(p)
        elif now[p] is not None and SECRET_RE.search((ROOT / p).read_text(encoding="utf-8", errors="ignore")):
            secret.append(p)
        else:
            paths.append(p)
    notes = []
    if paths:
        key = _commit_key(sid, paths)
        names = ", ".join(Path(p).stem[:50] for p in paths[:3]) + (f" и ещё {len(paths) - 3}" if len(paths) > 3 else "")
        msg = f"{key} docs: {names}" if key else f"docs: {names}"
        res = _git("add", "-A", "--", *paths)
        if res.returncode == 0:
            res = _git("commit", "-q", "--only", "-m", msg, "--", *paths)
        if res.returncode != 0:
            notes.append(f"Автокоммит {ROOT} не удался: {(res.stderr or res.stdout).strip()[:300]}")
            paths = []
    if shared:
        notes.append("Не закоммичены, их правит и другой чат: " + ", ".join(shared)
                     + ". Закоммить вручную, когда тот чат закончит.")
    if secret:
        notes.append("Не закоммичены, похоже на секрет внутри: " + ", ".join(secret) + ". Убери значение из файла.")
    keep = (touched & set(now)) - set(paths)
    _save(touched_file, sorted(keep))
    for p in touched - keep:                             # закоммичено хуком, агентом или откачено
        owners.get(p, {}).pop(sid, None)
    _save(OWNERS, {p: o for p, o in owners.items() if o})
    return "\n".join(notes) or None


def _emit(event: str, text: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}},
                     ensure_ascii=False))


def cmd_hook() -> int:
    try:
        payload = json.load(sys.stdin)
        event = payload.get("hook_event_name", "")
        cwd = payload.get("cwd") or ""
        sid = payload.get("session_id") or ""
        if event == "SessionStart":
            source = payload.get("source", "")
            if source == "compact":
                _save(STATE / "pressure" / f"{sid or 'unknown'}.json", [])
            handoff = find_active(cwd, sid)
            if not handoff:
                return 0
            age_days = (time.time() - handoff.stat().st_mtime) / 86400
            if source == "startup" and age_days > 3:
                return 0
            _emit("SessionStart", _inject(handoff, ""))
        elif event == "PreToolUse":
            _track(event, payload, sid)
        elif event == "Stop":
            if note := _autocommit(sid):
                print(json.dumps({"systemMessage": note}, ensure_ascii=False))
        elif event in ("UserPromptSubmit", "PostToolUse"):
            if event == "PostToolUse":
                try:
                    _track(event, payload, sid)
                except Exception:  # noqa: BLE001 — сбой учёта не должен глушить сигналы о контексте
                    pass
            parts = []
            journal = (_prompt_journal(str(payload.get("prompt", ""))) if event == "UserPromptSubmit"
                       else _tool_journal(payload))
            if journal and bind_session(sid, journal):
                parts.append(_inject(journal, "Чат привязан к задаче. ") if event == "UserPromptSubmit"
                             else f"Чат привязан к журналу {journal}: хуки и сжатие контекста дальше ведут его.")
            if text := _pressure(payload):
                parts.append(text)
            if parts:
                _emit(event, "\n\n".join(parts))
        elif event == "PostCompact" and payload.get("compact_summary"):
            ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            out = STATE / "compact" / f"{ts}-{payload.get('session_id', 'unknown')}.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(f"cwd: {cwd}\n\n{payload['compact_summary']}\n", encoding="utf-8")
    except Exception:  # noqa: BLE001 — хук не должен мешать работе
        pass
    return 0


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "start":
        return cmd_start(argv[1], argv[2] if len(argv) > 2 else None)
    if argv[:1] == ["hook"]:
        return cmd_hook()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
