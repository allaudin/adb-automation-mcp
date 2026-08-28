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
    ctx: Context, serial: str, local_path: str, display_id: int | None = None
) -> TakeScreenshotResult:
    """Capture the device's current screen as a PNG: `screencap -p`.

    AdbBackend has no primitive for streaming binary output over its `str`-
    based CommandResult, so this captures to a temporary path on the device
    with `screencap -p`, pulls it here with the existing AdbBackend.pull
    primitive (the same mechanism pull_file uses), and always removes the
    device-side temp file afterward — success, failure, or anything in
    between.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        local_path: Where to write the PNG on this server's host, relative
            to (or, if absolute, still required to resolve inside) the
            server's configured local_root.
        display_id: Capture one specific display (`-d`, see list_displays)
            on a multi-display device. Omit to capture the default display.

    Returns:
        The serial, the resolved local_path actually written, display_id,
        success (always True — see Error handling), and width/height/
        size_bytes read back from the captured PNG when determinable (None
        otherwise — best-effort metadata, not guaranteed).

    Error handling:
        local_path is checked before any device round-trip: if the server
        has no local_root configured at all, or local_path resolves outside
        it (including via ".." or an absolute path elsewhere on the host),
        the call is refused rather than writing anywhere — there is no
        default local_root; an operator must set ADB_AUTOMATION_LOCAL_ROOT
        explicitly (POLICY_DENIED). Beyond that: an unknown serial or
        unresponsive adb binary raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE
        (whether during capture or the pull); a permission rejection during
        either step raises PERMISSION_DENIED; the device-side temp file
        vanishing before it could be pulled raises REMOTE_FILE_NOT_FOUND;
        any other screencap or pull failure raises a generic BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", local_path="screen.png". A
        typical response:

        ```json
        {
          "status": "success",
          "message": "Captured screenshot from emulator-5554 to /var/adb-files/screen.png.",
          "data": {
            "serial": "emulator-5554",
            "local_path": "/var/adb-files/screen.png",
            "display_id": null,
            "success": true,
            "width": 1080,
            "height": 2400,
            "size_bytes": 843221,
            "output": "/data/local/tmp/adb_automation_mcp_screenshot_....png: 1 file pulled, 0 skipped. 4.2 MB/s (843221 bytes in 0.191s)\\n"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    screen = cast(ScreenService, services["screen"])
    return await screen.take_screenshot(serial, local_path, display_id=display_id)
