"""Domain logic for the binder module: Binder IPC call statistics
(`adb shell dumpsys binder_calls_stats` and `... --reset`).

`binder_calls_stats` output is large and its collection is configuration-
dependent (often off by default). get_binder_call_stats returns the header
(sampling interval), the "Summary:" totals, a bounded list of the top
per-UID callers, and the "Exceptions thrown" tally — never the raw
per-call rows. reset_binder_call_stats zeroes the counters before a
measured flow.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)

_START_TIME_RE = re.compile(r"^Start time:\s*(?P<v>.+?)\s*$", re.MULTILINE)
_INTERVAL_RE = re.compile(r"^Sampling interval period:\s*(\d+)", re.MULTILINE)
_SUMMARY_RE = re.compile(
    r"Summary:\s*total_cpu_time=(?P<cpu>\d+),\s*calls_count=(?P<calls>\d+),"
    r"\s*avg_call_cpu_time=(?P<avg>\S+)"
)
# "      123456      61.2%      40      512  com.android.systemui/10141"
_CALLER_RE = re.compile(
    r"^\s*(?P<cpu>\d+)\s+(?P<pct>[\d.]+)%\s+(?P<recorded>\d+)\s+(?P<calls>\d+)\s+(?P<who>\S+)\s*$"
)
_EXCEPTION_RE = re.compile(r"^\s*(?P<count>\d+)\s+(?P<cls>[\w.$]+)\s*$")
_CALLERS_HEADER = "Per-UID Summary"
_EXCEPTIONS_HEADER = "Exceptions thrown"


class BinderCaller(BaseModel):
    """One row of the "Per-UID Summary" — a package/uid and its Binder CPU
    cost over the sampling window.
    """

    who: str
    cpu_time_micros: int
    percent_of_total: float
    recorded_call_count: int
    call_count: int


class BinderException(BaseModel):
    """One line of the "Exceptions thrown" tally."""

    class_name: str
    count: int


class BinderCallStats(BaseModel):
    """Binder IPC call statistics (`adb shell dumpsys binder_calls_stats`).

    collecting is False when the device isn't currently accumulating stats
    (calls_count is 0) — a normal state, not an error; call
    reset_binder_call_stats and drive a workload first. sampling_interval_ms
    is how often the tracker samples. top_callers is bounded to `limit`
    rows; exceptions is the "Exceptions thrown" tally. avg_call_cpu_time_micros
    is None when the dump reported "NaN".
    """

    serial: str
    collecting: bool
    start_time: str | None
    sampling_interval_ms: int | None
    total_cpu_time_micros: int | None
    calls_count: int | None
    avg_call_cpu_time_micros: int | None
    top_callers: list[BinderCaller]
    exceptions: list[BinderException]

    def summary(self) -> str:
        if not self.collecting:
            return f"Binder call stats on {self.serial} are not currently collecting."
        return (
            f"{self.serial}: {self.calls_count} binder calls, "
            f"{self.total_cpu_time_micros}us CPU, {len(self.top_callers)} top callers."
        )


class ResetBinderCallStatsResult(BaseModel):
    """Confirmation that `adb shell dumpsys binder_calls_stats --reset` ran."""

    serial: str
    reset: bool

    def summary(self) -> str:
        return f"Reset binder call stats on {self.serial}."


class BinderService:
    """Reads and resets Binder IPC call statistics."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def get_binder_call_stats(self, serial: str, limit: int = 20) -> BinderCallStats:
        if not 1 <= limit <= 200:
            raise InvalidArgumentError(
                "limit must be between 1 and 200.", details={"serial": serial, "limit": limit}
            )
        result = await self._backend.shell(serial, "dumpsys binder_calls_stats")
        _raise_for_shell_failure(serial, result)
        text = result.stdout

        start = _START_TIME_RE.search(text)
        interval = _INTERVAL_RE.search(text)
        summary = _SUMMARY_RE.search(text)
        calls_count = int(summary.group("calls")) if summary else None
        avg_raw = summary.group("avg") if summary else None
        try:
            avg = int(float(avg_raw)) if avg_raw not in (None, "NaN") else None
        except ValueError:
            avg = None

        return BinderCallStats(
            serial=serial,
            collecting=bool(calls_count),
            start_time=start.group("v") if start else None,
            sampling_interval_ms=int(interval.group(1)) if interval else None,
            total_cpu_time_micros=int(summary.group("cpu")) if summary else None,
            calls_count=calls_count,
            avg_call_cpu_time_micros=avg,
            top_callers=_parse_callers(text, limit),
            exceptions=_parse_exceptions(text),
        )

    async def reset_binder_call_stats(self, serial: str) -> ResetBinderCallStatsResult:
        result = await self._backend.shell(serial, "dumpsys binder_calls_stats --reset")
        _raise_for_shell_failure(serial, result)
        return ResetBinderCallStatsResult(serial=serial, reset=True)


def _parse_callers(text: str, limit: int) -> list[BinderCaller]:
    lines = text.splitlines()
    callers: list[BinderCaller] = []
    capturing = False
    for line in lines:
        if line.startswith(_CALLERS_HEADER):
            capturing = True
            continue
        if not capturing:
            continue
        if not line.strip():
            if callers:
                break
            continue
        m = _CALLER_RE.match(line)
        if m is None:
            break
        callers.append(
            BinderCaller(
                who=m.group("who"),
                cpu_time_micros=int(m.group("cpu")),
                percent_of_total=float(m.group("pct")),
                recorded_call_count=int(m.group("recorded")),
                call_count=int(m.group("calls")),
            )
        )
        if len(callers) >= limit:
            break
    return callers


def _parse_exceptions(text: str) -> list[BinderException]:
    lines = text.splitlines()
    out: list[BinderException] = []
    capturing = False
    for line in lines:
        if line.startswith(_EXCEPTIONS_HEADER):
            capturing = True
            continue
        if not capturing:
            continue
        if not line.strip() or line.lstrip().startswith("/!\\"):
            break
        m = _EXCEPTION_RE.match(line)
        if m is None:
            continue
        out.append(BinderException(class_name=m.group("cls"), count=int(m.group("count"))))
    return out


def _raise_for_shell_failure(serial: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})
