"""Domain logic for the files module: copying files between a connected
Android device and this server's host — `adb pull` (device → host) and
`adb push` (host → device), via the existing AdbBackend primitives. Both
directions confine the host path to `ADB_AUTOMATION_LOCAL_ROOT`; private-app-data
semantics (e.g. `run-as` for another app's sandboxed files) aren't handled —
the remote path is passed to adb exactly as given.
"""

from __future__ import annotations

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


class PullFileResult(BaseModel):
    """Outcome of pulling one file from a device to this server's host
    (`adb pull`).

    Only ever returned on success — `adb pull` always resolves synchronously
    to a definitive exit code (unlike e.g. start_activity's fire-and-forget
    -W ambiguity), so every failure kind (missing source, permission denied,
    device unavailable, or any other pull failure) is classified and raised
    instead of returned as data — see FilesService.pull_file's Error
    handling. success is always True here; it's kept as an explicit field
    since a caller inspecting just the data payload should still see it
    stated, not merely implied by the envelope's status.
    """

    serial: str
    remote_path: str
    local_path: str
    success: bool
    output: str

    def summary(self) -> str:
        return f"Pulled {self.remote_path} from {self.serial} to {self.local_path}."


class PushFileResult(BaseModel):
    """Outcome of pushing one host file to a device (`adb push`).

    Only ever returned on success — `adb push` resolves synchronously to a
    definitive exit code, so every failure kind (host source missing / outside
    local_root, unwritable remote path, device unavailable, other) is raised,
    not returned as data. success is always True here (an explicit field for
    the same reason as PullFileResult.success).
    """

    serial: str
    local_path: str
    remote_path: str
    success: bool
    output: str

    def summary(self) -> str:
        return f"Pushed {self.local_path} to {self.remote_path} on {self.serial}."


class FilesService:
    """Copies files between a connected device and this server's host."""

    def __init__(self, backend: AdbBackend, local_root: Path | None = None) -> None:
        self._backend = backend
        self._local_root = local_root.resolve() if local_root is not None else None

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

    async def pull_file(self, serial: str, remote_path: str, local_path: str) -> PullFileResult:
        resolved_local_path = self._resolve_local_path(local_path)
        result = await self._backend.pull(serial, remote_path, str(resolved_local_path))
        _raise_for_pull_failure(serial, remote_path, str(resolved_local_path), result)
        return PullFileResult(
            serial=serial,
            remote_path=remote_path,
            local_path=str(resolved_local_path),
            success=True,
            output=result.stdout,
        )

    async def push_file(self, serial: str, local_path: str, remote_path: str) -> PushFileResult:
        resolved_local_path = self._resolve_local_path(local_path)
        if not resolved_local_path.is_file():
            raise InvalidArgumentError(
                f"local_path '{local_path}' does not name an existing file inside local_root.",
                details={"local_path": str(resolved_local_path)},
            )
        result = await self._backend.push(serial, str(resolved_local_path), remote_path)
        _raise_for_push_failure(serial, str(resolved_local_path), remote_path, result)
        return PushFileResult(
            serial=serial,
            local_path=str(resolved_local_path),
            remote_path=remote_path,
            success=True,
            output=result.stdout,
        )


def _raise_for_push_failure(
    serial: str, local_path: str, remote_path: str, result: CommandResult
) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb push exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    lowered = message.lower()
    if "read-only file system" in lowered or "permission denied" in lowered:
        raise PermissionDeniedError(
            message, details={"serial": serial, "remote_path": remote_path}
        )
    # A remote *directory* that doesn't exist: "adb: error: failed to copy
    # '...' to '...': remote No such file or directory".
    if "no such file or directory" in lowered:
        raise RemoteFileNotFoundError(
            message, details={"serial": serial, "remote_path": remote_path}
        )
    raise BackendError(
        message,
        details={
            "serial": serial,
            "local_path": local_path,
            "remote_path": remote_path,
            "exit_code": result.exit_code,
        },
    )


def _raise_for_pull_failure(serial: str, remote_path: str, local_path: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb pull exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's) — the adb-client rejects an unknown serial
    # before any pull is attempted.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    # `adb pull`'s well-known, long-stable wording for a remote path that
    # doesn't exist on the device: "adb: error: remote object '<path>' does
    # not exist".
    if "does not exist" in message:
        raise RemoteFileNotFoundError(message, details={"serial": serial, "remote_path": remote_path})
    # Same for a remote path the shell user can't read (e.g. inside another
    # app's private data dir without root): "adb: error: failed to stat
    # remote object '<path>': Permission denied".
    if "Permission denied" in message or "Permission Denial" in message:
        raise PermissionDeniedError(message, details={"serial": serial, "remote_path": remote_path})
    raise BackendError(
        message,
        details={
            "serial": serial,
            "remote_path": remote_path,
            "local_path": local_path,
            "exit_code": result.exit_code,
        },
    )
