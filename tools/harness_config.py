"""Конфиг agent-harness: один TOML на машину, его читают инструменты, хуки и установщик.

Где искать: $AGENT_HARNESS_CONFIG, иначе ~/.config/agent-harness/config.toml. Без файла работают значения
по умолчанию (база ~/kb, ключи задач OPS-/INC-), чтобы хуки никогда не падали из-за конфига.
Только стандартная библиотека, Python 3.11+.
"""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

HARNESS_HOME = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("AGENT_HARNESS_CONFIG", "~/.config/agent-harness/config.toml")).expanduser()


def _path(value: str) -> Path:
    return Path(os.path.expandvars(value)).expanduser()


@dataclass(frozen=True)
class Config:
    kb_root: Path = field(default_factory=lambda: _path("~/kb"))
    work_dir: Path = field(default_factory=lambda: _path("~/work"))
    code_root: Path | None = None
    reports_dir: Path = field(default_factory=lambda: _path("~/work/reports"))
    state_dir: Path = field(default_factory=lambda: _path("~/.agents/state"))
    org_name: str = "Acme"
    ticket_prefixes: tuple[str, ...] = ("OPS", "INC")
    ticket_example: str = "OPS-1234"
    tracker_project: str = "OPS"
    tracker_issue_type: str = "Task"
    tracker_assignee: str = ""
    tracker_url: str = ""
    wiki_space: str = ""
    chat_url: str = ""
    alert_channels: tuple[str, ...] = ()
    mcp_hub: str = "ops-toolbox"
    handoff_thresholds: tuple[int, ...] = (50, 75)
    autocommit: bool = True
    raw: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def ticket_group(self) -> str:
        """Регулярка ключа задачи без границ слова: (?:OPS|INC)-\\d+."""
        return "(?:" + "|".join(re.escape(p) for p in self.ticket_prefixes) + r")-\d+"

    def ticket_re(self, max_digits: int | None = None) -> re.Pattern:
        digits = rf"\d{{1,{max_digits}}}" if max_digits else r"\d+"
        prefixes = "|".join(re.escape(p) for p in self.ticket_prefixes)
        return re.compile(rf"\b(?:{prefixes})-{digits}\b", re.I)

    def placeholders(self) -> dict[str, str]:
        """Значения для подстановок {{ИМЯ}} в скиллах и шаблонах (см. CONTRIBUTING.md)."""
        home = str(Path.home())
        tilde = lambda p: str(p).replace(home, "~", 1) if str(p).startswith(home) else str(p)  # noqa: E731
        return {
            "HARNESS_HOME": tilde(HARNESS_HOME),
            "KB_ROOT": tilde(self.kb_root),
            "WORK_DIR": tilde(self.work_dir),
            "ORG_NAME": self.org_name,
            "TICKET_PREFIXES": "|".join(self.ticket_prefixes),
            "TICKET_EXAMPLE": self.ticket_example,
            "TRACKER_PROJECT": self.tracker_project,
            "TRACKER_ISSUE_TYPE": self.tracker_issue_type,
            "TRACKER_ASSIGNEE": self.tracker_assignee or "<исполнитель>",
            "TRACKER_URL": self.tracker_url or "<адрес трекера>",
            "WIKI_SPACE": self.wiki_space or "<пространство вики>",
            "CHAT_URL": self.chat_url or "<адрес чата>",
            "ALERT_CHANNELS": ", ".join(self.alert_channels) or "<каналы алертов>",
            "MCP_HUB": self.mcp_hub,
        }


def load(path: Path | None = None) -> Config:
    path = path or CONFIG_PATH
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return Config()
    p, org, tr = data.get("paths", {}), data.get("org", {}), data.get("tracker", {})
    wiki, chat, mcp, hooks = data.get("wiki", {}), data.get("chat", {}), data.get("mcp", {}), data.get("hooks", {})
    d = Config()
    return Config(
        kb_root=_path(p.get("kb_root", str(d.kb_root))),
        work_dir=_path(p.get("work_dir", str(d.work_dir))),
        code_root=_path(p["code_root"]) if p.get("code_root") else None,
        reports_dir=_path(p.get("reports_dir", str(d.reports_dir))),
        state_dir=_path(p.get("state_dir", str(d.state_dir))),
        org_name=org.get("name", d.org_name),
        ticket_prefixes=tuple(tr.get("prefixes", d.ticket_prefixes)),
        ticket_example=tr.get("example", f"{tuple(tr.get('prefixes', d.ticket_prefixes))[0]}-1234"),
        tracker_project=tr.get("project", d.tracker_project),
        tracker_issue_type=tr.get("issue_type", d.tracker_issue_type),
        tracker_assignee=tr.get("assignee", d.tracker_assignee),
        tracker_url=tr.get("url", d.tracker_url),
        wiki_space=wiki.get("space", d.wiki_space),
        chat_url=chat.get("url", d.chat_url),
        alert_channels=tuple(chat.get("alert_channels", d.alert_channels)),
        mcp_hub=mcp.get("hub", d.mcp_hub),
        handoff_thresholds=tuple(int(x) for x in hooks.get("handoff_thresholds", d.handoff_thresholds)),
        autocommit=bool(hooks.get("autocommit", d.autocommit)),
        raw=data,
    )


CONFIG = load()
