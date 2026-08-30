"""Domain logic for the screen module: capturing the device's current screen
as a PNG, saving it to this server's host, and returning the saved path.

Captures with `adb exec-out screencap -p` (the `exec_out` backend primitive):
exec-out streams the command's stdout as raw bytes with no PTY/CRLF
translation, so the PNG comes back intact in one round-trip — no device-side
temp file, no `adb pull`. The bytes are written to
`<ADB_AUTOMATION_LOCAL_ROOT>/screenshots/`, the same host-filesystem gate
`pull_file`/`stop_log_session` use, and the tool returns the absolute path
(plus width/height/size) so the caller knows where the file is.
"""

from __future__ import annotations

import re
import struct
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, ExecOutResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
    PolicyViolationError,
)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

# Where saved screenshots land, relative to ADB_AUTOMATION_LOCAL_ROOT — fixed so
# a caller can't scatter PNGs across the whole root.
_SCREENSHOT_SUBDIR = "screenshots"


class TakeScreenshotResult(BaseModel):
    """Outcome of capturing a device screenshot and saving it to the host.

    local_path is the absolute path the PNG was written to — that is the point
    of the tool: the caller reads the file from there. width/height are
    best-effort metadata read from the PNG header (None only if the bytes
    somehow aren't a parseable PNG — a BACKEND_ERROR is raised before that in
    the normal path); size_bytes is the file size. Only ever returned on
    success; see ScreenService.take_screenshot's Error handling.
    """

    serial: str
    display_id: int | None
    local_path: str
    width: int | None
    height: int | None
    size_bytes: int
    success: bool

    def summary(self) -> str:
        dims = f"{self.width}x{self.height} " if self.width and self.height else ""
        return f"Saved {dims}screenshot from {self.serial} to {self.local_path}."


class ScreenService:
    """Captures the device's current screen and saves it to this server's host."""

    def __init__(self, backend: AdbBackend, local_root: Path | None = None) -> None:
        self._backend = backend
        self._local_root = local_root.resolve() if local_root is not None else None

    def _resolve_local_path(self, rel: str) -> Path:
        if self._local_root is None:
            raise PolicyViolationError(
                "No local_root configured for this server — host-file-writing "
                "tools are disabled until an operator sets ADB_AUTOMATION_LOCAL_ROOT.",
                details={"local_path": rel},
            )
        resolved = (self._local_root / rel).resolve()
        if not resolved.is_relative_to(self._local_root):
            raise PolicyViolationError(
                f"local_path '{rel}' resolves outside the configured local_root.",
                details={"local_path": rel, "local_root": str(self._local_root)},
            )
        return resolved

    async def take_screenshot(
        self,
        serial: str,
        display_id: int | None = None,
        filename: str | None = None,
    ) -> TakeScreenshotResult:
        parts = ["screencap", "-p"]
        if display_id is not None:
            parts.extend(["-d", str(display_id)])

        result = await self._backend.exec_out(serial, " ".join(parts))
        _raise_for_exec_out_failure(serial, result)

        png = result.stdout
        if not png.startswith(_PNG_SIGNATURE):
            # screencap reports some failures (e.g. an invalid display_id) by
            # printing a short error to stdout and *still exiting 0* — verified
            # live: "Failed to take screenshot. Status: -2\nCapturing failed."
            detail = png[:200].decode("utf-8", errors="replace").strip()
            raise BackendError(
                f"screencap produced no PNG data: {detail}" if detail else "screencap produced no PNG data.",
                details={"serial": serial, "display_id": display_id, "bytes_returned": len(png)},
            )

        width, height = _read_png_dimensions(png)

        name = _screenshot_filename(serial, filename)
        target = self._resolve_local_path(f"{_SCREENSHOT_SUBDIR}/{name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(png)

        return TakeScreenshotResult(
            serial=serial,
            display_id=display_id,
            local_path=str(target),
            width=width,
            height=height,
            size_bytes=len(png),
            success=True,
        )


def _raise_for_exec_out_failure(serial: str, result: ExecOutResult) -> None:
    if result.exit_code == 0:
        return
    message = result.stderr.strip() or "adb exec-out screencap exited non-zero."
    # `adb exec-out` rejects an unknown serial before anything reaches the
    # device, but with different wording (and exit 255) than `adb shell`:
    # "error: device '<serial>' not found" rather than "adb: device ...".
    # Verified live against a real emulator.
    if "not found" in message and "device '" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission denied" in message or "Permission Denial" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})


def _read_png_dimensions(png: bytes) -> tuple[int | None, int | None]:
    # The IHDR chunk always immediately follows the 8-byte PNG signature:
    # 4-byte length, 4-byte type "IHDR", then big-endian 4-byte width + 4-byte
    # height — fixed by the PNG spec, never varies.
    if len(png) >= 24 and png[:8] == _PNG_SIGNATURE:
        width, height = struct.unpack(">II", png[16:24])
        return width, height
    return None, None


_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def _screenshot_filename(serial: str, filename: str | None) -> str:
    if filename is not None:
        stripped = filename.strip()
        if not stripped or stripped in {".", ".."} or "/" in filename or "\\" in filename:
            raise InvalidArgumentError(
                "filename must be a bare name with no path separators.",
                details={"filename": filename},
            )
        return stripped if stripped.lower().endswith(".png") else f"{stripped}.png"
    slug = _UNSAFE_FILENAME_CHARS.sub("-", serial)
    return f"screenshot-{slug}-{datetime.now(timezone.utc):%Y%m%d-%H%M%S}.png"
