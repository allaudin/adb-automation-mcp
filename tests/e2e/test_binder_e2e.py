"""Layer 3 protocol-level E2E tests for the binder module."""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_get_binder_call_stats_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("get_binder_call_stats", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.collecting is True
    assert result.data.data.calls_count == 722
    assert result.data.data.top_callers[0].who == "com.android.systemui/10141"


@pytest.mark.asyncio
async def test_get_binder_call_stats_tool_not_collecting_is_success() -> None:
    mcp = _build_test_server(
        FakeBackend(
            binder_calls_stats_result=CommandResult(
                stdout=(
                    "Sampling interval period: 1000\n"
                    "  Summary: total_cpu_time=0, calls_count=0, avg_call_cpu_time=NaN\n"
                ),
                stderr="",
                exit_code=0,
                duration_ms=5.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_binder_call_stats", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.collecting is False


@pytest.mark.asyncio
async def test_get_binder_call_stats_tool_bad_limit_returns_invalid_argument() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_binder_call_stats", {"serial": "emulator-5554", "limit": 0}
        )

    assert result.data.status == "error"
    assert result.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_reset_binder_call_stats_tool_round_trips_without_gate() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}
        result = await client.call_tool("reset_binder_call_stats", {"serial": "emulator-5554"})

    assert "reset_binder_call_stats" in tools
    assert result.data.status == "success"
    assert result.data.data.reset is True
