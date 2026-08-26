"""Module-level, statically-introspectable tool functions for the user module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.user.service import CurrentUser, UserDump, UserInfo, UserService
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
        user_id: The Android user ID to look up (see get_current_user or
            dump_user to find valid IDs on this device).

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
