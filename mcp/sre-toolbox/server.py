"""
SRE MCP-сервер.

Предоставляет Claude инструменты для работы с:
  - Alertmanager           (активные алерты через /api/v2/alerts)
  - VictoriaMetrics Select (PromQL через /api/v1/query, /api/v1/query_range)
  - VictoriaLogs           (LogsQL через /select/logsql/query)
  - Obsidian vault         (локальный knowledge base с runbooks и постмортемами)
  - Audit log              (JSONL по умолчанию)

Параметры подключения берутся из config.yaml (см. config.example.yaml).
Запуск:
    python server.py
    # или с явным путём к конфигу:
    MCP_CONFIG=/etc/mcp/config.yaml python server.py

Регистрация в Claude Desktop — см. README.md.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote as _urlquote

import httpx
import yaml
from mcp.server.fastmcp import FastMCP

# Подтягиваем секреты из .env рядом с server.py (если файл есть).
# В config.yaml подстановка идёт через ${VAR} — переменная должна быть в окружении к моменту load_config.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).with_name(".env"))
except ImportError:
    pass


# =============================================================================
#  Конфигурация
# =============================================================================

CONFIG_PATH = os.environ.get(
    "MCP_CONFIG",
    str(Path(__file__).with_name("config.yaml")),
)


def _expand_env(value: Any) -> Any:
    """Рекурсивно подменяет ${VAR} в строках значениями переменных окружения."""
    if isinstance(value, str):
        def repl(m: re.Match[str]) -> str:
            return os.environ.get(m.group(1), "")
        return re.sub(r"\$\{([A-Z0-9_]+)\}", repl, value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_config(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        print(
            f"[mcp] config not found at {path}. "
            f"Скопируйте config.example.yaml -> config.yaml.",
            file=sys.stderr,
        )
        sys.exit(2)
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return _expand_env(raw)


CFG = load_config(CONFIG_PATH)

# Логи — ТОЛЬКО в stderr. В stdio-режиме stdout зарезервирован для JSON-RPC.
logging.basicConfig(
    level=getattr(logging, CFG["server"].get("log_level", "INFO")),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    stream=sys.stderr,
)
log = logging.getLogger("sre-mcp")


# =============================================================================
#  Защитный слой: redactor, allowlist, audit
# =============================================================================

class Redactor:
    """Маскировка чувствительных данных в строках перед возвратом Claude."""

    def __init__(self, cfg: dict[str, Any]) -> None:
        self.enabled = bool(cfg.get("enabled"))
        self.rules: list[tuple[str, re.Pattern[str]]] = []
        for item in cfg.get("patterns", []) or []:
            try:
                self.rules.append((item["name"], re.compile(item["regex"])))
            except re.error as e:
                log.warning("bad redaction regex %s: %s", item.get("name"), e)
        self.hits: Counter[str] = Counter()

    def scrub(self, text: str) -> str:
        if not self.enabled or not text:
            return text
        out = text
        for name, rx in self.rules:
            new_out, n = rx.subn(f"<REDACTED:{name}>", out)
            if n:
                self.hits[name] += n
            out = new_out
        return out

    def scrub_any(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.scrub(obj)
        if isinstance(obj, dict):
            return {k: self.scrub_any(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.scrub_any(v) for v in obj]
        return obj


REDACTOR = Redactor(CFG.get("redaction", {}) or {})


def audit(tool: str, args: dict[str, Any], result_size: int) -> None:
    """
    Audit-log запись. Пишет в JSONL-файл (если задан) и/или в Postgres
    (если AUDIT_DB сконфигурирован и подключён). Best-effort.
    """
    entry_jsonl = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "args": args,
        "result_bytes": result_size,
        "redaction_hits": dict(REDACTOR.hits),
    }
    path = CFG["server"].get("audit_log_path") or ""
    if path:
        try:
            path = str(Path(path).expanduser())
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry_jsonl, ensure_ascii=False) + "\n")
        except OSError as e:
            log.warning("audit write to file failed: %s", e)



def check_allowlist(promql_or_logsql: str) -> str | None:
    """Возвращает текст ошибки, если запрос нарушает allowlist; иначе None."""
    allow = CFG.get("allowlist", {}) or {}
    services = allow.get("services") or []
    namespaces = allow.get("namespaces") or []
    if not services and not namespaces:
        return None
    # Простая проверка: если allowlist задан, в запросе должен явно фигурировать
    # один из разрешённых сервисов или неймспейсов.
    text = promql_or_logsql
    if services and not any(s in text for s in services):
        return (
            f"запрос отклонён: ни один из разрешённых сервисов не упомянут. "
            f"Разрешены: {', '.join(services)}"
        )
    if namespaces and not any(n in text for n in namespaces):
        return (
            f"запрос отклонён: ни один из разрешённых namespace не упомянут. "
            f"Разрешены: {', '.join(namespaces)}"
        )
    return None


# =============================================================================
#  HTTP-клиенты
# =============================================================================

def _auth_headers(section: dict[str, Any]) -> dict[str, str]:
    h: dict[str, str] = {}
    auth = section.get("auth", {}) or {}
    token = (auth.get("bearer_token") or "").strip()
    if token:
        h["Authorization"] = f"Bearer {token}"
    extra = section.get("headers", {}) or {}
    h.update({str(k): str(v) for k, v in extra.items() if v is not None})
    return h


def _basic_auth(section: dict[str, Any]) -> tuple[str, str] | None:
    auth = section.get("auth", {}) or {}
    user = auth.get("basic_user")
    pw = auth.get("basic_password")
    if user and pw:
        return (user, pw)
    return None


def _verify_ssl(section: dict[str, Any]) -> bool | str:
    """Настраивает TLS verification для httpx-клиентов.

    Значения:
      true / отсутствует  — стандартный trust store;
      false              — отключить проверку;
      "path/to/ca.pem"   — использовать указанный CA bundle.
    Относительный путь считается от директории config.yaml.
    """
    value = section.get("verify_ssl", True)
    if isinstance(value, str):
        normalized = value.strip()
        if normalized.lower() in {"true", "yes", "1"}:
            return True
        if normalized.lower() in {"false", "no", "0"}:
            return False
        path = Path(normalized).expanduser()
        if not path.is_absolute():
            path = Path(CONFIG_PATH).expanduser().resolve().parent / path
        return str(path)
    return bool(value)


def _trim(value: Any, max_chars: int) -> Any:
    """Обрезает строку до max_chars с суффиксом о количестве отброшенных символов."""
    if isinstance(value, str) and len(value) > max_chars:
        return value[:max_chars] + f"…(+{len(value) - max_chars} chars)"
    return value


VM_CFG = CFG["victoriametrics"]
VL_CFG = CFG["victorialogs"]
AM_CFG = CFG.get("alertmanager", {}) or {}
OB_CFG = CFG.get("obsidian", {}) or {}
JIRA_CFG = CFG.get("jira", {}) or {}
CONF_CFG = CFG.get("confluence", {}) or {}
GL_CFG = CFG.get("gitlab", {}) or {}
MM_CFG = CFG.get("mattermost", {}) or {}
GR_CFG = CFG.get("grafana", {}) or {}
VM_LIMITS = VM_CFG.get("limits", {}) or {}
VL_LIMITS = VL_CFG.get("limits", {}) or {}
AM_LIMITS = AM_CFG.get("limits", {}) or {}
OB_LIMITS = OB_CFG.get("limits", {}) or {}
JIRA_LIMITS = JIRA_CFG.get("limits", {}) or {}
CONF_LIMITS = CONF_CFG.get("limits", {}) or {}
GL_LIMITS = GL_CFG.get("limits", {}) or {}
MM_LIMITS = MM_CFG.get("limits", {}) or {}
GR_LIMITS = GR_CFG.get("limits", {}) or {}


def _client_vm() -> httpx.AsyncClient:
    headers = _auth_headers(VM_CFG)
    # httpx BasicAuth writes Authorization after client headers. Prefer bearer auth
    # whenever it is configured, instead of replacing it with stale basic auth.
    auth = None if "Authorization" in headers else _basic_auth(VM_CFG)
    return httpx.AsyncClient(
        timeout=VM_CFG.get("timeout_seconds", 15),
        headers=headers,
        auth=auth,
        verify=_verify_ssl(VM_CFG),
    )


def _client_vl() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=VL_CFG.get("timeout_seconds", 30),
        headers=_auth_headers(VL_CFG),
        auth=_basic_auth(VL_CFG),
        verify=_verify_ssl(VL_CFG),
    )


def _client_am(section: dict[str, Any] | None = None) -> httpx.AsyncClient:
    """Клиент к одному Alertmanager; section — уже слитый конфиг инстанса."""
    section = section or AM_CFG
    return httpx.AsyncClient(
        timeout=section.get("timeout_seconds", 10),
        headers=_auth_headers(section),
        auth=_basic_auth(section),
        verify=_verify_ssl(section),
    )


def _client_jira() -> httpx.AsyncClient:
    headers = _auth_headers(JIRA_CFG)
    # Для POST/PUT — JSON по умолчанию.
    headers.setdefault("Accept", "application/json")
    headers.setdefault("Content-Type", "application/json")
    return httpx.AsyncClient(
        timeout=JIRA_CFG.get("timeout_seconds", 20),
        headers=headers,
        auth=_basic_auth(JIRA_CFG),
        verify=_verify_ssl(JIRA_CFG),
    )


def _client_confluence() -> httpx.AsyncClient:
    headers = _auth_headers(CONF_CFG)
    headers.setdefault("Accept", "application/json")
    headers.setdefault("Content-Type", "application/json")
    return httpx.AsyncClient(
        timeout=CONF_CFG.get("timeout_seconds", 20),
        headers=headers,
        auth=_basic_auth(CONF_CFG),
        verify=_verify_ssl(CONF_CFG),
    )


def _client_gitlab() -> httpx.AsyncClient:
    headers = _auth_headers(GL_CFG)
    headers.setdefault("Accept", "application/json")
    headers.setdefault("Content-Type", "application/json")
    return httpx.AsyncClient(
        timeout=GL_CFG.get("timeout_seconds", 20),
        headers=headers,
        auth=_basic_auth(GL_CFG),
        verify=_verify_ssl(GL_CFG),
    )


def _client_mattermost() -> httpx.AsyncClient:
    headers = _auth_headers(MM_CFG)
    headers.setdefault("Accept", "application/json")
    headers.setdefault("Content-Type", "application/json")
    return httpx.AsyncClient(
        timeout=MM_CFG.get("timeout_seconds", 20),
        headers=headers,
        auth=_basic_auth(MM_CFG),
        verify=_verify_ssl(MM_CFG),
    )


def _client_grafana() -> httpx.AsyncClient:
    cfg = GR_CFG
    headers = _auth_headers(cfg)
    # Grafana service-account tokens are organization-scoped. Keep
    # organization selection in server-side config; it is never a tool arg.
    organization_id = cfg.get("organization_id") or cfg.get("org_id")
    if organization_id not in (None, ""):
        headers.setdefault("X-Grafana-Org-Id", str(organization_id))
    headers.setdefault("Accept", "application/json")
    headers.setdefault("Content-Type", "application/json")
    return httpx.AsyncClient(
        timeout=cfg.get("timeout_seconds", 20),
        headers=headers,
        auth=_basic_auth(cfg),
        verify=_verify_ssl(cfg),
    )


# =============================================================================
#  MCP-сервер
# =============================================================================

mcp = FastMCP(CFG["server"].get("name", "sre-toolbox"))

import tools.jira as _tools_jira
_tools_jira.register(mcp, JIRA_CFG, _client_jira, REDACTOR, audit)

import tools.confluence as _tools_confluence
_tools_confluence.register(mcp, CONF_CFG, _client_confluence, REDACTOR, audit)

import tools.gitlab as _tools_gitlab
_tools_gitlab.register(mcp, GL_CFG, _client_gitlab, REDACTOR, audit)

import tools.mattermost as _tools_mattermost
_tools_mattermost.register(mcp, MM_CFG, _client_mattermost, REDACTOR, audit)

import tools.grafana as _tools_grafana
_tools_grafana.register(mcp, GR_CFG, _client_grafana, REDACTOR, audit)

import tools.alertmanager as _tools_alertmanager
_tools_alertmanager.register(mcp, AM_CFG, _client_am, REDACTOR, audit)

import tools.victoria_metrics as _tools_vm
_tools_vm.register(
    mcp,
    VM_CFG,
    _client_vm,
    REDACTOR,
    audit,
    check_allowlist,
)

import tools.victoria_logs as _tools_vl
_tools_vl.register(
    mcp,
    VL_CFG,
    _client_vl,
    REDACTOR,
    audit,
    check_allowlist,
)

import tools.obsidian as _tools_obsidian
_tools_obsidian.register(mcp, OB_CFG, REDACTOR, audit)


# =============================================================================
#  Entry point
# =============================================================================

if __name__ == "__main__":
    log.info("starting sre-mcp server, config=%s", CONFIG_PATH)
    mcp.run()
