"""Layer 1 unit tests: DebuggingService against FakeBackend directly."""

from __future__ import annotations

from pathlib import Path

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
    PolicyViolationError,
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


# --- set_debug_app / clear_debug_app / list_jdwp_processes ------------


@pytest.mark.asyncio
async def test_set_debug_app__default_command() -> None:
    backend = RecordingBackend()

    result = await DebuggingService(backend).set_debug_app("emulator-5554", "com.example.app")

    assert backend.command == "am set-debug-app com.example.app"
    assert result.wait_for_debugger is False
    assert result.persistent is False


@pytest.mark.asyncio
async def test_set_debug_app__wait_and_persistent_flags() -> None:
    backend = RecordingBackend()

    result = await DebuggingService(backend).set_debug_app(
        "emulator-5554", "com.example.app", wait_for_debugger=True, persistent=True
    )

    assert backend.command == "am set-debug-app -w --persistent com.example.app"
    assert result.wait_for_debugger is True
    assert result.persistent is True


@pytest.mark.asyncio
async def test_set_debug_app__unknown_package_is_not_an_error() -> None:
    result = await DebuggingService(FakeBackend()).set_debug_app("emulator-5554", "com.nope.nope")
    assert result.package == "com.nope.nope"


@pytest.mark.asyncio
async def test_set_debug_app__blank_package_rejected_before_backend() -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await DebuggingService(Exploding()).set_debug_app("emulator-5554", "  ")


@pytest.mark.asyncio
async def test_set_debug_app__permission_denied() -> None:
    backend = FakeBackend(set_debug_app_result=_cr(stderr="Permission Denial\n", exit_code=1))
    with pytest.raises(PermissionDeniedError):
        await DebuggingService(backend).set_debug_app("emulator-5554", "com.x")


@pytest.mark.asyncio
async def test_clear_debug_app__command_and_idempotent() -> None:
    backend = RecordingBackend()

    result = await DebuggingService(backend).clear_debug_app("emulator-5554")

    assert backend.command == "am clear-debug-app"
    assert result.cleared is True


@pytest.mark.asyncio
async def test_clear_debug_app__unclassified_backend_error() -> None:
    backend = FakeBackend(clear_debug_app_result=_cr(stderr="broken\n", exit_code=2))
    with pytest.raises(BackendError):
        await DebuggingService(backend).clear_debug_app("emulator-5554")


@pytest.mark.asyncio
async def test_list_jdwp_processes__parses_pids() -> None:
    result = await DebuggingService(FakeBackend()).list_jdwp_processes("emulator-5554")

    assert result.count == 3
    assert result.pids == [1224, 1568, 2411]


@pytest.mark.asyncio
async def test_list_jdwp_processes__none() -> None:
    backend = FakeBackend(jdwp_result=_cr(stdout=""))
    result = await DebuggingService(backend).list_jdwp_processes("emulator-5554")
    assert result.count == 0
    assert result.pids == []


@pytest.mark.asyncio
async def test_list_jdwp_processes__invalid_lines_ignored_and_deduped() -> None:
    backend = FakeBackend(jdwp_result=_cr(stdout="1224\nnot-a-pid\n1224\n1568\n"))
    result = await DebuggingService(backend).list_jdwp_processes("emulator-5554")
    assert result.pids == [1224, 1568]


@pytest.mark.asyncio
async def test_list_jdwp_processes__device_offline_raises_device_not_found() -> None:
    backend = FakeBackend(
        jdwp_result=_cr(stderr="error: device offline\n", exit_code=1)
    )
    with pytest.raises(DeviceNotFoundError):
        await DebuggingService(backend).list_jdwp_processes("emulator-5554")


@pytest.mark.asyncio
async def test_list_jdwp_processes__backend_unavailable() -> None:
    with pytest.raises(AdbUnavailableError):
        await DebuggingService(FakeBackend(unavailable=True)).list_jdwp_processes("emulator-5554")


# --- capture_native_backtrace / capture_native_tombstone ------------


