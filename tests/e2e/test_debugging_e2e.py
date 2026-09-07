"""Layer 3 protocol-level E2E tests for get_process_exit_history."""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_get_process_exit_history_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_process_exit_history",
            {"serial": "emulator-5554", "package": "com.example.app"},
        )

    assert result.data.status == "success"
    assert result.data.data.count == 2
    assert result.data.data.records[0].reason == "APP CRASH(EXCEPTION)"
    assert result.data.data.records[1].trace_available is True


@pytest.mark.asyncio
async def test_get_process_exit_history_tool_registered_and_read() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}

    assert "get_process_exit_history" in tools


@pytest.mark.asyncio
async def test_get_process_exit_history_tool_no_history_is_success_empty() -> None:
    mcp = _build_test_server(
        FakeBackend(
            activity_exit_info_result=CommandResult(
                stdout="ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)\n",
                stderr="",
                exit_code=0,
                duration_ms=5.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_process_exit_history", {"serial": "emulator-5554", "package": "com.x"}
        )

    assert result.data.status == "success"
    assert result.data.data.records == []


@pytest.mark.asyncio
async def test_get_process_exit_history_tool_blank_package_returns_invalid_argument() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_process_exit_history", {"serial": "emulator-5554", "package": "  "}
        )

    assert result.data.status == "error"
    assert result.data.error.code == "INVALID_ARGUMENT"
