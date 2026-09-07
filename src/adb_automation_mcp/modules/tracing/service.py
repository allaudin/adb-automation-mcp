"""Domain logic for the tracing module: capturing a bounded Perfetto system
trace with safe semantic presets
(`adb shell perfetto -o <dev> -t <N>s -b 32mb <cats>` + `adb pull`).

v1 deliberately does not accept an arbitrary Perfetto config — the caller
picks a preset (cpu / scheduling / graphics / app_startup / memory / binder)
which maps to a curated set of atrace categories and ftrace events. The
trace is written to the device's perfetto-traces dir, pulled into
`ADB_AUTOMATION_LOCAL_ROOT/traces/`, and the device file is deleted (on
success and on failure).
"""

from __future__ import annotations

import re
import shlex
import uuid
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
    PolicyViolationError,
    RemoteFileNotFoundError,
    TracingUnavailableError,
)

_TRACE_SUBDIR = "traces"
_IPC_TRACE_SUBDIR = "ipc_traces"
_REMOTE_TMP_DIR = "/data/local/tmp"
# perfetto's own domain can write here; /data/local/tmp is SELinux-denied to it.
_REMOTE_TRACE_DIR = "/data/misc/perfetto-traces"
_MIN_DURATION_S = 1
_MAX_DURATION_S = 120
_BUFFER = "32mb"
_TIMEOUT_SLACK_S = 25.0
# `am trace-ipc stop` RPCs into every process to collect its transaction log
# and can take well over a minute on a busy device.
_IPC_STOP_TIMEOUT_S = 180.0

# preset -> the atrace categories / ftrace events passed as perfetto light-config
# tokens. Kept small and widely-supported; unknown tokens perfetto just skips.
_PRESETS: dict[str, list[str]] = {
    "cpu": ["sched", "freq", "idle"],
    "scheduling": ["sched", "freq", "idle", "sched/sched_switch", "sched/sched_wakeup"],
    "graphics": ["gfx", "view", "sched", "freq"],
    "app_startup": ["am", "wm", "gfx", "view", "sched", "freq"],
    "memory": ["sched", "dalvik", "kmem/rss_stat"],
    "binder": ["binder_driver", "sched", "freq"],
}
PRESETS: tuple[str, ...] = tuple(_PRESETS)

_WROTE_RE = re.compile(r"Wrote\s+(\d+)\s+bytes")


class SystemTraceResult(BaseModel):
    """Outcome of capturing a Perfetto system trace and saving it to the host.

    local_path is the absolute path the .perfetto-trace was written to on
    this server's host — that's the point of the tool. preset /
    duration_seconds / package echo the request. device_bytes is what
    perfetto reported writing on the device (None if that line wasn't
    found); size_bytes is the pulled file's size on disk. Only ever
    returned on success.
    """

    serial: str
    preset: str
    duration_seconds: int
    package: str | None
    local_path: str
    device_bytes: int | None
    size_bytes: int | None
    success: bool

    def summary(self) -> str:
        scope = f" ({self.package})" if self.package else ""
        return (
            f"Captured a {self.duration_seconds}s '{self.preset}' trace{scope} "
            f"from {self.serial} to {self.local_path}."
        )


class IpcTraceSession(BaseModel):
    """State returned by start_ipc_trace (`adb shell am trace-ipc start`).

    Starting produces no artifact — the Binder/IPC transaction dump is
    written by stop_ipc_trace. tracing is always true when start succeeds;
    `am` doesn't report whether a session was already running (starting
    again is harmless), so this doesn't distinguish that.
    """

    serial: str
    tracing: bool

    def summary(self) -> str:
        return f"Started IPC transaction tracing on {self.serial}."


class IpcTraceResult(BaseModel):
    """Outcome of stop_ipc_trace: the dumped IPC trace saved to the host
    (`adb shell am trace-ipc stop --dump-file <dev>` + `adb pull`).

    local_path is the absolute path the (text) trace was written to on this
    server's host. size_bytes is its size on disk, or null if it couldn't
    be stat'd. Only ever returned on success.
    """

    serial: str
    local_path: str
    size_bytes: int | None
    success: bool

    def summary(self) -> str:
        return f"Saved IPC transaction trace from {self.serial} to {self.local_path}."


