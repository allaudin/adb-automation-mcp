"""Module-level, statically-introspectable tool functions for the displays module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.displays.service import DisplayList, DisplaysService
from adb_automation_mcp.registry import category


@category("read")
async def list_displays(ctx: Context, serial: str) -> DisplayList:
    """Enumerate a device's logical displays: `adb shell dumpsys display`.

    This is the display-discovery anchor for the rest of the server — the
    display_id values it returns are what `-d` / `--display` on the
    screenshot, input, and activity-launch tools expect. `dumpsys display`
    is large and mostly unstable internal state; this reads only two
    curated markers (the `mViewports=[...]` line and the `Display States:`
    section) and parses them in Python. Changing display state (size,
    density, rotation) isn't implemented here.

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial and displays: a list (ordered by display_id, always at
        least one entry) of {display_id, state ("ON"/"OFF"/"DOZE"/…), type
        ("INTERNAL"/"EXTERNAL"/"VIRTUAL"/"OVERLAY"), width, height,
        density_dpi, rotation (0-3 quarter-turns), unique_id}. Every field
        except display_id may be None when `dumpsys display` didn't report
        it (e.g. dimensions/density/type are None for a powered-off display
        with no active viewport).

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A permission rejection raises
        PERMISSION_DENIED. If `dumpsys display` runs but its output has no
        recognizable display records at all (format drift, truncated
        output), this raises DISPLAY_INFO_UNAVAILABLE rather than returning
        an empty list. Any other non-zero exit raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "1 display on emulator-5554: 0.",
          "data": {
            "serial": "emulator-5554",
            "displays": [
              {
                "display_id": 0,
                "state": "ON",
                "type": "INTERNAL",
                "width": 1408,
                "height": 792,
                "density_dpi": 160,
                "rotation": 0,
                "unique_id": "local:4619827259835644672"
              }
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    displays = cast(DisplaysService, services["displays"])
    return await displays.list_displays(serial)
