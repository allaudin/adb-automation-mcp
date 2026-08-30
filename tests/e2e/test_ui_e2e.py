"""Layer 3 protocol-level E2E tests for dump_ui_hierarchy — a real
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
async def test_dump_ui_hierarchy_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("dump_ui_hierarchy", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.node_count == 2
    assert "<hierarchy" in result.data.data.xml


@pytest.mark.asyncio
async def test_dump_ui_hierarchy_tool_empty_hierarchy_returns_zero_nodes() -> None:
    mcp = _build_test_server(
        FakeBackend(
            ui_hierarchy_cat_result=CommandResult(stdout="", stderr="", exit_code=0, duration_ms=5.0)
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("dump_ui_hierarchy", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.xml == ""
    assert result.data.data.node_count == 0


@pytest.mark.asyncio
async def test_dump_ui_hierarchy_tool_null_root_node_returns_ui_hierarchy_unavailable_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            uiautomator_dump_result=CommandResult(
                stdout="",
                stderr="ERROR: null root node returned by UiTestAutomationBridge.\n",
                exit_code=0,
                duration_ms=800.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("dump_ui_hierarchy", {"serial": "emulator-5554"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "UI_HIERARCHY_UNAVAILABLE"


@pytest.mark.asyncio
async def test_dump_ui_hierarchy_tool_uiautomator_failure_returns_uiautomator_failed_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            uiautomator_dump_result=CommandResult(
                stdout="", stderr="/system/bin/sh: uiautomator: not found\n", exit_code=127, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("dump_ui_hierarchy", {"serial": "emulator-5554"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "UIAUTOMATOR_FAILED"


@pytest.mark.asyncio
async def test_dump_ui_hierarchy_tool_adb_failure_returns_device_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            uiautomator_dump_result=CommandResult(
                stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("dump_ui_hierarchy", {"serial": "bogus"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"


@pytest.mark.asyncio
async def test_dump_ui_hierarchy_tool_backend_unavailable_returns_adb_unavailable_error() -> None:
    mcp = _build_test_server(FakeBackend(unavailable=True))

    async with Client(mcp) as client:
        result = await client.call_tool("dump_ui_hierarchy", {"serial": "emulator-5554"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "ADB_UNAVAILABLE"
