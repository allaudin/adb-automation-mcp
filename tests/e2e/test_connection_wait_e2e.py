"""Layer 3 protocol-level E2E tests (see ARCHITECTURE.md §9) for
wait_for_device_state specifically, kept in its own file rather than added to
test_protocol_e2e.py to avoid two agents racing on the same shared fixture file
while working on separate modules in parallel.

Reuses _build_test_server from test_protocol_e2e.py rather than duplicating the
server-wiring helper.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_wait_for_device_state_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "wait_for_device_state", {"serial": "emulator-5554", "state": "device"}
        )

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.state == "device"
    assert result.data.data.transport == "any"
    assert result.data.data.waited_ms >= 0


@pytest.mark.asyncio
async def test_wait_for_device_state_tool_defaults_state_to_device() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("wait_for_device_state", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.state == "device"


@pytest.mark.asyncio
async def test_wait_for_device_state_tool_timeout_serializes_as_retryable_error() -> None:
    mcp = _build_test_server(FakeBackend(wait_for_device_timeout=True))

    async with Client(mcp) as client:
        result = await client.call_tool(
            "wait_for_device_state",
            {"serial": "emulator-5554", "state": "bootloader", "timeout_s": 2},
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "TIMEOUT"
    assert result.data.error.retryable is True


@pytest.mark.asyncio
async def test_wait_for_device_state_tool_rejects_unknown_state_via_input_schema() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        with pytest.raises(Exception):  # noqa: B017 - fastmcp raises on schema violation
            await client.call_tool(
                "wait_for_device_state", {"serial": "emulator-5554", "state": "banana"}
            )


@pytest.mark.asyncio
async def test_wait_for_device_state_tool_nonzero_exit_serializes_as_backend_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            wait_for_device_result=CommandResult(
                stdout="", stderr="error: bad wait-for- state\n", exit_code=1, duration_ms=3.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("wait_for_device_state", {"serial": "emulator-5554"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "BACKEND_ERROR"


@pytest.mark.asyncio
async def test_wait_for_device_state_tool_registered_by_default() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert "wait_for_device_state" in {tool.name for tool in tools}
