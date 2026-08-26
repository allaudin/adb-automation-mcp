"""Layer 1 unit tests: InputService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)
from adb_mcp.modules.input.service import InputService


@pytest.mark.asyncio
async def test_tap__valid_coordinates_succeeds() -> None:
    service = InputService(FakeBackend())

    result = await service.tap("emulator-5554", 500, 800)

    assert result.serial == "emulator-5554"
    assert result.x == 500
    assert result.y == 800
    assert result.display_id is None
    assert result.success is True


@pytest.mark.asyncio
async def test_tap__zero_coordinates_succeeds() -> None:
    service = InputService(FakeBackend())

    result = await service.tap("emulator-5554", 0, 0)

    assert result.x == 0
    assert result.y == 0
    assert result.success is True


@pytest.mark.asyncio
async def test_tap__sends_display_id_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = InputService(RecordingBackend())

    result = await service.tap("emulator-5554", 500, 800, display_id=1)

    assert captured["command"] == "input -d 1 tap 500 800"
    assert result.display_id == 1


@pytest.mark.asyncio
async def test_tap__omits_display_flag_when_not_given() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = InputService(RecordingBackend())

    await service.tap("emulator-5554", 500, 800)

    assert captured["command"] == "input tap 500 800"


@pytest.mark.asyncio
async def test_tap__negative_x_rejected_before_backend_call() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = InputService(RecordingBackend())

    with pytest.raises(InvalidArgumentError):
        await service.tap("emulator-5554", -1, 800)

    assert "command" not in captured


@pytest.mark.asyncio
async def test_tap__negative_y_rejected_before_backend_call() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = InputService(RecordingBackend())

    with pytest.raises(InvalidArgumentError):
        await service.tap("emulator-5554", 500, -1)

    assert "command" not in captured


@pytest.mark.asyncio
async def test_tap__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        input_tap_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = InputService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.tap("bogus", 500, 800)


@pytest.mark.asyncio
async def test_tap__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        input_tap_result=CommandResult(
            stdout="",
            stderr="Permission Denial: injecting input events\n",
            exit_code=1,
            duration_ms=10.0,
        )
    )
    service = InputService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.tap("emulator-5554", 500, 800)


@pytest.mark.asyncio
async def test_tap__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        input_tap_result=CommandResult(
            stdout="", stderr="Error: Injecting to display 5 was ignored.\n", exit_code=1, duration_ms=5.0
        )
    )
    service = InputService(backend)

    with pytest.raises(BackendError):
        await service.tap("emulator-5554", 500, 800)
