"""Module-level, statically-introspectable tool functions for the activities module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.activities.service import ActivitiesService, StartActivityResult
from adb_mcp.registry import category


@category("write")
async def start_activity(
    ctx: Context,
    serial: str,
    component: str,
    user_id: int | None = None,
    display_id: int | None = None,
    wait_for_launch: bool = False,
) -> StartActivityResult:
    """Launch an Android activity on a device: `adb shell am start`.

    Models the launch target semantically (an explicit component) rather
    than accepting a raw `am` command string — see the module docs for why
    this server never exposes arbitrary shell arguments. Only an explicit
    component launch is supported so far; other Intent options (action,
    extras, flags, data URI) aren't implemented yet, and this tool never
    starts broadcasts or services (see the broadcasts/android_services
    modules for those).

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        component: The activity to launch, in "package/class" form, e.g.
            "com.example.app/.MainActivity" (`-n`). A relative class name
            (starting with ".") is resolved against the package.
        user_id: Launch the activity as one specific Android user (`--user`,
            see list_users). Omit to use am's default user.
        display_id: Launch the activity on one specific display (`--display`,
            see list_displays). Omit to use the default display.
        wait_for_launch: Wait for the launch to complete and report detailed
            status (`-W`): populates status/launch_state/total_time_ms/
            wait_time_ms/activity. Without it (the default), `am start` is
            fire-and-forget — success=True only means the request wasn't
            immediately rejected, not that the activity finished launching.

    Returns:
        Whether the launch succeeded, the component requested, and — only
        when wait_for_launch=True and available — the ActivityManager-
        confirmed activity and launch timing/status detail. On a launch
        failure that isn't a bad request (success=False), error_type/
        error_message carry ActivityManager's own error text.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error. A malformed component string (not "package/class" shape)
        raises COMPONENT_NOT_FOUND; a protected activity the caller isn't
        allowed to start raises PERMISSION_DENIED; any other ActivityManager
        transport failure raises a generic BACKEND_ERROR. A well-formed
        component that ActivityManager can't resolve or launch (e.g. a class
        that doesn't exist) is NOT a tool error — it's a normal response with
        success=False and error_type/error_message populated, since that's a
        genuine launch outcome rather than a bad call.

    Example:
        Called with serial="emulator-5554",
        component="com.example.app/.MainActivity". A typical response:

        ```json
        {
          "status": "success",
          "message": "Launched com.example.app/.MainActivity on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "component": "com.example.app/.MainActivity",
            "user_id": null,
            "display_id": null,
            "wait_for_launch": false,
            "success": true,
            "activity": null,
            "status": null,
            "launch_state": null,
            "total_time_ms": null,
            "wait_time_ms": null,
            "error_type": null,
            "error_message": null,
            "output": "Starting: Intent { cmp=com.example.app/.MainActivity }\\n"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    activities = cast(ActivitiesService, services["activities"])
    return await activities.start_activity(
        serial,
        component,
        user_id=user_id,
        display_id=display_id,
        wait_for_launch=wait_for_launch,
    )
