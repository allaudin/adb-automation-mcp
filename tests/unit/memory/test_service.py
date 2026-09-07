"""Layer 1 unit tests: MemoryService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

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
    MemoryInfoUnavailableError,
    PackageNotRunningError,
    PermissionDeniedError,
    PolicyViolationError,
)
from adb_automation_mcp.modules.memory.service import MemoryService


class RecordingBackend(FakeBackend):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.commands: list[str] = []

    async def shell(
        self, serial: str, command: str, timeout_s: float | None = None
    ) -> CommandResult:
        self.commands.append(command)
        return await super().shell(serial, command, timeout_s)


def _cr(stdout: str = "", stderr: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(stdout=stdout, stderr=stderr, exit_code=exit_code, duration_ms=20.0)


_NOT_RUNNING = _cr(stdout="No process found for: com.nope\n")


# --- get_app_memory_summary ------------------------------------------


@pytest.mark.asyncio
async def test_get_app_memory_summary__command_and_parse() -> None:
    backend = RecordingBackend()

    result = await MemoryService(backend).get_app_memory_summary(
        "emulator-5554", "com.android.systemui"
    )

    assert backend.commands == ["dumpsys meminfo -s com.android.systemui"]
    assert result.pid == 1224
    assert result.process_name == "com.android.systemui"
    assert result.total_pss_kb == 105321
    assert result.total_rss_kb == 268416
    assert result.java_heap_pss_kb == 28048


@pytest.mark.asyncio
async def test_get_app_memory_summary__pid_input() -> None:
    backend = RecordingBackend()
    await MemoryService(backend).get_app_memory_summary("emulator-5554", "1224")
    assert backend.commands == ["dumpsys meminfo -s 1224"]


@pytest.mark.asyncio
async def test_get_app_memory_summary__blank_target_rejected_before_backend() -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await MemoryService(Exploding()).get_app_memory_summary("emulator-5554", "  ")


@pytest.mark.asyncio
async def test_get_app_memory_summary__not_running_raises_package_not_running() -> None:
    backend = FakeBackend(dumpsys_meminfo_result=_NOT_RUNNING)
    with pytest.raises(PackageNotRunningError):
        await MemoryService(backend).get_app_memory_summary("emulator-5554", "com.nope")


@pytest.mark.asyncio
async def test_get_app_memory_summary__malformed_raises_memory_info_unavailable() -> None:
    backend = FakeBackend(dumpsys_meminfo_result=_cr(stdout="Applications Memory Usage\n\n"))
    with pytest.raises(MemoryInfoUnavailableError):
        await MemoryService(backend).get_app_memory_summary("emulator-5554", "com.x")


@pytest.mark.asyncio
async def test_get_app_memory_summary__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        dumpsys_meminfo_result=_cr(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )
    with pytest.raises(DeviceNotFoundError):
        await MemoryService(backend).get_app_memory_summary("bogus", "com.x")


# --- get_app_memory_details ----------------------------------------


@pytest.mark.asyncio
async def test_get_app_memory_details__command_and_full_parse() -> None:
    backend = RecordingBackend()

    result = await MemoryService(backend).get_app_memory_details(
        "emulator-5554", "com.android.systemui"
    )

    assert backend.commands == ["dumpsys meminfo -a com.android.systemui"]
    assert result.total_pss_kb == 104328
    names = [c.name for c in result.categories]
    assert "Native Heap" in names and "TOTAL" in names
    native = next(c for c in result.categories if c.name == "Native Heap")
    assert native.pss_total_kb == 21824
    assert native.private_dirty_kb == 21748
    assert native.rss_total_kb == 25540
    assert result.objects["views"] == 855
    assert result.objects["local_binders"] == 374
    assert result.sql["memory_used"] == 0
    assert result.sql["malloc_size"] == 0


@pytest.mark.asyncio
async def test_get_app_memory_details__missing_optional_sections_are_empty() -> None:
    backend = FakeBackend(
        dumpsys_meminfo_detail_result=_cr(
            stdout=(
                "** MEMINFO in pid 99 [com.x] **\n"
                " App Summary\n"
                "           TOTAL PSS:   1000            TOTAL RSS:   2000      TOTAL SWAP (KB):   0\n"
            )
        )
    )

    result = await MemoryService(backend).get_app_memory_details("emulator-5554", "com.x")

    assert result.total_pss_kb == 1000
    assert result.categories == []
    assert result.objects == {}
    assert result.sql == {}


@pytest.mark.asyncio
async def test_get_app_memory_details__not_running_raises_package_not_running() -> None:
    backend = FakeBackend(dumpsys_meminfo_detail_result=_NOT_RUNNING)
    with pytest.raises(PackageNotRunningError):
        await MemoryService(backend).get_app_memory_details("emulator-5554", "com.nope")


@pytest.mark.asyncio
async def test_get_app_memory_details__garbage_raises_memory_info_unavailable() -> None:
    backend = FakeBackend(dumpsys_meminfo_detail_result=_cr(stdout="\x00 nonsense }}}\n"))
    with pytest.raises(MemoryInfoUnavailableError):
        await MemoryService(backend).get_app_memory_details("emulator-5554", "com.x")


# --- get_system_memory_summary -----------------------------------


@pytest.mark.asyncio
async def test_get_system_memory_summary__parses_totals_and_top() -> None:
    backend = RecordingBackend()

    result = await MemoryService(backend).get_system_memory_summary("emulator-5554")

    assert backend.commands == ["dumpsys meminfo"]
    assert result.total_ram_kb == 4007632
    assert result.free_ram_kb == 2516255
    assert result.used_ram_kb == 1406266
    assert result.lost_ram_kb == 95527
    assert result.zram_physical_used_kb == 15404
    assert result.zram_in_swap_kb == 19880
    assert result.zram_total_swap_kb == 3005720
    assert result.status == "status normal"
    assert result.top_processes[0].name == "system"
    assert result.top_processes[0].pid == 729
    assert result.top_processes[0].pss_kb == 266973
    # user-scoped entry keeps its user id
    carlauncher = next(p for p in result.top_processes if p.name.startswith("com.android.car.carlauncher"))
    assert carlauncher.user == 10


@pytest.mark.asyncio
async def test_get_system_memory_summary__zram_absent_is_none() -> None:
    backend = FakeBackend(
        dumpsys_meminfo_system_result=_cr(
            stdout=(
                "Total RAM: 2,000,000K (status normal)\n"
                " Free RAM: 1,000,000K\n"
                " Used RAM: 900,000K\n"
                " Lost RAM: 10,000K\n"
            )
        )
    )

    result = await MemoryService(backend).get_system_memory_summary("emulator-5554")

    assert result.total_ram_kb == 2000000
    assert result.zram_total_swap_kb is None
    assert result.top_processes == []


@pytest.mark.asyncio
async def test_get_system_memory_summary__malformed_raises_memory_info_unavailable() -> None:
    backend = FakeBackend(dumpsys_meminfo_system_result=_cr(stdout="nothing useful\n"))
    with pytest.raises(MemoryInfoUnavailableError):
        await MemoryService(backend).get_system_memory_summary("emulator-5554")


@pytest.mark.asyncio
async def test_get_system_memory_summary__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        dumpsys_meminfo_system_result=_cr(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )
    with pytest.raises(DeviceNotFoundError):
        await MemoryService(backend).get_system_memory_summary("bogus")


# --- get_memory_history --------------------------------------------


@pytest.mark.asyncio
async def test_get_memory_history__command_and_band_parse() -> None:
    backend = RecordingBackend()

    result = await MemoryService(backend).get_memory_history(
        "emulator-5554", "com.android.systemui", hours=3
    )

    assert backend.commands == ["dumpsys procstats --hours 3 com.android.systemui"]
    assert result.has_history is True
    assert result.window_start == "2026-09-07 07:48:12"
    states = [b.state for b in result.bands]
    assert states == ["TOTAL", "Persistent"]
    total = result.bands[0]
    assert total.percent == 100.0
    assert total.samples == 8
    assert total.pss_min_kb == 0
    assert total.pss_avg_kb == 63488  # 62MB -> 62*1024
    assert total.pss_max_kb == 105472  # 103MB
    assert total.rss_min_kb == 268288  # 262MB


@pytest.mark.asyncio
async def test_get_memory_history__multi_hour_window() -> None:
    backend = RecordingBackend()
    await MemoryService(backend).get_memory_history("emulator-5554", "com.x", hours=24)
    assert backend.commands == ["dumpsys procstats --hours 24 com.x"]


@pytest.mark.asyncio
async def test_get_memory_history__no_history_is_valid_empty() -> None:
    backend = FakeBackend(
        procstats_result=_cr(
            stdout="AGGREGATED OVER LAST 3 HOURS:\n          Start time: 2026-09-07 07:48:12\n"
        )
    )

    result = await MemoryService(backend).get_memory_history("emulator-5554", "com.x")

    assert result.has_history is False
    assert result.bands == []


@pytest.mark.asyncio
async def test_get_memory_history__invalid_hours_rejected_before_backend() -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await MemoryService(Exploding()).get_memory_history("emulator-5554", "com.x", hours=0)
    with pytest.raises(InvalidArgumentError):
        await MemoryService(Exploding()).get_memory_history("emulator-5554", "com.x", hours=999)


@pytest.mark.asyncio
async def test_get_memory_history__partial_output_does_not_crash() -> None:
    backend = FakeBackend(
        procstats_result=_cr(
            stdout=(
                "Process summary:\n"
                "  * com.x / u0a1 / v1:\n"
                "         TOTAL: 50% (garbled row without the expected shape)\n"
            )
        )
    )

    result = await MemoryService(backend).get_memory_history("emulator-5554", "com.x")

    assert result.has_history is False


@pytest.mark.asyncio
async def test_get_memory_history__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        procstats_result=_cr(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )
    with pytest.raises(DeviceNotFoundError):
        await MemoryService(backend).get_memory_history("bogus", "com.x")


# --- capture_heap_dump --------------------------------------------


@pytest.mark.asyncio
async def test_capture_heap_dump__managed_success_and_cleanup(tmp_path: Path) -> None:
    backend = RecordingBackend()

    result = await MemoryService(backend, local_root=tmp_path).capture_heap_dump(
        "emulator-5554", "com.android.systemui", "sysui.hprof"
    )

    dump_cmd = next(c for c in backend.commands if c.startswith("am dumpheap"))
    assert dump_cmd.startswith("am dumpheap com.android.systemui /data/local/tmp/")
    assert dump_cmd.endswith(".hprof")
    # temp file cleaned up afterwards
    assert any(c.startswith("rm -f /data/local/tmp/") for c in backend.commands)
    assert result.success is True
    assert result.native is False
    assert result.local_path == str(tmp_path / "heapdumps" / "sysui.hprof")


@pytest.mark.asyncio
async def test_capture_heap_dump__force_gc_and_native_and_user_flags(tmp_path: Path) -> None:
    backend = RecordingBackend()

    await MemoryService(backend, local_root=tmp_path).capture_heap_dump(
        "emulator-5554", "com.x", "x.hprof", force_gc=True, native=True, user_id=10
    )

    dump_cmd = next(c for c in backend.commands if c.startswith("am dumpheap"))
    assert dump_cmd.startswith("am dumpheap --user 10 -n -g com.x /data/local/tmp/")


@pytest.mark.asyncio
async def test_capture_heap_dump__no_local_root_raises_policy(tmp_path: Path) -> None:
    with pytest.raises(PolicyViolationError):
        await MemoryService(FakeBackend(), local_root=None).capture_heap_dump(
            "emulator-5554", "com.x", "x.hprof"
        )


@pytest.mark.asyncio
async def test_capture_heap_dump__path_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(PolicyViolationError):
        await MemoryService(FakeBackend(), local_root=tmp_path).capture_heap_dump(
            "emulator-5554", "com.x", "../../escape.hprof"
        )


@pytest.mark.asyncio
async def test_capture_heap_dump__unknown_process_raises_package_not_running_and_cleans_up(
    tmp_path: Path,
) -> None:
    backend = RecordingBackend(
        am_dumpheap_result=_cr(
            stdout=(
                "File: /data/local/tmp/x.hprof\n\n"
                "Exception occurred while executing 'dumpheap':\n"
                "java.lang.IllegalArgumentException: Unknown process: com.x\n"
            ),
            exit_code=255,
        )
    )

    with pytest.raises(PackageNotRunningError):
        await MemoryService(backend, local_root=tmp_path).capture_heap_dump(
            "emulator-5554", "com.x", "x.hprof"
        )
    assert any(c.startswith("rm -f /data/local/tmp/") for c in backend.commands)


@pytest.mark.asyncio
async def test_capture_heap_dump__pull_failure_raises(tmp_path: Path) -> None:
    class FailingPull(FakeBackend):
        async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
            return _cr(stderr="adb: error: remote object does not exist\n", exit_code=1)

    with pytest.raises(Exception) as exc:
        await MemoryService(FailingPull(), local_root=tmp_path).capture_heap_dump(
            "emulator-5554", "com.x", "x.hprof"
        )
    assert exc.type.__name__ in {"RemoteFileNotFoundError", "BackendError"}


@pytest.mark.asyncio
async def test_capture_heap_dump__bad_timeout_rejected_before_backend(tmp_path: Path) -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await MemoryService(Exploding(), local_root=tmp_path).capture_heap_dump(
            "emulator-5554", "com.x", "x.hprof", timeout_s=9999
        )


@pytest.mark.asyncio
async def test_memory_service__backend_unavailable_raises_adb_unavailable() -> None:
    with pytest.raises(AdbUnavailableError):
        await MemoryService(FakeBackend(unavailable=True)).get_system_memory_summary("emulator-5554")


@pytest.mark.asyncio
async def test_get_app_memory_summary__permission_denied() -> None:
    backend = FakeBackend(
        dumpsys_meminfo_result=_cr(stderr="Permission Denial: dumpsys meminfo\n", exit_code=1)
    )
    with pytest.raises(PermissionDeniedError):
        await MemoryService(backend).get_app_memory_summary("emulator-5554", "com.x")


@pytest.mark.asyncio
async def test_get_app_memory_summary__unclassified_backend_error() -> None:
    backend = FakeBackend(dumpsys_meminfo_result=_cr(stderr="weird failure\n", exit_code=2))
    with pytest.raises(BackendError):
        await MemoryService(backend).get_app_memory_summary("emulator-5554", "com.x")


# --- set_heap_watch / clear_heap_watch / get_memory_maps ------------


@pytest.mark.asyncio
async def test_set_heap_watch__command_and_confirm() -> None:
    backend = RecordingBackend()

    result = await MemoryService(backend).set_heap_watch(
        "emulator-5554", "com.example.app", 268435456
    )

    assert backend.commands == ["am set-watch-heap com.example.app 268435456"]
    assert result.threshold_bytes == 268435456
    assert result.watching is True


@pytest.mark.asyncio
async def test_set_heap_watch__non_positive_threshold_rejected() -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await MemoryService(Exploding()).set_heap_watch("emulator-5554", "com.x", 0)
    with pytest.raises(InvalidArgumentError):
        await MemoryService(Exploding()).set_heap_watch("emulator-5554", "com.x", -5)


@pytest.mark.asyncio
async def test_set_heap_watch__blank_package_rejected() -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await MemoryService(Exploding()).set_heap_watch("emulator-5554", "  ", 1024)


@pytest.mark.asyncio
async def test_set_heap_watch__unsupported_command_raises_backend_error() -> None:
    backend = FakeBackend(
        set_watch_heap_result=_cr(stdout="Error: unknown command 'set-watch-heap'\n", exit_code=255)
    )
    with pytest.raises(BackendError):
        await MemoryService(backend).set_heap_watch("emulator-5554", "com.x", 1024)


@pytest.mark.asyncio
async def test_clear_heap_watch__command_and_idempotent() -> None:
    backend = RecordingBackend()

    result = await MemoryService(backend).clear_heap_watch("emulator-5554", "com.example.app")

    assert backend.commands == ["am clear-watch-heap com.example.app"]
    assert result.cleared is True


@pytest.mark.asyncio
async def test_clear_heap_watch__unknown_serial() -> None:
    backend = FakeBackend(
        clear_watch_heap_result=_cr(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )
    with pytest.raises(DeviceNotFoundError):
        await MemoryService(backend).clear_heap_watch("bogus", "com.x")


@pytest.mark.asyncio
async def test_get_memory_maps__command_and_parse() -> None:
    backend = RecordingBackend()

    result = await MemoryService(backend).get_memory_maps("emulator-5554", 1224)

    assert backend.commands == ["cat /proc/1224/smaps_rollup"]
    assert result.pid == 1224
    assert result.rss_kb == 290988
    assert result.pss_kb == 127651
    assert result.pss_dirty_kb == 71000
    assert result.shared_clean_kb == 143216
    assert result.private_dirty_kb == 69252
    assert result.swap_kb == 8
    assert result.swap_pss_kb == 0


@pytest.mark.asyncio
async def test_get_memory_maps__non_positive_pid_rejected() -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await MemoryService(Exploding()).get_memory_maps("emulator-5554", 0)


@pytest.mark.asyncio
async def test_get_memory_maps__permission_denied() -> None:
    backend = FakeBackend(
        smaps_rollup_result=_cr(stdout="cat: /proc/1/smaps_rollup: Permission denied\n")
    )
    with pytest.raises(PermissionDeniedError):
        await MemoryService(backend).get_memory_maps("emulator-5554", 1)


@pytest.mark.asyncio
async def test_get_memory_maps__process_gone_raises_remote_file_not_found() -> None:
    from adb_automation_mcp.errors import RemoteFileNotFoundError

    backend = FakeBackend(
        smaps_rollup_result=_cr(stdout="cat: /proc/99999/smaps_rollup: No such file or directory\n")
    )
    with pytest.raises(RemoteFileNotFoundError):
        await MemoryService(backend).get_memory_maps("emulator-5554", 99999)


@pytest.mark.asyncio
async def test_get_memory_maps__malformed_output_raises_memory_info_unavailable() -> None:
    backend = FakeBackend(smaps_rollup_result=_cr(stdout="not smaps at all\n"))
    with pytest.raises(MemoryInfoUnavailableError):
        await MemoryService(backend).get_memory_maps("emulator-5554", 1224)
