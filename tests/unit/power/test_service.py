"""Layer 1 unit tests: PowerService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    PermissionDeniedError,
    PowerStateUnavailableError,
)
from adb_automation_mcp.modules.power.service import PowerService


@pytest.mark.asyncio
async def test_get_power_state__parses_wakefulness_and_interactive() -> None:
    service = PowerService(FakeBackend())

    result = await service.get_power_state("emulator-5554")

    assert result.serial == "emulator-5554"
    assert result.wakefulness == "Awake"
    assert result.interactive is True


@pytest.mark.asyncio
async def test_get_power_state__missing_interactive_field_is_none() -> None:
    backend = FakeBackend(
        dumpsys_power_result=CommandResult(
            stdout="Power Manager State:\n  mWakefulness=Asleep\n  mIsPowered=false\n",
            stderr="",
            exit_code=0,
            duration_ms=100.0,
        )
    )
    service = PowerService(backend)

    result = await service.get_power_state("emulator-5554")

    assert result.wakefulness == "Asleep"
    assert result.interactive is None


@pytest.mark.asyncio
async def test_get_power_state__interactive_false_is_parsed_correctly() -> None:
    backend = FakeBackend(
        dumpsys_power_result=CommandResult(
            stdout="Power Manager State:\n  mWakefulness=Asleep\n  mInteractive=false\n",
            stderr="",
            exit_code=0,
            duration_ms=100.0,
        )
    )
    service = PowerService(backend)

    result = await service.get_power_state("emulator-5554")

    assert result.interactive is False


@pytest.mark.asyncio
async def test_get_power_state__malformed_output_raises_power_state_unavailable() -> None:
    backend = FakeBackend(
        dumpsys_power_result=CommandResult(
            stdout="Can't find service: power\n", stderr="", exit_code=0, duration_ms=10.0
        )
    )
    service = PowerService(backend)

    with pytest.raises(PowerStateUnavailableError):
        await service.get_power_state("emulator-5554")


@pytest.mark.asyncio
async def test_get_power_state__empty_output_raises_power_state_unavailable() -> None:
    backend = FakeBackend(
        dumpsys_power_result=CommandResult(stdout="", stderr="", exit_code=0, duration_ms=5.0)
    )
    service = PowerService(backend)

    with pytest.raises(PowerStateUnavailableError):
        await service.get_power_state("emulator-5554")


@pytest.mark.asyncio
async def test_get_power_state__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        dumpsys_power_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = PowerService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.get_power_state("bogus")


@pytest.mark.asyncio
async def test_get_power_state__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        dumpsys_power_result=CommandResult(
            stdout="", stderr="some other unclassified failure\n", exit_code=1, duration_ms=5.0
        )
    )
    service = PowerService(backend)

    with pytest.raises(BackendError):
        await service.get_power_state("emulator-5554")


# --- reboot_device ---------------------------------------------------------


@pytest.mark.asyncio
async def test_reboot_device__sends_adb_reboot_and_reports_accepted() -> None:
    captured: dict[str, object] = {}

    class RecordingBackend(FakeBackend):
        async def reboot(self, serial: str, mode: str | None = None) -> CommandResult:
            captured["serial"] = serial
            captured["mode"] = mode
            return await super().reboot(serial, mode)

    result = await PowerService(RecordingBackend()).reboot_device("emulator-5554")

    assert captured == {"serial": "emulator-5554", "mode": None}
    assert result.serial == "emulator-5554"
    assert result.mode == "system"
    assert result.accepted is True
    assert result.output == ""


@pytest.mark.asyncio
async def test_reboot_device__unknown_serial_raises_device_not_found() -> None:
    # `adb -s bogus reboot` uses "error:" (not "adb:") for the not-found line.
    backend = FakeBackend(
        reboot_result=CommandResult(
            stdout="", stderr="error: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )

    with pytest.raises(DeviceNotFoundError):
        await PowerService(backend).reboot_device("bogus")


@pytest.mark.asyncio
async def test_reboot_device__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        reboot_result=CommandResult(
            stdout="", stderr="error: closed\n", exit_code=1, duration_ms=10.0
        )
    )

    with pytest.raises(BackendError):
        await PowerService(backend).reboot_device("emulator-5554")


@pytest.mark.asyncio
async def test_reboot_device__backend_unavailable_raises_adb_unavailable() -> None:
    with pytest.raises(AdbUnavailableError):
        await PowerService(FakeBackend(unavailable=True)).reboot_device("emulator-5554")


# --- wake_device ---------------------------------------------------------


@pytest.mark.asyncio
async def test_wake_device__sends_input_keyevent_wakeup() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command, timeout_s)

    result = await PowerService(RecordingBackend()).wake_device("emulator-5554")

    assert captured["command"] == "input keyevent WAKEUP"
    assert result.serial == "emulator-5554"
    assert result.keycode == "WAKEUP"
    assert result.accepted is True


@pytest.mark.asyncio
async def test_wake_device__already_awake_is_idempotent_success() -> None:
    # `input keyevent WAKEUP` is silent + exit 0 whether or not the screen
    # was actually asleep — waking an awake device is a no-op, not an error.
    result = await PowerService(FakeBackend()).wake_device("emulator-5554")

    assert result.accepted is True


@pytest.mark.asyncio
async def test_wake_device__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        input_keyevent_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )

    with pytest.raises(DeviceNotFoundError):
        await PowerService(backend).wake_device("bogus")


@pytest.mark.asyncio
async def test_wake_device__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        input_keyevent_result=CommandResult(
            stdout="",
            stderr="java.lang.SecurityException: Injecting to another application requires INJECT_EVENTS permission\nPermission Denial\n",
            exit_code=1,
            duration_ms=10.0,
        )
    )

    with pytest.raises(PermissionDeniedError):
        await PowerService(backend).wake_device("emulator-5554")


@pytest.mark.asyncio
async def test_wake_device__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        input_keyevent_result=CommandResult(
            stdout="", stderr="input: not found\n", exit_code=127, duration_ms=5.0
        )
    )

    with pytest.raises(BackendError):
        await PowerService(backend).wake_device("emulator-5554")


@pytest.mark.asyncio
async def test_wake_device__backend_unavailable_raises_adb_unavailable() -> None:
    with pytest.raises(AdbUnavailableError):
        await PowerService(FakeBackend(unavailable=True)).wake_device("emulator-5554")
