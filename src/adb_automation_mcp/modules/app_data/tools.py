"""Module-level, statically-introspectable tool functions for the app_data module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.app_data.service import AppDataService, ClearAppCacheResult
from adb_automation_mcp.registry import category


@category("write")
async def clear_app_cache(
    ctx: Context, serial: str, package_name: str, user_id: int | None = None
) -> ClearAppCacheResult:
    """Clear only a package's cache on a device: `adb shell pm clear --cache-only`.

    Scoped strictly to cache — never falls back to a full (non
    --cache-only) `pm clear` if the connected device doesn't support the
    flag, since clearing all application data has different, destructive
    semantics the caller didn't ask for (see clear_app_data, not yet
    implemented, for that). Do not use this tool expecting it to wipe an
    app's data; it only removes its cache.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package_name: The package whose cache to clear, e.g.
            "com.example.app".
        user_id: Clear the cache for one specific Android user (`--user`,
            see list_users). Omit to use pm's default user.

    Returns:
        The serial, package_name, user_id, success (always True — see Error
        handling), and the raw pm output. Only returned on success.

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A package_name that isn't
        installed (for the target user, if given) raises PACKAGE_NOT_FOUND.
        If the connected device's `pm` doesn't recognize `--cache-only` at
        all, this raises CACHE_ONLY_UNSUPPORTED rather than silently
        clearing full app data instead. A rejection the caller isn't
        permitted to perform raises PERMISSION_DENIED. `pm clear
        --cache-only`'s own bare "Failed" outcome (the device attempted the
        clear and declined it, for no more specific reason `pm` reports)
        raises ANDROID_REJECTED. Any other failure raises a generic
        BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", package_name="com.example.app".
        A typical response:

        ```json
        {
          "status": "success",
          "message": "Cleared cache for com.example.app on emulator-5554.",
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
    return await app_data.clear_app_cache(serial, package_name, user_id=user_id)
