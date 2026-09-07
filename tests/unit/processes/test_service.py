"""Layer 1 unit tests: ProcessesService against FakeBackend directly — no MCP
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
    InvalidArgumentError,
    PackageNotRunningError,
    PermissionDeniedError,
    ProcessMemoryUnavailableError,
)
from adb_automation_mcp.modules.processes.service import ProcessesService


class RecordingBackend(FakeBackend):
    """Captures the last shell command the service issued."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.command: str | None = None

    async def shell(
        self, serial: str, command: str, timeout_s: float | None = None
    ) -> CommandResult:
        self.command = command
        return await super().shell(serial, command, timeout_s)


def _shell(stdout: str = "", stderr: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(stdout=stdout, stderr=stderr, exit_code=exit_code, duration_ms=20.0)


@pytest.mark.asyncio
async def test_force_stop_app__success_with_empty_stdout() -> None:
    service = ProcessesService(FakeBackend())

    result = await service.force_stop_app("emulator-5554", "com.example.app")

    assert result.serial == "emulator-5554"
    assert result.package_name == "com.example.app"
    assert result.user_id is None
    assert result.output == ""


@pytest.mark.asyncio
async def test_force_stop_app__sends_user_id_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = ProcessesService(RecordingBackend())

    result = await service.force_stop_app("emulator-5554", "com.example.app", user_id=10)

    assert captured["command"] == "am force-stop --user 10 com.example.app"
    assert result.user_id == 10


@pytest.mark.asyncio
async def test_force_stop_app__nonexistent_package_still_succeeds() -> None:
    # Real, documented am behavior: forceStopPackage() doesn't validate that
    # the package is installed — it's a silent no-op with exit 0/empty
    # stdout when there's nothing to stop, same as a real match.
    service = ProcessesService(FakeBackend())

    result = await service.force_stop_app("emulator-5554", "com.example.does.not.exist")

    assert result.package_name == "com.example.does.not.exist"
    assert result.output == ""


@pytest.mark.asyncio
async def test_force_stop_app__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        force_stop_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = ProcessesService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.force_stop_app("bogus", "com.example.app")


@pytest.mark.asyncio
async def test_force_stop_app__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        force_stop_result=CommandResult(
            stdout="",
            stderr=(
                "java.lang.SecurityException: Permission Denial: forceStopPackage() from "
                "pid=1234, uid=2000 requires android.permission.FORCE_STOP_PACKAGES\n"
            ),
            exit_code=1,
            duration_ms=12.0,
        )
    )
    service = ProcessesService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.force_stop_app("emulator-5554", "com.example.app")


@pytest.mark.asyncio
async def test_force_stop_app__unclassified_backend_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        force_stop_result=CommandResult(
            stdout="", stderr="Error: Activity manager has died\n", exit_code=1, duration_ms=5.0
        )
    )
    service = ProcessesService(backend)

    with pytest.raises(BackendError):
        await service.force_stop_app("emulator-5554", "com.example.app")


# --- list_processes -----------------------------------------------------


@pytest.mark.asyncio
async def test_list_processes__sends_fixed_ps_command_and_parses_rows() -> None:
    backend = RecordingBackend()

    result = await ProcessesService(backend).list_processes("emulator-5554")

    assert backend.command == "ps -A -o PID,PPID,USER,RSS,NAME"
    assert result.serial == "emulator-5554"
    assert result.name_filter is None
    assert [p.pid for p in result.processes] == [1, 2, 1224]

    app = result.processes[2]
    assert app.pid == 1224
    assert app.ppid == 432
    assert app.user == "u0_a141"
    assert app.rss_kb == 260040
    assert app.name == "com.android.systemui"
    # kernel thread: bracketed name, RSS 0
    assert result.processes[1].name == "[kthreadd]"
    assert result.processes[1].rss_kb == 0


@pytest.mark.asyncio
async def test_list_processes__name_filter_applied_server_side() -> None:
    result = await ProcessesService(FakeBackend()).list_processes(
        "emulator-5554", name_filter="systemui"
    )

    assert result.name_filter == "systemui"
    assert [p.name for p in result.processes] == ["com.android.systemui"]


@pytest.mark.asyncio
async def test_list_processes__filter_matching_nothing_is_valid_empty_list() -> None:
    result = await ProcessesService(FakeBackend()).list_processes(
        "emulator-5554", name_filter="com.nope.nope"
    )

    assert result.processes == []


