"""Layer 3 protocol-level E2E tests for list_packages — a real fastmcp.Client
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
async def test_list_packages_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("list_packages", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.packages == [
        "com.android.chrome",
        "com.example.thirdparty",
        "com.android.systemui",
    ]


@pytest.mark.asyncio
async def test_list_packages_tool_empty_list_is_success_not_error() -> None:
    backend = FakeBackend(
        list_packages_result=CommandResult(stdout="", stderr="", exit_code=0, duration_ms=50.0)
    )
    mcp = _build_test_server(backend)

    async with Client(mcp) as client:
        result = await client.call_tool("list_packages", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.packages == []


@pytest.mark.asyncio
async def test_list_packages_tool_accepts_user_id_and_package_filter() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "list_packages",
            {"serial": "emulator-5554", "user_id": 10, "package_filter": "third_party"},
        )

    assert result.data.status == "success"
    assert captured["command"] == "pm list packages -3 --user 10"


@pytest.mark.asyncio
async def test_list_packages_tool_unknown_serial_returns_device_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            list_packages_result=CommandResult(
                stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("list_packages", {"serial": "bogus"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"
