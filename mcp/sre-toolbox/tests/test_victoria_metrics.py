from __future__ import annotations

import copy
import json
import unittest
from typing import Any

from tools import victoria_metrics


class _FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, Any] = {}

    def tool(self):
        def decorator(function):
            self.tools[function.__name__] = function
            return function

        return decorator


class _FakeResponse:
    def __init__(self, body: Any, status_code: int = 200) -> None:
        self._body = body
        self.status_code = status_code

    def json(self) -> Any:
        return copy.deepcopy(self._body)


class _FakeClient:
    def __init__(self, response_factory, calls: list[dict[str, Any]]) -> None:
        self._response_factory = response_factory
        self._calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def get(self, url: str, params: dict[str, Any]):
        self._calls.append({"url": url, "params": dict(params)})
        return self._response_factory()


class _DirectFactory:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def __call__(self):
        response = self.responses.pop(0)
        return _FakeClient(lambda: response, self.calls)


class _Redactor:
    def scrub_any(self, value: Any) -> Any:
        return value


class VictoriaMetricsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.direct = _DirectFactory([
            _FakeResponse({
                "status": "success",
                "data": {"result": [{"metric": {"vm_account_id": "100"}, "value": [1, "7"]}]},
            }),
        ])
        self.audit: list[tuple[str, dict[str, Any], int]] = []

        def record_audit(tool: str, args: dict[str, Any], size: int) -> None:
            self.audit.append((tool, args, size))

        self.mcp = _FakeMCP()
        self.vm_cfg = {
            "url": "https://vmauth.example.com/select/multitenant/prometheus/",
            "timeout_seconds": 15,
            "limits": {
                "request_timeout_seconds": 5,
                "max_timeout_seconds": 10,
                "max_range_seconds": 30 * 86400,
                "min_step_seconds": 15,
                "max_step_seconds": 3600,
                "max_points_requested": 100000,
                "max_series_returned": 30,
                "max_points_per_series": 120,
                "max_response_bytes": 4096,
            },
        }
        victoria_metrics.register(
            self.mcp,
            self.vm_cfg,
            self.direct,
            _Redactor(),
            record_audit,
            None,
        )

    async def test_query_uses_configured_endpoint(self) -> None:
        result = await self.mcp.tools["vm_query"]("up")

        self.assertEqual(result["results"][0]["value"], 7.0)
        self.assertEqual(
            self.direct.calls[0]["url"],
            "https://vmauth.example.com/select/multitenant/prometheus/api/v1/query",
        )
        self.assertEqual(self.audit[0][1], {"promql": "up", "time": None})

    async def test_range_and_label_queries(self) -> None:
        self.direct.responses = [
            _FakeResponse({
                "status": "success",
                "data": {"result": [{"metric": {"job": "redis"}, "values": [[1, "1"], [2, "3"]]}]},
            }),
            _FakeResponse({"status": "success", "data": ["100", "200"]}),
        ]
        range_result = await self.mcp.tools["vm_query_range"](
            "up", "2026-10-17T00:00:00Z", "2026-10-17T01:00:00Z", "1m", True,
        )
        labels = await self.mcp.tools["vm_label_values"]("vm_account_id")

        self.assertEqual(range_result["series"][0]["max"], 3.0)
        self.assertEqual(labels["values"], ["100", "200"])
        self.assertTrue(self.direct.calls[1]["url"].endswith("/api/v1/label/vm_account_id/values"))

    async def test_invalid_url_is_rejected_without_request(self) -> None:
        self.vm_cfg["url"] = "https://user:pw@example.com"

        result = await self.mcp.tools["vm_query"]("up")

        self.assertEqual(result["error"], "invalid VictoriaMetrics URL configuration")
        self.assertEqual(self.direct.calls, [])

    async def test_range_limits_are_checked_before_network(self) -> None:
        result = await self.mcp.tools["vm_query_range"](
            "up", "2026-01-01T00:00:00Z", "2026-02-15T00:00:00Z", "1m", True,
        )

        self.assertIn("max_range", result["error"])
        self.assertEqual(self.direct.calls, [])

    async def test_step_and_serialized_response_limits_are_enforced(self) -> None:
        step_result = await self.mcp.tools["vm_query_range"](
            "up", "2026-07-01T00:00:00Z", "2026-07-01T01:00:00Z", "1s", True,
        )
        self.assertIn("min_step", step_result["error"])
        self.assertEqual(self.direct.calls, [])

        self.vm_cfg["limits"]["max_response_bytes"] = 1024
        self.direct.responses = [
            _FakeResponse({"status": "success", "data": ["x" * 50] * 500}),
        ]
        response_result = await self.mcp.tools["vm_label_values"]("instance")
        self.assertTrue(response_result["truncated_response"])
        self.assertLessEqual(len(json.dumps(response_result).encode()), 1024)

    async def test_upstream_error_is_reported_without_body(self) -> None:
        self.direct.responses = [
            _FakeResponse({"status": "error", "error": "denied"}, status_code=403),
        ]
        result = await self.mcp.tools["vm_query"]("up")

        self.assertEqual(result, {"error": "metrics upstream request failed", "status": 403})


if __name__ == "__main__":
    unittest.main()
