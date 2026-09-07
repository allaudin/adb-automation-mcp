"""Layer 3 protocol-level E2E tests for run_instrumentation — a real
fastmcp.Client speaking actual MCP protocol to a running FastMCP server
instance, backed by FakeBackend. Kept in its own file (not
test_protocol_e2e.py) to avoid concurrent edits to a shared test file.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server

_COMPONENT = "com.example.test/androidx.test.runner.AndroidJUnitRunner"


@pytest.mark.asyncio
async def test_run_instrumentation_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "run_instrumentation", {"serial": "emulator-5554", "component": _COMPONENT}
        )

    assert result.data.status == "success"
    assert result.data.data.completed is True
    assert result.data.data.tests_passed == 2
    assert result.data.data.result_code == -1


@pytest.mark.asyncio
async def test_run_instrumentation_tool_is_registered_without_destructive_gate() -> None:
    # run_instrumentation is `write`, not `destructive`.
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}

    assert "run_instrumentation" in tools


@pytest.mark.asyncio
async def test_run_instrumentation_tool_accepts_typed_e_args() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command, timeout_s)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "run_instrumentation",
            {
                "serial": "emulator-5554",
                "component": _COMPONENT,
                "args": {"class": "com.example.FooTest"},
            },
        )

    assert result.data.status == "success"
    assert "-e class com.example.FooTest" in captured["command"]


@pytest.mark.asyncio
async def test_run_instrumentation_tool_bad_timeout_returns_invalid_argument_error() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "run_instrumentation",
            {"serial": "emulator-5554", "component": _COMPONENT, "timeout_s": 9999},
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_run_instrumentation_tool_unable_to_start_returns_structured_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            instrument_result=CommandResult(
                stdout=(
                    "android.util.AndroidException: INSTRUMENTATION_FAILED: bogus/bogus.Runner\n"
                    "INSTRUMENTATION_STATUS: Error=Unable to find instrumentation info for: "
                    "ComponentInfo{bogus/bogus.Runner}\n"
                    "INSTRUMENTATION_STATUS_CODE: -1\n"
                ),
                stderr="",
                exit_code=0,
                duration_ms=10.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "run_instrumentation",
            {"serial": "emulator-5554", "component": "bogus/bogus.Runner"},
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "INSTRUMENTATION_FAILED"
