"""Layer 3 protocol-level E2E tests for force_stop_app — a real fastmcp.Client
speaking actual MCP protocol to a running FastMCP server instance, backed by
FakeBackend. Kept in its own file (not test_protocol_e2e.py) to avoid
concurrent edits to a shared test file.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_force_stop_app_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "force_stop_app", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.package_name == "com.example.app"
    assert result.data.data.output == ""


@pytest.mark.asyncio
async def test_force_stop_app_tool_accepts_user_id() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "force_stop_app",
            {"serial": "emulator-5554", "package_name": "com.example.app", "user_id": 10},
        )

    assert result.data.status == "success"
    assert result.data.data.user_id == 10
    assert captured["command"] == "am force-stop --user 10 com.example.app"


@pytest.mark.asyncio
async def test_force_stop_app_tool_nonexistent_package_is_still_success() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "force_stop_app",
            {"serial": "emulator-5554", "package_name": "com.example.does.not.exist"},
        )

    assert result.data.status == "success"
    assert result.data.data.package_name == "com.example.does.not.exist"


@pytest.mark.asyncio
async def test_force_stop_app_tool_permission_denial_returns_permission_denied_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            force_stop_result=CommandResult(
                stdout="",
                stderr="java.lang.SecurityException: Permission Denial: forceStopPackage()\n",
                exit_code=1,
                duration_ms=12.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "force_stop_app", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_force_stop_app_tool_backend_failure_returns_backend_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            force_stop_result=CommandResult(
                stdout="", stderr="Error: Activity manager has died\n", exit_code=1, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "force_stop_app", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "BACKEND_ERROR"
