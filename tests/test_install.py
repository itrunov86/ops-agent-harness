"""harness init / install / doctor / uninstall на временном HOME."""

import json
import re
import unittest

from helpers import HarnessCase, REPO

PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")


class InstallTest(HarnessCase):
    def test_dry_run_changes_nothing(self):
        self.harness("install", "--dry-run")
        self.assertFalse((self.home / ".agents/skills").exists())
        self.assertFalse((self.home / ".claude").exists())
        self.assertFalse((self.home / "kb").exists())

    def test_install_renders_everything(self):
        out = self.harness("install").stdout
        skills = self.home / ".agents/skills"
        names = {p.name for p in skills.iterdir()}
        self.assertIn("handoff", names)
        self.assertIn("postmortem", names)                       # team-skills включены по умолчанию
        for f in skills.rglob("*.md"):
            self.assertIsNone(PLACEHOLDER.search(f.read_text(encoding="utf-8")), f"{f}: подстановка не заполнена")
        handoff = (skills / "handoff/SKILL.md").read_text(encoding="utf-8")
        self.assertIn(str(self.home / "kb").replace(str(self.home), "~"), handoff)
        link = self.home / ".claude/skills/handoff"
        self.assertTrue(link.is_symlink() and link.resolve() == (skills / "handoff").resolve())
        rules = (self.home / ".codex/AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("OPS-1234", rules)
        self.assertIn("@~/.codex/AGENTS.md", (self.home / ".claude/CLAUDE.md").read_text(encoding="utf-8"))
        self.assertTrue((self.home / ".claude/agents/kb-scout.md").exists())
        self.assertTrue((self.home / ".codex/agents/kb-scout.toml").exists())
        self.assertTrue((self.home / "kb/.git").exists())
        self.assertTrue((self.home / "chats").is_dir())
        self.assertIn("Готово", out)

    def test_hooks_merge_keeps_user_hooks(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        user_hook = {"type": "command", "command": "echo mine"}
        settings.write_text(json.dumps({"model": "opus", "hooks": {"Stop": [{"hooks": [user_hook]}]}}))
        self.harness("install")
        data = json.loads(settings.read_text())
        self.assertEqual(data["model"], "opus")
        stop = [h["command"] for g in data["hooks"]["Stop"] for h in g["hooks"]]
        self.assertIn("echo mine", stop)
        self.assertTrue(any("agent_session.py hook" in c for c in stop))
        for event in ("UserPromptSubmit", "SessionStart", "PreToolUse", "PostToolUse", "PostCompact"):
            self.assertIn(event, data["hooks"])
        codex = json.loads((self.home / ".codex/hooks.json").read_text())
        self.assertNotIn("PostCompact", codex["hooks"])

    def test_install_is_idempotent(self):
        self.harness("install")
        before = (self.home / ".claude/settings.json").read_text()
        out = self.harness("install").stdout
        self.assertEqual(before, (self.home / ".claude/settings.json").read_text())
        self.assertNotIn("!", out.replace("Готово.", ""))

    def test_foreign_files_are_not_overwritten(self):
        rules = self.home / ".codex/AGENTS.md"
        rules.parent.mkdir(parents=True)
        rules.write_text("my own rules\n")
        mine = self.home / ".agents/skills/handoff"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("my handoff\n")
        res = self.harness("install", check=False)
        self.assertEqual(res.returncode, 1)
        self.assertEqual(rules.read_text(), "my own rules\n")
        self.assertTrue((self.home / ".codex/AGENTS.md.harness-new").exists())
        self.assertEqual((mine / "SKILL.md").read_text(), "my handoff\n")
        self.harness("install", "--force")
        self.assertIn("agent-harness", rules.read_text())
        backups = list((self.home / ".agents/backups").rglob("AGENTS.md"))
        self.assertTrue(backups and backups[0].read_text() == "my own rules\n")

    def test_existing_kb_is_left_alone(self):
        kb = self.home / "kb"
        kb.mkdir()
        (kb / "mine.md").write_text("x")
        self.harness("install")
        self.assertEqual(sorted(p.name for p in kb.iterdir()), ["mine.md"])

    def test_exclude_and_team_flags(self):
        self.config.write_text(self.config.read_text() + '\n[skills]\nteam = false\nexclude = ["yandex-cloud-devops"]\n')
        self.harness("install")
        names = {p.name for p in (self.home / ".agents/skills").iterdir()}
        self.assertNotIn("postmortem", names)
        self.assertNotIn("yandex-cloud-devops", names)
        self.assertIn("handoff", names)

    def test_doctor_after_install(self):
        self.assertEqual(self.harness("doctor", check=False).returncode, 1)
        self.harness("install")
        res = self.harness("doctor", check=False)
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_uninstall_removes_only_harness(self):
        settings = self.home / ".claude/settings.json"
        settings.parent.mkdir(parents=True)
        settings.write_text(json.dumps({"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}))
        self.harness("install")
        self.harness("uninstall")
        data = json.loads(settings.read_text())
        self.assertEqual(data["hooks"], {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]})
        self.assertFalse((self.home / ".agents/skills/handoff").exists())
        self.assertFalse((self.home / ".claude/skills/handoff").is_symlink())
        self.assertTrue((self.home / "kb/.git").exists())         # база знаний остаётся

    def test_init_defaults(self):
        self.config.unlink()
        self.harness("init", "--defaults")
        self.assertTrue(self.config.exists())
        self.assertEqual(self.harness("init", "--defaults", check=False).returncode, 1)

    def test_every_skill_has_frontmatter(self):
        for skill in list((REPO / "skills").glob("*/SKILL.md")) + list((REPO / "team-skills").glob("*/SKILL.md")):
            text = skill.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("---\n"), skill)
            head = text.split("\n---", 1)[0]
            self.assertRegex(head, rf"(?m)^name:\s*{skill.parent.name}\s*$", skill)
            self.assertRegex(head, r"(?m)^description:\s*\S", skill)


if __name__ == "__main__":
    unittest.main()
