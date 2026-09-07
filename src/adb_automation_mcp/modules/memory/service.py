"""Domain logic for the memory module: structured memory diagnostics for a
connected device.

- ``get_app_memory_summary`` / ``get_app_memory_details`` — ``dumpsys meminfo
  -s|-a <target>``; the shared ``adb_automation_mcp.meminfo`` parsers turn the
  text into typed fields (App Summary totals, the per-mapping table, the
  Objects / SQL sections).
- ``get_system_memory_summary`` — bare ``dumpsys meminfo``: RAM totals + the
  top PSS consumers.
- ``get_memory_history`` — ``dumpsys procstats --hours <h> <package>``: the
  "Process summary" min/avg/max PSS/USS/RSS bands.
- ``capture_heap_dump`` — ``am dumpheap`` to a device temp file, ``adb
  pull`` into ``ADB_AUTOMATION_LOCAL_ROOT/heapdumps/``, then delete the temp
  file (on success and on failure).

All parsing is in Python; large diagnostic output is bounded before it
reaches the response envelope.
"""

from __future__ import annotations

import re
import shlex
import uuid
from contextlib import suppress
from pathlib import Path

from pydantic import BaseModel

from adb_automation_mcp import meminfo
from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    MemoryInfoUnavailableError,
    PackageNotRunningError,
    PermissionDeniedError,
    PolicyViolationError,
    RemoteFileNotFoundError,
)

_HEAPDUMP_SUBDIR = "heapdumps"
_REMOTE_TMP_DIR = "/data/local/tmp"
_MIN_HOURS = 1
_MAX_HOURS = 72
_MIN_TIMEOUT_S = 5.0
_MAX_TIMEOUT_S = 600.0
_TOP_PROCESS_LIMIT = 15

# One "Process summary" band, e.g.
#   "     TOTAL: 100% (0.00-62MB-103MB/0.00-54MB-90MB/262MB-258MB-262MB over 8)"
_PROCSTATS_BAND_RE = re.compile(
    r"^\s*(?P<state>[A-Za-z][A-Za-z ]*?):\s*(?P<pct>[\d.]+)%\s*\("
    r"(?P<pss>[^/]+)/(?P<uss>[^/]+)/(?P<rss>[^)]+?)\s+over\s+(?P<samples>\d+)\)"
)
_PROCSTATS_START_RE = re.compile(r"^\s*Start time:\s*(?P<start>.+?)\s*$", re.MULTILINE)
_SIZE_RE = re.compile(r"^([\d.]+)\s*(GB|MB|KB|B)?$")


class AppMemorySummary(BaseModel):
    """Compact per-app memory snapshot (`adb shell dumpsys meminfo -s`).

    The `*_pss_kb` fields are the App Summary Pss column (null when that row
    was absent for this build); total_pss_kb / total_rss_kb / total_swap_kb
    are the table's TOTAL line. All values are raw kilobyte integers.
    """

    serial: str
    target: str
    pid: int | None
    process_name: str | None
    java_heap_pss_kb: int | None
    native_heap_pss_kb: int | None
    code_pss_kb: int | None
    stack_pss_kb: int | None
    graphics_pss_kb: int | None
    private_other_pss_kb: int | None
    system_pss_kb: int | None
    total_pss_kb: int | None
    total_rss_kb: int | None
    total_swap_kb: int | None

    def summary(self) -> str:
        who = self.process_name or self.target
        if self.total_pss_kb is not None:
            return f"{who} on {self.serial}: {self.total_pss_kb} KB total PSS."
        return f"Memory summary for {who} on {self.serial}."


class MemoryCategory(BaseModel):
    """One row of the `-a` per-mapping table (e.g. "Native Heap", ".so mmap",
    "TOTAL"). Trailing columns a build omits come back null.
    """

    name: str
    pss_total_kb: int | None = None
    pss_clean_kb: int | None = None
    shared_dirty_kb: int | None = None
    private_dirty_kb: int | None = None
    shared_clean_kb: int | None = None
    private_clean_kb: int | None = None
    swap_dirty_kb: int | None = None
    rss_total_kb: int | None = None
    heap_size_kb: int | None = None
    heap_alloc_kb: int | None = None
    heap_free_kb: int | None = None


