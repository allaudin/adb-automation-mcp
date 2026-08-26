"""Module-level, statically-introspectable tool functions for the user module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.user.service import (
    CreateUserResult,
    CurrentUser,
    RemoveUserResult,
    SwitchUserResult,
    UserDump,
    UserInfo,
    UserList,
    UserService,
)
from adb_mcp.registry import category


@category("read")
async def get_current_user(ctx: Context, serial: str) -> CurrentUser:
    """Get the current Android user on a device: `adb shell am get-current-user`.

    Relevant on multi-user devices (work profiles, guest users, Android
    Automotive) where more than one user account can exist; most single-user
    devices just report user 0 (the primary/owner user).

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The device's serial and its current Android user ID.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "Current user on emulator-5554 is 0.",
          "data": {"serial": "emulator-5554", "user_id": 0},
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    user = cast(UserService, services["user"])
    return await user.get_current_user(serial)


@category("read")
async def dump_user(ctx: Context, serial: str) -> UserDump:
    """Dump detailed Android user info for a device: `adb shell dumpsys user`.

    UserManagerService's diagnostic dump — every user's state, flags,
    restrictions, and running/locked status — far more detail than
    get_current_user's bare user ID. No userId argument: verified live that
    `dumpsys user`'s optional userId has no effect at all (`dumpsys user 0`,
    `dumpsys user 10`, and `dumpsys user 9999` all produced identical output)
    — it always dumps every user on the device, so there's nothing to pass.
    For detail on just one specific user, use user_info instead.

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The raw dumpsys text output, plus the serial requested.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the serial
        doesn't match a connected device, that surfaces as an actual tool
        error.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "Dumped users on emulator-5554 (23000 chars).",
          "data": {
            "serial": "emulator-5554",
            "output": "Current user: 10\\n\\nUsers:\\n  UserInfo{0:null:811} ..."
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    user = cast(UserService, services["user"])
    return await user.dump_user(serial)


@category("read")
async def user_info(ctx: Context, serial: str, user_id: int) -> UserInfo:
    """Get detailed info for one Android user: `adb shell dumpsys user --user ID`.

    Unlike dump_user's plain `dumpsys user` (which always dumps every user
    and ignores any ID you give it), `--user` genuinely filters — verified
    live that `--user 0` and `--user 10` return different, single-user
    blocks. Use this when you want just one user's detail; use dump_user for
    every user at once.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        user_id: The Android user ID to look up (see list_users to find valid
            IDs on this device).

    Returns:
        The requested user's raw dumpsys block, plus the serial and user_id
        requested.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error. A user_id that doesn't exist on an otherwise-reachable
        device is also an error (not success:false data) — verified live that
        adb reports this as ordinary stdout ("User <id> not found") with exit
        code 0, so this tool detects that text and raises rather than
        returning it as if it were real user data.

    Example:
        Called with serial="emulator-5554", user_id=10. A typical response:

        ```json
        {
          "status": "success",
          "message": "User 10 info on emulator-5554 (850 chars).",
          "data": {
            "serial": "emulator-5554",
            "user_id": 10,
            "output": "UserInfo{10:Driver:412} serialNo=10 isPrimary=false\\n..."
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    user = cast(UserService, services["user"])
    return await user.user_info(serial, user_id)


@category("read")
async def list_users(ctx: Context, serial: str) -> UserList:
    """List every Android user on a device: `adb shell cmd user list -v`.

    Structured, one entry per user (id, name, type, flags, and states like
    "running"/"current"/"visible") — the fastest way to see what user IDs
    actually exist before calling user_info or switch_user with one.

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The device's serial and every user currently defined on it.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "2 users on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "users": [
              {
                "user_id": 0,
                "name": "System User",
                "type": "system.HEADLESS",
                "flags": ["INITIALIZED", "PRIMARY", "SYSTEM"],
                "states": ["running"]
              },
              {
                "user_id": 10,
                "name": "Driver",
                "type": "full.SECONDARY",
                "flags": ["ADMIN", "FULL", "INITIALIZED"],
                "states": ["running", "current", "visible"]
              }
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    user = cast(UserService, services["user"])
    return await user.list_users(serial)


@category("write")
async def switch_user(ctx: Context, serial: str, user_id: int) -> SwitchUserResult:
    """Switch the active Android user on a device: `adb shell am switch-user ID`.

    Changes what's actually running in the foreground on the device — not a
    read, and not safely re-invocable without consequence (it interrupts
    whatever the current user was doing). Use list_users first to find a
    valid target user ID.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        user_id: The Android user ID to switch to (see list_users).

    Returns:
        The serial and user_id switched to. Only returned on success —
        see Error handling below.

    Error handling:
        Unlike connect_device, `am switch-user`'s exit code was verified live
        to be reliable, so failure is a real tool error, not success:false
        data: an invalid user_id fails with "Error: Failed to switch to user
        <id>", exit code 1 — same as an unreachable serial or an unresponsive
        adb binary.

    Example:
        Called with serial="emulator-5554", user_id=0. A typical response:

        ```json
        {
          "status": "success",
          "message": "Switched to user 0 on emulator-5554.",
          "data": {"serial": "emulator-5554", "user_id": 0},
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    user = cast(UserService, services["user"])
    return await user.switch_user(serial, user_id)


@category("write")
async def create_user(ctx: Context, serial: str, name: str) -> CreateUserResult:
    """Create a full secondary Android user on a device: `adb shell pm create-user NAME`.

    Creates the user only — it does not switch to it (use switch_user
    separately if that's the goal). name is shell-quoted before being sent to
    the device, verified live to handle spaces and shell metacharacters
    safely.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        name: Display name for the new user. Can contain spaces.

    Returns:
        The serial, the newly assigned user_id, and the name requested.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error. Only the unreachable-serial failure path was verified
        live for this specific command — other real failure modes (e.g. a
        device's max-user-count limit) haven't been triggered and observed,
        so they'll surface as a generic backend error rather than a more
        specific one.

    Example:
        Called with serial="emulator-5554", name="Guest". A typical response:

        ```json
        {
          "status": "success",
          "message": "Created user 12 (Guest) on emulator-5554.",
          "data": {"serial": "emulator-5554", "user_id": 12, "name": "Guest"},
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    user = cast(UserService, services["user"])
    return await user.create_user(serial, name)


@category("destructive")
async def remove_user(ctx: Context, serial: str, user_id: int) -> RemoveUserResult:
    """Delete an Android user/profile from a device: `adb shell pm remove-user ID`.

    Irreversibly deletes the user and all of its data — destructive, and
    denied by policy unless the server is explicitly configured with
    ADB_MCP_ALLOW_DESTRUCTIVE=1. Verified live that this also fails (not just
    for a nonexistent user) if user_id is the device's current/foreground
    user — switch_user away from it first.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        user_id: The Android user ID to remove (see list_users).

    Returns:
        The serial and user_id removed.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error. Verified live that removal failure — whether user_id
        doesn't exist or is currently active — always reads "Error: couldn't
        remove user id <id>", exit code 1; adb doesn't distinguish the two
        reasons in the message, so neither does this tool.

    Example:
        Called with serial="emulator-5554", user_id=12. A typical response:

        ```json
        {
          "status": "success",
          "message": "Removed user 12 on emulator-5554.",
          "data": {"serial": "emulator-5554", "user_id": 12},
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    user = cast(UserService, services["user"])
    return await user.remove_user(serial, user_id)