@pytest.mark.asyncio
async def test_capture_native_backtrace__command_and_parse() -> None:
    backend = RecordingBackend()

    result = await DebuggingService(backend).capture_native_backtrace("emulator-5554", 1224)

    assert backend.command == "debuggerd -b 1224"
    assert result.pid == 1224
    assert result.process_name == "com.android.systemui"
    assert result.abi == "x86_64"
    assert result.thread_count == 2
    assert result.threads[0].name == "ndroid.systemui"
    assert result.threads[0].sys_tid == 1224
    assert result.threads[0].frame_count == 3
    assert result.threads[1].name == "Binder:1224_1"
    assert result.threads[1].frame_count == 2
    assert "__epoll_pwait" in result.text


@pytest.mark.asyncio
async def test_capture_native_backtrace__non_positive_pid_rejected() -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await DebuggingService(Exploding()).capture_native_backtrace("emulator-5554", 0)


@pytest.mark.asyncio
async def test_capture_native_backtrace__root_required_raises_permission_denied() -> None:
    backend = FakeBackend(debuggerd_backtrace_result=_cr(stdout="debuggerd: root is required\n"))
    with pytest.raises(PermissionDeniedError):
        await DebuggingService(backend).capture_native_backtrace("emulator-5554", 1224)


@pytest.mark.asyncio
async def test_capture_native_backtrace__dead_pid_raises_backend_error() -> None:
    backend = FakeBackend(debuggerd_backtrace_result=_cr(stdout="Cannot attach to process 99\n"))
    with pytest.raises(BackendError):
        await DebuggingService(backend).capture_native_backtrace("emulator-5554", 99)


@pytest.mark.asyncio
async def test_capture_native_backtrace__unknown_serial() -> None:
    backend = FakeBackend(
        debuggerd_backtrace_result=_cr(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )
    with pytest.raises(DeviceNotFoundError):
        await DebuggingService(backend).capture_native_backtrace("bogus", 1224)


@pytest.mark.asyncio
async def test_capture_native_tombstone__writes_file_and_parses(tmp_path: Path) -> None:
    backend = RecordingBackend()

    result = await DebuggingService(backend, local_root=tmp_path).capture_native_tombstone(
        "emulator-5554", 1224, "sysui.txt"
    )

    assert backend.command == "debuggerd 1224"
    assert result.local_path == str(tmp_path / "tombstones" / "sysui.txt")
    assert (tmp_path / "tombstones" / "sysui.txt").read_text().startswith("*** ***")
    assert result.process_name == "com.android.systemui"
    assert result.abi == "x86_64"
    assert result.signal is not None and result.signal.startswith("35 ")
    assert result.frame_count == 24
    assert result.device_tombstone_ref == "tombstone_27.pb"
    assert result.size_bytes is not None and result.size_bytes > 0


@pytest.mark.asyncio
async def test_capture_native_tombstone__no_local_root_raises_policy() -> None:
    with pytest.raises(PolicyViolationError):
        await DebuggingService(FakeBackend(), local_root=None).capture_native_tombstone(
            "emulator-5554", 1224, "x.txt"
        )


@pytest.mark.asyncio
async def test_capture_native_tombstone__path_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(PolicyViolationError):
        await DebuggingService(FakeBackend(), local_root=tmp_path).capture_native_tombstone(
            "emulator-5554", 1224, "../../escape.txt"
        )


@pytest.mark.asyncio
async def test_capture_native_tombstone__root_required_raises_permission_denied(
    tmp_path: Path,
) -> None:
    backend = FakeBackend(debuggerd_tombstone_result=_cr(stdout="debuggerd: root is required\n"))
    with pytest.raises(PermissionDeniedError):
        await DebuggingService(backend, local_root=tmp_path).capture_native_tombstone(
            "emulator-5554", 1224, "x.txt"
        )


@pytest.mark.asyncio
async def test_capture_native_tombstone__non_positive_pid_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidArgumentError):
        await DebuggingService(FakeBackend(), local_root=tmp_path).capture_native_tombstone(
            "emulator-5554", -1, "x.txt"
        )
