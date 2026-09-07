"""Domain logic for the debugging module:

- recent process-exit history for a package (`adb shell dumpsys activity
  exit-info <package>`), parsed into typed `ApplicationExitInfo` records;
- setting / clearing ActivityManager's debug app (`adb shell am
  set-debug-app` / `am clear-debug-app`);
- listing processes that currently expose a JDWP transport (`adb jdwp`);
- capturing a native backtrace (`adb shell debuggerd -b <pid>`) or a full
  native tombstone (`adb shell debuggerd <pid>`) for a running process.
"""

from __future__ import annotations

import re
import shlex
from contextlib import suppress
from pathlib import Path

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
    PolicyViolationError,
)

_TOMBSTONE_SUBDIR = "tombstones"
_TRACE_CAP = 40_000
_DEBUGGERD_ROOT_MARKER = "root is required"
_BT_PID_RE = re.compile(r"^-{3,}\s*pid\s+(?P<pid>\d+)\s+at\b", re.MULTILINE)
_BT_CMDLINE_RE = re.compile(r"^Cmd ?line:\s*(?P<v>.+?)\s*$", re.MULTILINE)
_BT_ABI_RE = re.compile(r"^ABI:\s*'?(?P<v>[^'\n]+)'?\s*$", re.MULTILINE)
_BT_THREAD_RE = re.compile(r'^"(?P<name>[^"]*)"\s+sysTid=(?P<tid>\d+)', re.MULTILINE)
_FRAME_RE = re.compile(r"^\s*#\d+\s+pc\s", re.MULTILINE)
_TS_SIGNAL_RE = re.compile(r"^signal\s+(?P<v>.+?)\s*$", re.MULTILINE)
_TS_FRAMES_RE = re.compile(r"^(?P<n>\d+)\s+total frames\s*$", re.MULTILINE)
_TS_PB_RE = re.compile(r"(tombstone_\d+\.pb)")

_BLOCK_SPLIT_RE = re.compile(r"ApplicationExitInfo #\d+:")
_TIMESTAMP_RE = re.compile(r"timestamp=(?P<v>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)")
_PID_RE = re.compile(r"\bpid=(\d+)")
_REAL_UID_RE = re.compile(r"\brealUid=(\d+)")
_USER_RE = re.compile(r"\buser=(\d+)")
_PROCESS_RE = re.compile(r"\bprocess=(\S+)")
_REASON_RE = re.compile(r"\breason=(\d+)\s+\((?P<label>.*)\)\s+subreason=(?P<sub>\d+)")
_SUBREASON_LABEL_RE = re.compile(r"\bsubreason=\d+\s+\((?P<label>.*)\)\s+status=")
_STATUS_RE = re.compile(r"\bstatus=(-?\d+)")
_IMPORTANCE_RE = re.compile(r"\bimportance=(-?\d+)")
_PSS_RE = re.compile(r"\bpss=(\S+)")
_RSS_RE = re.compile(r"\brss=(\S+)")
_STATE_RE = re.compile(r"\bstate=(\S+)")
_TRACE_RE = re.compile(r"\btrace=(\S+)")
_DESCRIPTION_RE = re.compile(r"^\s*description=(?P<v>.*?)\s*$", re.MULTILINE)


class ProcessExitRecord(BaseModel):
    """One `ApplicationExitInfo` record.

    reason_code / reason are ActivityManager's numeric reason and its label
    (e.g. 4 / "APP CRASH(EXCEPTION)", 6 / "LOW MEMORY", 2 / "SIGNALED"). pss
    and rss are the raw strings the dump reports ("0.00", "167MB").
    trace_available is True when a tombstone/ANR trace path was recorded (not
    the trace itself). has_anr_info is True when the record carried an
    anrInfo block.
    """

    timestamp: str
    pid: int | None
    real_uid: int | None
    user: int | None
    process: str | None
    reason_code: int | None
    reason: str | None
    subreason_code: int | None
    subreason: str | None
    status: int | None
    importance: int | None
    pss: str | None
    rss: str | None
    state: str | None
    description: str | None
    trace_available: bool
    has_anr_info: bool


