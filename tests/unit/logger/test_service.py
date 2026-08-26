"""Layer 1 unit tests: LoggerService against FakeBackend directly — no MCP
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
    PackageNotRunningError,
)
from adb_mcp.modules.logger.service import (
    ClearLogsResult,
    LogBufferSize,
    LogDump,
    LoggerService,
    PackageLogDump,
)


@pytest.mark.asyncio
async def test_read_logs__returns_raw_logcat_output() -> None:
    service = LoggerService(FakeBackend())

    result = await service.read_logs("emulator-5554")

    assert result.serial == "emulator-5554"
    assert result.buffer == "main"
    assert "beginning of main" in result.output


@pytest.mark.asyncio
async def test_read_logs__builds_command_with_buffer_and_max_lines() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = LoggerService(RecordingBackend())

    await service.read_logs("emulator-5554", buffer="crash", max_lines=50)

    assert captured["command"] == "logcat -d -v threadtime -t 50 -b crash"


@pytest.mark.asyncio
async def test_read_logs__min_priority_builds_wildcard_filterspec() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = LoggerService(RecordingBackend())

    await service.read_logs("emulator-5554", min_priority="W")

    assert captured["command"] == "logcat -d -v threadtime -t 200 -b main *:W"


@pytest.mark.asyncio
async def test_read_logs__tag_builds_exclusive_filterspec_and_is_shell_quoted() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = LoggerService(RecordingBackend())

    await service.read_logs("emulator-5554", tag="; echo pwned; #", min_priority="D")

    assert captured["command"] == "logcat -d -v threadtime -t 200 -b main '; echo pwned; #:D' *:S"


@pytest.mark.asyncio
async def test_read_logs__pid_filter_appends_pid_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = LoggerService(RecordingBackend())

    await service.read_logs("emulator-5554", pid=725)

    assert captured["command"] == "logcat -d -v threadtime -t 200 -b main --pid=725"


@pytest.mark.asyncio
async def test_read_logs__empty_string_tag_is_treated_as_no_tag() -> None:
    # Regression: some MCP clients send "" for an unfilled optional string
    # field instead of omitting it. Verified live that an empty tag builds
    # the malformed filterspec ":V", which logcat rejects with "Invalid
    # filter expression ':V'." — "" must be treated the same as None.
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = LoggerService(RecordingBackend())

    await service.read_logs("emulator-5554", pid=725, tag="")

    assert captured["command"] == "logcat -d -v threadtime -t 200 -b main --pid=725"


@pytest.mark.asyncio
async def test_read_logs__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        read_logs_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = LoggerService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.read_logs("bogus")


@pytest.mark.asyncio
async def test_read_logs__adb_unavailable_propagates_as_error() -> None:
    service = LoggerService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.read_logs("emulator-5554")


def test_log_dump_summary_counts_lines() -> None:
    summary = LogDump(serial="emulator-5554", buffer="main", output="a\nb\nc\n").summary()
    assert "3" in summary
    assert "main" in summary
    assert "emulator-5554" in summary


@pytest.mark.asyncio
async def test_clear_logs__success_returns_serial_and_buffer() -> None:
    service = LoggerService(FakeBackend())

    result = await service.clear_logs("emulator-5554", buffer="crash")

    assert result.serial == "emulator-5554"
    assert result.buffer == "crash"


@pytest.mark.asyncio
async def test_clear_logs__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        clear_logs_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = LoggerService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.clear_logs("bogus")


@pytest.mark.asyncio
async def test_clear_logs__adb_unavailable_propagates_as_error() -> None:
    service = LoggerService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.clear_logs("emulator-5554")


def test_clear_logs_result_summary_mentions_buffer() -> None:
    summary = ClearLogsResult(serial="emulator-5554", buffer="main").summary()
    assert "main" in summary
    assert "emulator-5554" in summary


@pytest.mark.asyncio
async def test_get_log_buffer_size__returns_raw_output() -> None:
    service = LoggerService(FakeBackend())

    result = await service.get_log_buffer_size("emulator-5554", buffer="main")

    assert result.serial == "emulator-5554"
    assert result.buffer == "main"
    assert "ring buffer" in result.output


@pytest.mark.asyncio
async def test_get_log_buffer_size__unknown_buffer_raises_backend_error() -> None:
    # Real adb behavior, verified live: "Unknown -b buffer '<name>'", exit 1.
    backend = FakeBackend(
        get_log_buffer_size_result=CommandResult(
            stdout="", stderr="logcat: Unknown -b buffer 'bogus_buffer'.\n", exit_code=1, duration_ms=15.0
        )
    )
    service = LoggerService(backend)

    with pytest.raises(BackendError):
        await service.get_log_buffer_size("emulator-5554", buffer="main")


@pytest.mark.asyncio
async def test_get_log_buffer_size__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        get_log_buffer_size_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = LoggerService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.get_log_buffer_size("bogus")


@pytest.mark.asyncio
async def test_get_log_buffer_size__adb_unavailable_propagates_as_error() -> None:
    service = LoggerService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.get_log_buffer_size("emulator-5554")


def test_log_buffer_size_summary_mentions_buffer_and_output() -> None:
    summary = LogBufferSize(serial="emulator-5554", buffer="main", output="x" * 10).summary()
    assert "main" in summary
    assert "emulator-5554" in summary


@pytest.mark.asyncio
async def test_read_package_logs__resolves_pid_and_returns_output() -> None:
    service = LoggerService(FakeBackend())

    result = await service.read_package_logs("emulator-5554", "com.android.systemui")

    assert result.serial == "emulator-5554"
    assert result.package == "com.android.systemui"
    assert result.pid == 19861
    assert "beginning of main" in result.output


@pytest.mark.asyncio
async def test_read_package_logs__quotes_package_name_for_pidof() -> None:
    captured: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured.append(command)
            return await super().shell(serial, command)

    service = LoggerService(RecordingBackend())

    await service.read_package_logs("emulator-5554", "; echo pwned; #")

    assert captured[0] == "pidof -s '; echo pwned; #'"


@pytest.mark.asyncio
async def test_read_package_logs__second_call_filters_by_resolved_pid() -> None:
    captured: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured.append(command)
            return await super().shell(serial, command)

    service = LoggerService(RecordingBackend())

    await service.read_package_logs("emulator-5554", "com.android.systemui", buffer="crash", max_lines=10)

    assert captured[1] == "logcat -d -v threadtime -t 10 -b crash --pid=19861"


@pytest.mark.asyncio
async def test_read_package_logs__not_running_raises_package_not_running() -> None:
    # Real adb behavior, verified live: pidof exits 1 with empty stdout AND
    # empty stderr both for "not installed" and "installed but not running".
    backend = FakeBackend(
        pidof_result=CommandResult(stdout="", stderr="", exit_code=1, duration_ms=20.0)
    )
    service = LoggerService(backend)

    with pytest.raises(PackageNotRunningError):
        await service.read_package_logs("emulator-5554", "com.bogus.doesnotexist")


@pytest.mark.asyncio
async def test_read_package_logs__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        pidof_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = LoggerService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.read_package_logs("bogus", "com.android.systemui")


@pytest.mark.asyncio
async def test_read_package_logs__other_pidof_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        pidof_result=CommandResult(
            stdout="", stderr="pidof: some unexpected failure", exit_code=1, duration_ms=10.0
        )
    )
    service = LoggerService(backend)

    with pytest.raises(BackendError):
        await service.read_package_logs("emulator-5554", "com.android.systemui")


@pytest.mark.asyncio
async def test_read_package_logs__adb_unavailable_propagates_as_error() -> None:
    service = LoggerService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.read_package_logs("emulator-5554", "com.android.systemui")


def test_package_log_dump_summary_mentions_package_and_pid() -> None:
    summary = PackageLogDump(
        serial="emulator-5554", package="com.android.systemui", pid=19861, output="a\nb\n"
    ).summary()
    assert "com.android.systemui" in summary
    assert "19861" in summary
    assert "2" in summary
