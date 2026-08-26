"""Module-level, statically-introspectable tool functions for the
date_time module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.date_time.service import DateTimeService, DeviceDateTime
from adb_mcp.registry import category


@category("read")
async def get_date_time(ctx: Context, serial: str) -> DeviceDateTime:
    """Get the device's current system date/time: `adb shell date`.

    Always reads the DEVICE's own clock via `date`, never the MCP host's —
    the returned timestamp reflects what the device itself reports.
    Requests an explicit, machine-readable ISO-8601-shaped `+FORMAT`
    rather than `date`'s locale-dependent default human-readable output,
    so the result is predictable to parse. Setting the date/time or time
    zone isn't implemented yet.

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial, timestamp (ISO-8601 shaped, no time zone, e.g.
        "2026-08-26T18:23:45"), and utc_offset (e.g. "+0000") when the
        device's `date` supports reporting it — None otherwise (see Error
        handling).

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. If the device's `date` doesn't
        support the requested timestamp format at all (output that doesn't
        match the expected shape), that raises DEVICE_CLOCK_UNAVAILABLE.
        If only the separate UTC-offset query is unsupported or fails for
        a non-device reason, that's not treated as a failure of the call —
        utc_offset simply comes back as None, still with a valid
        timestamp. A permission rejection raises PERMISSION_DENIED; any
        other failure raises a generic BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "Device time on emulator-5554: 2026-08-26T18:23:45+0000.",
          "data": {
            "serial": "emulator-5554",
            "timestamp": "2026-08-26T18:23:45",
            "utc_offset": "+0000"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    date_time = cast(DateTimeService, services["date_time"])
    return await date_time.get_date_time(serial)
