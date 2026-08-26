"""Layer 3 protocol-level E2E tests for take_screenshot — a real fastmcp.Client
speaking actual MCP protocol to a running FastMCP server instance, backed by
FakeBackend. Kept in its own file (not test_protocol_e2e.py) to avoid
concurrent edits to a shared test file.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.modules.screen.service import ScreenService
from adb_mcp.policy import PolicyConfig, PolicyEngine
from adb_mcp.registry import Registry, discover_modules


def _build_test_server_with_local_root(backend: FakeBackend, local_root: Path | None) -> FastMCP:
    # screen.take_screenshot needs a configured local_root, which the shared
    # _build_test_server helper in test_protocol_e2e.py doesn't parameterize
    # (no other module needed it before files/screen), so this builds a
    # server the same way but constructs the screen service directly with
    # local_root instead of reading ADB_MCP_LOCAL_ROOT from the environment.
    manifests = discover_modules()
    registry = Registry(policy=PolicyEngine(PolicyConfig()))

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        services = registry.build_services(backend, manifests)
        services["screen"] = ScreenService(backend, local_root=local_root)
        yield {"backend": backend, "services": services}

    mcp = FastMCP("test-server", lifespan=lifespan)
    registry.register_tools(mcp, manifests)
    registry.register_resources(mcp, manifests)
    return mcp


@pytest.mark.asyncio
async def test_take_screenshot_tool_round_trips_over_mcp_protocol(tmp_path: Path) -> None:
    mcp = _build_test_server_with_local_root(FakeBackend(), tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "take_screenshot", {"serial": "emulator-5554", "local_path": "screen.png"}
        )

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.local_path == str(tmp_path / "screen.png")
    assert result.data.data.success is True


@pytest.mark.asyncio
async def test_take_screenshot_tool_no_local_root_returns_policy_denied_error() -> None:
    mcp = _build_test_server_with_local_root(FakeBackend(), None)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "take_screenshot", {"serial": "emulator-5554", "local_path": "screen.png"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "POLICY_DENIED"


@pytest.mark.asyncio
async def test_take_screenshot_tool_screencap_failure_returns_backend_error(tmp_path: Path) -> None:
    backend = FakeBackend(
        screencap_result=CommandResult(
            stdout="", stderr="Error: unable to open display\n", exit_code=1, duration_ms=20.0
        )
    )
    mcp = _build_test_server_with_local_root(backend, tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "take_screenshot", {"serial": "emulator-5554", "local_path": "screen.png"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "BACKEND_ERROR"


@pytest.mark.asyncio
async def test_take_screenshot_tool_pull_failure_returns_remote_file_not_found_error(tmp_path: Path) -> None:
    backend = FakeBackend(
        pull_result=CommandResult(
            stdout="",
            stderr="adb: error: remote object '/data/local/tmp/adb_mcp_screenshot_x.png' does not exist\n",
            exit_code=1,
            duration_ms=15.0,
        )
    )
    mcp = _build_test_server_with_local_root(backend, tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "take_screenshot", {"serial": "emulator-5554", "local_path": "screen.png"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "REMOTE_FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_take_screenshot_tool_cleanup_runs_regardless_of_pull_outcome(tmp_path: Path) -> None:
    shell_commands: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            shell_commands.append(command)
            return await super().shell(serial, command)

    backend = RecordingBackend(
        pull_result=CommandResult(
            stdout="", stderr="adb: error: remote object 'x' does not exist\n", exit_code=1, duration_ms=15.0
        )
    )
    mcp = _build_test_server_with_local_root(backend, tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "take_screenshot", {"serial": "emulator-5554", "local_path": "screen.png"}
        )

    assert result.data.status == "error"
    rm_commands = [c for c in shell_commands if c.startswith("rm -f /data/local/tmp/adb_mcp_screenshot_")]
    assert len(rm_commands) == 1
