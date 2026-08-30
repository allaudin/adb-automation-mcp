"""Layer 3 protocol-level E2E tests for grant_permission — a real
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


@pytest.mark.asyncio
async def test_grant_permission_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "grant_permission",
            {
                "serial": "emulator-5554",
                "package_name": "com.example.app",
                "permission": "android.permission.CAMERA",
            },
        )

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.package_name == "com.example.app"
    assert result.data.data.permission == "android.permission.CAMERA"
    assert result.data.data.success is True
    assert result.data.data.output == ""


@pytest.mark.asyncio
async def test_grant_permission_tool_accepts_user_id() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "grant_permission",
            {
                "serial": "emulator-5554",
                "package_name": "com.example.app",
                "permission": "android.permission.CAMERA",
                "user_id": 10,
            },
        )

    assert result.data.status == "success"
    assert result.data.data.user_id == 10
    assert captured["command"] == (
        "pm grant --user 10 com.example.app android.permission.CAMERA"
    )


@pytest.mark.asyncio
async def test_grant_permission_tool_unknown_package_returns_package_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            grant_permission_result=CommandResult(
                stdout="",
                stderr="Error: java.lang.IllegalArgumentException: Unknown package: com.example.bogus\n",
                exit_code=1,
                duration_ms=20.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "grant_permission",
            {
                "serial": "emulator-5554",
                "package_name": "com.example.bogus",
                "permission": "android.permission.CAMERA",
            },
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PACKAGE_NOT_FOUND"


@pytest.mark.asyncio
async def test_grant_permission_tool_not_requested_returns_permission_not_declared_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            grant_permission_result=CommandResult(
                stdout="",
                stderr=(
                    "Error: java.lang.SecurityException: Permission android.permission.CAMERA "
                    "isn't requested by package com.example.app\n"
                ),
                exit_code=1,
                duration_ms=20.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "grant_permission",
            {
                "serial": "emulator-5554",
                "package_name": "com.example.app",
                "permission": "android.permission.CAMERA",
            },
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PERMISSION_NOT_DECLARED"


@pytest.mark.asyncio
async def test_grant_permission_tool_non_runtime_permission_returns_non_runtime_permission_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            grant_permission_result=CommandResult(
                stdout="",
                stderr=(
                    "Error: java.lang.SecurityException: android.permission.INTERNET "
                    "is not a changeable permission type\n"
                ),
                exit_code=1,
                duration_ms=15.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "grant_permission",
            {
                "serial": "emulator-5554",
                "package_name": "com.example.app",
                "permission": "android.permission.INTERNET",
            },
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "NON_RUNTIME_PERMISSION"


@pytest.mark.asyncio
async def test_grant_permission_tool_policy_fixed_returns_permission_policy_restricted_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            grant_permission_result=CommandResult(
                stdout="",
                stderr=(
                    "Error: java.lang.SecurityException: Cannot grant permission "
                    "android.permission.CAMERA to com.example.app: policy fixed\n"
                ),
                exit_code=1,
                duration_ms=15.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "grant_permission",
            {
                "serial": "emulator-5554",
                "package_name": "com.example.app",
                "permission": "android.permission.CAMERA",
            },
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PERMISSION_POLICY_RESTRICTED"


@pytest.mark.asyncio
async def test_grant_permission_tool_generic_security_exception_returns_permission_denied_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            grant_permission_result=CommandResult(
                stdout="",
                stderr=(
                    "Error: java.lang.SecurityException: Neither user 2000 nor current process has "
                    "android.permission.GRANT_RUNTIME_PERMISSIONS\n"
                ),
                exit_code=1,
                duration_ms=15.0,
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "grant_permission",
            {
                "serial": "emulator-5554",
                "package_name": "com.example.app",
                "permission": "android.permission.CAMERA",
            },
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_grant_permission_tool_adb_failure_returns_device_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            grant_permission_result=CommandResult(
                stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "grant_permission",
            {
                "serial": "bogus",
                "package_name": "com.example.app",
                "permission": "android.permission.CAMERA",
            },
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"
