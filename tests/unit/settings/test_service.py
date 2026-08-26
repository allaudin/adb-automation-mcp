"""Layer 1 unit tests: SettingsService against FakeBackend directly — no
MCP registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import BackendError, DeviceNotFoundError, PermissionDeniedError
from adb_mcp.modules.settings.service import SettingsService


@pytest.mark.asyncio
async def test_get_setting__system_namespace_returns_value() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = SettingsService(RecordingBackend())

    result = await service.get_setting("emulator-5554", "system", "screen_brightness")

    assert captured["command"] == "settings get system screen_brightness"
    assert result.serial == "emulator-5554"
    assert result.namespace == "system"
    assert result.key == "screen_brightness"
    assert result.value == "128"
    assert result.user_id is None


@pytest.mark.asyncio
async def test_get_setting__secure_namespace_returns_value() -> None:
    backend = FakeBackend(
        get_setting_result=CommandResult(stdout="1\n", stderr="", exit_code=0, duration_ms=20.0)
    )
    service = SettingsService(backend)

    result = await service.get_setting("emulator-5554", "secure", "location_mode")

    assert result.namespace == "secure"
    assert result.value == "1"


@pytest.mark.asyncio
async def test_get_setting__global_namespace_returns_value() -> None:
    backend = FakeBackend(
        get_setting_result=CommandResult(stdout="0\n", stderr="", exit_code=0, duration_ms=20.0)
    )
    service = SettingsService(backend)

    result = await service.get_setting("emulator-5554", "global", "airplane_mode_on")

    assert result.namespace == "global"
    assert result.value == "0"


@pytest.mark.asyncio
async def test_get_setting__sends_user_id_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = SettingsService(RecordingBackend())

    result = await service.get_setting("emulator-5554", "system", "screen_brightness", user_id=10)

    assert captured["command"] == "settings --user 10 get system screen_brightness"
    assert result.user_id == 10


@pytest.mark.asyncio
async def test_get_setting__missing_value_returns_none_not_error() -> None:
    backend = FakeBackend(
        get_setting_result=CommandResult(stdout="null\n", stderr="", exit_code=0, duration_ms=15.0)
    )
    service = SettingsService(backend)

    result = await service.get_setting("emulator-5554", "system", "nonexistent_key")

    assert result.value is None


@pytest.mark.asyncio
async def test_get_setting__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        get_setting_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = SettingsService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.get_setting("bogus", "system", "screen_brightness")


@pytest.mark.asyncio
async def test_get_setting__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        get_setting_result=CommandResult(
            stdout="", stderr="Permission Denial: reading settings\n", exit_code=1, duration_ms=10.0
        )
    )
    service = SettingsService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.get_setting("emulator-5554", "secure", "location_mode")


@pytest.mark.asyncio
async def test_get_setting__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        get_setting_result=CommandResult(
            stdout="", stderr="some other unclassified failure\n", exit_code=1, duration_ms=5.0
        )
    )
    service = SettingsService(backend)

    with pytest.raises(BackendError):
        await service.get_setting("emulator-5554", "system", "screen_brightness")
