"""Layer 3 protocol-level E2E tests for get_power_state — a real
fastmcp.Client speaking actual MCP protocol to a running FastMCP server
instance, backed by FakeBackend. Kept in its own file (not
test_protocol_e2e.py) to avoid concurrent edits to a shared test file.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_get_power_state_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("get_power_state", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.wakefulness == "Awake"
    assert result.data.data.interactive is True


@pytest.mark.asyncio
async def test_get_power_state_tool_missing_interactive_field_is_none() -> None:
    mcp = _build_test_server(
        FakeBackend(
            dumpsys_power_result=CommandResult(
                stdout="Power Manager State:\n  mWakefulness=Asleep\n",
                stderr="",
                exit_code=0,
                duration_ms=100.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_power_state", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.wakefulness == "Asleep"
    assert result.data.data.interactive is None


@pytest.mark.asyncio
async def test_get_power_state_tool_malformed_output_returns_power_state_unavailable_error() -> (
    None
):
    mcp = _build_test_server(
        FakeBackend(
            dumpsys_power_result=CommandResult(
                stdout="Can't find service: power\n", stderr="", exit_code=0, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_power_state", {"serial": "emulator-5554"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "POWER_STATE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_get_power_state_tool_adb_failure_returns_device_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            dumpsys_power_result=CommandResult(
                stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_power_state", {"serial": "bogus"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"
