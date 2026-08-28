"""Domain logic for the input module: injecting a single touch/tap event
(`adb shell input tap`). Swipe, text, and key events aren't implemented yet.
"""

from __future__ import annotations

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)


class TapResult(BaseModel):
    """Outcome of injecting a tap event (`adb shell input tap`).

    Not verified live (no device was available in this environment) —
    shaped on `Input.java`'s documented, long-stable behavior: `input tap`
    produces no stdout at all on success, resolving synchronously to either
    an injected event or one of the failure modes classified in
    InputService.tap's Error handling. success is always True here; it's
    kept as an explicit field since a caller inspecting just the data
    payload should still see it stated, not merely implied by the
    envelope's status.
    """

    serial: str
    x: int
    y: int
    display_id: int | None
    success: bool
    output: str

    def summary(self) -> str:
        return f"Tapped ({self.x}, {self.y}) on {self.serial}."


class InputService:
    """Injects touch/tap events on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def tap(self, serial: str, x: int, y: int, display_id: int | None = None) -> TapResult:
        if x < 0 or y < 0:
            raise InvalidArgumentError(
                "x and y must be non-negative integers.",
                details={"serial": serial, "x": x, "y": y},
            )

        parts = ["input"]
        if display_id is not None:
            parts.extend(["-d", str(display_id)])
        parts.extend(["tap", str(x), str(y)])

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_tap_failure(serial, x, y, result)
        return TapResult(
            serial=serial, x=x, y=y, display_id=display_id, success=True, output=result.stdout
        )


def _raise_for_tap_failure(serial: str, x: int, y: int, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's) — the adb-client rejects an unknown serial
    # before any command reaches a device.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial, "x": x, "y": y})
    raise BackendError(message, details={"serial": serial, "x": x, "y": y, "exit_code": result.exit_code})
