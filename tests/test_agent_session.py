"""Хуки agent_session.py: привязка журнала к чату и автокоммит базы знаний."""

import json
import time
import unittest

from helpers import HarnessCase, TOOLS


class SessionBindingTest(HarnessCase):
    def setUp(self):
        super().setUp()
        self.kb = self.make_kb()
        for key, slug in (("OPS-1", "alpha"), ("OPS-2", "beta")):
            self.tool("agent_session.py", "start", key, slug, cwd=self.home / "chats")
        self.git(self.kb, "add", "-A")
        self.git(self.kb, "commit", "-qm", "journals")

    def test_plain_start_in_shared_folder(self):
        self.assertEqual(self.hook("SessionStart", "A", source="startup"), "")

    def test_ticket_mention_does_not_bind(self):
        self.assertEqual(self.hook("UserPromptSubmit", "A", prompt="разбери алерт, похоже на OPS-1"), "")

    def test_key_at_start_binds_and_survives_compact(self):
        self.assertIn("OPS-1-alpha", self.hook("UserPromptSubmit", "B", prompt="OPS-1 продолжаем"))
        self.assertEqual(self.hook("UserPromptSubmit", "B", prompt="OPS-1 дальше"), "")
        self.assertIn("OPS-1-alpha", self.hook("SessionStart", "B", source="compact"))
        self.assertEqual(self.hook("SessionStart", "other", source="compact"), "")

    def test_switch_phrase_rebinds(self):
        self.hook("UserPromptSubmit", "C", prompt="OPS-1 продолжаем")
        self.assertIn("OPS-2-beta", self.hook("UserPromptSubmit", "C", prompt="переключаемся на OPS-2"))
        self.assertIn("OPS-2-beta", self.hook("UserPromptSubmit", "D", prompt="ок, работаем по OPS-2"))

    def test_start_command_binds_but_echo_does_not(self):
        start = f"python3 {TOOLS}/agent_session" + ".py start OPS-2 beta"
        out = self.hook("PostToolUse", "E", tool_name="Bash", tool_input={"command": f"cd /tmp && {start}"})
        self.assertIn("OPS-2-beta", out)
        out = self.hook("PostToolUse", "F", tool_name="Bash",
                        tool_input={"command": f"echo '{{\"command\":\"{start}\"}}' | cat"})
        self.assertEqual(out, "")
        out = self.hook("PostToolUse", "G", tool_name="shell", tool_input={"command": ["bash", "-lc", start]})
        self.assertIn("OPS-2-beta", out)

    def test_writing_journal_binds_reading_does_not(self):
        path = str(self.kb / "tasks/OPS-1-alpha/handoff.md")
        self.assertIn("OPS-1-alpha", self.hook("PostToolUse", "H", tool_name="Edit", tool_input={"file_path": path}))
        self.assertEqual(self.hook("PostToolUse", "I", tool_name="Bash", tool_input={"command": f"cat {path}"}), "")

    def test_start_does_not_bind_shared_folder(self):
        active = json.loads((self.home / ".agents/state/active-tasks.json").read_text()) \
            if (self.home / ".agents/state/active-tasks.json").exists() else {}
        self.assertNotIn(str((self.home / "chats").resolve()), active)


class AutocommitTest(HarnessCase):
    def setUp(self):
        super().setUp()
        self.kb = self.make_kb()

    def act(self, sid, fn, tool="Bash", tool_input=None):
        tool_input = tool_input or {"command": "x"}
        self.hook("PreToolUse", sid, tool_name=tool, tool_input=tool_input)
        time.sleep(0.01)
        fn()
        self.hook("PostToolUse", sid, tool_name=tool, tool_input=tool_input)

    def head(self):
        return self.git(self.kb, "rev-parse", "HEAD").strip()

    def test_commits_own_files_only(self):
        (self.kb / "foreign.md").write_text("чужая правка\n")
        self.act("A", lambda: (self.kb / "findings/ops-77-note.md").write_text("n\n"))
        self.act("A", lambda: (self.kb / "AGENTS.md").write_text("edited\n"))
        self.assertEqual(self.hook("Stop", "A"), "")
        subject = self.git(self.kb, "log", "-1", "--format=%s").strip()
        files = self.git(self.kb, "show", "--name-only", "--format=", "HEAD").split()
        self.assertEqual(sorted(files), ["AGENTS.md", "findings/ops-77-note.md"])
        self.assertTrue(subject.startswith("OPS-77 docs:"), subject)
        self.assertIn("foreign.md", self.git(self.kb, "status", "--porcelain"))

    def test_bound_chat_key_wins(self):
        self.tool("agent_session.py", "start", "OPS-5", "x", cwd=self.home / "chats")
        self.hook("UserPromptSubmit", "B", prompt="OPS-5 продолжаем")
        self.act("B", lambda: (self.kb / "reference/r.md").write_text("r\n"))
        self.hook("Stop", "B")
        self.assertTrue(self.git(self.kb, "log", "-1", "--format=%s").startswith("OPS-5 docs:"))

    def test_shared_and_secret_files_are_skipped(self):
        self.act("C", lambda: (self.kb / "shared.md").write_text("C\n"))
        self.act("D", lambda: (self.kb / "shared.md").write_text("C+D\n"))
        before = self.head()
        self.assertIn("другой чат", self.hook("Stop", "C"))
        self.assertEqual(before, self.head())
        self.act("E", lambda: (self.kb / "leak.md").write_text("token hvs.CAESIJ1234567890abcdefghijklmnop\n"))
        self.assertIn("секрет", self.hook("Stop", "E"))
        self.assertEqual(before, self.head())

    def test_manual_commit_releases_marks(self):
        self.act("F", lambda: (self.kb / "AGENTS.md").write_text("F\n"))
        self.git(self.kb, "commit", "-qam", "OPS-1 manual")
        before = self.head()
        self.assertEqual(self.hook("Stop", "F"), "")
        self.assertEqual(before, self.head())
        owners = json.loads((self.home / ".agents/state/autocommit/owners.json").read_text())
        self.assertNotIn("F", owners.get("AGENTS.md", {}))

    def test_autocommit_can_be_disabled(self):
        self.config.write_text(self.config.read_text().replace("autocommit = true", "autocommit = false"))
        before = self.head()
        self.act("G", lambda: (self.kb / "AGENTS.md").write_text("G\n"))
        self.hook("Stop", "G")
        self.assertEqual(before, self.head())


if __name__ == "__main__":
    unittest.main()
