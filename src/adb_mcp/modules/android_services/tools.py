"""Module-level, statically-introspectable tool functions for the
android_services module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.android_services.service import AndroidServicesService, StartServiceResult
from adb_mcp.registry import category


@category("write")
async def start_service(
    ctx: Context, serial: str, component: str, user_id: int | None = None
) -> StartServiceResult:
    """Start an Android service on a device: `adb shell am start-service`.

    Models the target semantically (an explicit component) rather than
    accepting a raw `am` command string — see the module docs for why this
    server never exposes arbitrary shell arguments. Only a plain
    (non-foreground) service start is supported so far — foreground-service
    starts, and stopping/querying a service's status, aren't implemented
    yet (see the activities/broadcasts modules for launching activities or
    sending broadcasts instead).

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        component: The service to start, in "package/class" form, e.g.
            "com.example.app/.MyService" (`-n`). A relative class name
            (starting with ".") is resolved against the package.
        user_id: Start the service as one specific Android user (`--user`,
            see list_users). Omit to use am's default user.

    Returns:
        The serial, component, and user_id the service was started with,
        plus the raw am output. Only returned on success — see Error
        handling below for how each failure kind is distinguished.

    Error handling:
        Unlike most tools here, `am start-service` resolves synchronously to
        one of several distinct outcomes, each raised as its own tool error
        rather than returned as success:false data: a malformed component
        string (not "package/class" shape) or a well-formed component that
        doesn't match any declared service both raise COMPONENT_NOT_FOUND; a
        service requiring a permission the caller doesn't hold raises
        PERMISSION_DENIED; Android 8+'s background-service-start limits (the
        caller tried to start a service while the app is in the background)
        raise BACKGROUND_SERVICE_RESTRICTED; an unresponsive adb binary or
        unknown serial raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE; any other
        ActivityManager/adb failure raises a generic BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554",
        component="com.example.app/.MyService". A typical response:

        ```json
        {
          "status": "success",
          "message": "Started service com.example.app/.MyService on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "component": "com.example.app/.MyService",
            "user_id": null,
            "output": "Starting service: Intent { cmp=com.example.app/.MyService }\\n"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    android_services = cast(AndroidServicesService, services["android_services"])
    return await android_services.start_service(serial, component, user_id=user_id)