class AppMemoryDetails(BaseModel):
    """Detailed per-app memory breakdown (`adb shell dumpsys meminfo -a`).

    Carries the same App Summary totals as AppMemorySummary, plus categories
    (the per-mapping table), objects (the "Objects" section: view/binder/
    parcel counts, ...) and sql (the "SQL" section). objects and sql are
    empty maps when the build didn't emit those sections. The raw dump is
    deliberately not exposed.
    """

    serial: str
    target: str
    pid: int | None
    process_name: str | None
    java_heap_pss_kb: int | None
    native_heap_pss_kb: int | None
    code_pss_kb: int | None
    stack_pss_kb: int | None
    graphics_pss_kb: int | None
    private_other_pss_kb: int | None
    system_pss_kb: int | None
    total_pss_kb: int | None
    total_rss_kb: int | None
    total_swap_kb: int | None
    categories: list[MemoryCategory]
    objects: dict[str, int]
    sql: dict[str, int]

    def summary(self) -> str:
        who = self.process_name or self.target
        return (
            f"{who} on {self.serial}: {len(self.categories)} memory categories, "
            f"{len(self.objects)} object counts."
        )


class TopProcess(BaseModel):
    """One entry of the system "Total PSS by process" list."""

    name: str
    pid: int
    user: int | None
    pss_kb: int


class SystemMemorySummary(BaseModel):
    """System-wide memory totals (`adb shell dumpsys meminfo`).

    All *_kb values are kilobytes; any the dump didn't carry are null.
    status is the "(status normal)" word from the Total RAM line.
    top_processes is the (bounded) "Total PSS by process" list.
    """

    serial: str
    total_ram_kb: int | None
    free_ram_kb: int | None
    used_ram_kb: int | None
    lost_ram_kb: int | None
    zram_physical_used_kb: int | None
    zram_in_swap_kb: int | None
    zram_total_swap_kb: int | None
    status: str | None
    top_processes: list[TopProcess]

    def summary(self) -> str:
        total = f"{self.total_ram_kb} KB" if self.total_ram_kb is not None else "unknown"
        free = f"{self.free_ram_kb} KB" if self.free_ram_kb is not None else "unknown"
        return f"{self.serial}: {total} total RAM, {free} free, {len(self.top_processes)} top procs."


class MemoryHistoryBand(BaseModel):
    """One "Process summary" band from procstats (e.g. state "TOTAL", "Top",
    "Persistent"). Each min/avg/max is kilobytes; a field procstats didn't
    report is null.
    """

    state: str
    percent: float | None
    samples: int | None
    pss_min_kb: int | None
    pss_avg_kb: int | None
    pss_max_kb: int | None
    uss_min_kb: int | None
    uss_avg_kb: int | None
    uss_max_kb: int | None
    rss_min_kb: int | None
    rss_avg_kb: int | None
    rss_max_kb: int | None


class MemoryHistory(BaseModel):
    """Historical process-state memory bands over a window
    (`adb shell dumpsys procstats --hours <hours> <package>`).

    has_history is False (with an empty bands list) when procstats has no
    accumulated samples for this package in the window — a normal result,
    not an error. window_start is procstats' reported aggregation start.
    """

    serial: str
    package: str
    hours: int
    has_history: bool
    window_start: str | None
    bands: list[MemoryHistoryBand]

    def summary(self) -> str:
        if not self.has_history:
            return f"No procstats history for {self.package} on {self.serial} (last {self.hours}h)."
        return (
            f"{self.package} on {self.serial}: {len(self.bands)} memory band(s) "
            f"over the last {self.hours}h."
        )


