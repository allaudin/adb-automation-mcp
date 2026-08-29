"""Module-level, statically-introspectable tool functions for the screen module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.screen.service import ScreenService, TakeScreenshotResult
from adb_automation_mcp.registry import category, image_content


@category("read")
@image_content
async def take_screenshot(
    ctx: Context,
    serial: str,
    display_id: int | None = None,
    save: bool = False,
    filename: str | None = None,
) -> TakeScreenshotResult:
    """Capture the device's current screen and return it as a PNG image.

    Runs `adb exec-out screencap -p` and returns the raw PNG to the caller as
    an image content block (renderable by MCP hosts), plus structured metadata.
    The image is always returned inline; `save` additionally writes it to disk.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        display_id: Capture one specific display (`-d`, see list_displays)
            on a multi-display device. Omit to capture the default display.
        save: Also write the PNG to
            `<ADB_AUTOMATION_LOCAL_ROOT>/screenshots/`. Off by default; the
            image is returned inline either way.
        filename: Bare filename for the saved file (no path separators);
            `.png` is appended if missing. Omit for an auto name like
            `screenshot-<serial>-<UTC timestamp>.png`. Ignored unless `save`
            is true.

    Returns:
        An image content block (`image/png`) carrying the screenshot, alongside
        structured metadata: the serial, display_id, mime_type, size_bytes,
        best-effort width/height read from the PNG header, and local_path (the
        host path it was also saved to when `save` is true, else null).

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A permission rejection raises
        PERMISSION_DENIED. If screencap runs but returns no PNG data (e.g. an
        invalid display_id on some builds), this raises BACKEND_ERROR rather
        than returning an empty image; any other non-zero exit also raises
        BACKEND_ERROR. With `save` true: no `ADB_AUTOMATION_LOCAL_ROOT`
        configured (or a `filename` that resolves outside it) raises
        POLICY_DENIED; a `filename` containing a path separator raises
        INVALID_ARGUMENT.

    Example:
        Called with serial="emulator-5554". A typical response carries an
        image block plus structured content:

        ```json
        {
          "content": [
            { "type": "image", "mimeType": "image/png", "data": "iVBORw0KGgo..." }
          ],
          "structuredContent": {
            "status": "success",
            "message": "Captured 1080x2400 screenshot from emulator-5554.",
            "data": {
              "serial": "emulator-5554",
              "display_id": null,
              "mime_type": "image/png",
              "width": 1080,
              "height": 2400,
              "size_bytes": 843221,
              "success": true,
              "local_path": null
            },
            "error": null
          }
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    screen = cast(ScreenService, services["screen"])
    return await screen.take_screenshot(serial, display_id=display_id, save=save, filename=filename)
