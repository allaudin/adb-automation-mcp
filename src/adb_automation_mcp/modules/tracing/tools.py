"""Module-level, statically-introspectable tool functions for the tracing module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import Literal, cast

from fastmcp import Context

from adb_automation_mcp.modules.tracing.service import SystemTraceResult, TracingService
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
