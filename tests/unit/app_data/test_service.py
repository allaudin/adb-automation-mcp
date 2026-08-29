"""Layer 1 unit tests: AppDataService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AndroidRejectionError,
    BackendError,
    DeviceNotFoundError,
    PackageNotFoundError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.app_data.service import AppDataService


@pytest.mark.asyncio
async def test_clear_app_data__success() -> None:
    service = AppDataService(FakeBackend())

    result = await service.clear_app_data("emulator-5554", "com.example.app")

    assert result.serial == "emulator-5554"
    assert result.package_name == "com.example.app"
    assert result.user_id is None
    assert result.success is True


@pytest.mark.asyncio
async def test_clear_app_data__sends_bare_pm_clear_and_user_id_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = AppDataService(RecordingBackend())

    result = await service.clear_app_data("emulator-5554", "com.example.app", user_id=10)

    assert captured["command"] == "pm clear --user 10 com.example.app"
    assert result.user_id == 10


@pytest.mark.asyncio
async def test_clear_app_data__no_user_id_omits_user_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = AppDataService(RecordingBackend())

    await service.clear_app_data("emulator-5554", "com.example.app")

    assert captured["command"] == "pm clear com.example.app"


@pytest.mark.asyncio
async def test_clear_app_data__package_not_found_raises_package_not_found() -> None:
    backend = FakeBackend(
        clear_app_data_result=CommandResult(
            stdout="", stderr="Error: Package not found: com.example.bogus\n", exit_code=1, duration_ms=15.0
        )
    )
    service = AppDataService(backend)

    with pytest.raises(PackageNotFoundError):
        await service.clear_app_data("emulator-5554", "com.example.bogus")


@pytest.mark.asyncio
async def test_clear_app_data__android_rejection_raises_android_rejection() -> None:
    backend = FakeBackend(
        clear_app_data_result=CommandResult(stdout="Failed\n", stderr="", exit_code=0, duration_ms=40.0)
    )
    service = AppDataService(backend)

    with pytest.raises(AndroidRejectionError):
        await service.clear_app_data("emulator-5554", "com.example.app")


@pytest.mark.asyncio
async def test_clear_app_data__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        clear_app_data_result=CommandResult(
            stdout="",
            stderr="java.lang.SecurityException: Permission Denial: clearApplicationUserData\n",
            exit_code=1,
            duration_ms=12.0,
        )
    )
    service = AppDataService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.clear_app_data("emulator-5554", "com.example.app")


@pytest.mark.asyncio
async def test_clear_app_data__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        clear_app_data_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = AppDataService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.clear_app_data("bogus", "com.example.app")


@pytest.mark.asyncio
async def test_clear_app_data__unclassified_backend_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        clear_app_data_result=CommandResult(
            stdout="", stderr="Error: Package manager has died\n", exit_code=1, duration_ms=5.0
        )
    )
    service = AppDataService(backend)

    with pytest.raises(BackendError):
        await service.clear_app_data("emulator-5554", "com.example.app")
