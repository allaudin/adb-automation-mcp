"""Domain logic for the debugging module: recent process-exit history for a
package (`adb shell dumpsys activity exit-info <package>`).

ActivityManager keeps a bounded `ApplicationExitInfo` ring per package. This
parses those "ApplicationExitInfo #N:" blocks into typed records (reason,
timestamp, pid, importance, pss/rss, whether a trace was captured) so an
agent can explain why an app died without reading the dump. No records is a
valid empty result.
"""

from __future__ import annotations

import re
import shlex

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)

_BLOCK_SPLIT_RE = re.compile(r"ApplicationExitInfo #\d+:")
_TIMESTAMP_RE = re.compile(r"timestamp=(?P<v>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)")
_PID_RE = re.compile(r"\bpid=(\d+)")
_REAL_UID_RE = re.compile(r"\brealUid=(\d+)")
_USER_RE = re.compile(r"\buser=(\d+)")
_PROCESS_RE = re.compile(r"\bprocess=(\S+)")
_REASON_RE = re.compile(r"\breason=(\d+)\s+\((?P<label>.*)\)\s+subreason=(?P<sub>\d+)")
_SUBREASON_LABEL_RE = re.compile(r"\bsubreason=\d+\s+\((?P<label>.*)\)\s+status=")
_STATUS_RE = re.compile(r"\bstatus=(-?\d+)")
_IMPORTANCE_RE = re.compile(r"\bimportance=(-?\d+)")
_PSS_RE = re.compile(r"\bpss=(\S+)")
_RSS_RE = re.compile(r"\brss=(\S+)")
_STATE_RE = re.compile(r"\bstate=(\S+)")
_TRACE_RE = re.compile(r"\btrace=(\S+)")
_DESCRIPTION_RE = re.compile(r"^\s*description=(?P<v>.*?)\s*$", re.MULTILINE)


class ProcessExitRecord(BaseModel):
    """One `ApplicationExitInfo` record.

    reason_code / reason are ActivityManager's numeric reason and its label
    (e.g. 4 / "APP CRASH(EXCEPTION)", 6 / "LOW MEMORY", 2 / "SIGNALED"). pss
    and rss are the raw strings the dump reports ("0.00", "167MB").
    trace_available is True when a tombstone/ANR trace path was recorded (not
    the trace itself). has_anr_info is True when the record carried an
    anrInfo block.
    """

    timestamp: str
    pid: int | None
    real_uid: int | None
    user: int | None
    process: str | None
    reason_code: int | None
    reason: str | None
    subreason_code: int | None
    subreason: str | None
    status: int | None
    importance: int | None
    pss: str | None
    rss: str | None
    state: str | None
    description: str | None
    trace_available: bool
    has_anr_info: bool


class ProcessExitHistory(BaseModel):
    """Recent process-exit records for one package
    (`adb shell dumpsys activity exit-info <package>`), newest first.

    An empty records list is a normal result — the package has no retained
    exit history (never crashed/exited, or its records aged out of the
    bounded ring).
    """

    serial: str
    package: str
    count: int
    records: list[ProcessExitRecord]

    def summary(self) -> str:
        if not self.count:
            return f"No process-exit history for {self.package} on {self.serial}."
        newest = self.records[0]
        noun = "record" if self.count == 1 else "records"
        return (
            f"{self.count} exit {noun} for {self.package} on {self.serial} "
            f"(newest: {newest.reason or 'unknown'} at {newest.timestamp})."
        )


class DebuggingService:
    """Reads process-exit history from a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def get_process_exit_history(self, serial: str, package: str) -> ProcessExitHistory:
        if not package.strip():
            raise InvalidArgumentError(
                "package must be a non-empty package name.", details={"package": package}
            )
        result = await self._backend.shell(
            serial, f"dumpsys activity exit-info {shlex.quote(package)}"
        )
        _raise_for_shell_failure(serial, result)
        records = _parse_exit_records(result.stdout)
        return ProcessExitHistory(
            serial=serial, package=package, count=len(records), records=records
        )


def _int_or_none(match: re.Match[str] | None) -> int | None:
    return int(match.group(1)) if match else None


def _parse_exit_records(text: str) -> list[ProcessExitRecord]:
    parts = _BLOCK_SPLIT_RE.split(text)
    records: list[ProcessExitRecord] = []
    for block in parts[1:]:  # parts[0] is the preamble before the first block
        ts = _TIMESTAMP_RE.search(block)
        if ts is None:
            continue
        reason = _REASON_RE.search(block)
        sub_label = _SUBREASON_LABEL_RE.search(block)
        trace = _TRACE_RE.search(block)
        desc = _DESCRIPTION_RE.search(block)
        pss = _PSS_RE.search(block)
        rss = _RSS_RE.search(block)
        state = _STATE_RE.search(block)
        process = _PROCESS_RE.search(block)
        description = desc.group("v") if desc else None
        records.append(
            ProcessExitRecord(
                timestamp=ts.group("v"),
                pid=_int_or_none(_PID_RE.search(block)),
                real_uid=_int_or_none(_REAL_UID_RE.search(block)),
                user=_int_or_none(_USER_RE.search(block)),
                process=process.group(1) if process else None,
                reason_code=int(reason.group(1)) if reason else None,
                reason=reason.group("label") if reason else None,
                subreason_code=int(reason.group("sub")) if reason else None,
                subreason=sub_label.group("label") if sub_label else None,
                status=_int_or_none(_STATUS_RE.search(block)),
                importance=_int_or_none(_IMPORTANCE_RE.search(block)),
                pss=pss.group(1) if pss else None,
                rss=rss.group(1) if rss else None,
                state=state.group(1) if state else None,
                description=None if description in (None, "null") else description,
                trace_available=trace is not None and trace.group(1) != "null",
                has_anr_info="anrInfo=" in block and "anrInfo=null" not in block,
            )
        )
    return records


def _raise_for_shell_failure(serial: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})
