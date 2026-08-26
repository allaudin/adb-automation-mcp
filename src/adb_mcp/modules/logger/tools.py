"""Module-level, statically-introspectable tool functions for the logger module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.logger.service import (
    ClearLogsResult,
    LogBuffer,
    LogBufferSize,
    LogDump,
    LoggerService,
    LogPriority,
    PackageLogDump,
)
from adb_mcp.registry import category


@category("read")
async def read_logs(
    ctx: Context,
    serial: str,
    buffer: LogBuffer = "main",
    max_lines: int = 200,
    min_priority: LogPriority | None = None,
    tag: str | None = None,
    pid: int | None = None,
) -> LogDump:
    """Dump recent device logs: `adb shell logcat -d -v threadtime -t N -b BUFFER`.

    Dump-and-exit, not a live tail: this returns a snapshot of what's already
    in the buffer, not a stream of future log lines.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        buffer: Which ring buffer to read. "kernel" only exists on
            userdebug/eng builds and "security" only under Device Owner —
            either can legitimately fail on a given device.
        max_lines: How many of the most recent raw lines to read, before any
            tag/priority filter is applied (see Error handling below for why
            that ordering matters). 0 is silently clamped to 1; negative
            values are a real error.
        min_priority: Minimum priority to include ("V" < "D" < "I" < "W" <
            "E" < "F" < "S"=silent). None means no filter (everything).
        tag: If set, show only this tag (at min_priority or above) and
            silence every other tag — verified live this is genuinely
            exclusive, not additive with min_priority's usual "everything at
            this level or above" meaning.
        pid: If set, show only log lines from this process ID.

    Returns:
        The raw logcat text for the requested buffer, plus the serial and
        buffer requested.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error. Verified live that max_lines truncates the RAW buffer
        first, then filters — a narrow tag/priority filter combined with a
        small max_lines can come back with empty output (data, not an error)
        even though matching lines exist further back in the buffer; increase
        max_lines if that happens.

    Example:
        Called with serial="emulator-5554", buffer="main", max_lines=3. A
        typical response:

        ```json
        {
          "status": "success",
          "message": "Read 3 log line(s) from main on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "buffer": "main",
            "output": "--------- beginning of main\\n08-26 08:24:26.364 462 11426 E audio_hw_generic_caremu: mixer_thread_loop error[-1] writing data to pcm\\n..."
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    logger_service = cast(LoggerService, services["logger"])
    return await logger_service.read_logs(
        serial, buffer=buffer, max_lines=max_lines, min_priority=min_priority, tag=tag, pid=pid
    )


@category("write")
async def clear_logs(ctx: Context, serial: str, buffer: LogBuffer = "main") -> ClearLogsResult:
    """Clear a device's log buffer: `adb shell logcat -c -b BUFFER`.

    Pairs with read_logs for the standard debugging workflow: clear, reproduce
    the issue, then read_logs to see only what happened since. Wipes
    diagnostic history, not user/app data, so this is "write" rather than
    "destructive".

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        buffer: Which ring buffer to clear.

    Returns:
        The serial and buffer cleared.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error.

    Example:
        Called with serial="emulator-5554", buffer="main". A typical response:

        ```json
        {
          "status": "success",
          "message": "Cleared main log buffer on emulator-5554.",
          "data": {"serial": "emulator-5554", "buffer": "main"},
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    logger_service = cast(LoggerService, services["logger"])
    return await logger_service.clear_logs(serial, buffer=buffer)


@category("read")
async def get_log_buffer_size(ctx: Context, serial: str, buffer: LogBuffer = "main") -> LogBufferSize:
    """Report a log buffer's ring size and usage: `adb shell logcat -g -b BUFFER`.

    Cheap, read-only introspection — useful before deciding max_lines for
    read_logs, or whether to clear_logs first.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        buffer: Which ring buffer to report on.

    Returns:
        The serial, buffer, and logd's raw size/usage text for it.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error. Verified live that an unknown buffer name (or one this
        device's build doesn't have, e.g. "kernel" on a user build) fails
        with "Unknown -b buffer '<name>'", exit 1.

    Example:
        Called with serial="emulator-5554", buffer="crash". A typical
        response:

        ```json
        {
          "status": "success",
          "message": "Log buffer size for crash on emulator-5554: crash: ring buffer is 2 MiB (512 KiB consumed, 22 KiB readable), max entry is 5120 B, max payload is 4068 B",
          "data": {
            "serial": "emulator-5554",
            "buffer": "crash",
            "output": "crash: ring buffer is 2 MiB (512 KiB consumed, 22 KiB readable), max entry is 5120 B, max payload is 4068 B"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    logger_service = cast(LoggerService, services["logger"])
    return await logger_service.get_log_buffer_size(serial, buffer=buffer)


@category("read")
async def read_package_logs(
    ctx: Context,
    serial: str,
    package: str,
    buffer: LogBuffer = "main",
    max_lines: int = 200,
    min_priority: LogPriority | None = None,
) -> PackageLogDump:
    """Dump recent logs for one package: resolves its PID via `adb shell pidof
    -s PACKAGE`, then `adb shell logcat -d -v threadtime -t N -b BUFFER
    --pid=PID`.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        package: Exact package/process name (e.g. "com.android.systemui") —
            pidof requires an exact match, not a substring.
        buffer: Which ring buffer to read.
        max_lines: How many of the most recent raw lines to read before any
            priority filter and the pid filter are applied. Same
            truncate-then-filter ordering caveat as read_logs.
        min_priority: Minimum priority to include. None means no filter.

    Returns:
        The serial, package, resolved pid, and matching logcat text.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error. Verified live that pidof exits 1 with no output both when
        the package isn't installed and when it's installed but not currently
        running — adb can't tell those apart, so this raises a single
        "no running process for package" error either way rather than
        guessing which. Also verified live that logcat only accepts one
        --pid per call, so a multi-process package (isolated services,
        separate process names) only returns its primary process's logs —
        a known limitation, not a bug.

    Example:
        Called with serial="emulator-5554", package="com.android.systemui".
        A typical response:

        ```json
        {
          "status": "success",
          "message": "Read 4 log line(s) for com.android.systemui (pid 19861) on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "package": "com.android.systemui",
            "pid": 19861,
            "output": "--------- beginning of main\\n08-26 08:24:32.118 19861 19934 D SystemUI: ...\\n..."
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    logger_service = cast(LoggerService, services["logger"])
    return await logger_service.read_package_logs(
        serial, package, buffer=buffer, max_lines=max_lines, min_priority=min_priority
    )
