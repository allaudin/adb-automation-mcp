"""Module-level, statically-introspectable tool functions for the debugging module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.debugging.service import (
    ClearDebugAppResult,
    DebuggingService,
    JdwpProcessList,
    ProcessExitHistory,
    SetDebugAppResult,
)
from adb_automation_mcp.registry import category


@category("read")
async def get_process_exit_history(
    ctx: Context, serial: str, package: str
) -> ProcessExitHistory:
    """Get a package's recent process-exit records: `adb shell dumpsys
    activity exit-info <package>`.

    ActivityManager keeps a bounded `ApplicationExitInfo` ring per package.
    This parses it into typed records — reason (crash / ANR / low-memory
    kill / self-exit / signalled), timestamp, pid, importance, pss/rss, and
    whether a trace was captured — so an agent can explain why an app died.
    Reading only. A package with no retained history returns an empty list,
    not an error.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package: The package to look up, e.g. "com.example.app".

    Returns:
        The serial / package / count, and records (newest first). Each
        record has timestamp, pid, real_uid, user, process, reason_code +
        reason label, subreason_code + subreason label, status, importance,
        pss and rss (the raw strings the dump reports), state, description,
        trace_available (bool), and has_anr_info (bool). Fields the record
        didn't carry are null.

    Error handling:
        A blank package raises INVALID_ARGUMENT before anything runs. An
        unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A permission rejection raises
        PERMISSION_DENIED; any other non-zero exit raises BACKEND_ERROR. An
        unknown package or one with no history is an empty result, not an
        error.

    Example:
        Called with serial="emulator-5554", package="com.example.app". A
        typical response:

        ```json
        {
          "status": "success",
          "message": "2 exit records for com.example.app on emulator-5554 (newest: APP CRASH(EXCEPTION) at 2026-09-06 22:39:39.266).",
          "data": {
            "serial": "emulator-5554",
            "package": "com.example.app",
            "count": 2,
            "records": [
              {
                "timestamp": "2026-09-06 22:39:39.266",
                "pid": 5486,
                "real_uid": 10234,
                "user": 0,
                "process": "com.example.app",
                "reason_code": 4,
                "reason": "APP CRASH(EXCEPTION)",
                "subreason_code": 0,
                "subreason": "UNKNOWN",
                "status": 0,
                "importance": 400,
                "pss": "0.00",
                "rss": "167MB",
                "state": "empty",
                "description": "crash",
                "trace_available": false,
                "has_anr_info": false
              }
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    debugging = cast(DebuggingService, services["debugging"])
    return await debugging.get_process_exit_history(serial, package)


@category("write")
async def set_debug_app(
    ctx: Context,
    serial: str,
    package: str,
    wait_for_debugger: bool = False,
    persistent: bool = False,
) -> SetDebugAppResult:
    """Mark an app as ActivityManager's debug app: `adb shell am set-debug-app`.

    Records package as the debug app so its next launch is
    debugger-friendly. This does NOT attach a debugger — it only sets the
    marker. With wait_for_debugger the next launch of the app blocks until a
    debugger connects (`-w`); with persistent the setting survives reboot
    (`--persistent`). Pair with clear_debug_app when done.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package: The package to mark, e.g. "com.example.app".
        wait_for_debugger: Block the app's next launch until a debugger
            attaches (`-w`).
        persistent: Keep the setting across reboots (`--persistent`).

    Returns:
        The serial, package, and the wait_for_debugger / persistent flags
        that were applied.

    Error handling:
        A blank package raises INVALID_ARGUMENT before anything runs. An
        unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A permission rejection raises
        PERMISSION_DENIED; any other non-zero exit raises BACKEND_ERROR. An
        unknown package is NOT an error — `am` doesn't validate it.

    Example:
        Called with serial="emulator-5554", package="com.example.app",
        wait_for_debugger=true. A typical response:

        ```json
        {
          "status": "success",
          "message": "Set com.example.app as the debug app on emulator-5554 (waits for debugger on next launch).",
          "data": {
            "serial": "emulator-5554",
            "package": "com.example.app",
            "wait_for_debugger": true,
            "persistent": false
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    debugging = cast(DebuggingService, services["debugging"])
    return await debugging.set_debug_app(
        serial, package, wait_for_debugger=wait_for_debugger, persistent=persistent
    )


@category("write")
async def clear_debug_app(ctx: Context, serial: str) -> ClearDebugAppResult:
    """Clear ActivityManager's configured debug app: `adb shell am
    clear-debug-app`.

    Undoes a previous set_debug_app. Idempotent — calling it when no debug
    app is set is a successful no-op, and `cleared` being true does not
    imply one had been configured.

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial and cleared (always true on success).

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A permission rejection raises
        PERMISSION_DENIED; any other non-zero exit raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "Cleared the debug app on emulator-5554.",
          "data": {"serial": "emulator-5554", "cleared": true},
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    debugging = cast(DebuggingService, services["debugging"])
    return await debugging.clear_debug_app(serial)


@category("read")
async def list_jdwp_processes(ctx: Context, serial: str) -> JdwpProcessList:
    """List processes exposing a JDWP transport: `adb jdwp`.

    Returns the PIDs of the device's debuggable processes that currently
    have a Java Debug Wire Protocol endpoint open — the candidates you can
    attach a debugger or `jdb` to. `adb jdwp` streams and never exits on its
    own, so this returns a snapshot taken after a short settle window.

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial, count, and pids (a list of integers, in first-seen
        order, deduplicated). An empty list is a normal result.

    Error handling:
        An unknown/offline serial raises DEVICE_NOT_FOUND; the adb binary
        being unreachable raises ADB_UNAVAILABLE. Any other non-zero exit
        raises BACKEND_ERROR. Non-numeric lines in the output are ignored.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "3 JDWP-debuggable process(es) on emulator-5554: [1224, 1568, 2411].",
          "data": {"serial": "emulator-5554", "count": 3, "pids": [1224, 1568, 2411]},
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    debugging = cast(DebuggingService, services["debugging"])
    return await debugging.list_jdwp_processes(serial)
