"""Layer 3 protocol-level E2E tests (ADR-004/ARCHITECTURE.md §9): a real
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


def _build_test_server(backend: FakeBackend) -> FastMCP:
    manifests = discover_modules()
    registry = Registry(policy=PolicyEngine(PolicyConfig()))

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
