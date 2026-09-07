"""Layer 3 protocol-level E2E tests for get_process_exit_history."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.modules.debugging.service import DebuggingService
from adb_automation_mcp.policy import PolicyConfig, PolicyEngine
from adb_automation_mcp.registry import Registry, discover_modules
from tests.e2e.test_protocol_e2e import _build_test_server


def _server_with_local_root(backend: FakeBackend, local_root: Path | None) -> FastMCP:
    manifests = discover_modules()
    registry = Registry(policy=PolicyEngine(PolicyConfig()))

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        services = registry.build_services(backend, manifests)
        services["debugging"] = DebuggingService(backend, local_root=local_root)
        yield {"backend": backend, "services": services}

    mcp = FastMCP("test-server", lifespan=lifespan)
    registry.register_tools(mcp, manifests)
    registry.register_resources(mcp, manifests)
    return mcp


@pytest.mark.asyncio
async def test_get_process_exit_history_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_process_exit_history",
            {"serial": "emulator-5554", "package": "com.example.app"},
        )

    assert result.data.status == "success"
    assert result.data.data.count == 2
    assert result.data.data.records[0].reason == "APP CRASH(EXCEPTION)"
    assert result.data.data.records[1].trace_available is True


@pytest.mark.asyncio
async def test_get_process_exit_history_tool_registered_and_read() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}

    assert "get_process_exit_history" in tools


@pytest.mark.asyncio
async def test_get_process_exit_history_tool_no_history_is_success_empty() -> None:
    mcp = _build_test_server(
        FakeBackend(
            activity_exit_info_result=CommandResult(
                stdout="ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)\n",
                stderr="",
                exit_code=0,
                duration_ms=5.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_process_exit_history", {"serial": "emulator-5554", "package": "com.x"}
        )

    assert result.data.status == "success"
    assert result.data.data.records == []


@pytest.mark.asyncio
async def test_get_process_exit_history_tool_blank_package_returns_invalid_argument() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_process_exit_history", {"serial": "emulator-5554", "package": "  "}
        )

    assert result.data.status == "error"
    assert result.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_set_debug_app_tool_round_trips_and_flags() -> None:
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
            "set_debug_app",
            {
                "serial": "emulator-5554",
                "package": "com.example.app",
                "wait_for_debugger": True,
                "persistent": True,
            },
        )

    assert result.data.status == "success"
    assert result.data.data.wait_for_debugger is True
    assert captured["command"] == "am set-debug-app -w --persistent com.example.app"


@pytest.mark.asyncio
async def test_clear_debug_app_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}
        result = await client.call_tool("clear_debug_app", {"serial": "emulator-5554"})

    assert "clear_debug_app" in tools
    assert result.data.status == "success"
    assert result.data.data.cleared is True


@pytest.mark.asyncio
async def test_list_jdwp_processes_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("list_jdwp_processes", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.pids == [1224, 1568, 2411]


@pytest.mark.asyncio
async def test_list_jdwp_processes_tool_device_offline_is_structured_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            jdwp_result=CommandResult(
                stdout="", stderr="error: device offline\n", exit_code=1, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("list_jdwp_processes", {"serial": "emulator-5554"})

    assert result.data.status == "error"
    assert result.data.error.code == "DEVICE_NOT_FOUND"


@pytest.mark.asyncio
async def test_capture_native_backtrace_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "capture_native_backtrace", {"serial": "emulator-5554", "pid": 1224}
        )

    assert result.data.status == "success"
    assert result.data.data.process_name == "com.android.systemui"
    assert result.data.data.thread_count == 2


@pytest.mark.asyncio
async def test_capture_native_backtrace_tool_root_required_is_structured_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            debuggerd_backtrace_result=CommandResult(
                stdout="debuggerd: root is required\n", stderr="", exit_code=0, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "capture_native_backtrace", {"serial": "emulator-5554", "pid": 1224}
        )

    assert result.data.status == "error"
    assert result.data.error.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_capture_native_backtrace_tool_bad_pid_returns_invalid_argument() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "capture_native_backtrace", {"serial": "emulator-5554", "pid": 0}
        )

    assert result.data.status == "error"
    assert result.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_capture_native_tombstone_tool_round_trips_with_local_root(tmp_path: Path) -> None:
    mcp = _server_with_local_root(FakeBackend(), tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "capture_native_tombstone",
            {"serial": "emulator-5554", "pid": 1224, "local_path": "sysui.txt"},
        )

    assert result.data.status == "success"
    assert result.data.data.local_path == str(tmp_path / "tombstones" / "sysui.txt")
    assert result.data.data.frame_count == 24
    assert result.data.data.device_tombstone_ref == "tombstone_27.pb"


@pytest.mark.asyncio
async def test_capture_native_tombstone_tool_no_local_root_returns_policy_denied(
    tmp_path: Path,
) -> None:
    mcp = _server_with_local_root(FakeBackend(), None)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "capture_native_tombstone",
            {"serial": "emulator-5554", "pid": 1224, "local_path": "x.txt"},
        )

    assert result.data.status == "error"
    assert result.data.error.code == "POLICY_DENIED"


@pytest.mark.asyncio
async def test_capture_native_tombstone_tool_registered_without_gate() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}

    assert "capture_native_tombstone" in tools
