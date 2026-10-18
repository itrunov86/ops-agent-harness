from __future__ import annotations

import unittest
from typing import Any

from tools import alertmanager


class _FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self):
        def decorator(function):
            self.tools[function.__name__] = function
            return function

        return decorator


class _FakeResponse:
    def __init__(self, body: Any) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._body


class _FakeClient:
    def __init__(self, body: Any, calls: list[str]) -> None:
        self.body = body
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str):
        self.calls.append(url)
        return _FakeResponse(self.body)


class _Factory:
    def __init__(self, body: Any) -> None:
        self.body = body
        self.calls: list[str] = []
        self.cfgs: list[dict[str, Any]] = []

    def __call__(self, section: dict[str, Any]):
        self.cfgs.append(section)
        return _FakeClient(self.body, self.calls)


class _Redactor:
    def scrub_any(self, value: Any) -> Any:
        return value


_ALERT = {
    "labels": {"alertname": "KubePodCrashLooping", "severity": "warning", "job": "kube-state-metrics"},
    "annotations": {"summary": "crash"},
    "startsAt": "2026-10-17T00:00:00Z",
    "status": {"state": "active"},
}


def _register(cfg: dict[str, Any], factory: _Factory) -> _FakeMCP:
    mcp = _FakeMCP()
    alertmanager.register(mcp, cfg, factory, _Redactor(), lambda *a: None)
    return mcp


class AlertmanagerInstanceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.factory = _Factory([_ALERT])
        self.mcp = _register(
            {
                "default_instance": "primary",
                "timeout_seconds": 10,
                "verify_ssl": "certs/ca.pem",
                "instances": {
                    "secondary": {"url": "https://am-secondary.example.com/", "aliases": ["sec"]},
                    "primary": {"url": "https://am-primary.example.com", "timeout_seconds": 5},
                },
            },
            self.factory,
        )

    async def test_default_instance_is_used(self) -> None:
        result = await self.mcp.tools["am_active_alerts"]()

        self.assertEqual(result["instance"], "primary")
        self.assertEqual(result["count"], 1)
        self.assertEqual(self.factory.calls, ["https://am-primary.example.com/api/v2/alerts"])
        self.assertEqual(self.factory.cfgs[0]["timeout_seconds"], 5)
        self.assertEqual(self.factory.cfgs[0]["verify_ssl"], "certs/ca.pem")

    async def test_instance_selected_by_alias(self) -> None:
        result = await self.mcp.tools["am_silences"](True, "sec")

        self.assertEqual(result["instance"], "secondary")
        self.assertEqual(self.factory.calls, ["https://am-secondary.example.com/api/v2/silences"])

    async def test_unknown_instance_lists_available_without_request(self) -> None:
        result = await self.mcp.tools["am_active_alerts"](instance="https://attacker.invalid")

        self.assertIn("available: primary, secondary", result["error"])
        self.assertEqual(self.factory.calls, [])

    async def test_legacy_single_url_still_works(self) -> None:
        factory = _Factory([_ALERT])
        mcp = _register({"url": "https://am.example.com"}, factory)

        result = await mcp.tools["am_active_alerts"]()

        self.assertEqual(result["instance"], "default")
        self.assertEqual(factory.calls, ["https://am.example.com/api/v2/alerts"])

    async def test_not_configured(self) -> None:
        mcp = _register({}, _Factory([]))

        result = await mcp.tools["am_active_alerts"]()

        self.assertIn("не сконфигурирован", result["error"])


if __name__ == "__main__":
    unittest.main()
