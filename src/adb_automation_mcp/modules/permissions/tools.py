"""Module-level, statically-introspectable tool functions for the
permissions module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.permissions.service import (
    GrantPermissionResult,
    PackagePermissions,
    PermissionsService,
    RevokePermissionResult,
)
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


@category("write")
async def revoke_permission(
    ctx: Context, serial: str, package_name: str, permission: str, user_id: int | None = None
) -> RevokePermissionResult:
    """Revoke one Android runtime permission from a package: `adb shell pm revoke`.

    The counterpart to grant_permission. Idempotent — revoking a permission
    the package doesn't currently hold (or doesn't even request) is a
    success, not an error, since the intended end state is reached either way.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package_name: The package to revoke the permission from, e.g.
            "com.example.app".
        permission: The fully-qualified runtime permission to revoke, e.g.
            "android.permission.CAMERA".
        user_id: Revoke for one specific Android user (`--user`, see
            list_users). Omit to use pm's default user. On multi-user
            devices a package is often only installed for a secondary user,
            in which case this must name that user or the revoke fails with
            PACKAGE_NOT_FOUND.

    Returns:
        The serial, package_name, permission, and user_id the revoke was
        issued for, plus success (always True — see Error handling) and the
        raw `pm revoke` output (normally empty on success).

    Error handling:
        An empty package_name or permission, or a negative user_id, raises
        INVALID_ARGUMENT before any adb call. An unknown serial or
        unresponsive adb binary raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A
        package_name not installed (for the targeted user) raises
        PACKAGE_NOT_FOUND. A permission unknown to the platform raises
        PERMISSION_NOT_DECLARED. A permission that isn't a runtime/dangerous
        permission raises NON_RUNTIME_PERMISSION. A policy-fixed permission
        state raises PERMISSION_POLICY_RESTRICTED. A caller lacking the
        rights raises PERMISSION_DENIED. Any other `pm`/adb failure raises
        BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", package_name="com.example.app",
        permission="android.permission.CAMERA". A typical response:

        ```json
        {
          "status": "success",
          "message": "Revoked android.permission.CAMERA from com.example.app on emulator-5554.",
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
    return await permissions.revoke_permission(serial, package_name, permission, user_id=user_id)


@category("read")
async def get_package_permissions(
    ctx: Context, serial: str, package_name: str
) -> PackagePermissions:
    """A package's full permission picture: `adb shell dumpsys package <pkg>`.

    Read this before calling grant_permission / revoke_permission blindly — it
    shows what the package requests, what its manifest defines, and what's
    actually granted (install-time, and runtime per Android user with flags).
    Parses the stable permission sub-blocks out of dumpsys, not the whole dump.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package_name: The package to inspect, e.g. "com.example.app".

    Returns:
        A PackagePermissions: requested_permissions (names the manifest uses),
        declared_permissions (name + protection level the manifest defines),
        install_permissions (name + granted, package-wide), and
        runtime_permissions — one entry per Android user, each listing name +
        granted + flags (USER_SET, SYSTEM_FIXED, POLICY_FIXED,
        GRANTED_BY_DEFAULT, RESTRICTION_UPGRADE_EXEMPT, …). Any section this
        Android version's dumpsys omits comes back as an empty list.

    Error handling:
        An empty package_name raises INVALID_ARGUMENT before any adb call. An
        unknown serial raises DEVICE_NOT_FOUND; an unreachable adb binary raises
        ADB_UNAVAILABLE. A package dumpsys has no record of raises
        PACKAGE_NOT_FOUND (dumpsys says "Unable to find package" and still exits
        0 — this tool turns that into the error).

    Example:
        Called with serial="emulator-5554", package_name="com.example.app". A
        typical response:

        ```json
        {
          "status": "success",
          "message": "com.example.app on emulator-5554: 4 requested, 2 install-time granted, 1 runtime granted across 1 user(s).",
          "data": {
            "serial": "emulator-5554",
            "package_name": "com.example.app",
            "requested_permissions": [
              "android.permission.INTERNET", "android.permission.CAMERA"
            ],
            "declared_permissions": [
              {"name": "com.example.app.CUSTOM", "protection": "signature"}
            ],
            "install_permissions": [
              {"name": "android.permission.INTERNET", "granted": true, "flags": []}
            ],
            "runtime_permissions": [
              {
                "user_id": 0,
                "permissions": [
                  {"name": "android.permission.CAMERA", "granted": true, "flags": ["USER_SET"]}
                ]
              }
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    permissions = cast(PermissionsService, services["permissions"])
    return await permissions.get_package_permissions(serial, package_name)
