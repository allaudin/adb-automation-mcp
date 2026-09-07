"""Layer 3 protocol-level E2E tests for the memory module — a real
fastmcp.Client speaking actual MCP protocol to a running FastMCP server
instance, backed by FakeBackend. Kept in its own file to avoid concurrent
edits to a shared test file.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.modules.memory.service import MemoryService
from adb_automation_mcp.policy import PolicyConfig, PolicyEngine
from adb_automation_mcp.registry import Registry, discover_modules
from tests.e2e.test_protocol_e2e import _build_test_server


def _server_with_local_root(backend: FakeBackend, local_root: Path | None) -> FastMCP:
    manifests = discover_modules()
    registry = Registry(policy=PolicyEngine(PolicyConfig()))

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        services = registry.build_services(backend, manifests)
        services["memory"] = MemoryService(backend, local_root=local_root)
        yield {"backend": backend, "services": services}

    mcp = FastMCP("test-server", lifespan=lifespan)
    registry.register_tools(mcp, manifests)
    registry.register_resources(mcp, manifests)
    return mcp


@pytest.mark.asyncio
async def test_get_app_memory_summary_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_app_memory_summary",
            {"serial": "emulator-5554", "target": "com.android.systemui"},
        )

    assert result.data.status == "success"
    assert result.data.data.pid == 1224
    assert result.data.data.total_pss_kb == 105321


@pytest.mark.asyncio
async def test_get_app_memory_summary_tool_not_running_is_structured_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            dumpsys_meminfo_result=CommandResult(
                stdout="No process found for: com.nope\n", stderr="", exit_code=0, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_app_memory_summary", {"serial": "emulator-5554", "target": "com.nope"}
        )

    assert result.data.status == "error"
    assert result.data.error.code == "PACKAGE_NOT_RUNNING"


@pytest.mark.asyncio
async def test_get_app_memory_details_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_app_memory_details",
            {"serial": "emulator-5554", "target": "com.android.systemui"},
        )

    assert result.data.status == "success"
    assert result.data.data.total_pss_kb == 104328
    assert any(c.name == "Native Heap" for c in result.data.data.categories)
    assert result.data.data.objects["views"] == 855


@pytest.mark.asyncio
async def test_get_system_memory_summary_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_system_memory_summary", {"serial": "emulator-5554"}
        )

    assert result.data.status == "success"
    assert result.data.data.total_ram_kb == 4007632
    assert result.data.data.top_processes[0].name == "system"


@pytest.mark.asyncio
async def test_get_memory_history_tool_round_trips_and_rejects_bad_hours() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        ok = await client.call_tool(
            "get_memory_history",
            {"serial": "emulator-5554", "package": "com.android.systemui", "hours": 3},
        )
        bad = await client.call_tool(
            "get_memory_history",
            {"serial": "emulator-5554", "package": "com.x", "hours": 0},
        )

    assert ok.data.status == "success"
    assert ok.data.data.has_history is True
    assert ok.data.data.bands[0].state == "TOTAL"
    assert bad.data.status == "error"
    assert bad.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_capture_heap_dump_tool_registered_without_destructive_gate() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}

    assert "capture_heap_dump" in tools


@pytest.mark.asyncio
async def test_capture_heap_dump_tool_round_trips_with_local_root(tmp_path: Path) -> None:
    mcp = _server_with_local_root(FakeBackend(), tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "capture_heap_dump",
            {
                "serial": "emulator-5554",
                "package": "com.android.systemui",
                "local_path": "sysui.hprof",
                "force_gc": True,
            },
        )

    assert result.data.status == "success"
    assert result.data.data.local_path == str(tmp_path / "heapdumps" / "sysui.hprof")
    assert result.data.data.force_gc is True


@pytest.mark.asyncio
async def test_capture_heap_dump_tool_no_local_root_returns_policy_denied(tmp_path: Path) -> None:
    mcp = _server_with_local_root(FakeBackend(), None)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "capture_heap_dump",
            {"serial": "emulator-5554", "package": "com.x", "local_path": "x.hprof"},
        )

    assert result.data.status == "error"
    assert result.data.error.code == "POLICY_DENIED"


@pytest.mark.asyncio
async def test_set_heap_watch_tool_round_trips_without_gate() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}
        result = await client.call_tool(
            "set_heap_watch",
            {"serial": "emulator-5554", "package": "com.example.app", "threshold_bytes": 268435456},
        )

    assert "set_heap_watch" in tools
    assert result.data.status == "success"
    assert result.data.data.threshold_bytes == 268435456


@pytest.mark.asyncio
async def test_set_heap_watch_tool_non_positive_threshold_returns_invalid_argument() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "set_heap_watch",
            {"serial": "emulator-5554", "package": "com.x", "threshold_bytes": 0},
        )

    assert result.data.status == "error"
    assert result.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_clear_heap_watch_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "clear_heap_watch", {"serial": "emulator-5554", "package": "com.example.app"}
        )

    assert result.data.status == "success"
    assert result.data.data.cleared is True


@pytest.mark.asyncio
async def test_get_memory_maps_tool_round_trips() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "get_memory_maps", {"serial": "emulator-5554", "pid": 1224}
        )

    assert result.data.status == "success"
    assert result.data.data.pss_kb == 127651
    assert result.data.data.swap_kb == 8


@pytest.mark.asyncio
async def test_get_memory_maps_tool_permission_denied_is_structured_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            smaps_rollup_result=CommandResult(
                stdout="cat: /proc/1/smaps_rollup: Permission denied\n",
                stderr="",
                exit_code=0,
                duration_ms=5.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_memory_maps", {"serial": "emulator-5554", "pid": 1})

    assert result.data.status == "error"
    assert result.data.error.code == "PERMISSION_DENIED"
