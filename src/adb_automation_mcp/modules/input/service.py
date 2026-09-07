"""Domain logic for the input module: injecting input events with
`adb shell input` — a tap, a swipe, literal text, or a single key event.
Each event type is a distinct typed tool; there is no generic `input` passthrough.
"""

from __future__ import annotations

import shlex
from typing import Literal, get_args

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)

# A curated set of Android key events useful for automation. Each maps to
# `KEYCODE_<name>`; an arbitrary keycode token is deliberately not accepted.
PressableKey = Literal[
    "HOME", "BACK", "MENU", "APP_SWITCH", "DPAD_UP", "DPAD_DOWN", "DPAD_LEFT",
    "DPAD_RIGHT", "DPAD_CENTER", "ENTER", "TAB", "SPACE", "DEL", "FORWARD_DEL",
    "ESCAPE", "PAGE_UP", "PAGE_DOWN", "MOVE_HOME", "MOVE_END", "POWER", "WAKEUP",
    "SLEEP", "VOLUME_UP", "VOLUME_DOWN", "VOLUME_MUTE", "MEDIA_PLAY_PAUSE",
    "MEDIA_PLAY", "MEDIA_PAUSE", "MEDIA_STOP", "MEDIA_NEXT", "MEDIA_PREVIOUS",
    "CAMERA", "CALL", "ENDCALL", "SEARCH", "NOTIFICATION", "SETTINGS",
    "BRIGHTNESS_UP", "BRIGHTNESS_DOWN",
]
_PRESSABLE_KEYS = frozenset(get_args(PressableKey))


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


class SwipeResult(BaseModel):
    """Outcome of injecting a swipe gesture (`adb shell input swipe`).

    Silent on success. Only ever returned on success; every failure kind is
    classified and raised, not returned as data.
    """

    serial: str
    x1: int
    y1: int
    x2: int
    y2: int
    duration_ms: int | None
    display_id: int | None
    success: bool
    output: str

    def summary(self) -> str:
        dur = f" over {self.duration_ms}ms" if self.duration_ms is not None else ""
        return f"Swiped ({self.x1},{self.y1})→({self.x2},{self.y2}) on {self.serial}{dur}."


class TextInputResult(BaseModel):
    """Outcome of injecting text into the focused field (`adb shell input text`).

    `input text` types into whatever view currently has input focus; if
    nothing does, the keystrokes are dropped by Android — this tool can't
    detect that. Silent on success.
    """

    serial: str
    text: str
    display_id: int | None
    success: bool
    output: str

    def summary(self) -> str:
        preview = self.text if len(self.text) <= 40 else self.text[:37] + "..."
        return f"Typed {preview!r} on {self.serial}."


class PressKeyResult(BaseModel):
    """Outcome of injecting one key event (`adb shell input keyevent`)."""

    serial: str
    key: str
    keycode: str
    display_id: int | None
    success: bool
    output: str

    def summary(self) -> str:
        return f"Pressed {self.key} on {self.serial}."


class InputService:
    """Injects input events (tap, swipe, text, key) on a connected device."""

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
        _raise_for_input_failure(serial, result, {"x": x, "y": y})
        return TapResult(
            serial=serial, x=x, y=y, display_id=display_id, success=True, output=result.stdout
        )

    async def swipe(
        self,
        serial: str,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int | None = None,
        display_id: int | None = None,
    ) -> SwipeResult:
        if min(x1, y1, x2, y2) < 0:
            raise InvalidArgumentError(
                "coordinates must be non-negative integers.",
                details={"serial": serial, "x1": x1, "y1": y1, "x2": x2, "y2": y2},
            )
        if duration_ms is not None and duration_ms < 0:
            raise InvalidArgumentError(
                "duration_ms must be a non-negative integer.",
                details={"serial": serial, "duration_ms": duration_ms},
            )

        parts = ["input"]
        if display_id is not None:
            parts.extend(["-d", str(display_id)])
        parts.extend(["swipe", str(x1), str(y1), str(x2), str(y2)])
        if duration_ms is not None:
            parts.append(str(duration_ms))

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_input_failure(serial, result, {"x1": x1, "y1": y1, "x2": x2, "y2": y2})
        return SwipeResult(
            serial=serial,
            x1=x1,
            y1=y1,
            x2=x2,
            y2=y2,
            duration_ms=duration_ms,
            display_id=display_id,
            success=True,
            output=result.stdout,
        )

    async def input_text(
        self, serial: str, text: str, display_id: int | None = None
    ) -> TextInputResult:
        if text == "":
            raise InvalidArgumentError(
                "text must not be empty.", details={"serial": serial}
            )

        # `input text` treats a literal space as an argument separator on some
        # builds; its documented convention is "%s" for a space. Substitute
        # first, then shell-quote the whole token so nothing else is
        # interpreted by the device shell.
        arg = shlex.quote(text.replace(" ", "%s"))
        parts = ["input"]
        if display_id is not None:
            parts.extend(["-d", str(display_id)])
        parts.extend(["text", arg])

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_input_failure(serial, result, {})
        return TextInputResult(
            serial=serial, text=text, display_id=display_id, success=True, output=result.stdout
        )

    async def press_key(
        self, serial: str, key: PressableKey, display_id: int | None = None
    ) -> PressKeyResult:
        if key not in _PRESSABLE_KEYS:
            raise InvalidArgumentError(
                f"Unknown key {key!r}.",
                details={"serial": serial, "valid": sorted(_PRESSABLE_KEYS)},
            )
        keycode = f"KEYCODE_{key}"

        parts = ["input"]
        if display_id is not None:
            parts.extend(["-d", str(display_id)])
        parts.extend(["keyevent", keycode])

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_input_failure(serial, result, {"key": key})
        return PressKeyResult(
            serial=serial,
            key=key,
            keycode=keycode,
            display_id=display_id,
            success=True,
            output=result.stdout,
        )


def _raise_for_input_failure(
    serial: str, result: CommandResult, extra: dict[str, object]
) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules — the adb-client rejects an unknown serial before any
    # command reaches a device.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial, **extra})
    raise BackendError(
        message, details={"serial": serial, "exit_code": result.exit_code, **extra}
    )
