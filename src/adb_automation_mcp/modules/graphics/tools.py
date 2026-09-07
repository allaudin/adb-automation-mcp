"""Module-level, statically-introspectable tool functions for the graphics module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.graphics.service import (
    FrameStats,
    GraphicsService,
    ResetFrameStatsResult,
)
from adb_automation_mcp.registry import category


@category("read")
async def get_frame_stats(
    ctx: Context, serial: str, package: str, include_histogram: bool = False
) -> FrameStats:
    """Get an app's rendering / jank statistics: `adb shell dumpsys gfxinfo
    <package> framestats`.

    Parses gfxinfo's stable summary block — total frames, janky frame count
    and percentage, frame-time percentiles, and the "Number <x>:" jank
    counters (missed vsync, high input latency, slow UI thread, ...). The
    large raw per-frame CSV that `framestats` also emits is never parsed or
    returned; the frame-time HISTOGRAM is returned only when you ask for it.
    Pair with reset_frame_stats to measure a specific flow.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package: The app to inspect, e.g. "com.example.app". Must be running
            with a rendering surface.
        include_histogram: When true, also return the frame-time bucket
            histogram ("<ms>" -> frame count). Off by default to keep
            responses small.

    Returns:
        The serial / package / pid / process_name; stats_since_ns;
        total_frames_rendered; janky_frames / janky_percent (and the legacy
        pair); p50_ms / p90_ms / p95_ms / p99_ms; counters (the jank
        counter map); and histogram (null unless include_histogram). Fields
        gfxinfo didn't emit are null.

    Error handling:
        A blank package raises INVALID_ARGUMENT before anything runs. An
        unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A package that isn't running
        ("No process found for: ...") raises PACKAGE_NOT_RUNNING. A
        permission rejection raises PERMISSION_DENIED; any other non-zero
        exit raises BACKEND_ERROR. A running app that has rendered no frames
        yet is a success with total_frames_rendered=0 and null percentiles.

    Example:
        Called with serial="emulator-5554", package="com.example.app". A
        typical response:

        ```json
        {
          "status": "success",
          "message": "com.example.app on emulator-5554: 728 frames rendered, 164 janky (22.53%).",
          "data": {
            "serial": "emulator-5554",
            "package": "com.example.app",
            "pid": 1224,
            "process_name": "com.example.app",
            "stats_since_ns": 11900917072,
            "total_frames_rendered": 728,
            "janky_frames": 164,
            "janky_percent": 22.53,
            "janky_frames_legacy": 116,
            "janky_percent_legacy": 15.93,
            "p50_ms": 7,
            "p90_ms": 23,
            "p95_ms": 31,
            "p99_ms": 400,
            "counters": {"missed_vsync": 14, "high_input_latency": 211, "slow_ui_thread": 16},
            "histogram": null
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    graphics = cast(GraphicsService, services["graphics"])
    return await graphics.get_frame_stats(serial, package, include_histogram=include_histogram)


@category("write")
async def reset_frame_stats(ctx: Context, serial: str, package: str) -> ResetFrameStatsResult:
    """Reset an app's graphics frame statistics: `adb shell dumpsys gfxinfo
    <package> reset`.

    Zeroes gfxinfo's frame counters so a subsequent get_frame_stats
    measures only the flow you run in between. Categorized `write` because
    it mutates on-device rendering-stats state. gfxinfo's reset has no
    meaningful textual output, so this returns a minimal confirmation.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package: The app whose frame stats to reset, e.g. "com.example.app".

    Returns:
        The serial, package, and reset (always true when this returns
        without error).

    Error handling:
        A blank package raises INVALID_ARGUMENT before anything runs. An
        unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A package that isn't running
        raises PACKAGE_NOT_RUNNING. A permission rejection raises
        PERMISSION_DENIED; any other non-zero exit raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", package="com.example.app". A
        typical response:

        ```json
        {
          "status": "success",
          "message": "Reset frame stats for com.example.app on emulator-5554.",
          "data": {"serial": "emulator-5554", "package": "com.example.app", "reset": true},
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    graphics = cast(GraphicsService, services["graphics"])
    return await graphics.reset_frame_stats(serial, package)
