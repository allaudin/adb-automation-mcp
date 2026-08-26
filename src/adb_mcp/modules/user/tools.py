"""Module-level, statically-introspectable tool functions for the user module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.user.service import CurrentUser, UserService
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
