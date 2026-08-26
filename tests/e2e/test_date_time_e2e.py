"""Layer 3 protocol-level E2E tests for get_date_time — a real fastmcp.Client
speaking actual MCP protocol to a running FastMCP server instance, backed by
FakeBackend. Kept in its own file (not test_protocol_e2e.py) to avoid
concurrent edits to a shared test file.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_get_date_time_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("get_date_time", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.timestamp == "2026-08-26T18:23:45"
    assert result.data.data.utc_offset == "+0000"


@pytest.mark.asyncio
async def test_get_date_time_tool_malformed_output_returns_device_clock_unavailable_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            device_timestamp_result=CommandResult(
                stdout="not a timestamp\n", stderr="", exit_code=0, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_date_time", {"serial": "emulator-5554"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_CLOCK_UNAVAILABLE"


@pytest.mark.asyncio
async def test_get_date_time_tool_unsupported_offset_format_degrades_to_none() -> None:
    mcp = _build_test_server(
        FakeBackend(
            device_utc_offset_result=CommandResult(
                stdout="%z\n", stderr="", exit_code=0, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_date_time", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.timestamp == "2026-08-26T18:23:45"
    assert result.data.data.utc_offset is None


@pytest.mark.asyncio
async def test_get_date_time_tool_adb_failure_returns_device_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            device_timestamp_result=CommandResult(
                stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_date_time", {"serial": "bogus"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"
