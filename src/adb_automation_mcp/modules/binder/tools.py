"""Module-level, statically-introspectable tool functions for the binder module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.binder.service import (
    BinderCallStats,
    BinderService,
    ResetBinderCallStatsResult,
)
from adb_automation_mcp.registry import category


@category("read")
async def get_binder_call_stats(ctx: Context, serial: str, limit: int = 20) -> BinderCallStats:
    """Get Binder IPC call statistics: `adb shell dumpsys binder_calls_stats`.

    Returns the sampling interval, the "Summary:" totals (total CPU time,
    call count, average per-call CPU), a bounded list of the top per-UID
    callers, and the "Exceptions thrown" tally. The large raw per-call rows
    are never returned. Binder-call-stats collection is often off by default
    — when it is, collecting is false and the totals are zero (a normal
    state, not an error); reset_binder_call_stats and drive a workload
    first.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        limit: Maximum number of top-caller rows to return, 1-200
            (default 20).

    Returns:
        The serial; collecting (whether stats are accumulating);
        start_time; sampling_interval_ms; total_cpu_time_micros;
        calls_count; avg_call_cpu_time_micros (null when the dump said
        "NaN"); top_callers (who / cpu_time_micros / percent_of_total /
        recorded_call_count / call_count); and exceptions (class_name /
        count).

    Error handling:
        A limit outside 1-200 raises INVALID_ARGUMENT before anything runs.
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A permission rejection raises
        PERMISSION_DENIED; any other non-zero exit raises BACKEND_ERROR.
        Empty / not-collecting stats are returned as data, not raised.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "emulator-5554: 722 binder calls, 201512us CPU, 2 top callers.",
          "data": {
            "serial": "emulator-5554",
            "collecting": true,
            "start_time": "2026-09-07 07:48:14",
            "sampling_interval_ms": 1000,
            "total_cpu_time_micros": 201512,
            "calls_count": 722,
            "avg_call_cpu_time_micros": 279,
            "top_callers": [
              {"who": "com.android.systemui/10141", "cpu_time_micros": 123456, "percent_of_total": 61.2, "recorded_call_count": 40, "call_count": 512}
            ],
            "exceptions": [{"class_name": "java.lang.SecurityException", "count": 3}]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    binder = cast(BinderService, services["binder"])
    return await binder.get_binder_call_stats(serial, limit=limit)


@category("write")
async def reset_binder_call_stats(ctx: Context, serial: str) -> ResetBinderCallStatsResult:
    """Reset Binder IPC call statistics: `adb shell dumpsys
    binder_calls_stats --reset`.

    Zeroes the Binder-call-stats counters so a subsequent
    get_binder_call_stats measures only the flow you run in between.
    Categorized `write` as a measurement-state mutation (it does not change
    device behavior).

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial and reset (always true when this returns without error).

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A permission rejection raises
        PERMISSION_DENIED; any other non-zero exit raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "Reset binder call stats on emulator-5554.",
          "data": {"serial": "emulator-5554", "reset": true},
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    binder = cast(BinderService, services["binder"])
    return await binder.reset_binder_call_stats(serial)
