"""Module-level, statically-introspectable tool functions for the profiling module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.profiling.service import (
    MethodProfileResult,
    MethodProfileSession,
    ProfilingService,
)
from adb_automation_mcp.registry import category


@category("write")
async def start_method_profile(
    ctx: Context,
    serial: str,
    package: str,
    sampling_interval_us: int | None = None,
    streaming: bool = False,
    user_id: int | None = None,
) -> MethodProfileSession:
    """Start Android method profiling for a process: `adb shell am profile
    start`.

    Begins a profile that records into a device-side `.trace` file. Call
    stop_method_profile (with the same package) to finalize it and pull the
    artifact — the device path is derived from the package, so you don't
    pass it. By default this is the instrumented (every-call) profiler; pass
    sampling_interval_us for the lower-overhead sampling profiler, or
    streaming for the streaming profiler (mutually exclusive with sampling).
    Starting a profile produces no artifact.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package: The process to profile — a package name or a numeric PID as
            a string. Must be running and debuggable/profileable.
        sampling_interval_us: Use the sampling profiler at this interval in
            microseconds (1–1000000). Omit for the instrumented profiler.
        streaming: Use the streaming profiler (`--streaming`). Cannot be
            combined with sampling_interval_us.
        user_id: Profile the process for a specific Android user (`--user`).
            Omit for the current user.

    Returns:
        The serial, package, device_trace_path (where the profiler is
        writing), the sampling_interval_us / streaming / user_id in effect,
        and started (always true when this returns without error).

    Error handling:
        A blank package, an out-of-range sampling_interval_us, a negative
        user_id, or sampling+streaming together raises INVALID_ARGUMENT
        before anything runs. An unknown serial raises DEVICE_NOT_FOUND. A
        process that can't be profiled (not debuggable/profileable) raises
        PERMISSION_DENIED. Any other `am profile` failure raises
        BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", package="com.example.app",
        sampling_interval_us=1000. A typical response:

        ```json
        {
          "status": "success",
          "message": "Started sampling every 1000us method profile of com.example.app on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "package": "com.example.app",
            "device_trace_path": "/data/local/tmp/adb_automation_mcp_methodprofile_com.example.app.trace",
            "sampling_interval_us": 1000,
            "streaming": false,
            "user_id": null,
            "started": true
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    profiling = cast(ProfilingService, services["profiling"])
    return await profiling.start_method_profile(
        serial,
        package,
        sampling_interval_us=sampling_interval_us,
        streaming=streaming,
        user_id=user_id,
    )


@category("write")
async def stop_method_profile(
    ctx: Context, serial: str, package: str, local_path: str, user_id: int | None = None
) -> MethodProfileResult:
    """Stop method profiling and save the trace to the host: `adb shell am
    profile stop` + `adb pull`.

    Finalizes the profile started by start_method_profile for the same
    package, pulls the `.trace` into
    `<ADB_AUTOMATION_LOCAL_ROOT>/profiles/`, and deletes the device file (on
    success and on failure). The trace bytes are not embedded in the
    response — only the saved path and size.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package: The process that was being profiled — must match the
            start_method_profile call.
        local_path: Destination path relative to the server's local_root
            `profiles/` directory, e.g. "app.trace" or "run1/app.trace".
            Must resolve inside local_root.
        user_id: The Android user the profile was started for (`--user`).
            Omit for the current user.

    Returns:
        The serial, package, local_path (the absolute host path the trace
        was written to), and size_bytes.

    Error handling:
        A blank package raises INVALID_ARGUMENT. No configured local_root,
        or a local_path escaping it, raises POLICY_DENIED. An unknown serial
        raises DEVICE_NOT_FOUND. If no profile was active (nothing to pull)
        the call raises REMOTE_FILE_NOT_FOUND. A failed pull raises
        BACKEND_ERROR. The device trace file is cleaned up in every case.

    Example:
        Called with serial="emulator-5554", package="com.example.app",
        local_path="app.trace". A typical response:

        ```json
        {
          "status": "success",
          "message": "Saved method profile of com.example.app from emulator-5554 to /data/out/profiles/app.trace.",
          "data": {
            "serial": "emulator-5554",
            "package": "com.example.app",
            "local_path": "/data/out/profiles/app.trace",
            "size_bytes": 94901,
            "success": true
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    profiling = cast(ProfilingService, services["profiling"])
    return await profiling.stop_method_profile(serial, package, local_path, user_id=user_id)
