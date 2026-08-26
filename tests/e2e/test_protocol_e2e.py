"""Layer 3 protocol-level E2E tests (see ARCHITECTURE.md §9): a real
fastmcp.Client speaking actual MCP protocol to a running FastMCP server instance,
backed by FakeBackend. This is the layer that catches registration/schema/
serialization bugs unit tests can't see, because neither Layer 0 (typing +
docstrings) nor Layer 1 (service-class-direct) goes through fastmcp's actual
serialization — e.g. the adb://devices resource this module used to register
returned pydantic model instances that fastmcp's resource-read path couldn't
JSON-encode, invisible to either lower layer.

_build_test_server still calls register_resources even though no module
currently declares any resources, so that machinery stays exercised for
whenever one does.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from adb_mcp.backend.protocol import DeviceInfo
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.policy import PolicyConfig, PolicyEngine
from adb_mcp.registry import Registry, discover_modules


def _build_test_server(backend: FakeBackend, *, allow_destructive: bool = False) -> FastMCP:
    manifests = discover_modules()
    registry = Registry(policy=PolicyEngine(PolicyConfig(allow_destructive=allow_destructive)))

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        yield {"backend": backend, "services": registry.build_services(backend, manifests)}

    mcp = FastMCP("test-server", lifespan=lifespan)
    registry.register_tools(mcp, manifests)
    registry.register_resources(mcp, manifests)
    return mcp


@pytest.mark.asyncio
async def test_check_adb_available_tool_round_trips_over_mcp_protocol() -> None:
    backend = FakeBackend(devices=[DeviceInfo(serial="emulator-5554", state="device")])
    mcp = _build_test_server(backend)

    async with Client(mcp) as client:
        result = await client.call_tool("check_adb_available", {})

    assert result.data.status == "success"
    assert result.data.data.available is True
    assert result.data.data.device_count == 1


@pytest.mark.asyncio
async def test_list_connected_devices_tool_round_trips_over_mcp_protocol() -> None:
    backend = FakeBackend(
        devices=[DeviceInfo(serial="emulator-5554", state="device", model="Pixel", product="redfin")]
    )
    mcp = _build_test_server(backend)

    async with Client(mcp) as client:
        result = await client.call_tool("list_connected_devices", {})

    assert result.data.status == "success"
    assert len(result.data.data) == 1
    assert result.data.data[0].serial == "emulator-5554"
    assert result.data.data[0].model == "Pixel"


@pytest.mark.asyncio
async def test_list_connected_devices_tool_empty_when_no_devices_connected() -> None:
    mcp = _build_test_server(FakeBackend(devices=[]))

    async with Client(mcp) as client:
        result = await client.call_tool("list_connected_devices", {})

    assert result.data.status == "success"
    assert result.data.data == []


@pytest.mark.asyncio
async def test_restart_adb_server_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("restart_adb_server", {})

    assert result.data.status == "success"
    assert result.data.data.success is True


@pytest.mark.asyncio
async def test_connect_device_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("connect_device", {"host": "192.168.1.50", "port": 5555})

    assert result.data.status == "success"
    assert result.data.data.success is True
    assert result.data.data.address == "192.168.1.50:5555"


@pytest.mark.asyncio
async def test_connect_device_tool_defaults_port_to_5555() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("connect_device", {"host": "192.168.1.50"})

    assert result.data.data.address == "192.168.1.50:5555"


@pytest.mark.asyncio
async def test_disconnect_device_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("disconnect_device", {"host": "192.168.1.50", "port": 5555})

    assert result.data.status == "success"
    assert result.data.data.success is True
    assert result.data.data.address == "192.168.1.50:5555"


@pytest.mark.asyncio
async def test_get_current_user_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("get_current_user", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.user_id == 0


@pytest.mark.asyncio
async def test_dump_user_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("dump_user", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert "UserInfo" in result.data.data.output


@pytest.mark.asyncio
async def test_user_info_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("user_info", {"serial": "emulator-5554", "user_id": 10})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.user_id == 10
    assert "UserInfo{10:" in result.data.data.output


@pytest.mark.asyncio
async def test_list_users_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("list_users", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert len(result.data.data.users) == 2
    assert result.data.data.users[1].user_id == 10
    assert result.data.data.users[1].name == "Driver"


@pytest.mark.asyncio
async def test_switch_user_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("switch_user", {"serial": "emulator-5554", "user_id": 0})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.user_id == 0


@pytest.mark.asyncio
async def test_create_user_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("create_user", {"serial": "emulator-5554", "name": "Guest"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.user_id == 12
    assert result.data.data.name == "Guest"


@pytest.mark.asyncio
async def test_remove_user_tool_round_trips_over_mcp_protocol() -> None:
    # destructive category: only registered when the server explicitly opts in.
    mcp = _build_test_server(FakeBackend(), allow_destructive=True)

    async with Client(mcp) as client:
        result = await client.call_tool("remove_user", {"serial": "emulator-5554", "user_id": 12})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.user_id == 12


@pytest.mark.asyncio
async def test_remove_user_tool_not_registered_when_destructive_disallowed() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert "remove_user" not in {tool.name for tool in tools}
