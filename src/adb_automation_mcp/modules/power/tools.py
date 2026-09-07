"""Module-level, statically-introspectable tool functions for the power module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.power.service import (
    PowerService,
    PowerState,
    RebootResult,
    WakeResult,
)
from adb_automation_mcp.registry import category


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


@category("write")
async def wake_device(ctx: Context, serial: str) -> WakeResult:
    """Wake a sleeping device's screen: `adb shell input keyevent WAKEUP`.

    Injects the WAKEUP power key so a device whose display has gone to
    sleep becomes interactive again — handy right before a screenshot or a
    sequence of UI taps. This does not unlock a locked keyguard; it only
    turns the screen back on. WAKEUP is idempotent: running it against an
    already-awake device is a harmless no-op, so this tool never fails just
    because the device was already awake. Putting the device back to sleep
    isn't implemented here.

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial, the keycode that was sent ("WAKEUP"), and accepted
        (always true when this returns without error — `input` produces no
        output, so success is read from its exit code). Chain
        get_power_state to confirm wakefulness afterwards if you need an
        independent check.

    Error handling:
        An unknown serial raises DEVICE_NOT_FOUND; an unresponsive adb
        binary raises ADB_UNAVAILABLE. A rejection of the key injection
        raises PERMISSION_DENIED; any other non-zero exit raises
        BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "Sent WAKEUP to emulator-5554; the screen should be awake.",
          "data": {
            "serial": "emulator-5554",
            "keycode": "WAKEUP",
            "accepted": true
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    power = cast(PowerService, services["power"])
    return await power.wake_device(serial)


@category("destructive")
async def reboot_device(ctx: Context, serial: str) -> RebootResult:
    """Reboot a device into its normal system image: `adb -s serial reboot`.

    Categorized destructive (denied by default) because it interrupts
    everything running on the device and takes it offline for the length of
    a boot. adb returns the instant the request is delivered — well before
    the device is back — so a successful result means only that the request
    was accepted. The device will disappear from adb immediately; chain
    wait_for_device_state(serial, state="device") to block until it's back
    online before continuing automation. Rebooting into bootloader/recovery
    isn't implemented here.

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial, mode ("system"), accepted (always true when this
        returns without error — adb took the request), and adb's raw output
        (normally empty).

    Error handling:
        An unknown serial raises DEVICE_NOT_FOUND; an unresponsive adb
        binary raises ADB_UNAVAILABLE. Any other non-zero exit raises
        BACKEND_ERROR. The device going offline right after this call is
        expected and is not reported as an error.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "Reboot request accepted for emulator-5554; it will drop off adb until it finishes booting.",
          "data": {
            "serial": "emulator-5554",
            "mode": "system",
            "accepted": true,
            "output": ""
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    power = cast(PowerService, services["power"])
    return await power.reboot_device(serial)
