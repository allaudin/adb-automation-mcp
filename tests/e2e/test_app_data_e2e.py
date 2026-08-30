"""Layer 3 protocol-level E2E tests for clear_app_data — a real fastmcp.Client
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
async def test_clear_app_data_tool_round_trips_over_mcp_protocol() -> None:
    # destructive category: only registered when the server explicitly opts in.
    mcp = _build_test_server(FakeBackend(), allow_destructive=True)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "clear_app_data", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.package_name == "com.example.app"
    assert result.data.data.success is True


@pytest.mark.asyncio
async def test_clear_app_data_tool_not_registered_when_destructive_disallowed() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert "clear_app_data" not in {tool.name for tool in tools}


@pytest.mark.asyncio
async def test_clear_app_data_tool_accepts_user_id() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend(), allow_destructive=True)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "clear_app_data",
            {"serial": "emulator-5554", "package_name": "com.example.app", "user_id": 10},
        )

    assert result.data.status == "success"
    assert result.data.data.user_id == 10
    assert captured["command"] == "pm clear --user 10 com.example.app"


@pytest.mark.asyncio
async def test_clear_app_data_tool_package_not_found_returns_package_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            clear_app_data_result=CommandResult(
                stdout="",
                stderr="Error: Package not found: com.example.bogus\n",
                exit_code=1,
                duration_ms=15.0,
            )
        ),
        allow_destructive=True,
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "clear_app_data", {"serial": "emulator-5554", "package_name": "com.example.bogus"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PACKAGE_NOT_FOUND"


@pytest.mark.asyncio
async def test_clear_app_data_tool_android_rejection_returns_android_rejected_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            clear_app_data_result=CommandResult(
                stdout="Failed\n", stderr="", exit_code=0, duration_ms=40.0
            )
        ),
        allow_destructive=True,
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "clear_app_data", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "ANDROID_REJECTED"


@pytest.mark.asyncio
async def test_clear_app_data_tool_backend_failure_returns_backend_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            clear_app_data_result=CommandResult(
                stdout="", stderr="Error: Package manager has died\n", exit_code=1, duration_ms=5.0
            )
        ),
        allow_destructive=True,
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "clear_app_data", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "BACKEND_ERROR"
