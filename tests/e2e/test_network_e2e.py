"""Layer 3 protocol-level E2E tests for list_network_interfaces — a real
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


@pytest.mark.asyncio
async def test_get_routes_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(
        FakeBackend(
            ip_route_result=CommandResult(
                stdout=(
                    "default via 10.0.2.2 dev eth0\n"
                    "10.0.2.0/24 dev eth0 proto kernel scope link src 10.0.2.15\n"
                ),
                stderr="",
                exit_code=0,
                duration_ms=20.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_routes", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert [r.destination for r in result.data.data.routes] == ["default", "10.0.2.0/24"]
    assert result.data.data.routes[0].is_default is True
    assert result.data.data.routes[0].gateway == "10.0.2.2"


@pytest.mark.asyncio
async def test_get_routes_tool_empty_output_is_success_with_no_routes() -> None:
    mcp = _build_test_server(
        FakeBackend(
            ip_route_result=CommandResult(
                stdout="", stderr="", exit_code=0, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_routes", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.routes == []


@pytest.mark.asyncio
async def test_get_connectivity_state_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("get_connectivity_state", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.has_active_network is True
    assert result.data.data.active_network_id == 100
    assert result.data.data.active_network is not None
    assert result.data.data.active_network.validated is True


@pytest.mark.asyncio
async def test_get_connectivity_state_tool_unrecognized_output_returns_structured_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            dumpsys_connectivity_result=CommandResult(
                stdout="Can't find service: connectivity\n",
                stderr="",
                exit_code=0,
                duration_ms=10.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_connectivity_state", {"serial": "emulator-5554"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "CONNECTIVITY_STATE_UNAVAILABLE"