class ProcessExitHistory(BaseModel):
    """Recent process-exit records for one package
    (`adb shell dumpsys activity exit-info <package>`), newest first.

    An empty records list is a normal result — the package has no retained
    exit history (never crashed/exited, or its records aged out of the
    bounded ring).
    """

    serial: str
    package: str
    count: int
    records: list[ProcessExitRecord]

    def summary(self) -> str:
        if not self.count:
            return f"No process-exit history for {self.package} on {self.serial}."
        newest = self.records[0]
        noun = "record" if self.count == 1 else "records"
        return (
            f"{self.count} exit {noun} for {self.package} on {self.serial} "
            f"(newest: {newest.reason or 'unknown'} at {newest.timestamp})."
        )


class SetDebugAppResult(BaseModel):
    """Outcome of `adb shell am set-debug-app [-w] [--persistent] <package>`.

    This only records the package as ActivityManager's debug app — it does
    NOT attach a debugger. wait_for_debugger reflects whether `-w` was
    passed (the next launch of the app blocks until a debugger connects);
    persistent reflects `--persistent` (the setting survives reboot).
    `am` doesn't validate the package, so an unknown one is not an error.
    """

    serial: str
    package: str
    wait_for_debugger: bool
    persistent: bool

    def summary(self) -> str:
        wait = " (waits for debugger on next launch)" if self.wait_for_debugger else ""
        return f"Set {self.package} as the debug app on {self.serial}{wait}."


class ClearDebugAppResult(BaseModel):
    """Outcome of `adb shell am clear-debug-app`.

    Idempotent — `am` reports no error when no debug app was set, so
    cleared is always true on success and does not imply one had been
    configured.
    """

    serial: str
    cleared: bool

    def summary(self) -> str:
        return f"Cleared the debug app on {self.serial}."


class JdwpProcessList(BaseModel):
    """PIDs of processes currently exposing a JDWP transport (`adb jdwp`).

    Only debuggable processes appear here. An empty list is a normal
    result. `adb jdwp` streams and never exits on its own, so this is a
    snapshot taken after a short settle window.
    """

    serial: str
    count: int
    pids: list[int]

    def summary(self) -> str:
        if not self.count:
            return f"No JDWP-debuggable processes on {self.serial}."
        return f"{self.count} JDWP-debuggable process(es) on {self.serial}: {self.pids}."


class NativeThread(BaseModel):
    """One thread in a native backtrace: its name, kernel tid, and how many
    stack frames were captured.
    """

    name: str
    sys_tid: int
    frame_count: int


class NativeBacktrace(BaseModel):
    """Native thread backtraces for a running process (`adb shell debuggerd
    -b <pid>`).

    process_name / abi come from the dump header. threads lists each
    thread's name / tid / frame count. text is the full backtrace dump,
    capped in length. Privileged on production builds — non-root devices
    reject this.
    """

    serial: str
    pid: int
    process_name: str | None
    abi: str | None
    thread_count: int
    threads: list[NativeThread]
    text: str


class NativeTombstone(BaseModel):
    """A full native tombstone for a process (`adb shell debuggerd <pid>`),
    saved to the host.

    local_path is where the tombstone text was written on this server's
    host. process_name / abi / signal come from the dump header;
    frame_count is the "N total frames" value; device_tombstone_ref is the
    `tombstone_NN.pb` filename the dump references on the device (None if
    not present). Only ever returned on success.
    """

    serial: str
    pid: int
    process_name: str | None
    abi: str | None
    signal: str | None
    frame_count: int | None
    device_tombstone_ref: str | None
    local_path: str
    size_bytes: int | None
    success: bool

    def summary(self) -> str:
        return f"Saved native tombstone for pid {self.pid} on {self.serial} to {self.local_path}."


