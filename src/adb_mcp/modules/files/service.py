"""Domain logic for the files module: copying files between a connected
Android device and this server's host (`adb pull`, via the existing
AdbBackend.pull primitive — no new backend primitive needed). `adb push` and
any private-app-data semantics (e.g. `run-as` for another app's sandboxed
files) aren't handled here — remote_path is passed to `adb pull` exactly as
given.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from adb_mcp.backend.protocol import AdbBackend, CommandResult
from adb_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
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


class FilesService:
    """Copies files between a connected device and this server's host."""

    def __init__(self, backend: AdbBackend, local_root: Path | None = None) -> None:
        self._backend = backend
        self._local_root = local_root.resolve() if local_root is not None else None

    def _resolve_local_path(self, local_path: str) -> Path:
        if self._local_root is None:
            raise PolicyViolationError(
                "No local_root configured for this server — host-file-writing "
                "tools are disabled until an operator sets ADB_MCP_LOCAL_ROOT.",
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
