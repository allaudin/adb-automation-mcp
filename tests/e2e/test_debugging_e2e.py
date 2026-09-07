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


@pytest.mark.asyncio
async def test_set_debug_app_tool_round_trips_and_flags() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command, timeout_s)

    mcp = _build_test_server(RecordingBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "set_debug_app",
            {
                "serial": "emulator-5554",
                "package": "com.example.app",
                "wait_for_debugger": True,
                "persistent": True,
            },
        )

    assert result.data.status == "success"
    assert result.data.data.wait_for_debugger is True
    assert captured["command"] == "am set-debug-app -w --persistent com.example.app"


@pytest.mark.asyncio
async def test_clear_debug_app_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}
        result = await client.call_tool("clear_debug_app", {"serial": "emulator-5554"})

    assert "clear_debug_app" in tools
    assert result.data.status == "success"
    assert result.data.data.cleared is True


@pytest.mark.asyncio
async def test_list_jdwp_processes_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("list_jdwp_processes", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.pids == [1224, 1568, 2411]


@pytest.mark.asyncio
async def test_list_jdwp_processes_tool_device_offline_is_structured_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            jdwp_result=CommandResult(
                stdout="", stderr="error: device offline\n", exit_code=1, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("list_jdwp_processes", {"serial": "emulator-5554"})

    assert result.data.status == "error"
    assert result.data.error.code == "DEVICE_NOT_FOUND"