class DebuggingService:
    """Process-exit history, debug-app config, JDWP listing, and native
    backtrace / tombstone capture for a device.
    """

    def __init__(self, backend: AdbBackend, local_root: Path | None = None) -> None:
        self._backend = backend
        self._local_root = local_root.resolve() if local_root is not None else None

    def _resolve_local_path(self, rel: str) -> Path:
        if self._local_root is None:
            raise PolicyViolationError(
                "No local_root configured for this server — capture_native_tombstone "
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

    async def capture_native_backtrace(self, serial: str, pid: int) -> NativeBacktrace:
        if pid <= 0:
            raise InvalidArgumentError(
                "pid must be a positive integer.", details={"serial": serial, "pid": pid}
            )
        result = await self._backend.shell(serial, f"debuggerd -b {pid}", timeout_s=60.0)
        _raise_for_debuggerd_failure(serial, pid, result)
        text = result.stdout
        cmdline = _BT_CMDLINE_RE.search(text)
        abi = _BT_ABI_RE.search(text)
        threads = _parse_native_threads(text)
        return NativeBacktrace(
            serial=serial,
            pid=pid,
            process_name=cmdline.group("v") if cmdline else None,
            abi=abi.group("v") if abi else None,
            thread_count=len(threads),
            threads=threads,
            text=_cap(text),
        )

    async def capture_native_tombstone(
        self, serial: str, pid: int, local_path: str
    ) -> NativeTombstone:
        if pid <= 0:
            raise InvalidArgumentError(
                "pid must be a positive integer.", details={"serial": serial, "pid": pid}
            )
        target = self._resolve_local_path(f"{_TOMBSTONE_SUBDIR}/{local_path}")
        target.parent.mkdir(parents=True, exist_ok=True)

        result = await self._backend.shell(serial, f"debuggerd {pid}", timeout_s=120.0)
        _raise_for_debuggerd_failure(serial, pid, result)
        text = result.stdout
        with suppress(OSError):
            target.write_text(text)

        cmdline = _BT_CMDLINE_RE.search(text)
        abi = _BT_ABI_RE.search(text)
        signal = _TS_SIGNAL_RE.search(text)
        frames = _TS_FRAMES_RE.search(text)
        pb = _TS_PB_RE.search(text)
        return NativeTombstone(
            serial=serial,
            pid=pid,
            process_name=cmdline.group("v") if cmdline else None,
            abi=abi.group("v") if abi else None,
            signal=signal.group("v") if signal else None,
            frame_count=int(frames.group("n")) if frames else None,
            device_tombstone_ref=pb.group(1) if pb else None,
            local_path=str(target),
            size_bytes=target.stat().st_size if target.is_file() else None,
            success=True,
        )

    async def set_debug_app(
        self,
        serial: str,
        package: str,
        wait_for_debugger: bool = False,
        persistent: bool = False,
    ) -> SetDebugAppResult:
        if not package.strip():
            raise InvalidArgumentError(
                "package must be a non-empty package name.", details={"package": package}
            )
        parts = ["am", "set-debug-app"]
        if wait_for_debugger:
            parts.append("-w")
        if persistent:
            parts.append("--persistent")
        parts.append(shlex.quote(package))
        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_shell_failure(serial, result)
        return SetDebugAppResult(
            serial=serial,
            package=package,
            wait_for_debugger=wait_for_debugger,
            persistent=persistent,
        )

    async def clear_debug_app(self, serial: str) -> ClearDebugAppResult:
        result = await self._backend.shell(serial, "am clear-debug-app")
        _raise_for_shell_failure(serial, result)
        return ClearDebugAppResult(serial=serial, cleared=True)

    async def list_jdwp_processes(self, serial: str) -> JdwpProcessList:
        result = await self._backend.jdwp(serial)
        if result.exit_code != 0:
            message = (result.stderr or result.stdout).strip() or "adb jdwp exited non-zero."
            if "not found" in message or "offline" in message:
                raise DeviceNotFoundError(message, details={"serial": serial})
            raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})
        pids = [int(tok) for tok in result.stdout.split() if tok.isdigit()]
        # preserve first-seen order, drop duplicates
        seen: dict[int, None] = {}
        for pid in pids:
            seen.setdefault(pid, None)
        ordered = list(seen)
        return JdwpProcessList(serial=serial, count=len(ordered), pids=ordered)

    async def get_process_exit_history(self, serial: str, package: str) -> ProcessExitHistory:
        if not package.strip():
            raise InvalidArgumentError(
                "package must be a non-empty package name.", details={"package": package}
            )
        result = await self._backend.shell(
            serial, f"dumpsys activity exit-info {shlex.quote(package)}"
        )
        _raise_for_shell_failure(serial, result)
        records = _parse_exit_records(result.stdout)
        return ProcessExitHistory(
            serial=serial, package=package, count=len(records), records=records
        )


