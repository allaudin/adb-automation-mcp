"""Layer 3 protocol-level E2E tests for the graphics module."""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_get_frame_stats_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_frame_stats", {"serial": "emulator-5554", "package": "com.example.app"}
        )

    assert result.data.status == "success"
    assert result.data.data.total_frames_rendered == 728
    assert result.data.data.janky_percent == 22.53
    assert result.data.data.counters["missed_vsync"] == 14
    assert result.data.data.histogram is None


@pytest.mark.asyncio
async def test_get_frame_stats_tool_include_histogram() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_frame_stats",
            {"serial": "emulator-5554", "package": "com.example.app", "include_histogram": True},
        )

    assert result.data.status == "success"
    assert result.data.data.histogram["5ms"] == 291


@pytest.mark.asyncio
async def test_get_frame_stats_tool_not_running_is_structured_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            gfxinfo_framestats_result=CommandResult(
                stdout="No process found for: com.x\n", stderr="", exit_code=0, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_frame_stats", {"serial": "emulator-5554", "package": "com.x"}
        )

    assert result.data.status == "error"
    assert result.data.error.code == "PACKAGE_NOT_RUNNING"


@pytest.mark.asyncio
async def test_reset_frame_stats_tool_round_trips_and_is_registered_without_gate() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}
        result = await client.call_tool(
            "reset_frame_stats", {"serial": "emulator-5554", "package": "com.example.app"}
        )

    assert "reset_frame_stats" in tools
    assert result.data.status == "success"
    assert result.data.data.reset is True
