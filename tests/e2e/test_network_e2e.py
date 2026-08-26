"""Layer 3 protocol-level E2E tests for list_network_interfaces — a real
fastmcp.Client speaking actual MCP protocol to a running FastMCP server
instance, backed by FakeBackend. Kept in its own file (not
test_protocol_e2e.py) to avoid concurrent edits to a shared test file.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_list_network_interfaces_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("list_network_interfaces", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    names = [iface.name for iface in result.data.data.interfaces]
    assert names == ["lo", "wlan0", "rmnet_data0"]


@pytest.mark.asyncio
async def test_list_network_interfaces_tool_no_addresses_on_down_interface() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("list_network_interfaces", {"serial": "emulator-5554"})

    down_iface = result.data.data.interfaces[2]
    assert down_iface.state == "DOWN"
    assert down_iface.ipv4_addresses == []
    assert down_iface.ipv6_addresses == []


@pytest.mark.asyncio
async def test_list_network_interfaces_tool_malformed_output_returns_empty_list() -> None:
    mcp = _build_test_server(
        FakeBackend(
            ip_addr_show_result=CommandResult(
                stdout="totally unrecognizable garbage\n", stderr="", exit_code=0, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("list_network_interfaces", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.interfaces == []


@pytest.mark.asyncio
async def test_list_network_interfaces_tool_command_unavailable_returns_network_tool_unavailable_error() -> (
    None
):
    mcp = _build_test_server(
        FakeBackend(
            ip_addr_show_result=CommandResult(
                stdout="", stderr="/system/bin/sh: ip: not found\n", exit_code=127, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("list_network_interfaces", {"serial": "emulator-5554"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "NETWORK_TOOL_UNAVAILABLE"


@pytest.mark.asyncio
async def test_list_network_interfaces_tool_adb_failure_returns_device_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            ip_addr_show_result=CommandResult(
                stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("list_network_interfaces", {"serial": "bogus"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"
