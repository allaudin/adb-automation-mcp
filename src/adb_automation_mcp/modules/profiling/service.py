"""Domain logic for the profiling module: Android method profiling for a
process (`adb shell am profile start|stop` + `adb pull`).

start_method_profile begins a profile writing to a deterministic device-side
path derived from the package; stop_method_profile finalizes it, pulls the
`.trace` into `ADB_AUTOMATION_LOCAL_ROOT/profiles/`, and deletes the device
file (on success and on failure). The device path isn't exposed as a caller
parameter — the two calls agree on it from the package name.
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
    RemoteFileNotFoundError,
)

_PROFILE_SUBDIR = "profiles"
_REMOTE_TMP_DIR = "/data/local/tmp"
_MIN_SAMPLING_US = 1
_MAX_SAMPLING_US = 1_000_000
# `am profile stop` finalizes and writes the .trace; a large trace can take
# a while to serialize.
_PROFILE_STOP_TIMEOUT_S = 120.0


def _remote_path_for(package: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", package)
    return f"{_REMOTE_TMP_DIR}/adb_automation_mcp_methodprofile_{safe}.trace"


class MethodProfileSession(BaseModel):
    """State returned by start_method_profile.

    device_trace_path is where the profiler is writing on the device;
    stop_method_profile derives the same path from the package, so callers
    don't pass it. sampling_interval_us is set for a sampling profile (None
    means the default instrumented/tracing profiler). Starting a profile
    doesn't produce an artifact — that comes from stop.
    """

    serial: str
    package: str
    device_trace_path: str
    sampling_interval_us: int | None
    streaming: bool
    user_id: int | None
    started: bool

    def summary(self) -> str:
        mode = (
            f"sampling every {self.sampling_interval_us}us"
            if self.sampling_interval_us
            else "instrumented"
        )
        return f"Started {mode} method profile of {self.package} on {self.serial}."


class MethodProfileResult(BaseModel):
    """Outcome of stop_method_profile: the finalized `.trace` saved to the host.

    local_path is the absolute path the trace was written to on this
    server's host. size_bytes is its size on disk, or null if it couldn't
    be stat'd. Only ever returned on success.
    """

    serial: str
    package: str
    local_path: str
    size_bytes: int | None
    success: bool

    def summary(self) -> str:
        return f"Saved method profile of {self.package} from {self.serial} to {self.local_path}."


class ProfilingService:
    """Runs Android method profiling and saves the trace to the host."""

    def __init__(self, backend: AdbBackend, local_root: Path | None = None) -> None:
        self._backend = backend
        self._local_root = local_root.resolve() if local_root is not None else None

    def _resolve_local_path(self, rel: str) -> Path:
        if self._local_root is None:
            raise PolicyViolationError(
                "No local_root configured for this server — stop_method_profile "
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

    async def start_method_profile(
        self,
        serial: str,
        package: str,
        sampling_interval_us: int | None = None,
        streaming: bool = False,
        user_id: int | None = None,
    ) -> MethodProfileSession:
        if not package.strip():
            raise InvalidArgumentError(
                "package must be a non-empty package/process name.", details={"package": package}
            )
        if sampling_interval_us is not None and streaming:
            raise InvalidArgumentError(
                "sampling_interval_us and streaming are mutually exclusive.",
                details={"serial": serial},
            )
        if sampling_interval_us is not None and not (
            _MIN_SAMPLING_US <= sampling_interval_us <= _MAX_SAMPLING_US
        ):
            raise InvalidArgumentError(
                f"sampling_interval_us must be between {_MIN_SAMPLING_US} and {_MAX_SAMPLING_US}.",
                details={"serial": serial, "sampling_interval_us": sampling_interval_us},
            )
        if user_id is not None and user_id < 0:
            raise InvalidArgumentError(
                "user_id must be a non-negative Android user id.", details={"serial": serial}
            )

        remote_path = _remote_path_for(package)
        parts = ["am", "profile", "start"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        if sampling_interval_us is not None:
            parts.extend(["--sampling", str(sampling_interval_us)])
        if streaming:
            parts.append("--streaming")
        parts.extend([shlex.quote(package), shlex.quote(remote_path)])

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_am_profile_failure(serial, package, result)
        return MethodProfileSession(
            serial=serial,
            package=package,
            device_trace_path=remote_path,
            sampling_interval_us=sampling_interval_us,
            streaming=streaming,
            user_id=user_id,
            started=True,
        )

    async def stop_method_profile(
        self, serial: str, package: str, local_path: str, user_id: int | None = None
    ) -> MethodProfileResult:
        if not package.strip():
            raise InvalidArgumentError(
                "package must be a non-empty package/process name.", details={"package": package}
            )
        target = self._resolve_local_path(f"{_PROFILE_SUBDIR}/{local_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        remote_path = _remote_path_for(package)

        parts = ["am", "profile", "stop"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        parts.append(shlex.quote(package))

        try:
            stop_result = await self._backend.shell(
                serial, " ".join(parts), timeout_s=_PROFILE_STOP_TIMEOUT_S
            )
            _raise_for_am_profile_failure(serial, package, stop_result)

            pull_result = await self._backend.pull(serial, remote_path, str(target))
            _raise_for_pull_failure(
                serial,
                remote_path,
                pull_result,
                "no method-profile trace was produced — was a profile started?",
            )
        finally:
            with suppress(Exception):
                await self._backend.shell(serial, f"rm -f {shlex.quote(remote_path)}")

        size_bytes = target.stat().st_size if target.is_file() else None
        return MethodProfileResult(
            serial=serial,
            package=package,
            local_path=str(target),
            size_bytes=size_bytes,
            success=True,
        )


def _raise_for_am_profile_failure(serial: str, package: str, result: CommandResult) -> None:
    combined = f"{result.stdout}\n{result.stderr}"
    if "SecurityException" in combined or "not profileable" in combined or "not debuggable" in combined:
        raise PermissionDeniedError(
            f"am profile was refused for {package} (not debuggable/profileable on this build).",
            details={"serial": serial, "package": package},
        )
    if result.exit_code == 0 and "Error:" not in combined:
        return
    message = (result.stderr or result.stdout).strip() or "am profile exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "package": package})


def _raise_for_pull_failure(
    serial: str, remote_path: str, result: CommandResult, missing_msg: str
) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb pull exited non-zero."
    if "does not exist" in message or "No such file" in message:
        raise RemoteFileNotFoundError(
            f"{missing_msg} ({message})", details={"serial": serial, "remote_path": remote_path}
        )
    raise BackendError(message, details={"serial": serial, "remote_path": remote_path})