class HeapDumpResult(BaseModel):
    """Outcome of capturing a heap dump and saving it to the host
    (`adb shell am dumpheap` + `adb pull`).

    local_path is the absolute path the .hprof was written to on this
    server's host — that's the point of the tool. native / force_gc /
    user_id echo the options used. size_bytes is the saved file's size, or
    null if it couldn't be stat'd. Only ever returned on success — every
    failure is classified and raised.
    """

    serial: str
    package: str
    local_path: str
    native: bool
    force_gc: bool
    user_id: int | None
    size_bytes: int | None
    success: bool

    def summary(self) -> str:
        kind = "native" if self.native else "managed"
        return f"Captured {kind} heap dump of {self.package} from {self.serial} to {self.local_path}."


class HeapWatchResult(BaseModel):
    """Outcome of `adb shell am set-watch-heap <package> <bytes>`.

    Configures ActivityManager to auto-collect a heap dump when the
    process's PSS reaches threshold_bytes. `am` doesn't validate the
    package, so an unknown one is not an error.
    """

    serial: str
    package: str
    threshold_bytes: int
    watching: bool

    def summary(self) -> str:
        return (
            f"Watching {self.package} on {self.serial}; a heap dump triggers at "
            f"{self.threshold_bytes} bytes PSS."
        )


class ClearHeapWatchResult(BaseModel):
    """Outcome of `adb shell am clear-watch-heap <package>`. Idempotent."""

    serial: str
    package: str
    cleared: bool

    def summary(self) -> str:
        return f"Cleared the heap watch for {self.package} on {self.serial}."


class MemoryMaps(BaseModel):
    """Aggregate memory-map figures for a process, from
    `/proc/<pid>/smaps_rollup` (all values in kilobytes).

    These are the kernel's own rollup totals — Rss/Pss and the
    shared/private clean/dirty split, plus swap. Any field the kernel
    didn't emit is null. This is a fixed, compact model, not a generic
    /proc reader.
    """

    serial: str
    pid: int
    rss_kb: int | None
    pss_kb: int | None
    pss_dirty_kb: int | None
    pss_anon_kb: int | None
    pss_file_kb: int | None
    pss_shmem_kb: int | None
    shared_clean_kb: int | None
    shared_dirty_kb: int | None
    private_clean_kb: int | None
    private_dirty_kb: int | None
    referenced_kb: int | None
    anonymous_kb: int | None
    swap_kb: int | None
    swap_pss_kb: int | None
    locked_kb: int | None

    def summary(self) -> str:
        pss = f"{self.pss_kb} KB PSS" if self.pss_kb is not None else "PSS unknown"
        return f"pid {self.pid} on {self.serial}: {pss}."


_SMAPS_FIELDS: tuple[tuple[str, str], ...] = (
    ("Rss", "rss_kb"),
    ("Pss", "pss_kb"),
    ("Pss_Dirty", "pss_dirty_kb"),
    ("Pss_Anon", "pss_anon_kb"),
    ("Pss_File", "pss_file_kb"),
    ("Pss_Shmem", "pss_shmem_kb"),
    ("Shared_Clean", "shared_clean_kb"),
    ("Shared_Dirty", "shared_dirty_kb"),
    ("Private_Clean", "private_clean_kb"),
    ("Private_Dirty", "private_dirty_kb"),
    ("Referenced", "referenced_kb"),
    ("Anonymous", "anonymous_kb"),
    ("Swap", "swap_kb"),
    ("SwapPss", "swap_pss_kb"),
    ("Locked", "locked_kb"),
)


