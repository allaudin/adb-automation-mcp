"""Module-level, statically-introspectable tool functions for the tracing module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import Literal, cast

from fastmcp import Context

from adb_automation_mcp.modules.tracing.service import (
    IpcTraceResult,
    IpcTraceSession,
    SystemTraceResult,
    TracingService,
)
from adb_automation_mcp.registry import category

TracePreset = Literal["cpu", "scheduling", "graphics", "app_startup", "memory", "binder"]


@category("write")
async def capture_system_trace(
    ctx: Context,
    serial: str,
    preset: TracePreset,
    local_path: str,
    duration_seconds: int = 10,
    package: str | None = None,
) -> SystemTraceResult:
    """Capture a bounded Perfetto system trace: `adb shell perfetto ...` +
    `adb pull`.

    v1 exposes semantic presets rather than a raw Perfetto config. Each
    preset maps to a curated set of scheduler / atrace categories:
    `cpu`, `scheduling`, `graphics`, `app_startup`, `memory`, `binder`.
    The trace runs for duration_seconds (1-120), is pulled into
    `<ADB_AUTOMATION_LOCAL_ROOT>/traces/`, and the device-side file is
    deleted afterwards (on success and on failure). The trace bytes are not
    embedded in the response — only the saved path and sizes.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        preset: The trace preset — one of "cpu", "scheduling", "graphics",
            "app_startup", "memory", "binder".
        local_path: Destination path relative to the server's local_root
            `traces/` directory, e.g. "startup.perfetto-trace" or
            "run1/cpu.perfetto-trace". Must resolve inside local_root.
        duration_seconds: How long to trace, 1-120 seconds (default 10).
        package: Optional app package to scope app-level (atrace) events to.
            Omit for a system-wide trace.

    Returns:
        The serial; the preset / duration_seconds / package requested;
        local_path (the absolute host path the trace was written to);
        device_bytes (what perfetto reported writing on the device, or
        null); and size_bytes (the pulled file size, or null).

    Error handling:
        An unknown preset, a duration outside 1-120, or a blank package
        raises INVALID_ARGUMENT before anything runs. No configured
        local_root, or a local_path escaping it, raises POLICY_DENIED. An
        unknown serial raises DEVICE_NOT_FOUND. A device without perfetto
        raises TRACING_UNAVAILABLE. A perfetto permission rejection raises
        PERMISSION_DENIED; a failed pull raises
        REMOTE_FILE_NOT_FOUND / BACKEND_ERROR. The device trace file is
        cleaned up in every case.

    Example:
        Called with serial="emulator-5554", preset="app_startup",
        duration_seconds=10, package="com.example.app",
        local_path="startup.perfetto-trace". A typical response:

        ```json
        {
          "status": "success",
          "message": "Captured a 10s 'app_startup' trace (com.example.app) from emulator-5554 to /data/out/traces/startup.perfetto-trace.",
          "data": {
            "serial": "emulator-5554",
            "preset": "app_startup",
            "duration_seconds": 10,
            "package": "com.example.app",
            "local_path": "/data/out/traces/startup.perfetto-trace",
            "device_bytes": 84260,
            "size_bytes": 84260,
            "success": true
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    tracing = cast(TracingService, services["tracing"])
    return await tracing.capture_system_trace(
        serial, preset, local_path, duration_seconds=duration_seconds, package=package
    )


@category("write")
async def start_ipc_trace(ctx: Context, serial: str) -> IpcTraceSession:
    """Start ActivityManager Binder/IPC transaction tracing: `adb shell am
    trace-ipc start`.

    Begins recording Binder transactions system-wide. This produces no
    artifact on its own — call stop_ipc_trace to dump the collected
    transactions and pull them to the host. Starting when a session is
    already running is harmless; `am` doesn't report that case, so this
    always reports tracing=true on success.

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial and tracing (always true on success).

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A permission rejection raises
        PERMISSION_DENIED; any other failure (including a build without IPC
        tracing) raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "Started IPC transaction tracing on emulator-5554.",
          "data": {"serial": "emulator-5554", "tracing": true},
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    tracing = cast(TracingService, services["tracing"])
    return await tracing.start_ipc_trace(serial)


@category("write")
async def stop_ipc_trace(ctx: Context, serial: str, local_path: str) -> IpcTraceResult:
    """Stop IPC tracing, dump it, and save it to the host: `adb shell am
    trace-ipc stop --dump-file <dev>` + `adb pull`.

    Stops the session started by start_ipc_trace, writes the Binder
    transaction dump to a device temp file, pulls it into
    `<ADB_AUTOMATION_LOCAL_ROOT>/ipc_traces/`, and deletes the device file
    (on success and on failure). The trace text is not embedded in the
    response — only the saved path and size.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        local_path: Destination path relative to the server's local_root
            `ipc_traces/` directory, e.g. "ipc.txt" or "run1/ipc.txt". Must
            resolve inside local_root.

    Returns:
        The serial, local_path (the absolute host path the trace was written
        to), and size_bytes.

    Error handling:
        No configured local_root, or a local_path escaping it, raises
        POLICY_DENIED. An unknown serial raises DEVICE_NOT_FOUND. Stopping
        with no active trace, or a failed dump/pull, raises
        REMOTE_FILE_NOT_FOUND / BACKEND_ERROR. The device temp file is
        cleaned up in every case.

    Example:
        Called with serial="emulator-5554", local_path="ipc.txt". A typical
        response:

        ```json
        {
          "status": "success",
          "message": "Saved IPC transaction trace from emulator-5554 to /data/out/ipc_traces/ipc.txt.",
          "data": {
            "serial": "emulator-5554",
            "local_path": "/data/out/ipc_traces/ipc.txt",
            "size_bytes": 6570,
            "success": true
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    tracing = cast(TracingService, services["tracing"])
    return await tracing.stop_ipc_trace(serial, local_path)
