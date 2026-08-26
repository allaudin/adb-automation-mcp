"""Layer 3 protocol-level E2E tests for pull_file — a real fastmcp.Client
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
from adb_mcp.modules.files.service import FilesService
from adb_mcp.policy import PolicyConfig, PolicyEngine
from adb_mcp.registry import Registry, discover_modules


def _build_test_server_with_local_root(backend: FakeBackend, local_root: Path | None) -> FastMCP:
    # files.pull_file needs a configured local_root, which the shared
    # _build_test_server helper in test_protocol_e2e.py doesn't parameterize
    # (no other module needed it), so this builds a server the same way but
    # constructs the files service directly with local_root instead of
    # reading ADB_MCP_LOCAL_ROOT from the environment.
    manifests = discover_modules()
    registry = Registry(policy=PolicyEngine(PolicyConfig()))

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        services = registry.build_services(backend, manifests)
        services["files"] = FilesService(backend, local_root=local_root)
        yield {"backend": backend, "services": services}

    mcp = FastMCP("test-server", lifespan=lifespan)
    registry.register_tools(mcp, manifests)
    registry.register_resources(mcp, manifests)
    return mcp


@pytest.mark.asyncio
async def test_pull_file_tool_round_trips_over_mcp_protocol(tmp_path: Path) -> None:
    mcp = _build_test_server_with_local_root(FakeBackend(), tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "pull_file",
            {"serial": "emulator-5554", "remote_path": "/sdcard/test.txt", "local_path": "test.txt"},
        )

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.remote_path == "/sdcard/test.txt"
    assert result.data.data.local_path == str(tmp_path / "test.txt")
    assert result.data.data.success is True


@pytest.mark.asyncio
async def test_pull_file_tool_no_local_root_returns_policy_denied_error() -> None:
    mcp = _build_test_server_with_local_root(FakeBackend(), None)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "pull_file",
            {"serial": "emulator-5554", "remote_path": "/sdcard/test.txt", "local_path": "test.txt"},
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "POLICY_DENIED"


@pytest.mark.asyncio
async def test_pull_file_tool_source_missing_returns_remote_file_not_found_error(tmp_path: Path) -> None:
    backend = FakeBackend(
        pull_result=CommandResult(
            stdout="",
            stderr="adb: error: remote object '/sdcard/missing.txt' does not exist\n",
            exit_code=1,
            duration_ms=15.0,
        )
    )
    mcp = _build_test_server_with_local_root(backend, tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "pull_file",
            {
                "serial": "emulator-5554",
                "remote_path": "/sdcard/missing.txt",
                "local_path": "test.txt",
            },
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "REMOTE_FILE_NOT_FOUND"


@pytest.mark.asyncio
async def test_pull_file_tool_permission_denied_returns_permission_denied_error(tmp_path: Path) -> None:
    backend = FakeBackend(
        pull_result=CommandResult(
            stdout="",
            stderr=(
                "adb: error: failed to stat remote object "
                "'/data/data/com.other.app/files/secret.txt': Permission denied\n"
            ),
            exit_code=1,
            duration_ms=15.0,
        )
    )
    mcp = _build_test_server_with_local_root(backend, tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "pull_file",
            {
                "serial": "emulator-5554",
                "remote_path": "/data/data/com.other.app/files/secret.txt",
                "local_path": "secret.txt",
            },
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_pull_file_tool_unknown_serial_returns_device_not_found_error(tmp_path: Path) -> None:
    backend = FakeBackend(
        pull_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    mcp = _build_test_server_with_local_root(backend, tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "pull_file", {"serial": "bogus", "remote_path": "/sdcard/test.txt", "local_path": "test.txt"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"


@pytest.mark.asyncio
async def test_pull_file_tool_backend_failure_returns_backend_error(tmp_path: Path) -> None:
    backend = FakeBackend(
        pull_result=CommandResult(
            stdout="", stderr="adb: error: failed to copy; I/O error\n", exit_code=1, duration_ms=25.0
        )
    )
    mcp = _build_test_server_with_local_root(backend, tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "pull_file", {"serial": "emulator-5554", "remote_path": "/sdcard/test.txt", "local_path": "test.txt"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "BACKEND_ERROR"
