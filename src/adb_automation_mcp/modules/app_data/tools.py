"""Module-level, statically-introspectable tool functions for the app_data module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.app_data.service import AppDataService, ClearAppDataResult
from adb_automation_mcp.registry import category


@category("destructive")
async def clear_app_data(
    ctx: Context, serial: str, package_name: str, user_id: int | None = None
) -> ClearAppDataResult:
    """Wipe a package's full application data on a device: `adb shell pm clear`.

    Resets the app to a fresh-install state — its databases, shared
    preferences, files *and* cache are all deleted. This is the unscoped
    `pm clear`, the only variant supported on effectively every Android
    version; there is no reliable cross-version ADB way to clear just the
    cache (`pm clear --cache-only` is Android 11+ only). Use this only when
    losing the app's data is acceptable.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package_name: The package whose data to wipe, e.g.
            "com.example.app".
        user_id: Wipe the data for one specific Android user (`--user`,
            see list_users). Omit to use pm's default user.

    Returns:
        The serial, package_name, user_id, success (always True — see Error
        handling), and the raw pm output. Only returned on success.

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A package_name that isn't
        installed (for the target user, if given) raises PACKAGE_NOT_FOUND.
        A rejection the caller isn't permitted to perform raises
        PERMISSION_DENIED. `pm clear`'s own bare "Failed" outcome (the
        device attempted the clear and declined it, for no more specific
        reason `pm` reports) raises ANDROID_REJECTED. Any other failure
        raises a generic BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", package_name="com.example.app".
        A typical response:

        ```json
        {
          "status": "success",
          "message": "Cleared application data for com.example.app on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "package_name": "com.example.app",
            "user_id": null,
            "success": true,
            "output": "Success\\n"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    app_data = cast(AppDataService, services["app_data"])
    return await app_data.clear_app_data(serial, package_name, user_id=user_id)
