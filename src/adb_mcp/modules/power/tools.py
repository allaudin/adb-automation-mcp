"""Module-level, statically-introspectable tool functions for the power module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.power.service import PowerService, PowerState
from adb_mcp.registry import category


@category("read")
async def get_power_state(ctx: Context, serial: str) -> PowerState:
    """Get the device's current high-level power state: `adb shell dumpsys power`.

    `dumpsys power`'s full output is large and full of unstable
    implementation detail, so this deliberately extracts only two fields:
    wakefulness (the device's core sleep/wake state) and, when present,
    whether it's currently interactive. Nothing else from the dump is
    parsed or exposed. Power-related control (reboot, shutdown, sleep,
    wake) isn't implemented yet.

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial, wakefulness (the raw value dumpsys reports, e.g.
        "Awake", "Asleep", "Dreaming", "Dozing"), and interactive (True/
        False when dumpsys reports it, None when that specific field isn't
        present in this dump — see Error handling).

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. dumpsys running but producing
        output with no recognizable wakefulness field at all (e.g. the
        power service isn't registered, or the dump format is otherwise
        unrecognizable) raises POWER_STATE_UNAVAILABLE — distinct from
        interactive simply being absent, which is returned as data
        (interactive=None), not raised. A permission rejection raises
        PERMISSION_DENIED; any other failure raises a generic
        BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "Awake on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "wakefulness": "Awake",
            "interactive": true
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    power = cast(PowerService, services["power"])
    return await power.get_power_state(serial)
