"""Layer 1 unit tests: PowerService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import BackendError, DeviceNotFoundError, PowerStateUnavailableError
from adb_mcp.modules.power.service import PowerService


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
