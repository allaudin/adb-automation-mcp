"""Layer 3 protocol-level E2E tests for start_service — a real fastmcp.Client
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
async def test_start_service_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_service",
            {"serial": "emulator-5554", "component": "com.example.app/.MyService"},
        )

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.component == "com.example.app/.MyService"


@pytest.mark.asyncio
async def test_start_service_tool_accepts_user_id() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_service",
            {"serial": "emulator-5554", "component": "com.example.app/.MyService", "user_id": 10},
        )

    assert result.data.status == "success"
    assert result.data.data.user_id == 10
    assert captured["command"] == "am start-service -n com.example.app/.MyService --user 10"


@pytest.mark.asyncio
async def test_start_service_tool_component_does_not_exist_returns_component_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            start_service_result=CommandResult(
                stdout="Starting service: Intent { cmp=com.example.app/.Bogus }\n",
                stderr="Error: Not found; no service started.\n",
                exit_code=0,
                duration_ms=40.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_service", {"serial": "emulator-5554", "component": "com.example.app/.Bogus"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "COMPONENT_NOT_FOUND"


@pytest.mark.asyncio
async def test_start_service_tool_requires_permission_returns_permission_denied_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            start_service_result=CommandResult(
                stdout="Starting service: Intent { cmp=com.example.app/.MyService }\n",
                stderr="Error: Requires permission com.example.app.permission.BIND_MY_SERVICE\n",
                exit_code=0,
                duration_ms=35.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_service", {"serial": "emulator-5554", "component": "com.example.app/.MyService"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_start_service_tool_background_restriction_returns_background_service_restricted_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            start_service_result=CommandResult(
                stdout="Starting service: Intent { cmp=com.example.app/.MyService }\n",
                stderr=(
                    "Error: java.lang.IllegalStateException: Not allowed to start service Intent "
                    "{ cmp=com.example.app/.MyService }: app is in background uid UidRecord{...}\n"
                ),
                exit_code=0,
                duration_ms=45.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_service", {"serial": "emulator-5554", "component": "com.example.app/.MyService"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "BACKGROUND_SERVICE_RESTRICTED"


@pytest.mark.asyncio
async def test_start_service_tool_adb_failure_returns_device_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            start_service_result=CommandResult(
                stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_service", {"serial": "bogus", "component": "com.example.app/.MyService"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"
