"""Layer 3 protocol-level E2E tests for list_packages — a real fastmcp.Client
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
async def test_list_packages_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("list_packages", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.packages == [
        "com.android.chrome",
        "com.example.thirdparty",
        "com.android.systemui",
    ]


@pytest.mark.asyncio
async def test_list_packages_tool_empty_list_is_success_not_error() -> None:
    backend = FakeBackend(
        list_packages_result=CommandResult(stdout="", stderr="", exit_code=0, duration_ms=50.0)
    )
    mcp = _build_test_server(backend)

    async with Client(mcp) as client:
        result = await client.call_tool("list_packages", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.packages == []


@pytest.mark.asyncio
async def test_list_packages_tool_accepts_user_id_and_package_filter() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "list_packages",
            {"serial": "emulator-5554", "user_id": 10, "package_filter": "third_party"},
        )

    assert result.data.status == "success"
    assert captured["command"] == "pm list packages -3 --user 10"


@pytest.mark.asyncio
async def test_list_packages_tool_unknown_serial_returns_device_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            list_packages_result=CommandResult(
                stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("list_packages", {"serial": "bogus"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"


# --- install_apk -----------------------------------------------------------


@pytest.mark.asyncio
async def test_install_apk_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "install_apk", {"serial": "emulator-5554", "apk_path": "/tmp/app.apk"}
        )

    assert result.data.status == "success"
    assert result.data.data.apk_path == "/tmp/app.apk"
    assert result.data.data.success is True


@pytest.mark.asyncio
async def test_install_apk_tool_registered_in_write_category_by_default() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert "install_apk" in {tool.name for tool in tools}


@pytest.mark.asyncio
async def test_install_apk_tool_exposes_only_semantic_options_not_raw_flags() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        tools = await client.list_tools()

    tool = next(t for t in tools if t.name == "install_apk")
    properties = tool.inputSchema["properties"]
    assert set(properties) == {
        "serial",
        "apk_path",
        "user_id",
        "replace_existing",
        "allow_downgrade",
        "grant_runtime_permissions",
        "allow_test_packages",
        "force_sdk",
    }
    assert "options" not in properties


@pytest.mark.asyncio
async def test_install_apk_tool_sends_flags_derived_from_semantic_options() -> None:
    captured: dict[str, object] = {}

    class RecordingBackend(FakeBackend):
        async def install(self, serial: str, apk_path: str, flags: list[str]) -> CommandResult:
            captured["flags"] = flags
            return await super().install(serial, apk_path, flags)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "install_apk",
            {
                "serial": "emulator-5554",
                "apk_path": "/tmp/app.apk",
                "user_id": 10,
                "replace_existing": True,
                "allow_downgrade": True,
            },
        )

    assert result.data.status == "success"
    assert captured["flags"] == ["--user", "10", "-r", "-d"]


@pytest.mark.asyncio
async def test_install_apk_tool_pm_rejection_returns_error_envelope() -> None:
    backend = FakeBackend(
        install_result=CommandResult(
            stdout="Performing Streamed Install\nFailure [INSTALL_FAILED_ALREADY_EXISTS]\n",
            stderr="",
            exit_code=1,
            duration_ms=100.0,
        )
    )
    mcp = _build_test_server(backend)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "install_apk", {"serial": "emulator-5554", "apk_path": "/tmp/app.apk"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "ANDROID_REJECTED"


@pytest.mark.asyncio
async def test_install_apk_tool_empty_apk_path_returns_invalid_argument_error() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("install_apk", {"serial": "emulator-5554", "apk_path": ""})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "INVALID_ARGUMENT"


# --- uninstall_package -------------------------------------------------------


@pytest.mark.asyncio
async def test_uninstall_package_tool_round_trips_over_mcp_protocol() -> None:
    # destructive category: only registered when the server explicitly opts in.
    mcp = _build_test_server(FakeBackend(), allow_destructive=True)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "uninstall_package", {"serial": "emulator-5554", "package_name": "com.example.app"}
        )

    assert result.data.status == "success"
    assert result.data.data.package_name == "com.example.app"
    assert result.data.data.success is True


@pytest.mark.asyncio
async def test_uninstall_package_tool_not_registered_when_destructive_disallowed() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = await client.list_tools()

    assert "uninstall_package" not in {tool.name for tool in tools}


@pytest.mark.asyncio
async def test_uninstall_package_tool_user_scoped_call_sends_user_flag_only() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    mcp = _build_test_server(RecordingBackend(), allow_destructive=True)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "uninstall_package",
            {"serial": "emulator-5554", "package_name": "com.example.app", "user_id": 10},
        )

    assert result.data.status == "success"
    assert captured["command"] == "pm uninstall --user 10 com.example.app"


@pytest.mark.asyncio
async def test_uninstall_package_tool_package_missing_returns_error_envelope() -> None:
    backend = FakeBackend(
        pm_uninstall_result=CommandResult(
            stdout="Failure [DELETE_FAILED_INTERNAL_ERROR]\n", stderr="", exit_code=1, duration_ms=50.0
        )
    )
    mcp = _build_test_server(backend, allow_destructive=True)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "uninstall_package", {"serial": "emulator-5554", "package_name": "com.doesnt.exist"}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PACKAGE_NOT_FOUND"


# --- install_existing_for_user -----------------------------------------------


@pytest.mark.asyncio
async def test_install_existing_for_user_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "install_existing_for_user",
            {"serial": "emulator-5554", "package_name": "com.example.app", "user_id": 10},
        )

    assert result.data.status == "success"
    assert result.data.data.package_name == "com.example.app"
    assert result.data.data.user_id == 10
    assert result.data.data.success is True


@pytest.mark.asyncio
async def test_install_existing_for_user_tool_does_not_require_apk_path() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        tools = await client.list_tools()

    tool = next(t for t in tools if t.name == "install_existing_for_user")
    assert "apk_path" not in tool.inputSchema["properties"]
    assert set(tool.inputSchema.get("required", [])) == {"serial", "package_name", "user_id"}


@pytest.mark.asyncio
async def test_install_existing_for_user_tool_unknown_package_returns_error_envelope() -> None:
    backend = FakeBackend(
        pm_install_existing_result=CommandResult(
            stdout="", stderr="Unknown package: com.doesnt.exist\n", exit_code=1, duration_ms=50.0
        )
    )
    mcp = _build_test_server(backend)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "install_existing_for_user",
            {"serial": "emulator-5554", "package_name": "com.doesnt.exist", "user_id": 10},
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "PACKAGE_NOT_FOUND"
