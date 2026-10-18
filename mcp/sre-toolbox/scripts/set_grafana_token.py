"""Проверить токен Grafana и записать его в config.yaml. Токен не печатается.

Полезно, если Grafana работает без постоянной базы: токен сервисного аккаунта
пропадает при каждом перезапуске пода, и его приходится выпускать заново.

    pbpaste | .venv/bin/python scripts/set_grafana_token.py

После записи переподключи sre-toolbox (/mcp → reconnect).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG = Path(os.environ.get("MCP_CONFIG") or os.environ.get("SRE_MCP_CONFIG", ROOT / "config.yaml"))


def main() -> int:
    token = sys.stdin.read().strip()
    if not token or any(ch.isspace() for ch in token):
        print("ошибка: в stdin нет токена одной строкой", file=sys.stderr)
        return 1

    cfg = yaml.safe_load(CONFIG.read_text())
    inst = cfg.get("grafana") or {}
    if not inst.get("url"):
        print("ошибка: в config.yaml нет grafana.url", file=sys.stderr)
        return 1

    verify: bool | str = inst.get("verify_ssl", True)
    if isinstance(verify, str):
        verify = str((CONFIG.parent / verify).resolve())
    with httpx.Client(verify=verify, timeout=15, trust_env=False) as client:
        r = client.get(
            f"{inst['url'].rstrip('/')}/api/search",
            params={"limit": 1},
            headers={"Authorization": f"Bearer {token}"},
        )
    if r.status_code != 200:
        print(f"ошибка: Grafana ответила {r.status_code}, токен не записан", file=sys.stderr)
        return 1

    inst.setdefault("auth", {})["bearer_token"] = token
    tmp = CONFIG.with_suffix(".yaml.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        yaml.safe_dump(cfg, f, sort_keys=False, allow_unicode=True, width=120)
    os.replace(tmp, CONFIG)
    print(f"ok: токен проверен (/api/search 200) и записан в {CONFIG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
