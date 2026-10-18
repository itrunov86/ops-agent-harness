"""Общее для тестов: временный HOME, свой конфиг и запуск инструментов отдельными процессами."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TOOLS = REPO / "tools"

CONFIG = """
[org]
name = "Acme"
[paths]
kb_root = "{home}/kb"
work_dir = "{home}/chats"
state_dir = "{home}/.agents/state"
reports_dir = "{home}/reports"
[tracker]
prefixes = ["OPS", "INC"]
example = "OPS-1234"
project = "OPS"
assignee = "jdoe"
url = "https://jira.example.com"
[mcp]
hub = "sre-toolbox"
[hooks]
autocommit = true
"""

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com"}


class HarnessCase(unittest.TestCase):
    """Каждый тест — в своём HOME; настоящие ~/.claude и ~/.codex не трогаются."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="harness-test-"))
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.config = self.home / ".config/agent-harness/config.toml"
        self.config.parent.mkdir(parents=True)
        self.config.write_text(CONFIG.format(home=self.home), encoding="utf-8")
        self.env = {**os.environ, **GIT_ENV, "HOME": str(self.home), "AGENT_HARNESS_CONFIG": str(self.config)}
        self.env.pop("AGENT_HANDOFF_THRESHOLDS", None)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_cmd(self, *args: str, input: str | None = None, cwd: Path | None = None,
                check: bool = True) -> subprocess.CompletedProcess:
        res = subprocess.run(list(args), input=input, capture_output=True, text=True, env=self.env,
                             cwd=str(cwd or self.home))
        if check and res.returncode != 0:
            self.fail(f"{args} → {res.returncode}\n{res.stdout}\n{res.stderr}")
        return res

    def harness(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        return self.run_cmd(sys.executable, str(REPO / "harness"), *args, check=check)

    def tool(self, name: str, *args: str, input: str | None = None, cwd: Path | None = None,
             check: bool = True) -> subprocess.CompletedProcess:
        return self.run_cmd(sys.executable, "-I", str(TOOLS / name), *args, input=input, cwd=cwd, check=check)

    def hook(self, event: str, sid: str, **payload) -> str:
        """Вызвать agent_session.py hook и вернуть текст additionalContext/systemMessage (или "")."""
        body = json.dumps({"hook_event_name": event, "session_id": sid, "cwd": str(self.home), **payload})
        out = self.tool("agent_session.py", "hook", input=body).stdout.strip()
        if not out:
            return ""
        data = json.loads(out)
        return data.get("systemMessage") or data.get("hookSpecificOutput", {}).get("additionalContext", "")

    def git(self, repo: Path, *args: str) -> str:
        return self.run_cmd("git", "-C", str(repo), *args).stdout

    def make_kb(self) -> Path:
        """База знаний из шаблона, как после `harness install`."""
        self.harness("install")
        return self.home / "kb"
