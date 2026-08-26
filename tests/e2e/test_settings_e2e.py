"""Layer 3 protocol-level E2E tests for get_setting — a real fastmcp.Client
speaking actual MCP protocol to a running FastMCP server instance, backed by
FakeBackend. Kept in its own file (not test_protocol_e2e.py) to avoid
concurrent edits to a shared test file.
"""

from __future__ import annotations

import pytest
from fastmcp import Client
from fastmcp.exceptions import ToolError

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_get_setting_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_setting",
            {"serial": "emulator-5554", "namespace": "system", "key": "screen_brightness"},
        )

    assert result.data.status == "success"
    assert result.data.data.namespace == "system"
    assert result.data.data.key == "screen_brightness"
    assert result.data.data.value == "128"


@pytest.mark.asyncio
async def test_get_setting_tool_accepts_secure_namespace_and_user_id() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(
        RecordingBackend(
            get_setting_result=CommandResult(stdout="1\n", stderr="", exit_code=0, duration_ms=15.0)
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_setting",
            {
                "serial": "emulator-5554",
                "namespace": "secure",
                "key": "location_mode",
                "user_id": 10,
            },
        )

    assert result.data.status == "success"
    assert result.data.data.namespace == "secure"
    assert result.data.data.user_id == 10
    assert captured["command"] == "settings --user 10 get secure location_mode"


@pytest.mark.asyncio
async def test_get_setting_tool_accepts_global_namespace() -> None:
    mcp = _build_test_server(
        FakeBackend(
            get_setting_result=CommandResult(stdout="0\n", stderr="", exit_code=0, duration_ms=15.0)
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_setting",
            {"serial": "emulator-5554", "namespace": "global", "key": "airplane_mode_on"},
        )

    assert result.data.status == "success"
    assert result.data.data.namespace == "global"
    assert result.data.data.value == "0"


@pytest.mark.asyncio
async def test_get_setting_tool_invalid_namespace_rejected_before_execution() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool(
                "get_setting",
                {"serial": "emulator-5554", "namespace": "bogus", "key": "screen_brightness"},
            )

    assert "command" not in captured


@pytest.mark.asyncio
async def test_get_setting_tool_missing_value_returns_none() -> None:
    mcp = _build_test_server(
        FakeBackend(
            get_setting_result=CommandResult(
                stdout="null\n", stderr="", exit_code=0, duration_ms=15.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_setting",
            {"serial": "emulator-5554", "namespace": "system", "key": "nonexistent_key"},
        )

    assert result.data.status == "success"
    assert result.data.data.value is None


@pytest.mark.asyncio
async def test_get_setting_tool_adb_failure_returns_device_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            get_setting_result=CommandResult(
                stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_setting", {"serial": "bogus", "namespace": "system", "key": "screen_brightness"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"