def _cap(text: str) -> str:
    return text if len(text) <= _TRACE_CAP else text[:_TRACE_CAP] + "\n...[output truncated]"


def _parse_native_threads(text: str) -> list[NativeThread]:
    matches = list(_BT_THREAD_RE.finditer(text))
    threads: list[NativeThread] = []
    for i, m in enumerate(matches):
        block_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[m.end() : block_end]
        threads.append(
            NativeThread(
                name=m.group("name"),
                sys_tid=int(m.group("tid")),
                frame_count=len(_FRAME_RE.findall(block)),
            )
        )
    return threads


def _raise_for_debuggerd_failure(serial: str, pid: int, result: CommandResult) -> None:
    combined = f"{result.stdout}\n{result.stderr}"
    if _DEBUGGERD_ROOT_MARKER in combined:
        raise PermissionDeniedError(
            "debuggerd requires root on this build.", details={"serial": serial, "pid": pid}
        )
    if "SecurityException" in combined or "Operation not permitted" in combined:
        raise PermissionDeniedError(
            f"debuggerd was refused for pid {pid}.", details={"serial": serial, "pid": pid}
        )
    if result.exit_code != 0:
        message = (result.stderr or result.stdout).strip() or "debuggerd exited non-zero."
        if message.startswith("adb:") and "not found" in message:
            raise DeviceNotFoundError(message, details={"serial": serial})
        raise BackendError(message, details={"serial": serial, "pid": pid})
    # exit 0 but no recognizable dump — usually a dead/nonexistent pid.
    if "pc " not in result.stdout and "total frames" not in result.stdout:
        raise BackendError(
            f"debuggerd produced no backtrace for pid {pid} (process gone or invalid?).",
            details={"serial": serial, "pid": pid, "output_head": result.stdout[:200]},
        )


def _int_or_none(match: re.Match[str] | None) -> int | None:
    return int(match.group(1)) if match else None


def _parse_exit_records(text: str) -> list[ProcessExitRecord]:
    parts = _BLOCK_SPLIT_RE.split(text)
    records: list[ProcessExitRecord] = []
    for block in parts[1:]:  # parts[0] is the preamble before the first block
        ts = _TIMESTAMP_RE.search(block)
        if ts is None:
            continue
        reason = _REASON_RE.search(block)
        sub_label = _SUBREASON_LABEL_RE.search(block)
        trace = _TRACE_RE.search(block)
        desc = _DESCRIPTION_RE.search(block)
        pss = _PSS_RE.search(block)
        rss = _RSS_RE.search(block)
        state = _STATE_RE.search(block)
        process = _PROCESS_RE.search(block)
        description = desc.group("v") if desc else None
        records.append(
            ProcessExitRecord(
                timestamp=ts.group("v"),
                pid=_int_or_none(_PID_RE.search(block)),
                real_uid=_int_or_none(_REAL_UID_RE.search(block)),
                user=_int_or_none(_USER_RE.search(block)),
                process=process.group(1) if process else None,
                reason_code=int(reason.group(1)) if reason else None,
                reason=reason.group("label") if reason else None,
                subreason_code=int(reason.group("sub")) if reason else None,
                subreason=sub_label.group("label") if sub_label else None,
                status=_int_or_none(_STATUS_RE.search(block)),
                importance=_int_or_none(_IMPORTANCE_RE.search(block)),
                pss=pss.group(1) if pss else None,
                rss=rss.group(1) if rss else None,
                state=state.group(1) if state else None,
                description=None if description in (None, "null") else description,
                trace_available=trace is not None and trace.group(1) != "null",
                has_anr_info="anrInfo=" in block and "anrInfo=null" not in block,
            )
        )
    return records


def _raise_for_shell_failure(serial: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})
