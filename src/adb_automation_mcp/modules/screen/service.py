"""Domain logic for the screen module: capturing the device's current screen
as a PNG and returning the raw image bytes.

Uses `adb exec-out screencap -p` (the `exec_out` backend primitive): exec-out
streams the command's stdout as raw bytes with no PTY/CRLF translation, so the
PNG comes back intact in one round-trip — no device-side temp file, no
`adb pull`, no host filesystem write. The registry wraps the returned
`image_bytes` into an MCP image content block for the client.
"""

from __future__ import annotations

import struct

from pydantic import BaseModel, Field

from adb_automation_mcp.backend.protocol import AdbBackend, ExecOutResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    PermissionDeniedError,
)

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class TakeScreenshotResult(BaseModel):
    """Outcome of capturing a device screenshot (`adb exec-out screencap -p`).

    The raw PNG is carried in `image_bytes` for the registry to emit as an MCP
    image content block; that field is excluded from the structured envelope
    (the bytes are delivered as the image block, not duplicated as JSON).
    width/height/size_bytes are best-effort metadata read from the PNG header —
    width/height are None if the bytes somehow aren't a parseable PNG (a
    BACKEND_ERROR is raised before that happens in the normal path). Only ever
    returned on success; see ScreenService.take_screenshot's Error handling.
    """

    serial: str
    display_id: int | None
    mime_type: str = "image/png"
    width: int | None
    height: int | None
    size_bytes: int
    success: bool
    image_bytes: bytes = Field(exclude=True, repr=False)

    def summary(self) -> str:
        dims = f"{self.width}x{self.height} " if self.width and self.height else ""
        return f"Captured {dims}screenshot from {self.serial}."


class ScreenService:
    """Captures the device's current screen and returns the PNG bytes."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def take_screenshot(
        self, serial: str, display_id: int | None = None
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
        return TakeScreenshotResult(
            serial=serial,
            display_id=display_id,
            width=width,
            height=height,
            size_bytes=len(png),
            success=True,
            image_bytes=png,
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
