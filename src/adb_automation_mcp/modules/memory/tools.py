"""Module-level, statically-introspectable tool functions for the memory module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.memory.service import (
    AppMemoryDetails,
    AppMemorySummary,
    HeapDumpResult,
    MemoryHistory,
    MemoryService,
    SystemMemorySummary,
)
from adb_automation_mcp.registry import category


@category("read")
async def get_app_memory_summary(ctx: Context, serial: str, target: str) -> AppMemorySummary:
    """Compact memory snapshot for one app/process: `adb shell dumpsys meminfo -s`.

    Parses only the stable "App Summary" totals (Java/Native heap, Code,
    Stack, Graphics, Private Other, System, and TOTAL PSS/RSS/SWAP), all in
    kilobytes. For the full per-mapping / object / SQL breakdown use
    get_app_memory_details.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        target: A package name (e.g. "com.android.systemui") or a numeric
            PID as a string.

    Returns:
        The serial and target queried; pid / process_name from meminfo's
        header; and the App Summary Pss category fields plus total_pss_kb /
        total_rss_kb / total_swap_kb. Any field the build didn't emit is null.

    Error handling:
        A blank target raises INVALID_ARGUMENT before anything runs. An
        unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A target with no running process
        ("No process found for: ...") raises PACKAGE_NOT_RUNNING. Output
        with no recognizable header or TOTAL line raises
        MEMORY_INFO_UNAVAILABLE. A permission rejection raises
        PERMISSION_DENIED; any other non-zero exit raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", target="com.android.systemui".
        A typical response:

        ```json
        {
          "status": "success",
          "message": "com.android.systemui on emulator-5554: 104328 KB total PSS.",
          "data": {
            "serial": "emulator-5554",
            "target": "com.android.systemui",
            "pid": 1224,
            "process_name": "com.android.systemui",
            "java_heap_pss_kb": 25324,
            "native_heap_pss_kb": 21748,
            "code_pss_kb": 37816,
            "stack_pss_kb": 1656,
            "graphics_pss_kb": 0,
            "private_other_pss_kb": 4280,
            "system_pss_kb": 13504,
            "total_pss_kb": 104328,
            "total_rss_kb": 264948,
            "total_swap_kb": 8
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    memory = cast(MemoryService, services["memory"])
    return await memory.get_app_memory_summary(serial, target)


@category("read")
async def get_app_memory_details(ctx: Context, serial: str, target: str) -> AppMemoryDetails:
    """Detailed memory breakdown for one app: `adb shell dumpsys meminfo -a`.

    Returns the App Summary totals plus the per-mapping table (categories:
    "Native Heap", "Dalvik Heap", ".so mmap", ... "TOTAL"), the "Objects"
    section (view / binder / parcel / WebView counts) and the "SQL" section.
    Sections vary by Android version, so objects and sql come back as maps
    and are empty when absent. The raw dump text is never exposed.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        target: A package name or a numeric PID as a string.

    Returns:
        The serial / target / pid / process_name; the App Summary total
        fields; categories (a list of per-mapping rows with pss/private/
        shared/rss/heap columns in KB, columns a build omits are null);
        objects (name -> count); and sql (name -> value).

    Error handling:
        Same as get_app_memory_summary: INVALID_ARGUMENT for a blank
        target, PACKAGE_NOT_RUNNING when nothing is running, and
        MEMORY_INFO_UNAVAILABLE when no memory sections are recognizable;
        DEVICE_NOT_FOUND / PERMISSION_DENIED / BACKEND_ERROR otherwise.

    Example:
        Called with serial="emulator-5554", target="com.android.systemui".
        A typical (trimmed) response:

        ```json
        {
          "status": "success",
          "message": "com.android.systemui on emulator-5554: 16 memory categories, 12 object counts.",
          "data": {
            "serial": "emulator-5554",
            "target": "com.android.systemui",
            "pid": 1224,
            "process_name": "com.android.systemui",
            "total_pss_kb": 104328,
            "total_rss_kb": 264948,
            "total_swap_kb": 8,
            "categories": [
              {"name": "Native Heap", "pss_total_kb": 21824, "private_dirty_kb": 21748, "rss_total_kb": 25540}
            ],
            "objects": {"views": 855, "activities": 0, "local_binders": 374},
            "sql": {"memory_used": 0, "malloc_size": 0}
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    memory = cast(MemoryService, services["memory"])
    return await memory.get_app_memory_details(serial, target)


@category("read")
async def get_system_memory_summary(ctx: Context, serial: str) -> SystemMemorySummary:
    """System-wide memory totals and top consumers: `adb shell dumpsys meminfo`.

    Reads the RAM totals block (Total / Free / Used / Lost RAM, ZRAM /
    swap) and the "Total PSS by process" list, bounded to the top entries.
    Everything else in the (large) dump is ignored.

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial; total_ram_kb / free_ram_kb / used_ram_kb / lost_ram_kb;
        zram_physical_used_kb / zram_in_swap_kb / zram_total_swap_kb; status
        (the "(status normal)" word); and top_processes (name, pid, user,
        pss_kb), newest-heaviest first, capped. Fields the dump didn't carry
        are null.

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. Output with no recognizable RAM
        totals raises MEMORY_INFO_UNAVAILABLE. A permission rejection raises
        PERMISSION_DENIED; any other non-zero exit raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554". A typical (trimmed) response:

        ```json
        {
          "status": "success",
          "message": "emulator-5554: 4007632 KB total RAM, 2516255 KB free, 15 top procs.",
          "data": {
            "serial": "emulator-5554",
            "total_ram_kb": 4007632,
            "free_ram_kb": 2516255,
            "used_ram_kb": 1406266,
            "lost_ram_kb": 95527,
            "zram_physical_used_kb": 15404,
            "zram_in_swap_kb": 19880,
            "zram_total_swap_kb": 3005720,
            "status": "status normal",
            "top_processes": [
              {"name": "system", "pid": 729, "user": null, "pss_kb": 266973}
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    memory = cast(MemoryService, services["memory"])
    return await memory.get_system_memory_summary(serial)


@category("read")
async def get_memory_history(
    ctx: Context, serial: str, package: str, hours: int = 3
) -> MemoryHistory:
    """Historical memory bands for a package: `adb shell dumpsys procstats
    --hours <hours> <package>`.

    Reads procstats' "Process summary" min/avg/max PSS/USS/RSS bands per
    process state ("TOTAL", "Top", "Persistent", ...) accumulated over the
    requested window. procstats samples lazily, so a package that hasn't
    been sampled in the window returns has_history=false — a normal result,
    not an error.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package: The package to look up, e.g. "com.example.app".
        hours: The look-back window, 1-72 hours (default 3).

    Returns:
        The serial / package / hours; has_history; window_start (procstats'
        aggregation start time); and bands — one entry per process state,
        each with percent, samples, and pss/uss/rss min/avg/max in
        kilobytes (fields procstats didn't report are null).

    Error handling:
        A blank package or an hours value outside 1-72 raises
        INVALID_ARGUMENT before anything runs. An unknown serial or
        unresponsive adb binary raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A
        permission rejection raises PERMISSION_DENIED; any other non-zero
        exit raises BACKEND_ERROR. No accumulated history is
        has_history=false, not an error.

    Example:
        Called with serial="emulator-5554", package="com.android.systemui",
        hours=3. A typical response:

        ```json
        {
          "status": "success",
          "message": "com.android.systemui on emulator-5554: 2 memory band(s) over the last 3h.",
          "data": {
            "serial": "emulator-5554",
            "package": "com.android.systemui",
            "hours": 3,
            "has_history": true,
            "window_start": "2026-09-07 07:48:12",
            "bands": [
              {
                "state": "TOTAL",
                "percent": 100.0,
                "samples": 8,
                "pss_min_kb": 0,
                "pss_avg_kb": 63488,
                "pss_max_kb": 105472,
                "uss_min_kb": 0,
                "uss_avg_kb": 55296,
                "uss_max_kb": 92160,
                "rss_min_kb": 268288,
                "rss_avg_kb": 264192,
                "rss_max_kb": 268288
              }
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    memory = cast(MemoryService, services["memory"])
    return await memory.get_memory_history(serial, package, hours=hours)


@category("write")
async def capture_heap_dump(
    ctx: Context,
    serial: str,
    package: str,
    local_path: str,
    force_gc: bool = False,
    native: bool = False,
    user_id: int | None = None,
    timeout_s: float = 120.0,
) -> HeapDumpResult:
    """Capture a heap dump and save it to the host: `adb shell am dumpheap`
    then `adb pull`.

    Dumps the managed heap (or the native heap with native=true) of a
    running process to a device temp file, pulls it into
    `<ADB_AUTOMATION_LOCAL_ROOT>/heapdumps/`, and deletes the temp file
    (on success and on failure). Categorized `write` because it forces the
    target process to pause and serialize its heap. The .hprof is not
    embedded in the response — only its path and size.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package: The process to dump — a package name or a numeric PID as a
            string. Must be running and debuggable/profileable.
        local_path: Destination path relative to the server's local_root
            `heapdumps/` directory, e.g. "app.hprof" or "run1/app.hprof".
            Must resolve inside local_root.
        force_gc: Pass `-g` to force a GC before dumping (smaller, cleaner
            managed heap).
        native: Pass `-n` to dump the native heap instead of the managed one.
        user_id: Dump the process for a specific Android user (`--user`).
            Omit for the current user.
        timeout_s: How long to wait for the dump to finish, 5-600 seconds
            (default 120). A large heap on a slow device can take a while.

    Returns:
        The serial and package; local_path (the absolute host path the
        .hprof was written to); native / force_gc / user_id echoed; and
        size_bytes (the saved file size, or null if it couldn't be stat'd).

    Error handling:
        A blank package, a negative user_id, or an out-of-range timeout_s
        raises INVALID_ARGUMENT. No configured local_root, or a local_path
        escaping it, raises POLICY_DENIED. An unknown serial raises
        DEVICE_NOT_FOUND. A package that isn't running raises
        PACKAGE_NOT_RUNNING; one that can't be dumped (not debuggable/
        profileable) raises PERMISSION_DENIED. A failed pull raises
        REMOTE_FILE_NOT_FOUND / BACKEND_ERROR. The device temp file is
        cleaned up in every case.

    Example:
        Called with serial="emulator-5554", package="com.android.systemui",
        local_path="systemui.hprof", force_gc=true. A typical response:

        ```json
        {
          "status": "success",
          "message": "Captured managed heap dump of com.android.systemui from emulator-5554 to /data/out/heapdumps/systemui.hprof.",
          "data": {
            "serial": "emulator-5554",
            "package": "com.android.systemui",
            "local_path": "/data/out/heapdumps/systemui.hprof",
            "native": false,
            "force_gc": true,
            "user_id": null,
            "size_bytes": 64329246,
            "success": true
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    memory = cast(MemoryService, services["memory"])
    return await memory.capture_heap_dump(
        serial,
        package,
        local_path,
        force_gc=force_gc,
        native=native,
        user_id=user_id,
        timeout_s=timeout_s,
    )
