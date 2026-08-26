"""Layer 1 unit tests: UiService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    PermissionDeniedError,
    RemoteFileNotFoundError,
    UiAutomatorFailedError,
    UiHierarchyUnavailableError,
)
from adb_mcp.modules.ui.service import UiService


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__successful_dump_returns_parsed_xml() -> None:
    service = UiService(FakeBackend())

    result = await service.dump_ui_hierarchy("emulator-5554")

    assert result.serial == "emulator-5554"
    assert result.success is True
    assert "<hierarchy" in result.xml
    assert result.node_count == 2
    assert "UI hierarchy dumped to:" in result.output


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__cleans_up_temp_file_on_success() -> None:
    commands: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            commands.append(command)
            return await super().shell(serial, command)

    service = UiService(RecordingBackend())

    await service.dump_ui_hierarchy("emulator-5554")

    assert commands[0].startswith("uiautomator dump /data/local/tmp/adb_mcp_ui_dump_")
    assert commands[1].startswith("cat /data/local/tmp/adb_mcp_ui_dump_")
    assert commands[2].startswith("rm -f /data/local/tmp/adb_mcp_ui_dump_")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__empty_hierarchy_returns_zero_nodes() -> None:
    backend = FakeBackend(
        ui_hierarchy_cat_result=CommandResult(stdout="", stderr="", exit_code=0, duration_ms=5.0)
    )
    service = UiService(backend)

    result = await service.dump_ui_hierarchy("emulator-5554")

    assert result.success is True
    assert result.xml == ""
    assert result.node_count == 0


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__uiautomator_command_not_found_raises_uiautomator_failed() -> None:
    backend = FakeBackend(
        uiautomator_dump_result=CommandResult(
            stdout="", stderr="/system/bin/sh: uiautomator: not found\n", exit_code=127, duration_ms=5.0
        )
    )
    service = UiService(backend)

    with pytest.raises(UiAutomatorFailedError):
        await service.dump_ui_hierarchy("emulator-5554")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__null_root_node_raises_ui_hierarchy_unavailable() -> None:
    backend = FakeBackend(
        uiautomator_dump_result=CommandResult(
            stdout="",
            stderr="ERROR: null root node returned by UiTestAutomationBridge.\n",
            exit_code=0,
            duration_ms=800.0,
        )
    )
    service = UiService(backend)

    with pytest.raises(UiHierarchyUnavailableError):
        await service.dump_ui_hierarchy("emulator-5554")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        uiautomator_dump_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    service = UiService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.dump_ui_hierarchy("bogus")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        uiautomator_dump_result=CommandResult(
            stdout="", stderr="Permission Denial: dumping UI hierarchy\n", exit_code=1, duration_ms=5.0
        )
    )
    service = UiService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.dump_ui_hierarchy("emulator-5554")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__temp_file_missing_raises_remote_file_not_found() -> None:
    backend = FakeBackend(
        ui_hierarchy_cat_result=CommandResult(
            stdout="",
            stderr="cat: /data/local/tmp/adb_mcp_ui_dump_xyz.xml: No such file or directory\n",
            exit_code=1,
            duration_ms=5.0,
        )
    )
    service = UiService(backend)

    with pytest.raises(RemoteFileNotFoundError):
        await service.dump_ui_hierarchy("emulator-5554")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__unclassified_dump_failure_raises_uiautomator_failed() -> None:
    backend = FakeBackend(
        uiautomator_dump_result=CommandResult(
            stdout="", stderr="java.lang.RuntimeException: crashed\n", exit_code=1, duration_ms=5.0
        )
    )
    service = UiService(backend)

    with pytest.raises(UiAutomatorFailedError):
        await service.dump_ui_hierarchy("emulator-5554")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__unclassified_cat_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        ui_hierarchy_cat_result=CommandResult(
            stdout="", stderr="some other unclassified failure\n", exit_code=1, duration_ms=5.0
        )
    )
    service = UiService(backend)

    with pytest.raises(BackendError):
        await service.dump_ui_hierarchy("emulator-5554")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__backend_unavailable_raises_adb_unavailable() -> None:
    service = UiService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.dump_ui_hierarchy("emulator-5554")
