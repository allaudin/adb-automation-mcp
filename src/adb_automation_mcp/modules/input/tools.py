"""Module-level, statically-introspectable tool functions for the input module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.input.service import (
    InputService,
    PressableKey,
    PressKeyResult,
    SwipeResult,
    TapResult,
    TextInputResult,
)
from adb_automation_mcp.registry import category


@category("write")
async def tap(ctx: Context, serial: str, x: int, y: int, display_id: int | None = None) -> TapResult:
    """Inject a single touch/tap event on a device: `adb shell input tap`.

    Models one specific input event (a tap) rather than accepting a raw
    `input` command string — see the module docs for why this server never
    exposes arbitrary shell arguments. Swipe, text, and key events aren't
    implemented yet.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        x: The horizontal coordinate to tap, in pixels from the screen's
            left edge. Must be a non-negative integer.
        y: The vertical coordinate to tap, in pixels from the screen's top
            edge. Must be a non-negative integer.
        display_id: Inject the tap on one specific display (`-d`, see
            list_displays) on a multi-display device. Omit to use the
            default display.

    Returns:
        The serial, x, y, and display_id the tap was injected with, plus
        success (always True — see Error handling) and the raw (usually
        empty) `input` output.

    Error handling:
        x or y being negative is rejected before any device round-trip
        (INVALID_ARGUMENT). Beyond that: an unknown serial or unresponsive
        adb binary raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE; a permission
        rejection raises PERMISSION_DENIED; any other `input`/adb failure
        raises a generic BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", x=500, y=800. A typical
        response:

        ```json
        {
          "status": "success",
          "message": "Tapped (500, 800) on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "x": 500,
            "y": 800,
            "display_id": null,
            "success": true,
            "output": ""
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    input_service = cast(InputService, services["input"])
    return await input_service.tap(serial, x, y, display_id=display_id)


@category("write")
async def swipe(
    ctx: Context,
    serial: str,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int | None = None,
    display_id: int | None = None,
) -> SwipeResult:
    """Inject a swipe gesture between two points: `adb shell input swipe`.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        x1: Start X, pixels from the left edge. Non-negative.
        y1: Start Y, pixels from the top edge. Non-negative.
        x2: End X, pixels from the left edge. Non-negative.
        y2: End Y, pixels from the top edge. Non-negative.
        duration_ms: How long the swipe takes, in milliseconds (non-negative).
            Omit to use `input`'s default. A longer duration reads as a drag /
            fling depending on distance.
        display_id: Inject on one specific display (`-d`, see list_displays).

    Returns:
        The serial, the four coordinates, duration_ms and display_id used,
        success (always True — see Error handling), and the raw (usually
        empty) `input` output.

    Error handling:
        A negative coordinate or duration is rejected before any device
        round-trip (INVALID_ARGUMENT). An unknown serial or unresponsive adb
        binary raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE; a permission rejection
        raises PERMISSION_DENIED; any other failure raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", x1=500, y1=1500, x2=500, y2=300,
        duration_ms=250. A typical response:

        ```json
        {
          "status": "success",
          "message": "Swiped (500,1500)→(500,300) on emulator-5554 over 250ms.",
          "data": {
            "serial": "emulator-5554",
            "x1": 500, "y1": 1500, "x2": 500, "y2": 300,
            "duration_ms": 250, "display_id": null,
            "success": true, "output": ""
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    input_service = cast(InputService, services["input"])
    return await input_service.swipe(
        serial, x1, y1, x2, y2, duration_ms=duration_ms, display_id=display_id
    )


@category("write")
async def input_text(
    ctx: Context, serial: str, text: str, display_id: int | None = None
) -> TextInputResult:
    """Type literal text into the focused input field: `adb shell input text`.

    The text goes to whatever view currently has input focus; if nothing is
    focused, Android drops the keystrokes and this tool cannot tell. Spaces
    are handled; some punctuation and non-ASCII characters may not inject
    reliably — that's an Android `input text` limitation, not a bug here.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        text: The string to type. Must not be empty.
        display_id: Inject on one specific display (`-d`, see list_displays).

    Returns:
        The serial, the text, display_id, success (always True — see Error
        handling), and the raw (usually empty) `input` output.

    Error handling:
        An empty text is rejected before any device round-trip
        (INVALID_ARGUMENT). An unknown serial or unresponsive adb binary
        raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE; a permission rejection raises
        PERMISSION_DENIED; any other failure raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", text="hello world". A typical
        response:

        ```json
        {
          "status": "success",
          "message": "Typed 'hello world' on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "text": "hello world",
            "display_id": null,
            "success": true,
            "output": ""
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    input_service = cast(InputService, services["input"])
    return await input_service.input_text(serial, text, display_id=display_id)


@category("write")
async def press_key(
    ctx: Context, serial: str, key: PressableKey, display_id: int | None = None
) -> PressKeyResult:
    """Inject one Android key event: `adb shell input keyevent`.

    key is a typed name from a curated set (HOME, BACK, ENTER, DPAD_*,
    VOLUME_*, WAKEUP, MEDIA_PLAY_PAUSE, …) — arbitrary keycodes aren't
    accepted. It's mapped to the matching `KEYCODE_<name>`.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        key: The key to press. One of the names in the input schema's enum
            (e.g. "BACK", "HOME", "ENTER", "DPAD_DOWN", "WAKEUP").
        display_id: Inject on one specific display (`-d`, see list_displays).

    Returns:
        The serial, the key name, the resolved keycode ("KEYCODE_<name>"),
        display_id, success (always True — see Error handling), and the raw
        (usually empty) `input` output.

    Error handling:
        An unknown key is rejected by the tool's input schema (and again in
        the service) before any device round-trip. An unknown serial or
        unresponsive adb binary raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE; a
        permission rejection raises PERMISSION_DENIED; any other failure
        raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", key="BACK". A typical response:

        ```json
        {
          "status": "success",
          "message": "Pressed BACK on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "key": "BACK",
            "keycode": "KEYCODE_BACK",
            "display_id": null,
            "success": true,
            "output": ""
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    input_service = cast(InputService, services["input"])
    return await input_service.press_key(serial, key, display_id=display_id)
