"""Layer 3 protocol-level E2E tests for the user-lifecycle tools (start_user,
is_user_stopped, get_user_state) — a real fastmcp.Client speaking actual MCP
protocol to a running FastMCP server instance, backed by FakeBackend. Kept in
its own file to avoid concurrent edits to a shared test file.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_start_user_tool_round_trips_when_destructive_disallowed() -> None:
    # start_user is `write`, so it's registered without the destructive gate.
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command, timeout_s)

    mcp = _build_test_server(RecordingBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_user",
            {"serial": "emulator-5554", "user_id": 10, "wait": True, "display_id": 2},
        )

    assert result.data.status == "success"
    assert result.data.data.started is True
    assert captured["command"] == "am start-user -w --display 2 10"


@pytest.mark.asyncio
async def test_start_user_tool_error_output_returns_backend_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            start_user_result=CommandResult(
                stdout="Error: could not start user\n", stderr="", exit_code=0, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_user", {"serial": "emulator-5554", "user_id": 999}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "BACKEND_ERROR"


@pytest.mark.asyncio
async def test_start_user_tool_negative_user_id_returns_invalid_argument_error() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_user", {"serial": "emulator-5554", "user_id": -1}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_is_user_stopped_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "is_user_stopped", {"serial": "emulator-5554", "user_id": 10}
        )

    assert result.data.status == "success"
    assert result.data.data.stopped is False


@pytest.mark.asyncio
async def test_is_user_stopped_tool_unknown_user_reports_stopped_true() -> None:
    mcp = _build_test_server(
        FakeBackend(
            is_user_stopped_result=CommandResult(
                stdout="true\n", stderr="", exit_code=0, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "is_user_stopped", {"serial": "emulator-5554", "user_id": 999}
        )

    assert result.data.status == "success"
    assert result.data.data.stopped is True


@pytest.mark.asyncio
async def test_get_user_state_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_user_state", {"serial": "emulator-5554", "user_id": 10}
        )

    assert result.data.status == "success"
    assert result.data.data.started is True
    assert result.data.data.state == "RUNNING_UNLOCKED"


@pytest.mark.asyncio
async def test_get_user_state_tool_not_started_is_success() -> None:
    mcp = _build_test_server(
        FakeBackend(
            user_state_result=CommandResult(
                stdout="User is not started: 11\n", stderr="", exit_code=0, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_user_state", {"serial": "emulator-5554", "user_id": 11}
        )

    assert result.data.status == "success"
    assert result.data.data.started is False
    assert result.data.data.state is None