class MemoryService:
    """Structured memory diagnostics for a connected device."""

    def __init__(self, backend: AdbBackend, local_root: Path | None = None) -> None:
        self._backend = backend
        self._local_root = local_root.resolve() if local_root is not None else None

    def _resolve_local_path(self, rel: str) -> Path:
        if self._local_root is None:
            raise PolicyViolationError(
                "No local_root configured for this server — capture_heap_dump "
                "cannot write to the host. Set ADB_AUTOMATION_LOCAL_ROOT.",
                details={"local_path": rel},
            )
        resolved = (self._local_root / rel).resolve()
        if not resolved.is_relative_to(self._local_root):
            raise PolicyViolationError(
                f"local_path '{rel}' resolves outside the configured local_root.",
                details={"local_path": rel, "local_root": str(self._local_root)},
            )
        return resolved

    async def get_app_memory_summary(self, serial: str, target: str) -> AppMemorySummary:
        _require_non_blank("target", target)
        text = await self._meminfo(serial, f"dumpsys meminfo -s {shlex.quote(target)}", target)
        pid, process_name = meminfo.parse_pid_header(text)
        summary = meminfo.parse_app_summary(text)
        if pid is None and summary["total_pss_kb"] is None:
            raise MemoryInfoUnavailableError(
                "dumpsys meminfo -s produced no recognizable header or TOTAL line.",
                details={"serial": serial, "target": target, "output_head": text[:400]},
            )
        return AppMemorySummary(
            serial=serial, target=target, pid=pid, process_name=process_name, **summary
        )

    async def get_app_memory_details(self, serial: str, target: str) -> AppMemoryDetails:
        _require_non_blank("target", target)
        text = await self._meminfo(serial, f"dumpsys meminfo -a {shlex.quote(target)}", target)
        pid, process_name = meminfo.parse_pid_header(text)
        summary = meminfo.parse_app_summary(text)
        categories = [
            MemoryCategory(
                name=str(row.pop("name")),
                **{key: int(value) for key, value in row.items()},
            )
            for row in meminfo.parse_detail_table(text)
        ]
        if pid is None and summary["total_pss_kb"] is None and not categories:
            raise MemoryInfoUnavailableError(
                "dumpsys meminfo -a produced no recognizable memory sections.",
                details={"serial": serial, "target": target, "output_head": text[:400]},
            )
        return AppMemoryDetails(
            serial=serial,
            target=target,
            pid=pid,
            process_name=process_name,
            categories=categories,
            objects=meminfo.parse_objects(text),
            sql=meminfo.parse_sql(text),
            **summary,
        )

    async def get_system_memory_summary(self, serial: str) -> SystemMemorySummary:
        result = await self._backend.shell(serial, "dumpsys meminfo")
        _raise_for_shell_failure(serial, result)
        text = result.stdout
        ram = meminfo.parse_system_ram(text)
        if ram["total_ram_kb"] is None and ram["free_ram_kb"] is None:
            raise MemoryInfoUnavailableError(
                "dumpsys meminfo produced no recognizable RAM totals.",
                details={"serial": serial, "output_head": text[:400]},
            )
        top = [
            TopProcess(name=str(p["name"]), pid=int(p["pid"]), user=p["user"], pss_kb=int(p["pss_kb"]))  # type: ignore[arg-type]
            for p in meminfo.parse_top_processes(text, limit=_TOP_PROCESS_LIMIT)
        ]
        return SystemMemorySummary(serial=serial, top_processes=top, **ram)  # type: ignore[arg-type]

    async def get_memory_history(
        self, serial: str, package: str, hours: int = 3
    ) -> MemoryHistory:
        _require_non_blank("package", package)
        if not _MIN_HOURS <= hours <= _MAX_HOURS:
            raise InvalidArgumentError(
                f"hours must be between {_MIN_HOURS} and {_MAX_HOURS}.",
                details={"serial": serial, "hours": hours},
            )
        result = await self._backend.shell(
            serial, f"dumpsys procstats --hours {hours} {shlex.quote(package)}"
        )
        _raise_for_shell_failure(serial, result)
        text = result.stdout
        start_match = _PROCSTATS_START_RE.search(text)
        bands = _parse_procstats_bands(text, package)
        return MemoryHistory(
            serial=serial,
            package=package,
            hours=hours,
            has_history=bool(bands),
            window_start=start_match.group("start") if start_match else None,
            bands=bands,
        )

    async def capture_heap_dump(
        self,
        serial: str,
        package: str,
        local_path: str,
        force_gc: bool = False,
        native: bool = False,
        user_id: int | None = None,
        timeout_s: float = 120.0,
    ) -> HeapDumpResult:
        _require_non_blank("package", package)
        if user_id is not None and user_id < 0:
            raise InvalidArgumentError(
                "user_id must be a non-negative Android user id.",
                details={"serial": serial, "user_id": user_id},
            )
        if not _MIN_TIMEOUT_S <= timeout_s <= _MAX_TIMEOUT_S:
            raise InvalidArgumentError(
                f"timeout_s must be between {_MIN_TIMEOUT_S} and {_MAX_TIMEOUT_S} seconds.",
                details={"serial": serial, "timeout_s": timeout_s},
            )
        target = self._resolve_local_path(f"{_HEAPDUMP_SUBDIR}/{local_path}")
        target.parent.mkdir(parents=True, exist_ok=True)

        remote_path = f"{_REMOTE_TMP_DIR}/adb_automation_mcp_heapdump_{uuid.uuid4().hex}.hprof"
        parts = ["am", "dumpheap"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        if native:
            parts.append("-n")
        if force_gc:
            parts.append("-g")
        parts.extend([shlex.quote(package), shlex.quote(remote_path)])

        try:
            dump_result = await self._backend.shell(serial, " ".join(parts), timeout_s=timeout_s)
            _raise_for_dumpheap_failure(serial, package, dump_result)

            pull_result = await self._backend.pull(serial, remote_path, str(target))
            _raise_for_pull_failure(serial, remote_path, pull_result)
        finally:
            with suppress(Exception):
                await self._backend.shell(serial, f"rm -f {shlex.quote(remote_path)}")

        size_bytes = target.stat().st_size if target.is_file() else None
        return HeapDumpResult(
            serial=serial,
            package=package,
            local_path=str(target),
            native=native,
            force_gc=force_gc,
            user_id=user_id,
            size_bytes=size_bytes,
            success=True,
        )

    async def set_heap_watch(
        self, serial: str, package: str, threshold_bytes: int
    ) -> HeapWatchResult:
        _require_non_blank("package", package)
        if threshold_bytes <= 0:
            raise InvalidArgumentError(
                "threshold_bytes must be a positive integer.",
                details={"serial": serial, "threshold_bytes": threshold_bytes},
            )
        result = await self._backend.shell(
            serial, f"am set-watch-heap {shlex.quote(package)} {threshold_bytes}"
        )
        _raise_for_am_failure(serial, result, "am set-watch-heap")
        return HeapWatchResult(
            serial=serial, package=package, threshold_bytes=threshold_bytes, watching=True
        )

    async def clear_heap_watch(self, serial: str, package: str) -> ClearHeapWatchResult:
        _require_non_blank("package", package)
        result = await self._backend.shell(serial, f"am clear-watch-heap {shlex.quote(package)}")
        _raise_for_am_failure(serial, result, "am clear-watch-heap")
        return ClearHeapWatchResult(serial=serial, package=package, cleared=True)

    async def get_memory_maps(self, serial: str, pid: int) -> MemoryMaps:
        if pid <= 0:
            raise InvalidArgumentError(
                "pid must be a positive integer.", details={"serial": serial, "pid": pid}
            )
        result = await self._backend.shell(serial, f"cat /proc/{pid}/smaps_rollup")
        combined = f"{result.stdout}\n{result.stderr}"
        if "Permission denied" in combined:
            raise PermissionDeniedError(
                f"reading /proc/{pid}/smaps_rollup is not permitted (root/SELinux).",
                details={"serial": serial, "pid": pid},
            )
        if "No such file" in combined or "No such process" in combined:
            raise RemoteFileNotFoundError(
                f"no /proc/{pid}/smaps_rollup — pid {pid} is not a running process.",
                details={"serial": serial, "pid": pid},
            )
        _raise_for_shell_failure(serial, result)

        values: dict[str, int | None] = {}
        for label, field in _SMAPS_FIELDS:
            m = re.search(rf"^{re.escape(label)}:\s*(\d+)\s*kB", result.stdout, re.MULTILINE)
            values[field] = int(m.group(1)) if m else None
        if all(v is None for v in values.values()):
            raise MemoryInfoUnavailableError(
                f"/proc/{pid}/smaps_rollup produced no recognizable fields.",
                details={"serial": serial, "pid": pid, "output_head": result.stdout[:200]},
            )
        return MemoryMaps(serial=serial, pid=pid, **values)

    async def _meminfo(self, serial: str, command: str, target: str) -> str:
        result = await self._backend.shell(serial, command)
        _raise_for_shell_failure(serial, result)
        if meminfo.NOT_RUNNING_MARKER in result.stdout:
            raise PackageNotRunningError(
                f"No running process found for '{target}' on {serial}.",
                details={"serial": serial, "target": target},
            )
        return result.stdout


def _require_non_blank(field: str, value: str) -> None:
    if not value.strip():
        raise InvalidArgumentError(
            f"{field} must be a non-empty string.", details={field: value}
        )


def _parse_size_kb(token: str) -> int | None:
    match = _SIZE_RE.match(token.strip())
    if match is None:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    factor = {"GB": 1024 * 1024, "MB": 1024, "KB": 1, "B": 1 / 1024, None: 1}[unit]
    return round(value * factor)


def _parse_triple(field: str) -> tuple[int | None, int | None, int | None]:
    parts = field.split("-")
    if len(parts) != 3:
        return None, None, None
    return _parse_size_kb(parts[0]), _parse_size_kb(parts[1]), _parse_size_kb(parts[2])


def _parse_procstats_bands(text: str, package: str) -> list[MemoryHistoryBand]:
    lines = text.splitlines()
    in_summary = False
    in_block = False
    bands: list[MemoryHistoryBand] = []
    for line in lines:
        stripped = line.strip()
        if stripped == "Process summary:":
            in_summary = True
            continue
        if not in_summary:
            continue
        if stripped.startswith("* "):
            in_block = stripped[2:].split(" / ", 1)[0] == package
            continue
        if not in_block:
            continue
        match = _PROCSTATS_BAND_RE.match(line)
        if match is None:
            continue
        pss = _parse_triple(match.group("pss"))
        uss = _parse_triple(match.group("uss"))
        rss = _parse_triple(match.group("rss"))
        bands.append(
            MemoryHistoryBand(
                state=match.group("state").strip(),
                percent=float(match.group("pct")),
                samples=int(match.group("samples")),
                pss_min_kb=pss[0],
                pss_avg_kb=pss[1],
                pss_max_kb=pss[2],
                uss_min_kb=uss[0],
                uss_avg_kb=uss[1],
                uss_max_kb=uss[2],
                rss_min_kb=rss[0],
                rss_avg_kb=rss[1],
                rss_max_kb=rss[2],
            )
        )
    return bands


def _raise_for_shell_failure(serial: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})


