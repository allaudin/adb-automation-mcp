"""Layer 3 protocol-level E2E tests for tap — a real fastmcp.Client speaking
actual MCP protocol to a running FastMCP server instance, backed by
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
async def test_tap_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("tap", {"serial": "emulator-5554", "x": 500, "y": 800})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.x == 500
    assert result.data.data.y == 800
    assert result.data.data.success is True


@pytest.mark.asyncio
async def test_tap_tool_accepts_display_id() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "tap", {"serial": "emulator-5554", "x": 500, "y": 800, "display_id": 1}
        )

    assert result.data.status == "success"
    assert result.data.data.display_id == 1
    assert captured["command"] == "input -d 1 tap 500 800"


@pytest.mark.asyncio
async def test_tap_tool_negative_coordinates_returns_invalid_argument_error() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("tap", {"serial": "emulator-5554", "x": -1, "y": 800})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_tap_tool_adb_failure_returns_device_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            input_tap_result=CommandResult(
                stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("tap", {"serial": "bogus", "x": 500, "y": 800})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"
