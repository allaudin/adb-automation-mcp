"""Module-level, statically-introspectable tool functions for the activities module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.activities.service import (
    ActivitiesService,
    ResolvedActivity,
    StartActivityResult,
)
from adb_automation_mcp.registry import category


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


@category("read")
async def resolve_activity(
    ctx: Context,
    serial: str,
    action: str | None = None,
    data_uri: str | None = None,
    mime_type: str | None = None,
    categories: list[str] | None = None,
    component: str | None = None,
    package_name: str | None = None,
    user_id: int | None = None,
) -> ResolvedActivity:
    """Resolve which Activity would handle an Intent, without launching it: `cmd package resolve-activity`.

    The safe way to find out what `start_activity` (or the system) would pick
    for a given Intent — nothing is started. Describe the Intent with the typed
    fields below (at least one is required); they map to the same `-a`/`-d`/
    `-t`/`-c`/`-n`/`-p` options Android's own tooling uses.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        action: Intent action, e.g. "android.intent.action.VIEW" (`-a`).
        data_uri: Intent data URI, e.g. "https://example.com" (`-d`).
        mime_type: Explicit MIME type, e.g. "text/plain" (`-t`).
        categories: Intent categories, e.g. ["android.intent.category.HOME"]
            (`-c`, repeatable).
        component: An explicit "package/class" component to resolve (`-n`) —
            resolution still confirms it exists and is enabled.
        package_name: Constrain resolution to one package (`-p`).
        user_id: Resolve as one Android user (`--user`, see list_users).

    Returns:
        resolved (False for the normal "no activity handles this" outcome, not
        an error), and when resolved: component ("package/class"), its
        package_name and activity_class, is_default (whether the winner is a
        registered default handler vs. the system resolver), the match hex, and
        priority.

    Error handling:
        Specifying no Intent fields at all, or a negative user_id, raises
        INVALID_ARGUMENT before any adb call. A malformed component string
        (not "package/class" shape) also raises INVALID_ARGUMENT — Android's
        Intent parser rejects it. An unknown serial raises DEVICE_NOT_FOUND;
        an unreachable adb binary raises ADB_UNAVAILABLE. A build whose
        `resolve-activity` lacks an option used here raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554",
        action="android.intent.action.MAIN",
        categories=["android.intent.category.HOME"]. A typical response:

        ```json
        {
          "status": "success",
          "message": "com.android.car.carlauncher/.CarLauncher resolves that intent on emulator-5554 (default).",
          "data": {
            "serial": "emulator-5554",
            "resolved": true,
            "component": "com.android.car.carlauncher/.CarLauncher",
            "package_name": "com.android.car.carlauncher",
            "activity_class": ".CarLauncher",
            "is_default": true,
            "match": "0x108000",
            "priority": 0
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    activities = cast(ActivitiesService, services["activities"])
    return await activities.resolve_activity(
        serial,
        action=action,
        data_uri=data_uri,
        mime_type=mime_type,
        categories=categories,
        component=component,
        package_name=package_name,
        user_id=user_id,
    )
