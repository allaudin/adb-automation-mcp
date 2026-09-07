"""Module-level, statically-introspectable tool functions for the diagnostics module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.diagnostics.service import (
    AdbAvailability,
    AdbVersionInfo,
    BugreportResult,
    DiagnosticsService,
)
from adb_automation_mcp.registry import category


@category("read")
async def check_adb_available(ctx: Context) -> AdbAvailability:
    """Check whether the adb binary is reachable and able to list connected devices.

    This is the right first call when anything else on this server is failing or
    behaving unexpectedly — it tells you whether the problem is "adb itself isn't
    working" versus something specific to a device or command.

    Returns:
        Whether adb is available right now, and how many devices it currently sees
        connected. device_count is only meaningful when available is true; reason
        explains why when it is false.

    Error handling:
        Deliberately does not raise for adb being unreachable — that is the expected
        "available: false" answer, not a tool failure. It can still fail with
        INTERNAL_ERROR for a genuine unexpected server-side bug.

    Example:
        Called with no arguments. A typical response:

        ```json
        {
          "status": "success",
          "message": "adb is available (1 device connected).",
          "data": {"available": true, "device_count": 1, "reason": null},
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    diagnostics = cast(DiagnosticsService, services["diagnostics"])
    return await diagnostics.check_adb_available()


@category("read")
async def get_adb_version(ctx: Context) -> AdbVersionInfo:
    """Report the version of the adb client this server is driving.

    Useful before attempting anything whose availability depends on the host's
    platform-tools release — wireless pairing, split-APK install, incremental
    delivery — so an agent can check the host is new enough instead of failing
    mid-automation and guessing why. Reads `adb version`; changes nothing.

    Returns:
        The parsed adb version: the wire-protocol bridge_version, the
        platform_tools_version that actually tracks feature support (null on
        very old builds), and optional revision, installed_path, and running_on
        fields. raw holds the unparsed command output for reference. Any line
        adb omits or rewords becomes null rather than an error.

    Error handling:
        Raises ADB_UNAVAILABLE if the adb binary cannot be found or executed,
        and BACKEND_ERROR if adb runs but exits non-zero. Reworded or partial
        version output is not an error — it parses to whatever fields are present.

    Example:
        Called with no arguments. A typical response:

        ```json
        {
          "status": "success",
          "message": "adb platform-tools 35.0.2 (bridge 1.0.41).",
          "data": {
            "bridge_version": "1.0.41",
            "platform_tools_version": "35.0.2",
            "revision": null,
            "installed_path": "/usr/lib/android-sdk/platform-tools/adb",
            "running_on": "Linux 6.8.0 (x86_64)",
            "raw": "Android Debug Bridge version 1.0.41\\nVersion 35.0.2\\n..."
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    diagnostics = cast(DiagnosticsService, services["diagnostics"])
    return await diagnostics.get_adb_version()


@category("write")
async def generate_bugreport(
    ctx: Context, serial: str, local_path: str, timeout_s: float = 300.0
) -> BugreportResult:
    """Generate a full Android bugreport and save it to the host: `adb -s
    <serial> bugreport <local_path>`.

    Runs the host `adb bugreport`, which builds the report on the device,
    pulls it back, and (on modern devices) produces a single `.zip`. The
    file lands under `<ADB_AUTOMATION_LOCAL_ROOT>/bugreports/`. The archive
    is large and is not embedded in the response — only its path and size.
    Categorized `write` because generating a bugreport briefly loads the
    device (dumpstate).

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        local_path: Destination path relative to the server's local_root
            `bugreports/` directory, e.g. "device.zip" or "run1/device.zip".
            Must resolve inside local_root. If it has no extension, adb adds
            `.zip`.
        timeout_s: How long to wait for the bugreport, 60-600 seconds
            (default 300). dumpstate can take minutes.

    Returns:
        The serial; local_path (the absolute host path actually written —
        adb may have appended `.zip`); is_zip (true for the modern zipped
        form, false for a legacy text bugreport); and size_bytes.

    Error handling:
        A blank local_path or an out-of-range timeout_s raises
        INVALID_ARGUMENT. No configured local_root, or a local_path
        escaping it, raises POLICY_DENIED. An unknown/offline serial or a
        device that disconnects mid-capture raises DEVICE_NOT_FOUND; the adb
        binary being unresponsive raises ADB_UNAVAILABLE. Any other non-zero
        exit raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", local_path="device.zip". A
        typical response:

        ```json
        {
          "status": "success",
          "message": "Saved zip bugreport from emulator-5554 to /data/out/bugreports/device.zip.",
          "data": {
            "serial": "emulator-5554",
            "local_path": "/data/out/bugreports/device.zip",
            "is_zip": true,
            "size_bytes": 5310611,
            "success": true
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    diagnostics = cast(DiagnosticsService, services["diagnostics"])
    return await diagnostics.generate_bugreport(serial, local_path, timeout_s=timeout_s)
