"""Layer 3 protocol-level E2E tests for the profiling module."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.modules.profiling.service import ProfilingService
from adb_automation_mcp.policy import PolicyConfig, PolicyEngine
from adb_automation_mcp.registry import Registry, discover_modules
from tests.e2e.test_protocol_e2e import _build_test_server


def _server_with_local_root(backend: FakeBackend, local_root: Path | None) -> FastMCP:
    manifests = discover_modules()
    registry = Registry(policy=PolicyEngine(PolicyConfig()))

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        services = registry.build_services(backend, manifests)
        services["profiling"] = ProfilingService(backend, local_root=local_root)
        yield {"backend": backend, "services": services}

    mcp = FastMCP("test-server", lifespan=lifespan)
    registry.register_tools(mcp, manifests)
    registry.register_resources(mcp, manifests)
    return mcp


@pytest.mark.asyncio
async def test_start_method_profile_tool_round_trips_without_gate() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}
        result = await client.call_tool(
            "start_method_profile",
            {"serial": "emulator-5554", "package": "com.example.app", "sampling_interval_us": 1000},
        )

    assert "start_method_profile" in tools
    assert result.data.status == "success"
    assert result.data.data.sampling_interval_us == 1000
    assert result.data.data.device_trace_path.endswith("com.example.app.trace")


@pytest.mark.asyncio
async def test_start_method_profile_tool_conflicting_options_returns_invalid_argument() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "start_method_profile",
            {
                "serial": "emulator-5554",
                "package": "com.x",
                "sampling_interval_us": 1000,
                "streaming": True,
            },
        )

    assert result.data.status == "error"
    assert result.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_stop_method_profile_tool_round_trips_with_local_root(tmp_path: Path) -> None:
    mcp = _server_with_local_root(FakeBackend(), tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "stop_method_profile",
            {"serial": "emulator-5554", "package": "com.example.app", "local_path": "app.trace"},
        )

    assert result.data.status == "success"
    assert result.data.data.local_path == str(tmp_path / "profiles" / "app.trace")


@pytest.mark.asyncio
async def test_stop_method_profile_tool_no_local_root_returns_policy_denied(tmp_path: Path) -> None:
    mcp = _server_with_local_root(FakeBackend(), None)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "stop_method_profile",
            {"serial": "emulator-5554", "package": "com.x", "local_path": "x.trace"},
        )

    assert result.data.status == "error"
    assert result.data.error.code == "POLICY_DENIED"


@pytest.mark.asyncio
async def test_stop_method_profile_tool_no_active_profile_returns_structured_error(
    tmp_path: Path,
) -> None:
    class FailingPull(FakeBackend):
        async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
            return CommandResult(
                stdout="",
                stderr="adb: error: remote object does not exist\n",
                exit_code=1,
                duration_ms=5.0,
            )

    mcp = _server_with_local_root(FailingPull(), tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "stop_method_profile",
            {"serial": "emulator-5554", "package": "com.x", "local_path": "x.trace"},
        )

    assert result.data.status == "error"
    assert result.data.error.code == "REMOTE_FILE_NOT_FOUND"
