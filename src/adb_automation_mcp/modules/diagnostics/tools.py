"""Module-level, statically-introspectable tool functions for the diagnostics module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.diagnostics.service import AdbAvailability, DiagnosticsService
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
