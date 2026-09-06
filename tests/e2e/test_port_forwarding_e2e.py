"""Layer 3 protocol-level E2E tests for create_forward — a real fastmcp.Client
speaking actual MCP protocol to a running FastMCP server instance, backed by
FakeBackend. Kept in its own file (not test_protocol_e2e.py) to avoid concurrent
edits to a shared test file.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_create_forward_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "create_forward",
            {"serial": "emulator-5554", "remote_port": 8080, "local_port": 6100},
        )

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.local_port == 6100
    assert result.data.data.remote_port == 8080
    assert result.data.data.local_spec == "tcp:6100"
    assert result.data.data.remote_spec == "tcp:8080"


@pytest.mark.asyncio
async def test_create_forward_tool_auto_allocates_local_port_when_zero() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "create_forward", {"serial": "emulator-5554", "remote_port": 8080}
        )

    assert result.data.status == "success"
    assert result.data.data.local_port == 41000


@pytest.mark.asyncio
async def test_create_forward_tool_conflict_serializes_as_structured_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            forward_result=CommandResult(
                stdout="",
                stderr="adb: error: cannot rebind existing socket\n",
                exit_code=1,
                duration_ms=4.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "create_forward",
            {
                "serial": "emulator-5554",
                "remote_port": 9999,
                "local_port": 6100,
                "no_rebind": True,
            },
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PORT_FORWARD_CONFLICT"


@pytest.mark.asyncio
async def test_create_forward_tool_out_of_range_port_rejected_by_input_schema_or_service() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "create_forward",
            {"serial": "emulator-5554", "remote_port": 70000, "local_port": 6100},
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_create_forward_tool_is_registered() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert "create_forward" in {tool.name for tool in tools}
