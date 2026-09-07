"""Layer 3 protocol-level E2E tests for list_displays — a real fastmcp.Client
speaking actual MCP protocol to a running FastMCP server instance, backed by
FakeBackend. Kept in its own file (not test_protocol_e2e.py) to avoid
concurrent edits to a shared test file.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_list_displays_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("list_displays", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert [d.display_id for d in result.data.data.displays] == [0, 2]
    assert result.data.data.displays[0].state == "ON"
    assert result.data.data.displays[0].width == 1408
    assert result.data.data.displays[0].density_dpi == 160


@pytest.mark.asyncio
async def test_list_displays_tool_unparseable_output_serializes_as_structured_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            dumpsys_display_result=CommandResult(
                stdout="DISPLAY MANAGER (dumpsys display)\n  mSafeMode=false\n",
                stderr="",
                exit_code=0,
                duration_ms=20.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("list_displays", {"serial": "emulator-5554"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DISPLAY_INFO_UNAVAILABLE"


@pytest.mark.asyncio
async def test_list_displays_tool_unknown_serial_returns_device_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            dumpsys_display_result=CommandResult(
                stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("list_displays", {"serial": "bogus"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"


@pytest.mark.asyncio
async def test_get_display_size_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(
        FakeBackend(
            wm_size_result=CommandResult(
                stdout="Physical size: 1408x792\nOverride size: 1080x720\n",
                stderr="",
                exit_code=0,
                duration_ms=20.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_display_size", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.physical_width == 1408
    assert result.data.data.override_width == 1080
    assert result.data.data.effective_width == 1080


@pytest.mark.asyncio
async def test_get_display_size_tool_negative_display_id_returns_invalid_argument() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_display_size", {"serial": "emulator-5554", "display_id": -1}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_get_display_density_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("get_display_density", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.physical_density == 160
    assert result.data.data.effective_density == 160


@pytest.mark.asyncio
async def test_get_display_density_tool_nonexistent_display_returns_display_info_unavailable() -> (
    None
):
    mcp = _build_test_server(
        FakeBackend(
            wm_density_result=CommandResult(
                stdout="Physical density: -1\n", stderr="", exit_code=0, duration_ms=20.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_display_density", {"serial": "emulator-5554", "display_id": 99}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DISPLAY_INFO_UNAVAILABLE"
