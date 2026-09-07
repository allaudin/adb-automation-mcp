"""Module-level, statically-introspectable tool functions for the displays module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.displays.service import (
    DisplayDensity,
    DisplayList,
    DisplaySize,
    DisplaysService,
)
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


@category("read")
async def get_display_size(
    ctx: Context, serial: str, display_id: int | None = None
) -> DisplaySize:
    """Get a display's pixel dimensions: `adb shell wm size [-d display_id]`.

    Read this before coordinate-based `tap`/`swipe` automation so taps land
    where you expect. Returns the panel's physical resolution and, when a
    `wm size WxH` override is currently in effect, the override too — plus
    the effective resolution apps actually see (the override if set, else
    physical). Setting or resetting the size isn't implemented here.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        display_id: Which logical display to query (see list_displays). Omit
            for the device's default display. Must be non-negative.

    Returns:
        The serial, the display_id queried (None for the default display),
        physical_width/physical_height, override_width/override_height (None
        when no override is set), and effective_width/effective_height.

    Error handling:
        A negative display_id raises INVALID_ARGUMENT before any adb call. An
        unknown serial or unresponsive adb binary raises DEVICE_NOT_FOUND/
        ADB_UNAVAILABLE; a permission rejection raises PERMISSION_DENIED. A
        display_id that doesn't exist (wm reports "0x0") and output with no
        recognizable "Physical size:" line both raise DISPLAY_INFO_UNAVAILABLE.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "default display on emulator-5554: 1408x792.",
          "data": {
            "serial": "emulator-5554",
            "display_id": null,
            "physical_width": 1408,
            "physical_height": 792,
            "override_width": null,
            "override_height": null,
            "effective_width": 1408,
            "effective_height": 792
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    displays = cast(DisplaysService, services["displays"])
    return await displays.get_display_size(serial, display_id)


@category("read")
async def get_display_density(
    ctx: Context, serial: str, display_id: int | None = None
) -> DisplayDensity:
    """Get a display's density in dpi: `adb shell wm density [-d display_id]`.

    Record this before a density-override test so you can restore it after,
    or to convert between dp and px for layout assertions. Returns the
    panel's physical density and, when a `wm density N` override is in
    effect, the override too — plus the effective density apps see. Setting
    or resetting the density isn't implemented here.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        display_id: Which logical display to query (see list_displays). Omit
            for the device's default display. Must be non-negative.

    Returns:
        The serial, the display_id queried (None for the default display),
        physical_density, override_density (None when no override is set),
        and effective_density (the override if set, else physical).

    Error handling:
        A negative display_id raises INVALID_ARGUMENT before any adb call. An
        unknown serial or unresponsive adb binary raises DEVICE_NOT_FOUND/
        ADB_UNAVAILABLE; a permission rejection raises PERMISSION_DENIED. A
        display_id that doesn't exist (wm reports "-1") and output with no
        recognizable "Physical density:" line both raise
        DISPLAY_INFO_UNAVAILABLE.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "default display on emulator-5554: 160dpi.",
          "data": {
            "serial": "emulator-5554",
            "display_id": null,
            "physical_density": 160,
            "override_density": null,
            "effective_density": 160
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    displays = cast(DisplaysService, services["displays"])
    return await displays.get_display_density(serial, display_id)
