#!/usr/bin/env python3
"""
agent_bench.py — A/B-прогон агентов на реальных задачах (agent-harness).

    python3 tools/agent_bench.py run [--agent claude|codex] [--ids 1,2] [--variants A,B] [--jobs 3] [--out DIR]
    python3 tools/agent_bench.py report DIR

A — основной агент ищет сам (Agent запрещён); B — поиск обязательно поручается субагенту kb-scout.
Обе сессии только читают: база знаний и код (paths.kb_root, paths.code_root), живые системы запрещены.
Вопросы — navigation/agent-bench-tasks.json в базе: [{"id": 1, "kind": "…", "q": "…", "facts": ["regex", …]}].
Метрики: доля ключевых фактов, пик контекста основного агента, стоимость, время, шаги.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness_config import CONFIG  # noqa: E402

ROOT = CONFIG.kb_root
KB_TOOL = Path(__file__).resolve().parent / "kb.py"
READ_DIRS = [ROOT] + ([CONFIG.code_root] if CONFIG.code_root else [])
TASKS = ROOT / "navigation" / "agent-bench-tasks.json"
HOME = Path.home()
ALLOWED = ["Read", "Grep", "Glob", "Bash(rg:*)", "Bash(sed -n:*)", "Bash(ls:*)", "Bash(git log:*)",
           f"Bash(python3 -I {KB_TOOL}:*)", f"Bash(python3 {KB_TOOL}:*)",
           f"mcp__{CONFIG.mcp_hub}__kb_search", f"mcp__{CONFIG.mcp_hub}__kb_list"]
BASE_PROMPT = ("{q}\n\nОтветь по существу: причина и ключевые факты, пути к источникам. Ищи в "
               + " и ".join(str(d) for d in READ_DIRS)
               + ". Живые системы (кластеры, облако, трекер, логи, метрики) не запрашивай.")
DELEGATE = ("Весь поиск и чтение файлов поручи субагенту kb-scout через инструмент Agent (subagent_type kb-scout); "
            "сам файлы не читай и не ищи. По его выжимке сформулируй ответ.")


def peak_context(cwd: Path, session_id: str) -> int:
    proj = HOME / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    f = proj / f"{session_id}.jsonl"
    peak = 0
    if f.exists():
        for line in f.open(encoding="utf-8", errors="ignore"):
            if '"usage"' not in line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            if o.get("isSidechain"):
                continue
            u = (o.get("message") or {}).get("usage") or {}
            peak = max(peak, sum(int(u.get(k) or 0) for k in
                                 ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")))
    return peak


def run_one(task: dict, variant: str, out: Path) -> dict:
    cwd = out / f"cwd-{task['id']}-{variant}"
    cwd.mkdir(parents=True, exist_ok=True)
    cmd = ["claude", "-p", "--output-format", "json", "--max-budget-usd", "3",
           *[a for d in READ_DIRS for a in ("--add-dir", str(d))],
           "--allowedTools", " ".join(ALLOWED + (["Agent"] if variant == "B" else []))]
    if variant == "A":
        cmd += ["--disallowedTools=Agent"]
    else:
        cmd += ["--append-system-prompt", DELEGATE]
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=cwd, input=BASE_PROMPT.format(q=task["q"]), capture_output=True, text=True,
                          timeout=1800)
    wall = time.time() - t0
    try:
        res = json.loads(proc.stdout)
    except ValueError:
        res = {"result": proc.stdout[-2000:] + proc.stderr[-2000:], "is_error": True}
    answer = res.get("result") or ""
    hits = [bool(re.search(f, answer, re.I)) for f in task["facts"]]
    row = {"id": task["id"], "kind": task["kind"], "variant": variant,
           "facts": f"{sum(hits)}/{len(hits)}", "score": round(sum(hits) / len(hits), 2),
           "missed": [f for f, h in zip(task["facts"], hits) if not h],
           "cost_usd": round(res.get("total_cost_usd") or 0, 3), "turns": res.get("num_turns"),
           "wall_s": round(wall), "peak_ctx": peak_context(cwd, res.get("session_id", "")),
           "models": sorted((res.get("modelUsage") or {}).keys()), "error": bool(res.get("is_error"))}
    (out / f"answer-{task['id']}-{variant}.md").write_text(answer, encoding="utf-8")
    with (out / "results.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"done {task['id']}{variant}: {row['facts']} ${row['cost_usd']} {row['wall_s']}s ctx={row['peak_ctx']}", flush=True)
    return row

CODEX = Path(os.environ.get("CODEX_BIN") or
             next(iter(sorted(HOME.glob(".vscode/extensions/openai.chatgpt-*/bin/macos-aarch64/codex"))), "codex"))
CODEX_NO_DELEGATE = "Не запускай субагентов: ищи и читай сам."
CODEX_DELEGATE = ("Весь поиск и чтение файлов поручи субагенту kb_scout (spawn kb_scout), дождись его ответа; сам файлы "
                  "не читай. По его выжимке сформулируй ответ.")


def codex_stats(cwd: Path, since: float) -> dict:
    """Пик контекста и токены родительского потока Codex по его rollout-файлу."""
    best = {}
    for f in sorted((HOME / ".codex" / "sessions").rglob("rollout-*.jsonl")):
        if f.stat().st_mtime < since:
            continue
        lines = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        try:
            meta = json.loads(lines[0])["payload"]
        except (ValueError, KeyError, IndexError):
            continue
        if meta.get("cwd") != str(cwd):
            continue
        sub = bool(meta.get("agent_role"))
        peak, total, model = 0, 0, ""
        for line in lines:
            if '"token_count"' in line:
                try:
                    info = json.loads(line)["payload"]["info"]
                    peak = max(peak, int(info["last_token_usage"]["input_tokens"]))
                    total = int(info["total_token_usage"]["total_tokens"])
                except (ValueError, KeyError, TypeError):
                    pass
            elif '"turn_context"' in line and (not model or sub):
                model = json.loads(line)["payload"].get("model", "")
        if sub:
            best["sub_tokens"] = best.get("sub_tokens", 0) + total
            best.setdefault("sub_models", []).append(model)
        else:
            best.update(peak_ctx=peak, parent_tokens=total, models=[model])
    best["tokens"] = best.get("parent_tokens", 0) + best.get("sub_tokens", 0)
    best["models"] = best.get("models", []) + best.get("sub_models", [])
    return best


def run_one_codex(task: dict, variant: str, out: Path) -> dict:
    cwd = out / f"cwd-{task['id']}-{variant}"
    cwd.mkdir(parents=True, exist_ok=True)
    answer_file = out / f"answer-{task['id']}-{variant}.md"
    prompt = BASE_PROMPT.format(q=task["q"]) + "\n\n" + (CODEX_DELEGATE if variant == "B" else CODEX_NO_DELEGATE)
    t0 = time.time()
    proc = subprocess.run([str(CODEX), "exec", "-s", "read-only", "--skip-git-repo-check", "-o", str(answer_file), "-"],
                          cwd=cwd, input=prompt, capture_output=True, text=True, timeout=1800)
    wall = time.time() - t0
    answer = answer_file.read_text(encoding="utf-8") if answer_file.exists() else proc.stderr[-2000:]
    hits = [bool(re.search(f, answer, re.I)) for f in task["facts"]]
    st = codex_stats(cwd, t0 - 5)
    row = {"id": task["id"], "kind": task["kind"], "variant": variant,
           "facts": f"{sum(hits)}/{len(hits)}", "score": round(sum(hits) / len(hits), 2),
           "missed": [f for f, h in zip(task["facts"], hits) if not h],
           "cost_usd": 0, "tokens": st.get("tokens", 0), "turns": None, "wall_s": round(wall),
           "peak_ctx": st.get("peak_ctx", 0), "models": st.get("models", []), "error": proc.returncode != 0}
    with (out / "results.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"done {task['id']}{variant}: {row['facts']} tok={row['tokens']} {row['wall_s']}s ctx={row['peak_ctx']}", flush=True)
    return row


def report(out: Path) -> None:
    rows = [json.loads(l) for l in (out / "results.jsonl").read_text().splitlines() if l.strip()]
    rows.sort(key=lambda r: (r["id"], r["variant"]))
    print(f"{'#':>2} {'тип':<6} {'вар':<3} {'факты':<6} {'$':>6} {'сек':>5} {'шаги':>5} {'пик контекста':>13}")
    for r in rows:
        print(f"{r['id']:>2} {r['kind']:<6} {r['variant']:<3} {r['facts']:<6} {r['cost_usd']:>6} {r['wall_s']:>5} "
              f"{str(r['turns']):>5} {r['peak_ctx']:>13}{'  ERR' if r['error'] else ''}")
    for kind in ("single", "multi", "code", None):
        for v in ("A", "B"):
            sel = [r for r in rows if r["variant"] == v and (kind is None or r["kind"] == kind)]
            if not sel:
                continue
            avg = lambda k: sum(r[k] for r in sel) / len(sel)
            tok = f", токенов {sum(r.get('tokens', 0) for r in sel)}" if any(r.get('tokens') for r in sel) else ""
            print(f"итог {kind or 'все':<6} {v}: точность {avg('score'):.0%}, ${sum(r['cost_usd'] for r in sel):.2f}{tok}, "
                  f"{avg('wall_s'):.0f} с, пик контекста {avg('peak_ctx'):.0f}")


def main(argv: list[str]) -> int:
    if argv[:1] == ["report"]:
        report(Path(argv[1]))
        return 0
    args = dict(zip(argv[1::2], argv[2::2])) if argv[:1] == ["run"] else {}
    if argv[:1] != ["run"]:
        print(__doc__)
        return 2
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    ids = {int(x) for x in args.get("--ids", "").split(",") if x}
    variants = args.get("--variants", "A,B").split(",")
    out = Path(args.get("--out") or CONFIG.reports_dir / f"agent-bench-{time.strftime('%Y%m%d-%H%M')}")
    out.mkdir(parents=True, exist_ok=True)
    jobs = [(t, v) for t in tasks if not ids or t["id"] in ids for v in variants]
    with ThreadPoolExecutor(int(args.get("--jobs", 3))) as ex:
        runner = run_one_codex if args.get("--agent") == "codex" else run_one
        list(ex.map(lambda tv: runner(*tv, out), jobs))
    report(out)
    print(f"\nответы и results.jsonl: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
