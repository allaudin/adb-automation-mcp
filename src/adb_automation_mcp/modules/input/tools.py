"""Module-level, statically-introspectable tool functions for the input module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.input.service import InputService, TapResult
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
