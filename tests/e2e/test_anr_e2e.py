"""Layer 3 protocol-level E2E tests for get_anr_reports — a real fastmcp.Client
speaking actual MCP protocol to a running FastMCP server instance, backed by
FakeBackend. Kept in its own file (not test_protocol_e2e.py) to avoid
concurrent edits to a shared test file.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_get_anr_reports_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_anr_reports", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "success"
    assert result.data.data.count == 2
    assert result.data.data.reports[0].timestamp == "2026-09-06 16:52:25"
    assert result.data.data.reports[0].subject.startswith("ANR in com.example.app")
    assert result.data.data.reports[0].trace is not None


@pytest.mark.asyncio
async def test_get_anr_reports_tool_registered_and_not_destructive() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}

    assert "get_anr_reports" in tools


@pytest.mark.asyncio
async def test_get_anr_reports_tool_include_traces_false_drops_body() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_anr_reports",
            {
                "serial": "emulator-5554",
                "package_name": "com.example.app",
                "include_traces": False,
            },
        )

    assert result.data.status == "success"
    assert all(r.trace is None for r in result.data.data.reports)


@pytest.mark.asyncio
async def test_get_anr_reports_tool_no_entries_is_success_empty() -> None:
    mcp = _build_test_server(
        FakeBackend(
            dropbox_print_result=CommandResult(
                stdout="Searching for: data_app_anr system_app_anr\n\n(No entries found.)\n",
                stderr="",
                exit_code=0,
                duration_ms=10.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_anr_reports", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "success"
    assert result.data.data.reports == []


@pytest.mark.asyncio
async def test_get_anr_reports_tool_bad_limit_returns_invalid_argument_error() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_anr_reports",
            {"serial": "emulator-5554", "package_name": "com.example.app", "limit": 0},
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "INVALID_ARGUMENT"