class TracingService:
    """Captures Perfetto system traces and Binder/IPC transaction traces and
    saves them to the host.
    """

    def __init__(self, backend: AdbBackend, local_root: Path | None = None) -> None:
        self._backend = backend
        self._local_root = local_root.resolve() if local_root is not None else None

    def _resolve_local_path(self, rel: str) -> Path:
        if self._local_root is None:
            raise PolicyViolationError(
                "No local_root configured for this server — capture_system_trace "
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

    async def capture_system_trace(
        self,
        serial: str,
        preset: str,
        local_path: str,
        duration_seconds: int = 10,
        package: str | None = None,
    ) -> SystemTraceResult:
        if preset not in _PRESETS:
            raise InvalidArgumentError(
                f"preset must be one of: {', '.join(PRESETS)}.",
                details={"serial": serial, "preset": preset},
            )
        if not _MIN_DURATION_S <= duration_seconds <= _MAX_DURATION_S:
            raise InvalidArgumentError(
                f"duration_seconds must be between {_MIN_DURATION_S} and {_MAX_DURATION_S}.",
                details={"serial": serial, "duration_seconds": duration_seconds},
            )
        if package is not None and not package.strip():
            raise InvalidArgumentError(
                "package, when given, must be non-blank.", details={"serial": serial}
            )

        target = self._resolve_local_path(f"{_TRACE_SUBDIR}/{local_path}")
        target.parent.mkdir(parents=True, exist_ok=True)

        remote_path = f"{_REMOTE_TRACE_DIR}/adb_automation_mcp_{uuid.uuid4().hex}.perfetto-trace"
        parts = ["perfetto", "-o", shlex.quote(remote_path), "-t", f"{duration_seconds}s", "-b", _BUFFER]
        if package is not None:
            parts.extend(["-a", shlex.quote(package)])
        parts.extend(_PRESETS[preset])

        try:
            trace_result = await self._backend.shell(
                serial, " ".join(parts), timeout_s=duration_seconds + _TIMEOUT_SLACK_S
            )
            _raise_for_perfetto_failure(serial, trace_result)

            pull_result = await self._backend.pull(serial, remote_path, str(target))
            _raise_for_pull_failure(serial, remote_path, pull_result)
        finally:
            with suppress(Exception):
                await self._backend.shell(serial, f"rm -f {shlex.quote(remote_path)}")

        wrote = _WROTE_RE.search(f"{trace_result.stdout}\n{trace_result.stderr}")
        size_bytes = target.stat().st_size if target.is_file() else None
        return SystemTraceResult(
            serial=serial,
            preset=preset,
            duration_seconds=duration_seconds,
            package=package,
            local_path=str(target),
            device_bytes=int(wrote.group(1)) if wrote else None,
            size_bytes=size_bytes,
            success=True,
        )

    async def start_ipc_trace(self, serial: str) -> IpcTraceSession:
        result = await self._backend.shell(serial, "am trace-ipc start")
        _raise_for_am_failure(serial, result, "am trace-ipc start")
        return IpcTraceSession(serial=serial, tracing=True)

    async def stop_ipc_trace(self, serial: str, local_path: str) -> IpcTraceResult:
        target = self._resolve_local_path(f"{_IPC_TRACE_SUBDIR}/{local_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        remote_path = f"{_REMOTE_TMP_DIR}/adb_automation_mcp_ipctrace_{stamp}_{uuid.uuid4().hex}.txt"

        try:
            stop_result = await self._backend.shell(
                serial,
                f"am trace-ipc stop --dump-file {shlex.quote(remote_path)}",
                timeout_s=_IPC_STOP_TIMEOUT_S,
            )
            _raise_for_am_failure(serial, stop_result, "am trace-ipc stop")

            pull_result = await self._backend.pull(serial, remote_path, str(target))
            _raise_for_pull_failure(serial, remote_path, pull_result)
        finally:
            with suppress(Exception):
                await self._backend.shell(serial, f"rm -f {shlex.quote(remote_path)}")

        size_bytes = target.stat().st_size if target.is_file() else None
        return IpcTraceResult(
            serial=serial, local_path=str(target), size_bytes=size_bytes, success=True
        )


def _raise_for_am_failure(serial: str, result: CommandResult, what: str) -> None:
    combined = f"{result.stdout}\n{result.stderr}"
    if "Permission denied" in combined or "Permission Denial" in combined:
        raise PermissionDeniedError(f"{what} was refused.", details={"serial": serial})
    if result.exit_code == 0 and "Error:" not in combined:
        return
    message = (result.stderr or result.stdout).strip() or f"{what} exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})


def _raise_for_perfetto_failure(serial: str, result: CommandResult) -> None:
    combined = f"{result.stdout}\n{result.stderr}"
    if "not found" in combined and "perfetto" in combined.lower() and result.exit_code != 0:
        raise TracingUnavailableError(
            "perfetto is not available on this device.",
            details={"serial": serial},
        )
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "perfetto exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission denied" in message or "Permission Denial" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})


def _raise_for_pull_failure(serial: str, remote_path: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb pull exited non-zero."
    if "does not exist" in message or "No such file" in message:
        raise RemoteFileNotFoundError(
            f"perfetto left no trace file to pull: {message}",
            details={"serial": serial, "remote_path": remote_path},
        )
    raise BackendError(message, details={"serial": serial, "remote_path": remote_path})
