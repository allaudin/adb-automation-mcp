"""Module-level, statically-introspectable tool functions for the
android_services module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.android_services.service import (
    AndroidServicesService,
    ServiceStatus,
    StartForegroundServiceResult,
    StartServiceResult,
    StopServiceResult,
)
from adb_automation_mcp.registry import category


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


@category("write")
async def start_foreground_service(
    ctx: Context, serial: str, component: str, user_id: int | None = None
) -> StartForegroundServiceResult:
    """Start an Android foreground service: `adb shell am start-foreground-service`.

    Separate from start_service because Android's background-execution rules
    differ: a plain start-service from the background is refused on Android 8+,
    while start-foreground-service is allowed but the app must then call
    startForeground() within a few seconds or the system kills it. This tool
    reports only that ActivityManager accepted and dispatched the start — not
    the later startForeground() call.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        component: The service to start, in "package/class" form, e.g.
            "com.example.app/.MyFgService" (`-n`). A relative class name
            (starting with ".") is resolved against the package.
        user_id: Start the service as one specific Android user (`--user`,
            see list_users). Omit to use am's default user.

    Returns:
        The serial, component, and user_id the service was started with, plus
        the raw am output. Only returned on success.

    Error handling:
        An empty component or negative user_id raises INVALID_ARGUMENT before
        any adb call. A malformed component string, or a well-formed component
        that matches no declared service, raises COMPONENT_NOT_FOUND. A service
        requiring a permission the caller doesn't hold raises PERMISSION_DENIED.
        A foreground-service-start restriction raises
        BACKGROUND_SERVICE_RESTRICTED. An unknown serial raises
        DEVICE_NOT_FOUND; an unreachable adb binary raises ADB_UNAVAILABLE; any
        other ActivityManager/adb failure raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554",
        component="com.example.app/.MyFgService". A typical response:

        ```json
        {
          "status": "success",
          "message": "Started foreground service com.example.app/.MyFgService on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "component": "com.example.app/.MyFgService",
            "user_id": null,
            "output": "Starting service: Intent { cmp=com.example.app/.MyFgService }\\n"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    android_services = cast(AndroidServicesService, services["android_services"])
    return await android_services.start_foreground_service(serial, component, user_id=user_id)


@category("write")
async def stop_service(
    ctx: Context, serial: str, component: str, user_id: int | None = None
) -> StopServiceResult:
    """Stop a started Android service: `adb shell am stop-service`.

    The counterpart to start_service — stops a service that was started via
    `am` (or `startService()`). Not an error if the service isn't running; that
    comes back as stopped=false / was_running=false, since the intended end
    state is reached either way.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        component: The service to stop, in "package/class" form, e.g.
            "com.example.app/.MyService" (`-n`). A relative class name
            (starting with ".") is resolved against the package.
        user_id: Stop the service for one specific Android user (`--user`,
            see list_users). Omit to use am's default user.

    Returns:
        The serial, component, user_id, and: stopped (True only when am
        reported "Service stopped"), was_running (False when am reported "was
        not running", None if the outcome wasn't recognized), plus the raw am
        output.

    Error handling:
        An empty component or negative user_id raises INVALID_ARGUMENT before
        any adb call. A malformed component string raises COMPONENT_NOT_FOUND —
        but note `am stop-service` does NOT distinguish an unknown service
        component from a known-but-not-running one, so an unknown component
        comes back as was_running=false, not an error. An unknown serial raises
        DEVICE_NOT_FOUND; an unreachable adb binary raises ADB_UNAVAILABLE; a
        permission denial raises PERMISSION_DENIED; any other am failure raises
        BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554",
        component="com.example.app/.MyService". A typical response:

        ```json
        {
          "status": "success",
          "message": "Stopped service com.example.app/.MyService on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "component": "com.example.app/.MyService",
            "user_id": null,
            "stopped": true,
            "was_running": true,
            "output": "Stopping service: Intent { cmp=com.example.app/.MyService }\\nService stopped\\n"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    android_services = cast(AndroidServicesService, services["android_services"])
    return await android_services.stop_service(serial, component, user_id=user_id)


@category("read")
async def get_service_status(
    ctx: Context, serial: str, component: str
) -> ServiceStatus:
    """Status snapshot for one Android Service: `adb shell dumpsys activity services <component>`.

    The way to verify what start_service / start_foreground_service actually
    did — process/PID, foreground state, start bookkeeping — without parsing
    dumpsys yourself. A Service can be active for more than one Android user at
    once, so instances is a list.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        component: The service to inspect, in "package/class" form, e.g.
            "com.example.app/.MyService" (relative ".Class" is resolved against
            the package).

    Returns:
        running (False with an empty instances list when the service isn't
        active anywhere — a normal result, not an error), and one entry per
        active instance: user_id, pid, process_name, package_name,
        is_foreground / foreground_id, start_requested / last_start_id,
        created_from_fg, and start_foreground_count. Fields this Android
        version's dump omits come back null.

    Error handling:
        An empty component raises INVALID_ARGUMENT before any adb call. An
        unknown serial raises DEVICE_NOT_FOUND; an unreachable adb binary
        raises ADB_UNAVAILABLE. `dumpsys activity services` can't tell a
        stopped service from an unknown or malformed component — all report
        "no services match" — so none of those raise; they come back as
        running=false.

    Example:
        Called with serial="emulator-5554",
        component="com.example.app/.MyFgService". A typical response:

        ```json
        {
          "status": "success",
          "message": "com.example.app/.MyFgService is running on emulator-5554: 2 instance(s), 1 foreground.",
          "data": {
            "serial": "emulator-5554",
            "component": "com.example.app/.MyFgService",
            "running": true,
            "instances": [
              {
                "user_id": 0,
                "pid": 1884,
                "process_name": "com.example.app",
                "package_name": "com.example.app",
                "is_foreground": true,
                "foreground_id": 1,
                "start_requested": true,
                "last_start_id": 2,
                "created_from_fg": false,
                "start_foreground_count": 1
              }
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    android_services = cast(AndroidServicesService, services["android_services"])
    return await android_services.get_service_status(serial, component)
