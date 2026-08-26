"""Layer 1 unit tests: LoggerService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    LogSessionNotFoundError,
    PackageNotRunningError,
    PolicyViolationError,
)
from adb_mcp.modules.logger.service import (
    ClearLogsResult,
    LogBufferSize,
    LogDump,
    LoggerService,
    LogSessionHandle,
    LogSessionResult,
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


@pytest.mark.asyncio
async def test_start_log_session__returns_handle_with_new_session_id() -> None:
    service = LoggerService(FakeBackend())

    handle = await service.start_log_session("emulator-5554", "test-session", buffer="main")

    assert handle.serial == "emulator-5554"
    assert handle.buffer == "main"
    assert handle.session_id
    assert handle.name == "test-session"
    assert handle.pid is None
    assert handle.package is None


@pytest.mark.asyncio
async def test_start_log_session__pid_is_echoed_back_in_handle() -> None:
    service = LoggerService(FakeBackend())

    handle = await service.start_log_session("emulator-5554", "test-session", pid=725)

    assert handle.pid == 725
    assert handle.package is None


@pytest.mark.asyncio
async def test_start_log_session__package_resolves_to_pid_in_handle() -> None:
    service = LoggerService(FakeBackend())  # default pidof_result stdout="19861\n"

    handle = await service.start_log_session(
        "emulator-5554", "test-session", package="com.android.systemui"
    )

    assert handle.pid == 19861
    assert handle.package == "com.android.systemui"


@pytest.mark.asyncio
async def test_start_log_session__package_not_running_raises_package_not_running() -> None:
    backend = FakeBackend(pidof_result=CommandResult(stdout="", stderr="", exit_code=1, duration_ms=20.0))
    service = LoggerService(backend)

    with pytest.raises(PackageNotRunningError):
        await service.start_log_session("emulator-5554", "test-session", package="com.bogus.doesnotexist")


@pytest.mark.asyncio
async def test_start_log_session__pid_and_package_together_raises_invalid_argument() -> None:
    service = LoggerService(FakeBackend())

    with pytest.raises(InvalidArgumentError):
        await service.start_log_session(
            "emulator-5554", "test-session", pid=725, package="com.android.systemui"
        )


@pytest.mark.asyncio
async def test_start_log_session__two_calls_get_distinct_session_ids() -> None:
    service = LoggerService(FakeBackend())

    first = await service.start_log_session("emulator-5554", "test-session")
    second = await service.start_log_session("emulator-5554", "test-session")

    assert first.session_id != second.session_id


@pytest.mark.asyncio
async def test_start_log_session__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        log_session_anchor_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = LoggerService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.start_log_session("bogus", "test-session")


@pytest.mark.asyncio
async def test_start_log_session__adb_unavailable_propagates_as_error() -> None:
    service = LoggerService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.start_log_session("emulator-5554", "test-session")


def test_log_session_handle_summary_mentions_session_id_name_and_buffer() -> None:
    summary = LogSessionHandle(
        session_id="abc123", serial="emulator-5554", buffer="main", name="wifi_repro", pid=None, package=None
    ).summary()
    assert "abc123" in summary
    assert "wifi_repro" in summary
    assert "main" in summary
    assert "emulator-5554" in summary


@pytest.mark.asyncio
async def test_stop_log_session__writes_captured_output_to_local_path(tmp_path: Path) -> None:
    service = LoggerService(FakeBackend(), local_root=tmp_path)
    handle = await service.start_log_session("emulator-5554", "test-session")

    result = await service.stop_log_session(handle.session_id, "session1.log")

    assert result.session_id == handle.session_id
    assert result.serial == "emulator-5554"
    assert result.buffer == "main"
    assert result.local_path == str(tmp_path / "session1.log")
    assert result.line_count > 0
    written = (tmp_path / "session1.log").read_text()
    assert "beginning of main" in written


@pytest.mark.asyncio
async def test_stop_log_session__second_stop_raises_session_not_found(tmp_path: Path) -> None:
    service = LoggerService(FakeBackend(), local_root=tmp_path)
    handle = await service.start_log_session("emulator-5554", "test-session")
    await service.stop_log_session(handle.session_id, "session1.log")

    with pytest.raises(LogSessionNotFoundError):
        await service.stop_log_session(handle.session_id, "session2.log")


@pytest.mark.asyncio
async def test_stop_log_session__unknown_session_id_raises_session_not_found(tmp_path: Path) -> None:
    service = LoggerService(FakeBackend(), local_root=tmp_path)

    with pytest.raises(LogSessionNotFoundError):
        await service.stop_log_session("does-not-exist", "session1.log")


@pytest.mark.asyncio
async def test_stop_log_session__no_local_root_configured_raises_policy_violation() -> None:
    service = LoggerService(FakeBackend())  # local_root omitted
    handle = await service.start_log_session("emulator-5554", "test-session")

    with pytest.raises(PolicyViolationError):
        await service.stop_log_session(handle.session_id, "session1.log")


@pytest.mark.asyncio
async def test_stop_log_session__path_escaping_local_root_raises_policy_violation(
    tmp_path: Path,
) -> None:
    service = LoggerService(FakeBackend(), local_root=tmp_path)
    handle = await service.start_log_session("emulator-5554", "test-session")

    with pytest.raises(PolicyViolationError):
        await service.stop_log_session(handle.session_id, "../outside.log")


@pytest.mark.asyncio
async def test_stop_log_session__absolute_path_outside_local_root_raises_policy_violation(
    tmp_path: Path,
) -> None:
    service = LoggerService(FakeBackend(), local_root=tmp_path)
    handle = await service.start_log_session("emulator-5554", "test-session")

    with pytest.raises(PolicyViolationError):
        await service.stop_log_session(handle.session_id, "/etc/passwd")


@pytest.mark.asyncio
async def test_stop_log_session__policy_violation_leaves_session_open(tmp_path: Path) -> None:
    # A rejected local_path shouldn't consume the session — the caller should
    # be able to retry with a valid path.
    service = LoggerService(FakeBackend(), local_root=tmp_path)
    handle = await service.start_log_session("emulator-5554", "test-session")

    with pytest.raises(PolicyViolationError):
        await service.stop_log_session(handle.session_id, "../outside.log")

    result = await service.stop_log_session(handle.session_id, "session1.log")
    assert result.session_id == handle.session_id


@pytest.mark.asyncio
async def test_stop_log_session__empty_buffer_at_start_omits_time_filter(tmp_path: Path) -> None:
    # Verified live: -t 1 -v epoch returns empty stdout, exit 0, on an empty
    # buffer — no anchor line to parse, so since=None and stop_log_session
    # must not send a -t flag at all (there's nothing to anchor on).
    captured: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured.append(command)
            return await super().shell(serial, command)

    backend = RecordingBackend(
        log_session_anchor_result=CommandResult(stdout="", stderr="", exit_code=0, duration_ms=10.0)
    )
    service = LoggerService(backend, local_root=tmp_path)
    handle = await service.start_log_session("emulator-5554", "test-session", buffer="crash")

    await service.stop_log_session(handle.session_id, "session1.log")

    assert captured[1] == "logcat -d -v threadtime -b crash"


@pytest.mark.asyncio
async def test_stop_log_session__anchor_is_passed_to_replay_command(tmp_path: Path) -> None:
    captured: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured.append(command)
            return await super().shell(serial, command)

    backend = RecordingBackend(
        log_session_anchor_result=CommandResult(
            stdout="         1787727659.552   548   548 I adbd    : hello\n",
            stderr="",
            exit_code=0,
            duration_ms=10.0,
        )
    )
    service = LoggerService(backend, local_root=tmp_path)
    handle = await service.start_log_session("emulator-5554", "test-session", buffer="main")

    await service.stop_log_session(handle.session_id, "session1.log")

    assert captured[1] == "logcat -d -v threadtime -b main -t 1787727659.552"


@pytest.mark.asyncio
async def test_stop_log_session__pid_configured_at_start_is_applied_at_replay(tmp_path: Path) -> None:
    captured: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured.append(command)
            return await super().shell(serial, command)

    service = LoggerService(RecordingBackend(), local_root=tmp_path)
    handle = await service.start_log_session("emulator-5554", "test-session", buffer="main", pid=725)

    await service.stop_log_session(handle.session_id, "session1.log")

    assert "--pid=725" in captured[1]


@pytest.mark.asyncio
async def test_stop_log_session__package_configured_at_start_resolves_pid_and_applies_at_replay(
    tmp_path: Path,
) -> None:
    captured: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured.append(command)
            return await super().shell(serial, command)

    service = LoggerService(RecordingBackend(), local_root=tmp_path)  # default pidof -> 19861
    handle = await service.start_log_session(
        "emulator-5554", "test-session", package="com.android.systemui"
    )

    result = await service.stop_log_session(handle.session_id, "session1.log")

    assert "--pid=19861" in captured[2]  # captured[0]=pidof, [1]=anchor probe, [2]=replay
    assert result.pid == 19861
    assert result.package == "com.android.systemui"


@pytest.mark.asyncio
async def test_stop_log_session__tag_and_min_priority_configured_at_start_are_applied_at_replay(
    tmp_path: Path,
) -> None:
    captured: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured.append(command)
            return await super().shell(serial, command)

    service = LoggerService(RecordingBackend(), local_root=tmp_path)
    handle = await service.start_log_session(
        "emulator-5554", "test-session", tag="WifiManager", min_priority="D"
    )

    await service.stop_log_session(handle.session_id, "session1.log")

    assert "WifiManager:D *:S" in captured[1]


def test_log_session_result_name_pid_package_round_trip() -> None:
    result = LogSessionResult(
        session_id="abc123",
        serial="emulator-5554",
        buffer="main",
        name="wifi_repro",
        pid=19861,
        package="com.android.systemui",
        local_path="/tmp/session1.log",
        line_count=5,
        duration_s=1.0,
    )
    assert result.pid == 19861
    assert result.package == "com.android.systemui"


@pytest.mark.asyncio
async def test_stop_log_session__unknown_serial_raises_device_not_found(tmp_path: Path) -> None:
    backend = FakeBackend(
        log_session_stop_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = LoggerService(backend, local_root=tmp_path)
    handle = await service.start_log_session("bogus", "test-session")

    with pytest.raises(DeviceNotFoundError):
        await service.stop_log_session(handle.session_id, "session1.log")


def test_log_session_result_summary_mentions_name_line_count_and_path() -> None:
    summary = LogSessionResult(
        session_id="abc123",
        serial="emulator-5554",
        buffer="main",
        name="wifi_repro",
        pid=None,
        package=None,
        local_path="/tmp/session1.log",
        line_count=42,
        duration_s=10.5,
    ).summary()
    assert "42" in summary
    assert "wifi_repro" in summary
    assert "/tmp/session1.log" in summary
