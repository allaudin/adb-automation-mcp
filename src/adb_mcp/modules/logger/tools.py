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
    LogSessionHandle,
    LogSessionResult,
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


@category("write")
async def start_log_session(
    ctx: Context,
    serial: str,
    name: str,
    buffer: LogBuffer = "main",
    min_priority: LogPriority | None = None,
    tag: str | None = None,
    pid: int | None = None,
    package: str | None = None,
) -> LogSessionHandle:
    """Start a log-capture session: anchors on the device's current log
    position, to be replayed later by stop_log_session.

    Not a live tail — this doesn't stream logs anywhere while the session is
    open. It records where the buffer currently is (plus whatever filter is
    given here), and stop_log_session later dumps everything matching that
    filter from that point to when it's called. See stop_log_session for how
    the captured logs actually reach a file. Filtering is configured here,
    not at stop time, so this API shape would still work if session capture
    ever became a true live background tail (whose filter flags have to be
    fixed when the process starts, not changed mid-stream) — a checkpoint-
    and-dump session's filter is applied at replay time either way, so the
    two are equivalent for now, but only one of them stays correct if that
    changes later.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        name: A human-readable label for this session (e.g. "wifi_repro") —
            purely for your own tracking across concurrent sessions; not
            interpreted by adb or validated for uniqueness.
        buffer: Which ring buffer to anchor on and later capture from.
        min_priority: Minimum priority to include at stop time. None means no
            filter (everything). Same semantics as read_logs's min_priority.
        tag: If set, only this tag (at min_priority or above) is captured and
            every other tag is silenced. Same semantics as read_logs's tag.
        pid: If set, only this process's logs are captured. Mutually
            exclusive with package — set at most one.
        package: If set, resolves to that package's PID the same way
            read_package_logs does (exact match via `pidof -s`, must be
            currently running) and captures only that process's logs.
            Mutually exclusive with pid.

    Returns:
        A session_id to pass to stop_log_session, plus the serial, buffer,
        name, and (if pid or package was given) the pid that will be
        filtered on.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error. Passing both pid and package is a tool error (ambiguous),
        not success:false data. package resolution can fail the same way
        read_package_logs's does: no running process for that package is a
        tool error, not a session that silently captures nothing. An empty
        buffer at start time is not an error — the session is still created;
        stop_log_session captures whatever's present at stop-time instead of
        filtering by timestamp.

    Example:
        Called with serial="emulator-5554", name="wifi_repro", tag="WifiManager".
        A typical response:

        ```json
        {
          "status": "success",
          "message": "Started log session 'wifi_repro' (3fa1f2b0-...) on main@emulator-5554.",
          "data": {
            "session_id": "3fa1f2b0-...",
            "serial": "emulator-5554",
            "buffer": "main",
            "name": "wifi_repro",
            "pid": null,
            "package": null
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    logger_service = cast(LoggerService, services["logger"])
    return await logger_service.start_log_session(
        serial, name, buffer=buffer, min_priority=min_priority, tag=tag, pid=pid, package=package
    )


@category("write")
async def stop_log_session(ctx: Context, session_id: str, local_path: str) -> LogSessionResult:
    """Stop a log-capture session and write everything logged since
    start_log_session to a file on the host running this server.

    local_path is a host filesystem path, not a device path — it's resolved
    against the server's configured local_root and must stay inside it (see
    Error handling). The captured text depends on the device's ring buffer
    not having wrapped past the session's start point — fine for a normal
    debugging session, not a hard guarantee for a very long or very
    high-volume one.

    Args:
        session_id: The id returned by start_log_session.
        local_path: Where to write the captured log text, relative to (or,
            if absolute, still required to resolve inside) the server's
            configured local_root.

    Returns:
        The session_id, serial, buffer, name, pid/package (if the session was
        filtered by one), the resolved local_path actually written, how many
        lines were captured, and the session's duration in seconds.

    Error handling:
        session_id must refer to a session that's still open — an unknown or
        already-stopped id is a tool error, not success:false data. Sessions
        are held in memory only, for the server process's lifetime; they
        don't expire on their own. local_path is checked before any device
        round-trip: if the server has no local_root configured at all, or
        local_path resolves outside it (including via ".." or an absolute
        path elsewhere on the host), the call is refused rather than writing
        anywhere — there is no default local_root; an operator must set
        ADB_MCP_LOCAL_ROOT explicitly. Beyond that, this propagates the same
        way most tools do: adb being unreachable or the session's serial no
        longer being connected surfaces as an actual tool error.

    Example:
        Called with session_id="3fa1f2b0-...", local_path="session1.log". A
        typical response:

        ```json
        {
          "status": "success",
          "message": "Wrote 148 log line(s) from session 'wifi_repro' (3fa1f2b0-...) to /var/adb-logs/session1.log.",
          "data": {
            "session_id": "3fa1f2b0-...",
            "serial": "emulator-5554",
            "buffer": "main",
            "name": "wifi_repro",
            "pid": null,
            "package": null,
            "local_path": "/var/adb-logs/session1.log",
            "line_count": 148,
            "duration_s": 42.7
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    logger_service = cast(LoggerService, services["logger"])
    return await logger_service.stop_log_session(session_id, local_path)
