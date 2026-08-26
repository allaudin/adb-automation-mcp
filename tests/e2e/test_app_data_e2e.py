"""Layer 3 protocol-level E2E tests for clear_app_cache — a real fastmcp.Client
speaking actual MCP protocol to a running FastMCP server instance, backed by
FakeBackend. Kept in its own file (not test_protocol_e2e.py) to avoid
concurrent edits to a shared test file.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_clear_app_cache_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "clear_app_cache", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.package_name == "com.example.app"
    assert result.data.data.success is True


@pytest.mark.asyncio
async def test_clear_app_cache_tool_accepts_user_id() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "clear_app_cache",
            {"serial": "emulator-5554", "package_name": "com.example.app", "user_id": 10},
        )

    assert result.data.status == "success"
    assert result.data.data.user_id == 10
    assert captured["command"] == "pm clear --cache-only --user 10 com.example.app"


@pytest.mark.asyncio
async def test_clear_app_cache_tool_package_not_found_returns_package_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            clear_app_cache_result=CommandResult(
                stdout="",
                stderr="Error: Package not found: com.example.bogus\n",
                exit_code=1,
                duration_ms=15.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "clear_app_cache", {"serial": "emulator-5554", "package_name": "com.example.bogus"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PACKAGE_NOT_FOUND"


@pytest.mark.asyncio
async def test_clear_app_cache_tool_unsupported_cache_only_returns_cache_only_unsupported_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            clear_app_cache_result=CommandResult(
                stdout="", stderr="Error: Unknown option: --cache-only\n", exit_code=1, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "clear_app_cache", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "CACHE_ONLY_UNSUPPORTED"


@pytest.mark.asyncio
async def test_clear_app_cache_tool_android_rejection_returns_android_rejected_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            clear_app_cache_result=CommandResult(
                stdout="Failed\n", stderr="", exit_code=0, duration_ms=40.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "clear_app_cache", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "ANDROID_REJECTED"


@pytest.mark.asyncio
async def test_clear_app_cache_tool_backend_failure_returns_backend_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            clear_app_cache_result=CommandResult(
                stdout="", stderr="Error: Package manager has died\n", exit_code=1, duration_ms=5.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "clear_app_cache", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "BACKEND_ERROR"
