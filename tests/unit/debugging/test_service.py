"""Layer 1 unit tests: DebuggingService against FakeBackend directly."""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.debugging.service import DebuggingService


class RecordingBackend(FakeBackend):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.command: str | None = None

    async def shell(
        self, serial: str, command: str, timeout_s: float | None = None
    ) -> CommandResult:
        self.command = command
        return await super().shell(serial, command, timeout_s)


def _cr(stdout: str = "", stderr: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(stdout=stdout, stderr=stderr, exit_code=exit_code, duration_ms=20.0)


@pytest.mark.asyncio
async def test_get_process_exit_history__command_and_parse_multiple_records() -> None:
    backend = RecordingBackend()

    result = await DebuggingService(backend).get_process_exit_history(
        "emulator-5554", "com.example.app"
    )

    assert backend.command == "dumpsys activity exit-info com.example.app"
    assert result.count == 2
    crash, self_exit = result.records
    assert crash.reason_code == 4
    assert crash.reason == "APP CRASH(EXCEPTION)"
    assert crash.subreason == "UNKNOWN"
    assert crash.pid == 5486
    assert crash.user == 0
    assert crash.importance == 400
    assert crash.pss == "0.00"
    assert crash.rss == "167MB"
    assert crash.state == "empty"
    assert crash.description == "crash"
    assert crash.trace_available is False
    assert crash.has_anr_info is False
    # second record: self-exit, with a trace path
    assert self_exit.reason_code == 1
    assert self_exit.reason == "EXIT_SELF"
    assert self_exit.trace_available is True
    assert self_exit.description is None


@pytest.mark.asyncio
async def test_get_process_exit_history__no_history_is_valid_empty() -> None:
    backend = FakeBackend(
        activity_exit_info_result=_cr(
            stdout=(
                "ACTIVITY MANAGER PROCESS EXIT INFO (dumpsys activity exit-info)\n"
                "Last Timestamp of Persistence Into Persistent Storage: 2026-09-07 10:06:28.946\n"
            )
        )
    )

    result = await DebuggingService(backend).get_process_exit_history("emulator-5554", "com.x")

    assert result.count == 0
    assert result.records == []


@pytest.mark.asyncio
async def test_get_process_exit_history__blank_package_rejected_before_backend() -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await DebuggingService(Exploding()).get_process_exit_history("emulator-5554", " ")


@pytest.mark.asyncio
async def test_get_process_exit_history__partial_record_does_not_crash() -> None:
    backend = FakeBackend(
        activity_exit_info_result=_cr(
            stdout=(
                "  package: com.x\n"
                "        ApplicationExitInfo #0:\n"
                "          timestamp=2026-09-06 22:39:39.266 pid=99 user=0\n"
                "          process=com.x\n"
            )
        )
    )

    result = await DebuggingService(backend).get_process_exit_history("emulator-5554", "com.x")

    assert result.count == 1
    rec = result.records[0]
    assert rec.pid == 99
    assert rec.reason_code is None
    assert rec.importance is None


@pytest.mark.asyncio
async def test_get_process_exit_history__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        activity_exit_info_result=_cr(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )
    with pytest.raises(DeviceNotFoundError):
        await DebuggingService(backend).get_process_exit_history("bogus", "com.x")


@pytest.mark.asyncio
async def test_get_process_exit_history__permission_denied() -> None:
    backend = FakeBackend(
        activity_exit_info_result=_cr(stderr="Permission Denial: exit-info\n", exit_code=1)
    )
    with pytest.raises(PermissionDeniedError):
        await DebuggingService(backend).get_process_exit_history("emulator-5554", "com.x")


@pytest.mark.asyncio
async def test_get_process_exit_history__unclassified_backend_error() -> None:
    backend = FakeBackend(activity_exit_info_result=_cr(stderr="weird\n", exit_code=2))
    with pytest.raises(BackendError):
        await DebuggingService(backend).get_process_exit_history("emulator-5554", "com.x")


@pytest.mark.asyncio
async def test_get_process_exit_history__backend_unavailable() -> None:
    with pytest.raises(AdbUnavailableError):
        await DebuggingService(FakeBackend(unavailable=True)).get_process_exit_history(
            "emulator-5554", "com.x"
        )
