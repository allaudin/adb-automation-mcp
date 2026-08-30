"""Module-level, statically-introspectable tool functions for the
permissions module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.permissions.service import GrantPermissionResult, PermissionsService
from adb_automation_mcp.registry import category


@category("write")
async def grant_permission(
    ctx: Context, serial: str, package_name: str, permission: str, user_id: int | None = None
) -> GrantPermissionResult:
    """Grant one Android runtime permission to a package: `adb shell pm grant`.

    Not every permission can actually be granted this way — see Error
    handling below for the platform's own rejections. Revoking, checking,
    and listing permissions aren't implemented yet.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package_name: The package to grant the permission to, e.g.
            "com.example.app".
        permission: The fully-qualified runtime permission to grant, e.g.
            "android.permission.CAMERA".
        user_id: Grant the permission for one specific Android user
            (`--user`, see list_users). Omit to use pm's default user.

    Returns:
        The serial, package_name, permission, and user_id the grant was
        issued for, plus success (always True — see Error handling) and
        the raw `pm grant` output (normally empty on success).

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A package_name that doesn't
        correspond to any installed app raises PACKAGE_NOT_FOUND. A
        permission the package's manifest doesn't request (or one unknown
        to the platform entirely) raises PERMISSION_NOT_DECLARED. A
        permission that isn't a runtime/dangerous permission (so isn't
        dynamically grantable at all) raises NON_RUNTIME_PERMISSION. A
        permission whose state on this package is fixed by device/
        enterprise policy raises PERMISSION_POLICY_RESTRICTED. A caller
        lacking the rights to grant permissions at all raises
        PERMISSION_DENIED. Any other `pm`/adb failure raises a generic
        BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", package_name="com.example.app",
        permission="android.permission.CAMERA". A typical response:

        ```json
        {
          "status": "success",
          "message": "Granted android.permission.CAMERA to com.example.app on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "package_name": "com.example.app",
            "permission": "android.permission.CAMERA",
            "user_id": null,
            "success": true,
            "output": ""
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    permissions = cast(PermissionsService, services["permissions"])
    return await permissions.grant_permission(serial, package_name, permission, user_id=user_id)
