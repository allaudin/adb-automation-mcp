"""Layer 1 unit tests: UserService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import AdbUnavailableError, BackendError, DeviceNotFoundError
from adb_mcp.modules.user.service import CurrentUser, UserService


@pytest.mark.asyncio
async def test_get_current_user__single_user_device_reports_user_0() -> None:
    service = UserService(FakeBackend())

    result = await service.get_current_user("emulator-5554")

    assert result.serial == "emulator-5554"
    assert result.user_id == 0


@pytest.mark.asyncio
async def test_get_current_user__multi_user_device_reports_actual_user_id() -> None:
    backend = FakeBackend(
        shell_result=CommandResult(stdout="10\n", stderr="", exit_code=0, duration_ms=45.0)
    )
    service = UserService(backend)

    result = await service.get_current_user("emulator-5554")

    assert result.user_id == 10


@pytest.mark.asyncio
async def test_get_current_user__unknown_serial_raises_device_not_found() -> None:
    # Real adb behavior, verified live: unknown serial fails at the
    # adb-client level with "adb: device '<serial>' not found", exit 1.
    backend = FakeBackend(
        shell_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = UserService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.get_current_user("bogus")


@pytest.mark.asyncio
async def test_get_current_user__other_nonzero_exit_raises_backend_error() -> None:
    backend = FakeBackend(
        shell_result=CommandResult(
            stdout="", stderr="some other adb shell failure", exit_code=1, duration_ms=10.0
        )
    )
    service = UserService(backend)

    with pytest.raises(BackendError):
        await service.get_current_user("emulator-5554")


@pytest.mark.asyncio
async def test_get_current_user__adb_unavailable_propagates_as_error() -> None:
    service = UserService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.get_current_user("emulator-5554")


def test_current_user_summary_mentions_serial_and_user_id() -> None:
    summary = CurrentUser(serial="emulator-5554", user_id=10).summary()
    assert "emulator-5554" in summary
    assert "10" in summary
