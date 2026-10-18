"""kb.py и build_hubs.py на базе из шаблона."""

import json
import unittest

from helpers import HarnessCase

DOC = """---
type: rca
date: 2026-01-20
tickets: [OPS-42]
services: [payments]
summary: "payments-api 5xx после уменьшения таймаута клиента шлюза до 1s; откат значения"
---

# OPS-42: payments-api отдаёт 5xx

TL;DR: после релиза чарта таймаут клиента шлюза стал 1s, запросы к банку рвались. Вернули 10s.

## Причина

Таймаут клиента шлюза в values.
"""


class KbTest(HarnessCase):
    def setUp(self):
        super().setUp()
        self.kb = self.make_kb()
        (self.kb / "alerts/OPS-42-payments-5xx-2026-01-20.md").write_text(DOC, encoding="utf-8")

    def test_lint_template_ok(self):
        res = self.tool("kb.py", "lint", check=False)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_search_finds_document_by_synonym_and_ticket(self):
        out = self.tool("kb.py", "search", "платежи таймаут").stdout
        self.assertIn("OPS-42-payments-5xx", out)
        out = self.tool("kb.py", "search", "--ticket", "OPS-42", "5xx").stdout
        self.assertIn("OPS-42-payments-5xx", out)

    def test_prompt_hook_uses_configured_prefixes(self):
        res = self.tool("kb.py", "hook", input=json.dumps({"prompt": "что было по OPS-42?"}))
        self.assertIn("OPS-42", res.stdout)
        res = self.tool("kb.py", "hook", input=json.dumps({"prompt": "что было по ABC-42?"}))
        self.assertEqual(res.stdout.strip(), "")

    def test_build_hubs_links_by_services_field(self):
        self.tool("build_hubs.py")
        hub = (self.kb / "services/Payments.md").read_text(encoding="utf-8")
        self.assertIn("[[OPS-42-payments-5xx-2026-01-20|", hub)

    def test_journal_links_use_full_path(self):
        self.tool("agent_session.py", "start", "OPS-9", "payments-move", cwd=self.home / "chats")
        journal = self.kb / "tasks/OPS-9-payments-move/handoff.md"
        journal.write_text(journal.read_text().replace("services: []", "services: [payments]"))
        self.tool("agent_session.py", "start", "OPS-10", "other", cwd=self.home / "chats")
        self.tool("build_hubs.py")
        hub = (self.kb / "services/Payments.md").read_text(encoding="utf-8")
        self.assertIn("[[tasks/OPS-9-payments-move/handoff|", hub)

    def test_mcp_server(self):
        msgs = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                {"jsonrpc": "2.0", "method": "notifications/initialized"},
                {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                 "params": {"name": "kb_search", "arguments": {"query": "payments 5xx", "ticket": ["OPS-42"]}}},
                {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "kb_list", "arguments": {}}}]
        out = self.tool("kb_mcp.py", input="\n".join(json.dumps(m) for m in msgs) + "\n").stdout.splitlines()
        replies = [json.loads(l) for l in out]
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4])
        self.assertEqual({t["name"] for t in replies[1]["result"]["tools"]}, {"kb_search", "kb_list"})
        self.assertIn("OPS-42-payments-5xx", replies[2]["result"]["content"][0]["text"])
        self.assertIn("OPS-42-payments-5xx", replies[3]["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
