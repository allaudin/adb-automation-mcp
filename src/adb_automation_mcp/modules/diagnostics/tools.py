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
            "raw": "Android Debug Bridge version 1.0.41\nVersion 35.0.2\n..."
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    diagnostics = cast(DiagnosticsService, services["diagnostics"])
    return await diagnostics.get_adb_version()
