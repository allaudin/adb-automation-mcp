"""Layer 3 protocol-level E2E tests for query_content — a real fastmcp.Client
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
async def test_query_content_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "query_content",
            {"serial": "emulator-5554", "uri": "content://settings/system"},
        )

    assert result.data.status == "success"
    assert result.data.data.row_count == 5
    assert result.data.data.rows[2]["name"] == "volume_music"
    assert result.data.data.rows[4]["value"] is None


@pytest.mark.asyncio
async def test_query_content_tool_registered_and_not_destructive() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}

    assert "query_content" in tools


@pytest.mark.asyncio
async def test_query_content_tool_no_result_is_success_empty() -> None:
    mcp = _build_test_server(
        FakeBackend(
            content_query_result=CommandResult(
                stdout="No result found.\n", stderr="", exit_code=0, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "query_content", {"serial": "emulator-5554", "uri": "content://x/y"}
        )

    assert result.data.status == "success"
    assert result.data.data.rows == []


@pytest.mark.asyncio
async def test_query_content_tool_bad_uri_returns_invalid_argument_error() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "query_content", {"serial": "emulator-5554", "uri": "not-a-uri"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_query_content_tool_missing_provider_returns_structured_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            content_query_result=CommandResult(
                stdout=(
                    "Error while accessing provider:nope\n"
                    "java.lang.IllegalStateException: Could not find provider: nope\n"
                ),
                stderr="",
                exit_code=0,
                duration_ms=10.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "query_content", {"serial": "emulator-5554", "uri": "content://nope/x"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "CONTENT_PROVIDER_NOT_FOUND"
