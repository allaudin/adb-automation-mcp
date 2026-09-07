"""Module-level, statically-introspectable tool functions for the processes module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.processes.service import (
    ForceStopResult,
    KillBackgroundResult,
    ProcessesService,
    ProcessIds,
    ProcessList,
    ProcessMemory,
)
from adb_automation_mcp.registry import category


@category("write")
async def force_stop_app(
    ctx: Context, serial: str, package_name: str, user_id: int | None = None
) -> ForceStopResult:
    """Force-stop an Android package on a device: `adb shell am force-stop`.

    Stops every process and component of the package, if any are running,
    and marks the package "stopped" until something explicitly launches it
    again. This is the heavy hammer — for a gentler, background-only kill
    that leaves package state alone, see kill_background_processes. Not a
    per-process kill: it operates on a package, not a single pid, which is
    why it isn't named kill_app.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package_name: The package to force-stop, e.g. "com.example.app".
        user_id: Force-stop the package for one specific Android user
            (`--user`, see list_users). Omit to stop it for every user.

    Returns:
        The serial, package_name, and user_id the force-stop was issued for,
        plus the raw (usually empty) am output. `am force-stop` normally
        produces no stdout at all on success — success is determined from
        the command's exit code, not from output content.

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A blank package_name raises
        INVALID_ARGUMENT before anything runs. A rejection due to the caller
        lacking FORCE_STOP_PACKAGES raises PERMISSION_DENIED (unusual over
        adb shell, which is granted this by default). Any other
        ActivityManager/adb failure raises a generic BACKEND_ERROR. A
        package_name that doesn't correspond to any installed app is NOT an
        error — forceStopPackage() doesn't validate that the package exists;
        it's a silent no-op when there's nothing to stop.

    Example:
        Called with serial="emulator-5554", package_name="com.example.app".
        A typical response:

        ```json
        {
          "status": "success",
          "message": "Force-stopped com.example.app on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "package_name": "com.example.app",
            "user_id": null,
            "output": ""
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    processes = cast(ProcessesService, services["processes"])
    return await processes.force_stop_app(serial, package_name, user_id=user_id)


@category("write")
async def kill_background_processes(
    ctx: Context, serial: str, package_name: str, user_id: int | None = None
) -> KillBackgroundResult:
    """Kill a package's killable background processes: `adb shell am kill`.

    Semantically distinct from force_stop_app: ActivityManager kills only
    the package's processes it currently considers safe to reclaim
    (cached/background) and leaves a foreground process alone, and it does
    not set the package's "stopped" flag. Use this to simulate the system
    reclaiming memory from a backgrounded app without fully tearing its
    package state down.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package_name: The package whose background processes to kill, e.g.
            "com.example.app".
        user_id: Restrict the kill to one Android user (`--user`, see
            list_users). Omit to apply it across users.

    Returns:
        The serial, package_name, and user_id the kill was issued for, plus
        am's raw (normally empty) output. Success is read from the exit
        code, not output content.

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A blank package_name raises
        INVALID_ARGUMENT before anything runs. A permission rejection raises
        PERMISSION_DENIED; any other non-zero exit raises BACKEND_ERROR. A
        package with nothing killable — not installed, or currently in the
        foreground — is NOT an error: `am kill` is a silent no-op there.

    Example:
        Called with serial="emulator-5554", package_name="com.example.app".
        A typical response:

        ```json
        {
          "status": "success",
          "message": "Requested background-process kill of com.example.app on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "package_name": "com.example.app",
            "user_id": null,
            "output": ""
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    processes = cast(ProcessesService, services["processes"])
    return await processes.kill_background_processes(serial, package_name, user_id=user_id)


@category("read")
async def list_processes(
    ctx: Context, serial: str, name_filter: str | None = None
) -> ProcessList:
    """List running processes on a device: `adb shell ps`.

    Runs `ps` with a fixed column set (PID, PPID, USER, RSS, NAME) and
    parses it into structured rows — no raw `ps` flags are exposed. Pass
    name_filter to keep only processes whose name contains that substring
    (matched on the device-reported process name, server-side), which is the
    usual way to find every process belonging to an app.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        name_filter: Optional case-sensitive substring; only processes whose
            name contains it are returned. Omit to return every process.

    Returns:
        The serial, the name_filter that was applied (or null), and a list
        of processes, each with pid, ppid, user, rss_kb (resident size in
        KB), and name. An empty list is a valid result when a filter matched
        nothing.

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A blank name_filter (given but
        empty/whitespace) raises INVALID_ARGUMENT before anything runs. A
        permission rejection raises PERMISSION_DENIED; any other non-zero
        exit raises BACKEND_ERROR. Unparseable `ps` lines are skipped rather
        than raising.

    Example:
        Called with serial="emulator-5554", name_filter="systemui". A
        typical response:

        ```json
        {
          "status": "success",
          "message": "1 process matching 'systemui' on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "name_filter": "systemui",
            "processes": [
              {
                "pid": 1224,
                "ppid": 432,
                "user": "u0_a141",
                "rss_kb": 260040,
                "name": "com.android.systemui"
              }
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    processes = cast(ProcessesService, services["processes"])
    return await processes.list_processes(serial, name_filter=name_filter)


@category("read")
async def get_process_id(ctx: Context, serial: str, name: str) -> ProcessIds:
    """Resolve a process/package name to its PIDs: `adb shell pidof`.

    Returns a list because one name can back several processes (an app with
    multiple `android:process` entries). A name with nothing running is a
    normal result (running=false, empty list), not an error — `pidof`
    can't distinguish "not installed" from "installed but not running", so
    neither does this.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        name: The process or package name to look up, e.g.
            "com.android.systemui" or "system_server".

    Returns:
        The serial, the name queried, pids (a list of integers, possibly
        empty), and running (true when at least one PID was found).

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A blank name raises
        INVALID_ARGUMENT before anything runs. Any non-zero exit that
        carries actual error output raises BACKEND_ERROR; a bare non-zero
        exit with no output is treated as "not running", not a failure.

    Example:
        Called with serial="emulator-5554", name="com.android.systemui". A
        typical response:

        ```json
        {
          "status": "success",
          "message": "'com.android.systemui' on emulator-5554: pid 1224.",
          "data": {
            "serial": "emulator-5554",
            "name": "com.android.systemui",
            "pids": [1224],
            "running": true
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    processes = cast(ProcessesService, services["processes"])
    return await processes.get_process_id(serial, name)


@category("read")
async def get_process_memory(ctx: Context, serial: str, target: str) -> ProcessMemory:
    """Read a curated memory snapshot for a process: `adb shell dumpsys
    meminfo -s`.

    Runs meminfo in summary mode and extracts only its stable "App Summary"
    Pss categories and the "TOTAL PSS / RSS / SWAP" line — the volatile
    per-mapping detail is dropped. All values are kilobyte integers exactly
    as meminfo reports them; no unit conversion is applied.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        target: A package name (e.g. "com.android.systemui") or a numeric
            PID as a string (e.g. "1224") to measure.

    Returns:
        The serial and the target queried; pid and process_name from
        meminfo's header; the per-category Pss values (java_heap_pss_kb,
        native_heap_pss_kb, code_pss_kb, stack_pss_kb, graphics_pss_kb,
        private_other_pss_kb, system_pss_kb), each null if that row was
        absent; and total_pss_kb / total_rss_kb / total_swap_kb (null on
        older builds that don't print the TOTAL line).

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A blank target raises
        INVALID_ARGUMENT before anything runs. A target with no running
        process ("No process found for: ...") raises PACKAGE_NOT_RUNNING.
        meminfo running but producing output with neither a recognizable
        header nor a TOTAL line raises PROCESS_MEMORY_UNAVAILABLE. A
        permission rejection raises PERMISSION_DENIED; any other non-zero
        exit raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", target="com.android.systemui".
        A typical response:

        ```json
        {
          "status": "success",
          "message": "com.android.systemui on emulator-5554: 105321 KB total PSS.",
          "data": {
            "serial": "emulator-5554",
            "target": "com.android.systemui",
            "pid": 1224,
            "process_name": "com.android.systemui",
            "java_heap_pss_kb": 28048,
            "native_heap_pss_kb": 21120,
            "code_pss_kb": 37168,
            "stack_pss_kb": 1632,
            "graphics_pss_kb": 0,
            "private_other_pss_kb": 4008,
            "system_pss_kb": 13345,
            "total_pss_kb": 105321,
            "total_rss_kb": 268416,
            "total_swap_kb": 0
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    processes = cast(ProcessesService, services["processes"])
    return await processes.get_process_memory(serial, target)
