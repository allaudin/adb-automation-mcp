"""Layer 3 protocol-level E2E tests (see ARCHITECTURE.md §9) for
restart_adbd_as_shell specifically, kept in its own file rather than added to
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
async def test_restart_adbd_as_shell_tool_round_trips_over_mcp_protocol() -> None:
    # write category (not destructive): registered without an opt-in.
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("restart_adbd_as_shell", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.success is True
    assert result.data.data.already_shell is False
    assert "non root" in result.data.data.output


@pytest.mark.asyncio
async def test_restart_adbd_as_shell_tool_already_non_root_round_trips() -> None:
    backend = FakeBackend(
        unroot_result=CommandResult(
            stdout="adbd not running as root\n", stderr="", exit_code=0, duration_ms=20.0
        )
    )
    mcp = _build_test_server(backend)

    async with Client(mcp) as client:
        result = await client.call_tool("restart_adbd_as_shell", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.success is True
    assert result.data.data.already_shell is True


@pytest.mark.asyncio
async def test_restart_adbd_as_shell_tool_unknown_serial_serializes_as_device_not_found() -> None:
    backend = FakeBackend(
        unroot_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    mcp = _build_test_server(backend)

    async with Client(mcp) as client:
        result = await client.call_tool("restart_adbd_as_shell", {"serial": "bogus"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"


@pytest.mark.asyncio
async def test_restart_adbd_as_shell_tool_registered_by_default() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert "restart_adbd_as_shell" in {tool.name for tool in tools}
