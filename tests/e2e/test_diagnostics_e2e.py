"""Layer 3 protocol-level E2E tests for get_adb_version — a real fastmcp.Client
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
async def test_get_adb_version_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("get_adb_version", {})

    assert result.data.status == "success"
    assert result.data.data.bridge_version == "1.0.41"
    assert result.data.data.platform_tools_version == "37.0.0-eng.allaud"
    assert result.data.data.running_on == "Linux 6.8.0-138-generic (x86_64)"


@pytest.mark.asyncio
async def test_get_adb_version_tool_malformed_output_serializes_as_success_with_nulls() -> None:
    mcp = _build_test_server(
        FakeBackend(
            version_result=CommandResult(
                stdout="garbage\n", stderr="", exit_code=0, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_adb_version", {})

    assert result.data.status == "success"
    assert result.data.data.bridge_version is None
    assert result.data.data.raw == "garbage"


@pytest.mark.asyncio
async def test_get_adb_version_tool_non_zero_exit_serializes_as_backend_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            version_result=CommandResult(
                stdout="", stderr="adb: broken\n", exit_code=2, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_adb_version", {})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "BACKEND_ERROR"


@pytest.mark.asyncio
async def test_get_adb_version_tool_adb_unavailable_serializes_as_error() -> None:
    mcp = _build_test_server(FakeBackend(unavailable=True))

    async with Client(mcp) as client:
        result = await client.call_tool("get_adb_version", {})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "ADB_UNAVAILABLE"
