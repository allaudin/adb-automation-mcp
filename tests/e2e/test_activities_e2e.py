"""Layer 3 protocol-level E2E tests for start_activity — a real fastmcp.Client
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
async def test_start_activity_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_activity",
            {"serial": "emulator-5554", "component": "com.example.app/.MainActivity"},
        )

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.component == "com.example.app/.MainActivity"
    assert result.data.data.success is True


@pytest.mark.asyncio
async def test_start_activity_tool_accepts_display_id() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_activity",
            {
                "serial": "emulator-5554",
                "component": "com.example.app/.MainActivity",
                "display_id": 2,
            },
        )

    assert result.data.status == "success"
    assert result.data.data.display_id == 2
    assert captured["command"] == "am start -n com.example.app/.MainActivity --display 2"


@pytest.mark.asyncio
async def test_start_activity_tool_accepts_user_id() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_activity",
            {
                "serial": "emulator-5554",
                "component": "com.example.app/.MainActivity",
                "user_id": 10,
            },
        )

    assert result.data.status == "success"
    assert result.data.data.user_id == 10
    assert captured["command"] == "am start -n com.example.app/.MainActivity --user 10"


@pytest.mark.asyncio
async def test_start_activity_tool_activity_manager_error_is_success_false_not_tool_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            start_activity_result=CommandResult(
                stdout=(
                    "Starting: Intent { cmp=com.example.app/.Bogus }\n"
                    "Error type 3\n"
                    "Error: Activity class {com.example.app/com.example.app.Bogus} does not exist.\n"
                ),
                stderr="",
                exit_code=0,
                duration_ms=60.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_activity",
            {"serial": "emulator-5554", "component": "com.example.app/.Bogus"},
        )

    assert result.data.status == "success"
    assert result.data.data.success is False
    assert result.data.data.error_type == 3
    assert "does not exist" in result.data.data.error_message


@pytest.mark.asyncio
async def test_start_activity_tool_malformed_component_returns_component_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            start_activity_result=CommandResult(
                stdout="",
                stderr="Error: Bad component name: not-a-component\n",
                exit_code=1,
                duration_ms=8.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_activity", {"serial": "emulator-5554", "component": "not-a-component"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "COMPONENT_NOT_FOUND"
