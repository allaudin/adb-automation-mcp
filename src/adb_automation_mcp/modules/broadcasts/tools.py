"""Module-level, statically-introspectable tool functions for the broadcasts module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.broadcasts.service import (
    BroadcastExtra,
    BroadcastResult,
    BroadcastsService,
)
from adb_automation_mcp.registry import category


@category("write")
async def send_broadcast(
    ctx: Context,
    serial: str,
    action: str,
    component: str | None = None,
    package: str | None = None,
    user_id: int | None = None,
    receiver_permission: str | None = None,
    extras: list[BroadcastExtra] | None = None,
) -> BroadcastResult:
    """Send an Android intent broadcast to a device: `adb shell am broadcast`.

    Models the intent semantically (action/component/package/extras) rather
    than accepting a raw command string — see the module docs for why this
    server never exposes arbitrary shell arguments.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        action: The broadcast's Intent action, e.g.
            "android.intent.action.MY_ACTION" (`-a`).
        component: Restrict delivery to one explicit receiver, in
            "package/class" form, e.g. "com.example.app/.MyReceiver" (`-n`).
            A relative class name (starting with ".") is resolved against
            the package. Omit to let any registered receiver match.
        package: Restrict delivery to receivers declared by one package
            (`-p`). Can be combined with component, though component alone
            already implies a package.
        user_id: Send the broadcast as one specific Android user (`--user`,
            see list_users). Omit to use am's default user.
        receiver_permission: Require receivers to hold this permission to
            receive the broadcast, e.g. "com.example.MY_PERMISSION"
            (`--receiver-permission`). Omit to require no permission.
        extras: Simple scalar Intent extras to attach (`--es`/`--ei`/`--el`/
            `--ef`/`--ez`). Array, URI, and component-name extras aren't
            supported.

    Returns:
        The broadcast's completion info: the serial/action/component/
        package/user_id/receiver_permission sent, the parsed result_code
        (and result_data/result_extras when a receiver set them), and the
        raw am output.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error. A malformed component string (not "package/class" shape)
        raises COMPONENT_NOT_FOUND; a protected action the caller isn't
        allowed to send raises PERMISSION_DENIED; any other ActivityManager
        failure raises a generic BACKEND_ERROR. A well-formed component or
        package that simply doesn't match any installed receiver is NOT an
        error — Android resolves receivers at delivery time, so that case
        completes normally with result_code=0.

    Example:
        Called with serial="emulator-5554",
        action="android.intent.action.MY_ACTION". A typical response:

        ```json
        {
          "status": "success",
          "message": "Broadcast 'android.intent.action.MY_ACTION' completed on emulator-5554 (result=0).",
          "data": {
            "serial": "emulator-5554",
            "action": "android.intent.action.MY_ACTION",
            "component": null,
            "package": null,
            "user_id": null,
            "receiver_permission": null,
            "result_code": 0,
            "result_data": null,
            "result_extras": null,
            "output": "Broadcasting: Intent { act=android.intent.action.MY_ACTION }\\nBroadcast completed: result=0\\n"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    broadcasts = cast(BroadcastsService, services["broadcasts"])
    return await broadcasts.send_broadcast(
        serial,
        action,
        component=component,
        package=package,
        user_id=user_id,
        receiver_permission=receiver_permission,
        extras=extras,
    )
