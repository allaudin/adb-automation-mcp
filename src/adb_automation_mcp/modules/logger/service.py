"""Domain logic for the logger module: pulls diagnostic logs off a connected
device (`adb shell logcat`), by package (`adb shell pidof` + `logcat --pid`),
clears buffers, reports buffer sizes, and captures a "session" of logs between
a start and stop call.

Every command here uses logcat's dump-and-exit mode (`-d`, or `-t N` which
implies `-d`) rather than a live tail: the shared shell(serial, command)
backend primitive every module uses is one-shot with a timeout, not a
long-lived stream, so this stays request/response. Session capture is a
checkpoint-and-dump, not a live background process: start_log_session
anchors on the device's own current log timestamp, and stop_log_session
replays from that anchor to now — the same one-shot primitive, no new
backend capability. A real continuous tail would need a new, stateful
backend primitive — deliberately out of scope here.
"""

from __future__ import annotations

import shlex
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    LogSessionNotFoundError,
    PackageNotRunningError,
    PolicyViolationError,
)

LogBuffer = Literal[
    "main", "system", "radio", "events", "crash", "kernel", "security", "default", "all"
]
LogPriority = Literal["V", "D", "I", "W", "E", "F", "S"]


class LogDump(BaseModel):
    """Raw `adb shell logcat -d ...` output for one buffer, verified live.

    max_lines maps to `-t N`: verified live that this selects the N most
    recent RAW lines of the buffer first, THEN applies any tag/priority
    filterspec — so a narrow filter combined with a small max_lines can come
    back empty even though matching lines exist further back in the buffer.
    Also verified live: `-t 0` is silently clamped to 1 (with a stderr
    warning, still exit 0); a negative value is a real command error.
    """

    serial: str
    buffer: str
    output: str

    def summary(self) -> str:
        lines = self.output.count("\n")
        return f"Read {lines} log line(s) from {self.buffer} on {self.serial}."


class ClearLogsResult(BaseModel):
    """Outcome of clearing a log buffer (`adb shell logcat -c -b BUFFER`)."""

    serial: str
    buffer: str

    def summary(self) -> str:
        return f"Cleared {self.buffer} log buffer on {self.serial}."


class LogBufferSize(BaseModel):
    """Raw `adb shell logcat -g -b BUFFER` output: ring buffer size and usage.

    Verified live that an unknown buffer name fails with "Unknown -b buffer
    '<name>'", exit 1 — relevant because "kernel" only exists on
    userdebug/eng builds and "security" only under Device Owner, so either
    can legitimately fail on a given device even though both are valid
    buffer names in general.
    """

    serial: str
    buffer: str
    output: str

    def summary(self) -> str:
        return f"Log buffer size for {self.buffer} on {self.serial}: {self.output}"


class PackageLogDump(BaseModel):
    """Raw logcat output filtered to one package's resolved PID.

    Verified live: resolved via `pidof -s <package>` (exact package/process
    name match, not substring), then `logcat --pid=<pid>`. logcat only
    accepts one `--pid` per invocation ("Only one --pid argument can be
    provided"), so a multi-process package (isolated services, separate
    process names) only surfaces its primary process's logs here — a known
    v1 limitation, not a bug.
    """

    serial: str
    package: str
    pid: int
    output: str

    def summary(self) -> str:
        lines = self.output.count("\n")
        return f"Read {lines} log line(s) for {self.package} (pid {self.pid}) on {self.serial}."


class LogSessionHandle(BaseModel):
    """A started log-capture session, from start_log_session.

    Not a live tail (see module docstring) — this just records an anchor
    point on the device, plus whatever filter was configured. If the buffer
    was completely empty at start time, there's no line to anchor on
    (verified live: `-t 1 -v epoch` returns empty stdout, exit 0, not an
    error, on an empty buffer); stop_log_session handles that by capturing
    everything present in the buffer at stop-time instead of filtering by
    timestamp.
    """

    session_id: str
    serial: str
    buffer: str
    name: str
    pid: int | None
    package: str | None

    def summary(self) -> str:
        return f"Started log session '{self.name}' ({self.session_id}) on {self.buffer}@{self.serial}."