def _raise_for_am_failure(serial: str, result: CommandResult, what: str) -> None:
    combined = f"{result.stdout}\n{result.stderr}"
    if "Permission Denial" in combined or "Permission denied" in combined:
        raise PermissionDeniedError(f"{what} was refused.", details={"serial": serial})
    if result.exit_code == 0 and "Exception occurred" not in combined and "Error:" not in combined:
        return
    message = (result.stderr or result.stdout).strip() or f"{what} exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})


def _raise_for_dumpheap_failure(serial: str, package: str, result: CommandResult) -> None:
    combined = f"{result.stdout}\n{result.stderr}"
    failed = result.exit_code != 0 or "Exception occurred while executing 'dumpheap'" in combined
    if not failed:
        return
    if "Unknown process" in combined:
        raise PackageNotRunningError(
            f"No running process '{package}' on {serial} to dump.",
            details={"serial": serial, "package": package},
        )
    if "SecurityException" in combined or "not debuggable" in combined or "not profileable" in combined:
        raise PermissionDeniedError(
            f"am dumpheap was refused for {package} (not debuggable/profileable on this build).",
            details={"serial": serial, "package": package},
        )
    message = (result.stderr or result.stdout).strip() or "am dumpheap failed."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "package": package})


def _raise_for_pull_failure(serial: str, remote_path: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb pull exited non-zero."
    if "does not exist" in message or "No such file" in message:
        raise RemoteFileNotFoundError(
            f"am dumpheap left no file to pull: {message}",
            details={"serial": serial, "remote_path": remote_path},
        )
    raise BackendError(message, details={"serial": serial, "remote_path": remote_path})
