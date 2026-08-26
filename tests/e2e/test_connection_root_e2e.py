"""Layer 3 protocol-level E2E tests (see ARCHITECTURE.md §9) for
restart_adbd_as_root specifically, kept in its own file rather than added to
test_protocol_e2e.py to avoid two agents racing on the same shared fixture
file while working on separate modules in parallel.

Reuses _build_test_server from test_protocol_e2e.py rather than duplicating
the server-wiring helper.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_restart_adbd_as_root_tool_round_trips_over_mcp_protocol() -> None:
    # destructive category: only registered when the server explicitly opts in.
    mcp = _build_test_server(FakeBackend(), allow_destructive=True)

    async with Client(mcp) as client:
        result = await client.call_tool("restart_adbd_as_root", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.success is True
    assert result.data.data.already_root is False


@pytest.mark.asyncio
async def test_restart_adbd_as_root_tool_already_root_round_trips_over_mcp_protocol() -> None:
    backend = FakeBackend(
        root_result=CommandResult(
            stdout="adbd is already running as root\n", stderr="", exit_code=0, duration_ms=50.0
        )
    )
    mcp = _build_test_server(backend, allow_destructive=True)

    async with Client(mcp) as client:
        result = await client.call_tool("restart_adbd_as_root", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.success is True
    assert result.data.data.already_root is True


@pytest.mark.asyncio
async def test_restart_adbd_as_root_tool_production_build_reports_success_false() -> None:
    backend = FakeBackend(
        root_result=CommandResult(
            stdout="adbd cannot run as root in production builds\n", stderr="", exit_code=0, duration_ms=30.0
        )
    )
    mcp = _build_test_server(backend, allow_destructive=True)

    async with Client(mcp) as client:
        result = await client.call_tool("restart_adbd_as_root", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.success is False
    assert result.data.data.already_root is False
    assert "production builds" in result.data.data.output


@pytest.mark.asyncio
async def test_restart_adbd_as_root_tool_not_registered_when_destructive_disallowed() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert "restart_adbd_as_root" not in {tool.name for tool in tools}
