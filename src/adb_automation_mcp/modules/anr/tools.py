"""Module-level, statically-introspectable tool functions for the anr module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.anr.service import AnrReportList, AnrService
from adb_automation_mcp.registry import category


@category("read")
async def get_anr_reports(
    ctx: Context,
    serial: str,
    package_name: str,
    limit: int = 5,
    include_traces: bool = True,
) -> AnrReportList:
    """Get a package's ANR reports from the device's DropBox
    (`adb shell dumpsys dropbox --print data_app_anr`, and again for
    `system_app_anr`).

    DropBox is the system store `DropBoxManagerService` keeps for crash / ANR
    records (the same source `adb bugreport` and `DropBoxManager` read).
    `dumpsys dropbox --print` accepts one tag at a time, so this queries both
    ANR tags, parses each entry's header block and body, and returns the ones
    whose recorded process/package matches package_name, newest first. No
    root required. Reading only — DropBox isn't modified.

    DropBox is size-capped and rotates, so ANRs older than roughly the last
    day or the last few hundred records may already have aged out; an empty
    result means "none currently in DropBox", not "this app never ANR'd".

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package_name: The package whose ANRs to fetch, e.g.
            "com.example.app". Matched against each entry's Process:/Package:
            header.
        limit: Maximum number of reports to return, newest first, 1-50
            (default 5).
        include_traces: When true (default) each report carries its full
            trace body (thread dumps, CPU usage), capped in length. Set
            false to get just the headers and subject line — much smaller
            responses when you only need to know that/when ANRs happened.

    Returns:
        The serial, package_name, count, and reports — each with tag
        ("data_app_anr" / "system_app_anr"), timestamp (device-local,
        verbatim), process, package, pid, uid, flags, subject (the "ANR in
        ..." line when present), size_bytes, and trace (null when
        include_traces is false). An empty reports list is a normal result.

    Error handling:
        A blank package_name or an out-of-range limit raises
        INVALID_ARGUMENT before anything runs. An unknown serial or
        unresponsive adb binary raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A
        permission rejection raises PERMISSION_DENIED; any other non-zero
        exit raises BACKEND_ERROR. "(No entries found.)" is a normal empty
        result, not an error.

    Example:
        Called with serial="emulator-5554", package_name="com.example.app",
        include_traces=false. A typical response:

        ```json
        {
          "status": "success",
          "message": "1 ANR report for com.example.app on emulator-5554 (newest 2026-09-06 16:52:25).",
          "data": {
            "serial": "emulator-5554",
            "package_name": "com.example.app",
            "count": 1,
            "reports": [
              {
                "tag": "data_app_anr",
                "timestamp": "2026-09-06 16:52:25",
                "process": "com.example.app",
                "package": "com.example.app",
                "pid": 12345,
                "uid": 10234,
                "flags": "0x30c8be45",
                "subject": "ANR in com.example.app (com.example.app/.MainActivity)",
                "size_bytes": 40219,
                "trace": null
              }
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    anr = cast(AnrService, services["anr"])
    return await anr.get_anr_reports(
        serial, package_name, limit=limit, include_traces=include_traces
    )
