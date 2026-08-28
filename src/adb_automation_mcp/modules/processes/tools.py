"""Module-level, statically-introspectable tool functions for the processes module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.processes.service import ForceStopResult, ProcessesService
from adb_automation_mcp.registry import category


@category("write")
async def force_stop_app(
    ctx: Context, serial: str, package_name: str, user_id: int | None = None
) -> ForceStopResult:
    """Force-stop an Android package on a device: `adb shell am force-stop`.

    Stops every process and component of the package, if any are running —
    not a per-process kill (see the module docs: `am kill` isn't implemented
    yet, and this tool is deliberately not named kill_app since it operates
    on a package, not a single process/pid).

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package_name: The package to force-stop, e.g. "com.example.app".
        user_id: Force-stop the package for one specific Android user
            (`--user`, see list_users). Omit to stop it for every user.

    Returns:
        The serial, package_name, and user_id the force-stop was issued for,
        plus the raw (usually empty) am output. `am force-stop` normally
        produces no stdout at all on success — success is determined from
        the command's exit code, not from output content.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error (DEVICE_NOT_FOUND). A rejection due to the caller lacking
        FORCE_STOP_PACKAGES raises PERMISSION_DENIED (unusual over adb shell,
        which is granted this by default). Any other ActivityManager/adb
        failure raises a generic BACKEND_ERROR. A package_name that doesn't
        correspond to any installed app is NOT an error —
        forceStopPackage() doesn't validate that the package exists; it's a
        silent no-op when there's nothing to stop, same as a real call
        against an already-stopped package.

    Example:
        Called with serial="emulator-5554", package_name="com.example.app".
        A typical response:

        ```json
        {
          "status": "success",
          "message": "Force-stopped com.example.app on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "package_name": "com.example.app",
            "user_id": null,
            "output": ""
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    processes = cast(ProcessesService, services["processes"])
    return await processes.force_stop_app(serial, package_name, user_id=user_id)
