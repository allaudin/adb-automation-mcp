"""Module-level, statically-introspectable tool functions for the screen module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.screen.service import ScreenService, TakeScreenshotResult
from adb_automation_mcp.registry import category


@category("read")
async def take_screenshot(
    ctx: Context,
    serial: str,
    display_id: int | None = None,
    filename: str | None = None,
) -> TakeScreenshotResult:
    """Capture the device's screen as a PNG, save it to the host, return the path.

    Runs `adb exec-out screencap -p`, writes the PNG to
    `<ADB_AUTOMATION_LOCAL_ROOT>/screenshots/`, and returns the absolute path
    it was saved to (plus width/height/size). The caller reads the image from
    that path — no image bytes are returned inline.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        display_id: Capture one specific display (`-d`, see list_displays)
            on a multi-display device. Omit to capture the default display.
        filename: Bare filename for the saved file (no path separators);
            `.png` is appended if missing. Omit for an auto name like
            `screenshot-<serial>-<UTC timestamp>.png`.

    Returns:
        The serial, display_id, the absolute local_path the PNG was saved to,
        best-effort width/height read from the PNG header, and size_bytes.

    Error handling:
        No `ADB_AUTOMATION_LOCAL_ROOT` configured (or a `filename` that
        resolves outside it) raises POLICY_DENIED. A `filename` containing a
        path separator raises INVALID_ARGUMENT. An unknown serial or
        unresponsive adb binary raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A
        permission rejection raises PERMISSION_DENIED. If screencap runs but
        returns no PNG data (e.g. an invalid display_id on some builds), or
        any other non-zero exit, this raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "Saved 1080x2400 screenshot from emulator-5554 to /srv/adb/screenshots/screenshot-emulator-5554-20260830-101500.png.",
          "data": {
            "serial": "emulator-5554",
            "display_id": null,
            "local_path": "/srv/adb/screenshots/screenshot-emulator-5554-20260830-101500.png",
            "width": 1080,
            "height": 2400,
            "size_bytes": 843221,
            "success": true
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    screen = cast(ScreenService, services["screen"])
    return await screen.take_screenshot(serial, display_id=display_id, filename=filename)
