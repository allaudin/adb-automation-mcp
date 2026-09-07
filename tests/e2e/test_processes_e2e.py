"""Layer 3 protocol-level E2E tests for force_stop_app — a real fastmcp.Client
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
async def test_force_stop_app_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "force_stop_app", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.package_name == "com.example.app"
    assert result.data.data.output == ""


@pytest.mark.asyncio
async def test_force_stop_app_tool_accepts_user_id() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "force_stop_app",
            {"serial": "emulator-5554", "package_name": "com.example.app", "user_id": 10},
        )

    assert result.data.status == "success"
    assert result.data.data.user_id == 10
    assert captured["command"] == "am force-stop --user 10 com.example.app"


@pytest.mark.asyncio
async def test_force_stop_app_tool_nonexistent_package_is_still_success() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "force_stop_app",
            {"serial": "emulator-5554", "package_name": "com.example.does.not.exist"},
        )

    assert result.data.status == "success"
    assert result.data.data.package_name == "com.example.does.not.exist"


@pytest.mark.asyncio
async def test_force_stop_app_tool_permission_denial_returns_permission_denied_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            force_stop_result=CommandResult(
                stdout="",
                stderr="java.lang.SecurityException: Permission Denial: forceStopPackage()\n",
                exit_code=1,
                duration_ms=12.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "force_stop_app", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_force_stop_app_tool_backend_failure_returns_backend_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            force_stop_result=CommandResult(
                stdout="", stderr="Error: Activity manager has died\n", exit_code=1, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "force_stop_app", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "BACKEND_ERROR"


@pytest.mark.asyncio
async def test_list_processes_tool_round_trips_and_filters_server_side() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "list_processes", {"serial": "emulator-5554", "name_filter": "systemui"}
        )

    assert result.data.status == "success"
    assert result.data.data.name_filter == "systemui"
    assert [p.name for p in result.data.data.processes] == ["com.android.systemui"]
    assert result.data.data.processes[0].pid == 1224


@pytest.mark.asyncio
async def test_list_processes_tool_blank_filter_returns_invalid_argument_error() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "list_processes", {"serial": "emulator-5554", "name_filter": "   "}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_get_process_id_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_process_id", {"serial": "emulator-5554", "name": "com.android.systemui"}
        )

    assert result.data.status == "success"
    assert result.data.data.pids == [1224]
    assert result.data.data.running is True


@pytest.mark.asyncio
async def test_get_process_id_tool_absent_process_is_success_not_running() -> None:
    mcp = _build_test_server(
        FakeBackend(
            pidof_names_result=CommandResult(
                stdout="", stderr="", exit_code=1, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_process_id", {"serial": "emulator-5554", "name": "com.nope.nope"}
        )

    assert result.data.status == "success"
    assert result.data.data.pids == []
    assert result.data.data.running is False


@pytest.mark.asyncio
async def test_kill_background_processes_tool_round_trips_and_accepts_user_id() -> None:
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
            "kill_background_processes",
            {"serial": "emulator-5554", "package_name": "com.example.app", "user_id": 10},
        )

    assert result.data.status == "success"
    assert result.data.data.user_id == 10
    assert captured["command"] == "am kill --user 10 com.example.app"


@pytest.mark.asyncio
async def test_kill_background_processes_tool_is_registered_without_destructive_gate() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert "kill_background_processes" in {tool.name for tool in tools}


@pytest.mark.asyncio
async def test_get_process_memory_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_process_memory", {"serial": "emulator-5554", "target": "com.android.systemui"}
        )

    assert result.data.status == "success"
    assert result.data.data.pid == 1224
    assert result.data.data.total_pss_kb == 105321
    assert result.data.data.total_rss_kb == 268416
    assert result.data.data.java_heap_pss_kb == 28048


@pytest.mark.asyncio
async def test_get_process_memory_tool_not_running_returns_structured_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            dumpsys_meminfo_result=CommandResult(
                stdout="No process found for: com.example.notinstalled\n",
                stderr="",
                exit_code=0,
                duration_ms=10.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_process_memory",
            {"serial": "emulator-5554", "target": "com.example.notinstalled"},
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PACKAGE_NOT_RUNNING"


@pytest.mark.asyncio
async def test_get_process_memory_tool_unparseable_output_returns_structured_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            dumpsys_meminfo_result=CommandResult(
                stdout="Applications Memory Usage (in Kilobytes):\n\n",
                stderr="",
                exit_code=0,
                duration_ms=10.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_process_memory",
            {"serial": "emulator-5554", "target": "com.android.systemui"},
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PROCESS_MEMORY_UNAVAILABLE"
