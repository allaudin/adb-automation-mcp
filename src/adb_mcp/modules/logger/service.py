"""Domain logic for the logger module: pulls diagnostic logs off a connected
device (`adb shell logcat`), by package (`adb shell pidof` + `logcat --pid`),
clears buffers, and reports buffer sizes.

Every command here uses logcat's dump-and-exit mode (`-d`, or `-t N` which
implies `-d`) rather than a live tail: the shared shell(serial, command)
backend primitive every module uses is one-shot with a timeout, not a
long-lived stream, so this stays request/response. A real continuous tail
would need a new, stateful backend primitive — deliberately out of scope here.
"""

from __future__ import annotations

import shlex
from typing import Literal

from pydantic import BaseModel

from adb_mcp.backend.protocol import AdbBackend, CommandResult
from adb_mcp.errors import BackendError, DeviceNotFoundError, PackageNotRunningError

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


class LoggerService:
    """Reads and manages Android log buffers on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

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

    async def read_package_logs(
        self,
        serial: str,
        package: str,
        buffer: LogBuffer = "main",
        max_lines: int = 200,
        min_priority: LogPriority | None = None,
    ) -> PackageLogDump:
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
        pid = int(pidof_result.stdout.strip())
        parts = ["logcat", "-d", "-v", "threadtime", "-t", str(max_lines), "-b", buffer, f"--pid={pid}"]
        parts.extend(self._build_filterspec(min_priority, None))
        result = await self._backend.shell(serial, " ".join(parts))
        self._raise_for_shell_failure(serial, result)
        return PackageLogDump(serial=serial, package=package, pid=pid, output=result.stdout)
