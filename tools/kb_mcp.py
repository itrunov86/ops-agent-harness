#!/usr/bin/env python3
"""
kb_mcp.py — MCP-сервер (stdio) с поиском по базе знаний: инструменты `kb_search` и `kb_list`.

Обёртка над kb.py: агент получает те же разделы и диапазоны строк, что и из CLI, но без shell.
Подключение (имя сервера `kb`, инструменты видны как mcp__kb__kb_search):

    claude mcp add --scope user kb -- python3 -I <harness>/tools/kb_mcp.py
    # ~/.codex/config.toml
    [mcp_servers.kb]
    command = "python3"
    args = ["-I", "<harness>/tools/kb_mcp.py"]

Только чтение. Только стандартная библиотека. Протокол — JSON-RPC 2.0 построчно через stdin/stdout.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

KB = Path(__file__).resolve().parent / "kb.py"
PROTOCOL = "2025-06-18"

FILTERS = {
    "service": {"type": "array", "items": {"type": "string"}, "description": "канонические имена из глоссария"},
    "ticket": {"type": "array", "items": {"type": "string"}, "description": "ключи задач"},
    "type": {"type": "array", "items": {"type": "string"}, "description": "rca, request, runbook, plan, decision, …"},
    "lifecycle": {"type": "array", "items": {"type": "string"}, "description": "current, historical, superseded, draft"},
    "since": {"type": "string", "description": "YYYY-MM-DD"},
}
TOOLS = [
    {"name": "kb_search",
     "description": "Поиск по базе знаний: до limit документов с подходящим разделом и диапазоном строк. "
                    "Читай только выданные строки (sed -n 'A,Bp' <path>). Запрос — сервис, симптом, алерт, ключ задачи.",
     "inputSchema": {"type": "object", "required": ["query"],
                     "properties": {"query": {"type": "string"}, "limit": {"type": "integer", "default": 6}, **FILTERS}}},
    {"name": "kb_list",
     "description": "Каталог документов базы знаний, новые сверху, с фильтрами по сервису, задаче, типу и дате.",
     "inputSchema": {"type": "object",
                     "properties": {"limit": {"type": "integer", "default": 40}, "stats": {"type": "boolean"}, **FILTERS}}},
]


def run_kb(name: str, args: dict) -> str:
    cmd = [sys.executable, "-I", str(KB), "search" if name == "kb_search" else "list"]
    if name == "kb_search":
        cmd += [str(args.get("query", ""))]
    cmd += ["--limit", str(int(args.get("limit") or (6 if name == "kb_search" else 40)))]
    for key in ("service", "ticket", "type", "lifecycle"):
        for value in args.get(key) or []:
            cmd += [f"--{key}", str(value)]
    if args.get("since"):
        cmd += ["--since", str(args["since"])]
    if name == "kb_list" and args.get("stats"):
        cmd += ["--stats"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return (res.stdout or res.stderr).strip() or "ничего не найдено"


def handle(msg: dict) -> dict | None:
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:                                   # уведомления (initialized, cancelled) ответа не ждут
        return None
    if method == "initialize":
        result = {"protocolVersion": msg.get("params", {}).get("protocolVersion", PROTOCOL),
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "agent-harness-kb", "version": "1.0"}}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = msg.get("params", {})
        if params.get("name") not in {t["name"] for t in TOOLS}:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "unknown tool"}}
        try:
            text, err = run_kb(params["name"], params.get("arguments") or {}), False
        except Exception as e:  # noqa: BLE001 — ошибку отдаём агенту текстом
            text, err = f"kb.py: {e}", True
        result = {"content": [{"type": "text", "text": text}], "isError": err}
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> int:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            reply = handle(json.loads(line))
        except ValueError:
            reply = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        if reply is not None:
            sys.stdout.write(json.dumps(reply, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
