"""Domain logic for the screen module: capturing the device's current screen
as a PNG (`screencap -p`) and pulling it to this server's host.

AdbBackend has no primitive for streaming binary command output — Shell's
CommandResult carries stdout/stderr as `str`, which would corrupt raw PNG
bytes decoded through it — and adding one is a backend-protocol change out
of scope for this module (see AdbBackend in backend/protocol.py). So this
follows the standard adb workaround instead: write the PNG to a temporary
path on the device with `screencap -p <path>`, pull it with the existing
AdbBackend.pull primitive, then always remove the device-side temp file.
"""

from __future__ import annotations

import shlex
import struct
import uuid
from contextlib import suppress
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

# /data/local/tmp is writable by the shell user without any storage
# permissions and, unlike /sdcard, isn't subject to scoped-storage/MediaStore
# scanning — the standard location for this exact screencap-then-pull
# pattern.
_REMOTE_TMP_DIR = "/data/local/tmp"

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class TakeScreenshotResult(BaseModel):
    """Outcome of capturing and pulling a device screenshot (`screencap -p`
    followed by `adb pull`).

    Not verified live (no device was available in this environment) —
    shaped on `screencap`'s documented behavior and the well-known PNG
    format. Only ever returned on success — see ScreenService.take_screenshot's
    Error handling for how a screencap failure or a pull failure is raised
    instead of returned as data. width/height/size_bytes are best-effort:
    they come from reading the PNG actually written to local_path after the
    pull, so they're None whenever that file isn't present or readable
    (e.g. under a backend whose pull() doesn't actually write host bytes) —
    "metadata that can be reliably determined", not always present.
    """

    serial: str
    local_path: str
    display_id: int | None
    success: bool
    width: int | None
    height: int | None
    size_bytes: int | None
    output: str

    def summary(self) -> str:
        return f"Captured screenshot from {self.serial} to {self.local_path}."


class ScreenService:
    """Captures the device's current screen and pulls it to this server's host."""

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

    async def take_screenshot(
        self, serial: str, local_path: str, display_id: int | None = None
    ) -> TakeScreenshotResult:
        resolved_local_path = self._resolve_local_path(local_path)
        remote_tmp_path = f"{_REMOTE_TMP_DIR}/adb_mcp_screenshot_{uuid.uuid4().hex}.png"
        parts = ["screencap", "-p"]
        if display_id is not None:
            parts.extend(["-d", str(display_id)])
        parts.append(remote_tmp_path)

        try:
            capture_result = await self._backend.shell(serial, " ".join(parts))
            _raise_for_screencap_failure(serial, capture_result)

            pull_result = await self._backend.pull(serial, remote_tmp_path, str(resolved_local_path))
            _raise_for_pull_failure(serial, remote_tmp_path, str(resolved_local_path), pull_result)

            width, height, size_bytes = _read_png_metadata(resolved_local_path)
            return TakeScreenshotResult(
                serial=serial,
                local_path=str(resolved_local_path),
                display_id=display_id,
                success=True,
                width=width,
                height=height,
                size_bytes=size_bytes,
                output=pull_result.stdout,
            )
        finally:
            # Best-effort, unconditional: never leave the temp screenshot on
            # the device, whether capture, pull, both, or neither failed —
            # and never let a cleanup failure mask the real outcome above.
            # (This still runs before the `return` above actually returns.)
            with suppress(Exception):
                await self._backend.shell(serial, f"rm -f {shlex.quote(remote_tmp_path)}")


def _raise_for_screencap_failure(serial: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "screencap exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's) — the adb-client rejects an unknown serial
    # before any command reaches a device.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission denied" in message or "Permission Denial" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})


def _raise_for_pull_failure(serial: str, remote_path: str, local_path: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb pull exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    # Same well-known `adb pull` wording used by the files module: "adb:
    # error: remote object '<path>' does not exist".
    if "does not exist" in message:
        raise RemoteFileNotFoundError(message, details={"serial": serial, "remote_path": remote_path})
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


def _read_png_metadata(path: Path) -> tuple[int | None, int | None, int | None]:
    try:
        size_bytes = path.stat().st_size
    except OSError:
        return None, None, None
    width: int | None = None
    height: int | None = None
    try:
        with path.open("rb") as f:
            header = f.read(24)
        # The IHDR chunk always immediately follows the 8-byte PNG
        # signature: 4-byte length, 4-byte type "IHDR", then big-endian
        # 4-byte width + 4-byte height — fixed by the PNG spec, never varies.
        if len(header) == 24 and header[:8] == _PNG_SIGNATURE:
            width, height = struct.unpack(">II", header[16:24])
    except OSError:
        pass
    return width, height, size_bytes