@pytest.mark.asyncio
async def test_list_processes__blank_filter_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await ProcessesService(ExplodingBackend()).list_processes("emulator-5554", name_filter="  ")


@pytest.mark.asyncio
async def test_list_processes__malformed_output_skips_bad_rows_without_crashing() -> None:
    backend = FakeBackend(
        ps_result=_shell(
            stdout=(
                "  PID  PPID USER            RSS NAME\n"
                "garbage line with too few\n"
                "   1     0 root          14776 init\n"
                "\x00\x00 not a row at all\n"
                "  99   ?    root            xx weird\n"
            )
        )
    )

    result = await ProcessesService(backend).list_processes("emulator-5554")

    assert [p.name for p in result.processes] == ["init"]


@pytest.mark.asyncio
async def test_list_processes__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        ps_result=_shell(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )

    with pytest.raises(DeviceNotFoundError):
        await ProcessesService(backend).list_processes("bogus")


@pytest.mark.asyncio
async def test_list_processes__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(ps_result=_shell(stderr="Permission denied\n", exit_code=1))

    with pytest.raises(PermissionDeniedError):
        await ProcessesService(backend).list_processes("emulator-5554")


@pytest.mark.asyncio
async def test_list_processes__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(ps_result=_shell(stderr="ps: bad -o argument\n", exit_code=1))

    with pytest.raises(BackendError):
        await ProcessesService(backend).list_processes("emulator-5554")


# --- get_process_id ---------------------------------------------------


@pytest.mark.asyncio
async def test_get_process_id__single_pid() -> None:
    backend = RecordingBackend()

    result = await ProcessesService(backend).get_process_id(
        "emulator-5554", "com.android.systemui"
    )

    assert backend.command == "pidof com.android.systemui"
    assert result.pids == [1224]
    assert result.running is True


@pytest.mark.asyncio
async def test_get_process_id__multiple_pids() -> None:
    backend = FakeBackend(pidof_names_result=_shell(stdout="111 222 333\n"))

    result = await ProcessesService(backend).get_process_id("emulator-5554", "system_server")

    assert result.pids == [111, 222, 333]
    assert result.running is True


@pytest.mark.asyncio
async def test_get_process_id__absent_process_is_valid_not_running_result() -> None:
    # `pidof` exits 1 with no output when nothing matches — not an error.
    backend = FakeBackend(pidof_names_result=_shell(exit_code=1))

    result = await ProcessesService(backend).get_process_id("emulator-5554", "com.nope.nope")

    assert result.pids == []
    assert result.running is False


@pytest.mark.asyncio
async def test_get_process_id__blank_name_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await ProcessesService(ExplodingBackend()).get_process_id("emulator-5554", "   ")


@pytest.mark.asyncio
async def test_get_process_id__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        pidof_names_result=_shell(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )

    with pytest.raises(DeviceNotFoundError):
        await ProcessesService(backend).get_process_id("bogus", "com.android.systemui")


@pytest.mark.asyncio
async def test_get_process_id__garbage_stdout_does_not_crash() -> None:
    backend = FakeBackend(pidof_names_result=_shell(stdout="not-a-number\n"))

    result = await ProcessesService(backend).get_process_id("emulator-5554", "x")

    assert result.pids == []
    assert result.running is False


# --- kill_background_processes --------------------------------------


@pytest.mark.asyncio
async def test_kill_background_processes__sends_am_kill() -> None:
    backend = RecordingBackend()

    result = await ProcessesService(backend).kill_background_processes(
        "emulator-5554", "com.example.app"
    )

    assert backend.command == "am kill com.example.app"
    assert result.serial == "emulator-5554"
    assert result.package_name == "com.example.app"
    assert result.user_id is None
    assert result.output == ""


@pytest.mark.asyncio
async def test_kill_background_processes__user_scope_maps_to_flag() -> None:
    backend = RecordingBackend()

    result = await ProcessesService(backend).kill_background_processes(
        "emulator-5554", "com.example.app", user_id=10
    )

    assert backend.command == "am kill --user 10 com.example.app"
    assert result.user_id == 10


@pytest.mark.asyncio
async def test_kill_background_processes__nonexistent_package_still_succeeds() -> None:
    # `am kill` is a silent no-op (exit 0) when nothing is killable.
    result = await ProcessesService(FakeBackend()).kill_background_processes(
        "emulator-5554", "com.example.not.installed"
    )

    assert result.package_name == "com.example.not.installed"
    assert result.output == ""


