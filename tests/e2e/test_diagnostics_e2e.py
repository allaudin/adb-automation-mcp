"""Layer 3 protocol-level E2E tests for get_adb_version — a real fastmcp.Client
speaking actual MCP protocol to a running FastMCP server instance, backed by
FakeBackend. Kept in its own file (not test_protocol_e2e.py) to avoid concurrent
edits to a shared test file.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from adb_automation_mcp.backend.protocol import CommandResult, DeviceInfo
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.modules.diagnostics.service import DiagnosticsService
from adb_automation_mcp.policy import PolicyConfig, PolicyEngine
from adb_automation_mcp.registry import Registry, discover_modules
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_get_adb_version_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("get_adb_version", {})

    assert result.data.status == "success"
    assert result.data.data.bridge_version == "1.0.41"
    assert result.data.data.platform_tools_version == "37.0.0-eng.allaud"
    assert result.data.data.running_on == "Linux 6.8.0-138-generic (x86_64)"


@pytest.mark.asyncio
async def test_get_adb_version_tool_malformed_output_serializes_as_success_with_nulls() -> None:
    mcp = _build_test_server(
        FakeBackend(
            version_result=CommandResult(
                stdout="garbage\n", stderr="", exit_code=0, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_adb_version", {})

    assert result.data.status == "success"
    assert result.data.data.bridge_version is None
    assert result.data.data.raw == "garbage"


@pytest.mark.asyncio
async def test_get_adb_version_tool_non_zero_exit_serializes_as_backend_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            version_result=CommandResult(
                stdout="", stderr="adb: broken\n", exit_code=2, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_adb_version", {})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "BACKEND_ERROR"


@pytest.mark.asyncio
async def test_get_adb_version_tool_adb_unavailable_serializes_as_error() -> None:
    mcp = _build_test_server(FakeBackend(unavailable=True))

    async with Client(mcp) as client:
        result = await client.call_tool("get_adb_version", {})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "ADB_UNAVAILABLE"


# --- generate_bugreport ----------------------------------------------


def _server_with_local_root(backend: FakeBackend, local_root: Path | None) -> FastMCP:
    manifests = discover_modules()
    registry = Registry(policy=PolicyEngine(PolicyConfig()))

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        services = registry.build_services(backend, manifests)
        services["diagnostics"] = DiagnosticsService(backend, local_root=local_root)
        yield {"backend": backend, "services": services}

    mcp = FastMCP("test-server", lifespan=lifespan)
    registry.register_tools(mcp, manifests)
    registry.register_resources(mcp, manifests)
    return mcp


@pytest.mark.asyncio
async def test_generate_bugreport_tool_round_trips_with_local_root(tmp_path: Path) -> None:
    backend = FakeBackend(devices=[DeviceInfo(serial="emulator-5554", state="device")])
    mcp = _server_with_local_root(backend, tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "generate_bugreport", {"serial": "emulator-5554", "local_path": "device.zip"}
        )

    assert result.data.status == "success"
    assert result.data.data.is_zip is True
    assert result.data.data.local_path == str(tmp_path / "bugreports" / "device.zip")


@pytest.mark.asyncio
async def test_generate_bugreport_tool_unknown_serial_returns_device_not_found(tmp_path: Path) -> None:
    # unknown serial is rejected by the preflight, not by a wait-for-device stall
    backend = FakeBackend(devices=[DeviceInfo(serial="emulator-5554", state="device")])
    mcp = _server_with_local_root(backend, tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "generate_bugreport", {"serial": "ghost-9999", "local_path": "device.zip"}
        )

    assert result.data.status == "error"
    assert result.data.error.code == "DEVICE_NOT_FOUND"


@pytest.mark.asyncio
async def test_generate_bugreport_tool_no_local_root_returns_policy_denied(tmp_path: Path) -> None:
    mcp = _server_with_local_root(FakeBackend(), None)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "generate_bugreport", {"serial": "emulator-5554", "local_path": "device.zip"}
        )

    assert result.data.status == "error"
    assert result.data.error.code == "POLICY_DENIED"


@pytest.mark.asyncio
async def test_generate_bugreport_tool_registered_without_destructive_gate() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}

    assert "generate_bugreport" in tools