class LogSessionResult(BaseModel):
    """Outcome of stop_log_session: everything logged between start and stop
    (filtered per whatever start_log_session was configured with), written to
    a file on the host running this server (not the device).

    Depends on the device's ring buffer not wrapping (overwriting the anchor
    entry) before stop is called — fine for a normal debugging session, not a
    hard guarantee for a very long or very high-volume one.
    """

    session_id: str
    serial: str
    buffer: str
    name: str
    pid: int | None
    package: str | None
    local_path: str
    line_count: int
    duration_s: float

    def summary(self) -> str:
        return (
            f"Wrote {self.line_count} log line(s) from session '{self.name}' "
            f"({self.session_id}) to {self.local_path}."
        )


@dataclass
class _LogSession:
    serial: str
    buffer: str
    since: str | None  # device epoch anchor "sssss.mmm", or None if buffer was empty at start
    name: str
    min_priority: LogPriority | None
    tag: str | None
    pid: int | None  # resolved, whether passed directly or resolved from package
    package: str | None
    created_at: float  # time.monotonic()


def _parse_epoch_anchor(output: str) -> str | None:
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("---------"):
            continue
        return stripped.split()[0]
    return None


class LoggerService:
    """Reads and manages Android log buffers on a connected device."""

    def __init__(self, backend: AdbBackend, local_root: Path | None = None) -> None:
        self._backend = backend
        self._local_root = local_root.resolve() if local_root is not None else None
        self._sessions: dict[str, _LogSession] = {}

    def _resolve_local_path(self, local_path: str) -> Path:
        if self._local_root is None:
            raise PolicyViolationError(
                "No local_root configured for this server — host-file-writing "
                "tools are disabled until an operator sets ADB_AUTOMATION_LOCAL_ROOT.",
                details={"local_path": local_path},
            )
        resolved = (self._local_root / local_path).resolve()
        if not resolved.is_relative_to(self._local_root):
            raise PolicyViolationError(
                f"local_path '{local_path}' resolves outside the configured local_root.",
                details={"local_path": local_path, "local_root": str(self._local_root)},
            )
        return resolved

    @staticmethod
    def _raise_for_shell_failure(serial: str, result: CommandResult) -> None:
        if result.exit_code == 0:
            return
        # Verified live against a real device: an unknown serial fails at the
        # adb-client level (before reaching any device) with
        # "adb: device '<serial>' not found", exit 1.
        message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
        if "not found" in message:
            raise DeviceNotFoundError(message, details={"serial": serial})
        raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})

    @staticmethod
    def _build_filterspec(min_priority: LogPriority | None, tag: str | None) -> list[str]:
        if tag:
            # Verified live: "TAG:LEVEL" plus a separate "*:S" token shows only
            # the given tag (at min_priority or above) and silences every other
            # tag. Two distinct filterspec words, not one combined string.
            return [shlex.quote(f"{tag}:{min_priority or 'V'}"), "*:S"]
        if min_priority is not None:
            return [f"*:{min_priority}"]
        return []

    async def read_logs(
        self,
        serial: str,
        buffer: LogBuffer = "main",
        max_lines: int = 200,
        min_priority: LogPriority | None = None,
        tag: str | None = None,
        pid: int | None = None,
    ) -> LogDump:
        parts = ["logcat", "-d", "-v", "threadtime", "-t", str(max_lines), "-b", buffer]
        if pid is not None:
            parts.append(f"--pid={pid}")
        parts.extend(self._build_filterspec(min_priority, tag))
        result = await self._backend.shell(serial, " ".join(parts))
        self._raise_for_shell_failure(serial, result)
        return LogDump(serial=serial, buffer=buffer, output=result.stdout)

    async def clear_logs(self, serial: str, buffer: LogBuffer = "main") -> ClearLogsResult:
        result = await self._backend.shell(serial, f"logcat -c -b {buffer}")
        self._raise_for_shell_failure(serial, result)
        return ClearLogsResult(serial=serial, buffer=buffer)

    async def get_log_buffer_size(self, serial: str, buffer: LogBuffer = "main") -> LogBufferSize:
        result = await self._backend.shell(serial, f"logcat -g -b {buffer}")
        self._raise_for_shell_failure(serial, result)
        return LogBufferSize(serial=serial, buffer=buffer, output=result.stdout.strip())

    async def _resolve_package_pid(self, serial: str, package: str) -> int:
        # package is free-form and reaches the device's own shell via `adb
        # shell` — shlex.quote it, verified live to correctly neutralize shell
        # metacharacters (an unquoted "; echo INJECTED; #" package name
        # actually executed on the device).
        pidof_result = await self._backend.shell(serial, f"pidof -s {shlex.quote(package)}")
        if pidof_result.exit_code != 0:
            message = (pidof_result.stderr or pidof_result.stdout).strip()
            if "not found" in message:
                raise DeviceNotFoundError(message, details={"serial": serial})
            if message:
                raise BackendError(message, details={"serial": serial, "package": package})
            # Verified live: pidof exits 1 with empty stdout AND empty stderr
            # both when the package isn't installed and when it's installed
            # but not currently running — adb can't distinguish the two, so
            # neither can this.
            raise PackageNotRunningError(
                f"No running process for package '{package}' on {serial} "
                "(it may not be installed, or is not currently running).",
                details={"serial": serial, "package": package},
            )
        return int(pidof_result.stdout.strip())

    async def read_package_logs(
        self,
        serial: str,
        package: str,
        buffer: LogBuffer = "main",
        max_lines: int = 200,
        min_priority: LogPriority | None = None,
    ) -> PackageLogDump:
        pid = await self._resolve_package_pid(serial, package)
        parts = ["logcat", "-d", "-v", "threadtime", "-t", str(max_lines), "-b", buffer, f"--pid={pid}"]
        parts.extend(self._build_filterspec(min_priority, None))
        result = await self._backend.shell(serial, " ".join(parts))
        self._raise_for_shell_failure(serial, result)
        return PackageLogDump(serial=serial, package=package, pid=pid, output=result.stdout)

    async def start_log_session(
        self,
        serial: str,
        name: str,
        buffer: LogBuffer = "main",
        min_priority: LogPriority | None = None,
        tag: str | None = None,
        pid: int | None = None,
        package: str | None = None,
    ) -> LogSessionHandle:
        if pid is not None and package is not None:
            raise InvalidArgumentError(
                "Pass either pid or package to filter by process, not both.",
                details={"pid": pid, "package": package},
            )
        resolved_pid = pid
        if package is not None:
            resolved_pid = await self._resolve_package_pid(serial, package)

        result = await self._backend.shell(serial, f"logcat -d -t 1 -b {buffer} -v epoch")
        self._raise_for_shell_failure(serial, result)
        since = _parse_epoch_anchor(result.stdout)
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = _LogSession(
            serial=serial,
            buffer=buffer,
            since=since,
            name=name,
            min_priority=min_priority,
            tag=tag,
            pid=resolved_pid,
            package=package,
            created_at=time.monotonic(),
        )
        return LogSessionHandle(
            session_id=session_id,
            serial=serial,
            buffer=buffer,
            name=name,
            pid=resolved_pid,
            package=package,
        )

    async def stop_log_session(self, session_id: str, local_path: str) -> LogSessionResult:
        session = self._sessions.get(session_id)
        if session is None:
            raise LogSessionNotFoundError(
                f"No active log session '{session_id}' (never started, or already stopped).",
                details={"session_id": session_id},
            )
        # Resolve and validate the host path before spending an adb round-trip,
        # so a policy violation doesn't leave the session silently consumed.
        resolved_path = self._resolve_local_path(local_path)

        parts = ["logcat", "-d", "-v", "threadtime", "-b", session.buffer]
        if session.since is not None:
            parts.extend(["-t", shlex.quote(session.since)])
        if session.pid is not None:
            parts.append(f"--pid={session.pid}")
        parts.extend(self._build_filterspec(session.min_priority, session.tag))
        result = await self._backend.shell(session.serial, " ".join(parts))
        self._raise_for_shell_failure(session.serial, result)

        resolved_path.parent.mkdir(parents=True, exist_ok=True)
        resolved_path.write_text(result.stdout)

        duration_s = time.monotonic() - session.created_at
        del self._sessions[session_id]
        return LogSessionResult(
            session_id=session_id,
            serial=session.serial,
            buffer=session.buffer,
            name=session.name,
            pid=session.pid,
            package=session.package,
            local_path=str(resolved_path),
            line_count=result.stdout.count("\n"),
            duration_s=duration_s,
        )
