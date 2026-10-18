from __future__ import annotations

import copy
import json
import unittest
from typing import Any

from tools import victoria_logs


class _FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self):
        def decorator(function):
            self.tools[function.__name__] = function
            return function

        return decorator


class _FakeResponse:
    def __init__(
        self,
        body: Any = None,
        status_code: int = 200,
        lines: list[str] | None = None,
        text: str = "",
    ) -> None:
        self._body = body
        self.status_code = status_code
        self._lines = list(lines or [])
        self.text = text

    def json(self) -> Any:
        if isinstance(self._body, Exception):
            raise self._body
        return copy.deepcopy(self._body)

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class _FakeStream:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeClient:
    def __init__(self, response: _FakeResponse, calls: list[dict[str, Any]]) -> None:
        self.response = response
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, params: dict[str, Any], headers: dict[str, str] | None = None):
        self.calls.append({"method": "GET", "url": url, "params": dict(params), "headers": headers})
        return self.response

    def stream(
        self,
        method: str,
        url: str,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ):
        self.calls.append({"method": method, "url": url, "params": dict(params), "headers": headers})
        return _FakeStream(self.response)


class _DirectFactory:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def __call__(self):
        return _FakeClient(self.responses.pop(0), self.calls)


class _Redactor:
    def scrub_any(self, value: Any) -> Any:
        return value


_START = "2026-10-17T00:00:00Z"
_END = "2026-10-17T01:00:00Z"


class VictoriaLogsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.direct = _DirectFactory([
            _FakeResponse(lines=[
                json.dumps({"_msg": "Redis error after 123 ms"}),
                json.dumps({"_msg": "Redis error after 456 ms"}),
            ]),
        ])
        self.audit: list[tuple[str, dict[str, Any], int]] = []
        self.mcp = _FakeMCP()
        self.vl_cfg = {
            "url": "https://vlogs.example.com",
            "timeout_seconds": 30,
            "default_tenant": "payments-prod",
            "tenants": {"payments-prod": 100, "infra": "10100", "broken": "x"},
            "limits": {
                "request_timeout_seconds": 5,
                "max_timeout_seconds": 10,
                "max_query_window_hours": 24,
                "max_lines_returned": 500,
                "max_streams_returned": 200,
                "max_response_bytes": 4096,
            },
        }

        def record_audit(tool: str, args: dict[str, Any], size: int) -> None:
            self.audit.append((tool, args, size))

        victoria_logs.register(self.mcp, self.vl_cfg, self.direct, _Redactor(), record_audit, None)

    async def query(self, **kwargs: Any) -> dict[str, Any]:
        args = {"start": _START, "end": _END, "limit": None, "mode": "patterns", **kwargs}
        return await self.mcp.tools["vl_query"]("error", **args)

    async def test_default_tenant_sets_account_header(self) -> None:
        result = await self.query()

        self.assertEqual(result["tenant"], "payments-prod")
        self.assertEqual(result["total_lines"], 2)
        self.assertEqual(self.direct.calls[0]["url"], "https://vlogs.example.com/select/logsql/query")
        self.assertEqual(self.direct.calls[0]["headers"], {"AccountID": "100", "ProjectID": "0"})
        self.assertEqual(self.audit[0][1]["tenant"], "payments-prod")

    async def test_tenant_can_be_selected_by_name_or_account_id(self) -> None:
        self.direct.responses.append(_FakeResponse(lines=[json.dumps({"_msg": "x"})]))
        by_name = await self.query(tenant="infra")
        by_id = await self.query(tenant="10100")

        self.assertEqual(by_name["tenant"], "infra")
        self.assertEqual(by_id["tenant"], "infra")
        self.assertEqual(self.direct.calls[1]["headers"]["AccountID"], "10100")

    async def test_unknown_tenant_lists_allowlist_without_request(self) -> None:
        result = await self.query(tenant="broken")

        self.assertIn("unknown tenant", result["error"])
        self.assertIn("infra, payments-prod", result["error"])
        self.assertEqual(self.direct.calls, [])

    async def test_without_tenant_map_no_headers_are_sent(self) -> None:
        self.vl_cfg.pop("tenants")
        self.vl_cfg.pop("default_tenant")
        mcp = _FakeMCP()
        victoria_logs.register(mcp, self.vl_cfg, self.direct, _Redactor(), lambda *a: None, None)

        result = await mcp.tools["vl_query"]("error", _START, _END, None, "lines")

        self.assertNotIn("tenant", result)
        self.assertIsNone(self.direct.calls[0]["headers"])

    async def test_streams_use_selected_tenant(self) -> None:
        self.direct.responses = [
            _FakeResponse(body={"values": [{"value": "{namespace=payments-prod}", "hits": 1}]}),
        ]
        result = await self.mcp.tools["vl_streams"]("*", 50, "infra")

        self.assertEqual(result["tenant"], "infra")
        self.assertEqual(result["streams"], [{"value": "{namespace=payments-prod}", "hits": 1}])
        self.assertEqual(self.direct.calls[0]["url"], "https://vlogs.example.com/select/logsql/streams")

    async def test_upstream_error_is_reported(self) -> None:
        self.direct.responses = [_FakeResponse(status_code=403)]

        result = await self.query()

        self.assertEqual(result, {"error": "logs upstream request failed", "status": 403})

    async def test_window_and_response_limits_are_enforced(self) -> None:
        range_result = await self.query(start="2026-07-01T00:00:00Z", end="2026-07-03T00:00:00Z")
        self.assertIn("max_query_window_hours", range_result["error"])
        self.assertEqual(self.direct.calls, [])

        self.vl_cfg["limits"]["max_response_bytes"] = 1024
        self.direct.responses = [_FakeResponse(lines=[json.dumps({"_msg": "x" * 10000})])]
        response_result = await self.query(limit=1, mode="lines")
        self.assertTrue(response_result["truncated_response"])
        self.assertLessEqual(len(json.dumps(response_result).encode()), 1024)


if __name__ == "__main__":
    unittest.main()