@pytest.mark.asyncio
async def test_kill_background_processes__blank_package_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await ProcessesService(ExplodingBackend()).kill_background_processes("emulator-5554", "")


@pytest.mark.asyncio
async def test_kill_background_processes__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        am_kill_result=_shell(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )

    with pytest.raises(DeviceNotFoundError):
        await ProcessesService(backend).kill_background_processes("bogus", "com.example.app")


@pytest.mark.asyncio
async def test_kill_background_processes__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        am_kill_result=_shell(
            stderr="java.lang.SecurityException: Permission Denial: killBackgroundProcesses\n",
            exit_code=1,
        )
    )

    with pytest.raises(PermissionDeniedError):
        await ProcessesService(backend).kill_background_processes("emulator-5554", "com.example.app")


# --- get_process_memory --------------------------------------------


@pytest.mark.asyncio
async def test_get_process_memory__parses_app_summary_and_totals() -> None:
    backend = RecordingBackend()

    result = await ProcessesService(backend).get_process_memory(
        "emulator-5554", "com.android.systemui"
    )

    assert backend.command == "dumpsys meminfo -s com.android.systemui"
    assert result.pid == 1224
    assert result.process_name == "com.android.systemui"
    assert result.java_heap_pss_kb == 28048
    assert result.native_heap_pss_kb == 21120
    assert result.code_pss_kb == 37168
    assert result.stack_pss_kb == 1632
    assert result.graphics_pss_kb == 0
    assert result.private_other_pss_kb == 4008
    assert result.system_pss_kb == 13345
    assert result.total_pss_kb == 105321
    assert result.total_rss_kb == 268416
    assert result.total_swap_kb == 0


@pytest.mark.asyncio
async def test_get_process_memory__accepts_numeric_pid_target() -> None:
    backend = RecordingBackend()

    await ProcessesService(backend).get_process_memory("emulator-5554", "1224")

    assert backend.command == "dumpsys meminfo -s 1224"


@pytest.mark.asyncio
async def test_get_process_memory__not_running_raises_package_not_running() -> None:
    backend = FakeBackend(
        dumpsys_meminfo_result=_shell(stdout="No process found for: com.example.notinstalled\n")
    )

    with pytest.raises(PackageNotRunningError):
        await ProcessesService(backend).get_process_memory(
            "emulator-5554", "com.example.notinstalled"
        )


@pytest.mark.asyncio
async def test_get_process_memory__blank_target_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await ProcessesService(ExplodingBackend()).get_process_memory("emulator-5554", "  ")


@pytest.mark.asyncio
async def test_get_process_memory__unparseable_output_raises_process_memory_unavailable() -> None:
    backend = FakeBackend(
        dumpsys_meminfo_result=_shell(stdout="Applications Memory Usage (in Kilobytes):\n\n")
    )

    with pytest.raises(ProcessMemoryUnavailableError):
        await ProcessesService(backend).get_process_memory("emulator-5554", "com.android.systemui")


@pytest.mark.asyncio
async def test_get_process_memory__version_variant_without_total_line_does_not_crash() -> None:
    backend = FakeBackend(
        dumpsys_meminfo_result=_shell(
            stdout=(
                "** MEMINFO in pid 900 [com.legacy.app] **\n"
                "                 Pss  Private  Private\n"
                "               Total    Dirty    Clean\n"
                "  Native Heap    512      500        0\n"
            )
        )
    )

    result = await ProcessesService(backend).get_process_memory("emulator-5554", "com.legacy.app")

    assert result.pid == 900
    assert result.process_name == "com.legacy.app"
    assert result.total_pss_kb is None
    assert result.java_heap_pss_kb is None


@pytest.mark.asyncio
async def test_get_process_memory__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        dumpsys_meminfo_result=_shell(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )

    with pytest.raises(DeviceNotFoundError):
        await ProcessesService(backend).get_process_memory("bogus", "com.android.systemui")


@pytest.mark.asyncio
async def test_get_process_memory__backend_unavailable_raises_adb_unavailable() -> None:
    with pytest.raises(AdbUnavailableError):
        await ProcessesService(FakeBackend(unavailable=True)).get_process_memory(
            "emulator-5554", "com.android.systemui"
        )
