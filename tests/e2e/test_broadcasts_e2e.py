"""Layer 3 protocol-level E2E tests for send_broadcast — a real fastmcp.Client
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
async def test_send_broadcast_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "send_broadcast",
            {"serial": "emulator-5554", "action": "android.intent.action.MY_ACTION"},
        )

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.action == "android.intent.action.MY_ACTION"
    assert result.data.data.result_code == 0


@pytest.mark.asyncio
async def test_send_broadcast_tool_accepts_component_user_id_and_extras() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "send_broadcast",
            {
                "serial": "emulator-5554",
                "action": "com.example.ACTION_FOO",
                "component": "com.example/.Receiver",
                "user_id": 10,
                "receiver_permission": "com.example.MY_PERMISSION",
                "extras": [{"key": "count", "value": "3", "type": "int"}],
            },
        )

    assert result.data.status == "success"
    assert result.data.data.component == "com.example/.Receiver"
    assert result.data.data.user_id == 10
    assert result.data.data.receiver_permission == "com.example.MY_PERMISSION"
    assert captured["command"] == (
        "am broadcast -a com.example.ACTION_FOO -n com.example/.Receiver --user 10 "
        "--receiver-permission com.example.MY_PERMISSION --ei count 3"
    )


@pytest.mark.asyncio
async def test_send_broadcast_tool_unknown_serial_returns_device_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            send_broadcast_result=CommandResult(
                stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "send_broadcast", {"serial": "bogus", "action": "android.intent.action.MY_ACTION"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"


@pytest.mark.asyncio
async def test_send_broadcast_tool_bad_component_returns_component_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            send_broadcast_result=CommandResult(
                stdout="",
                stderr="Error: Bad component name: not-a-component\n",
                exit_code=1,
                duration_ms=8.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "send_broadcast",
            {
                "serial": "emulator-5554",
                "action": "android.intent.action.MY_ACTION",
                "component": "not-a-component",
            },
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "COMPONENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_send_broadcast_tool_permission_denial_returns_permission_denied_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            send_broadcast_result=CommandResult(
                stdout="",
                stderr="java.lang.SecurityException: Permission Denial: not allowed to send broadcast\n",
                exit_code=1,
                duration_ms=12.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "send_broadcast", {"serial": "emulator-5554", "action": "android.intent.action.MY_ACTION"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_send_broadcast_tool_activity_manager_failure_returns_backend_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            send_broadcast_result=CommandResult(
                stdout="", stderr="Error: Activity manager has died\n", exit_code=1, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "send_broadcast", {"serial": "emulator-5554", "action": "android.intent.action.MY_ACTION"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "BACKEND_ERROR"
