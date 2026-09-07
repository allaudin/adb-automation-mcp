"""Domain logic for the anr module: retrieving Application Not Responding
(ANR) reports for a package from the device's DropBox
(`adb shell dumpsys dropbox --print data_app_anr system_app_anr`).

DropBox is the system-wide store `DropBoxManagerService` keeps for crash /
ANR / WTF / StrictMode records; `adb bugreport` and the `DropBoxManager`
public API read from the same place. ANR entries are tagged `data_app_anr`
(installed apps) or `system_app_anr` (system / privileged apps). `dumpsys
dropbox --print <tag>` takes exactly one tag, so this queries both in turn
and merges the results; each call writes one `====`-delimited entry per
record — a timestamp/tag header line, a block of `Key: value` headers
(Process, PID, Flags, Package, ...), then the full body (the `Subject:`
"Input dispatching timed out ..." line, `/proc/pressure`, per-process thread
dumps). That text is parsed in Python (no shell `grep`); entries are then
filtered to the requested package by their `Process:` / `Package:` header.

Sources: `adb shell dumpsys dropbox --help`; AOSP
`frameworks/base/services/core/java/com/android/server/DropBoxManagerService.java`.
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

# The ANR DropBox tags this tool reads. `system_server_anr` is deliberately
# excluded — those are system_server watchdog ANRs, not attributable to an
# app package.
_ANR_TAGS = ("data_app_anr", "system_app_anr")

_MIN_LIMIT = 1
_MAX_LIMIT = 50
_TRACE_CAP = 20_000

# A run of '=' on its own line separates DropBox entries in `--print` output.
_DELIMITER_RE = re.compile(r"^=+\s*$")

# First line of an entry, e.g.
# "2026-09-06 16:52:25 data_app_anr (text, 40219 bytes)"
_ENTRY_HEADER_RE = re.compile(
    r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<tag>\S+)\s+\((?P<kind>[^,]+),\s*(?P<bytes>\d+)\s*bytes\)\s*$"
)

_SUBJECT_RE = re.compile(r"^Subject:\s*(?P<subject>.+?)\s*$", re.MULTILINE)


class AnrReport(BaseModel):
    """One ANR record from the device's DropBox.

    timestamp is the device-local time DropBox recorded, verbatim
    ("YYYY-MM-DD HH:MM:SS"). process / package / pid / uid / flags come from
    the entry's header block; subject is the "Subject:" line from the body
    when present (e.g. "ANR in com.example.app (com.example.app/.MainActivity)").
    size_bytes is DropBox's reported entry size. trace is the full report
    body (thread dumps, CPU usage, ...), capped in length; it is null when
    the caller asked not to include traces.
    """

    tag: str
    timestamp: str
    process: str | None
    package: str | None
    pid: int | None
    uid: int | None
    flags: str | None
    subject: str | None
    size_bytes: int | None
    trace: str | None


class AnrReportList(BaseModel):
    """ANR reports for one package, newest first (`adb shell dumpsys dropbox
    --print data_app_anr system_app_anr`).

    An empty reports list means DropBox holds no ANR entries for this
    package — a normal result, not an error (DropBox is capped and rotates,
    so old ANRs age out).
    """

    serial: str
    package_name: str
    count: int
    reports: list[AnrReport]

    def summary(self) -> str:
        if not self.count:
            return f"No ANR reports for {self.package_name} on {self.serial}."
        noun = "report" if self.count == 1 else "reports"
        newest = self.reports[0].timestamp
        return (
            f"{self.count} ANR {noun} for {self.package_name} on {self.serial} "
            f"(newest {newest})."
        )


class AnrService:
    """Reads ANR reports out of the device's DropBox."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def get_anr_reports(
        self,
        serial: str,
        package_name: str,
        limit: int = 5,
        include_traces: bool = True,
    ) -> AnrReportList:
        if not package_name.strip():
            raise InvalidArgumentError(
                "package_name must be a non-empty package name.",
                details={"serial": serial},
            )
        if not _MIN_LIMIT <= limit <= _MAX_LIMIT:
            raise InvalidArgumentError(
                f"limit must be between {_MIN_LIMIT} and {_MAX_LIMIT}.",
                details={"serial": serial, "limit": limit},
            )

        # `dumpsys dropbox --print` accepts a single tag, so query each ANR tag.
        entries: list[AnrReport] = []
        for tag in _ANR_TAGS:
            result = await self._backend.shell(serial, f"dumpsys dropbox --print {tag}")
            _raise_for_dropbox_failure(serial, result)
            entries.extend(_parse_dropbox_entries(result.stdout))

        matched = [
            e
            for e in entries
            if e.tag.endswith("_anr")
            and (e.process == package_name or e.package == package_name)
        ]
        # DropBox prints oldest-first per tag; sort the merged list newest-first.
        # Timestamps are fixed-width "YYYY-MM-DD HH:MM:SS", so string order works.
        matched.sort(key=lambda e: e.timestamp, reverse=True)
        matched = matched[:limit]
        if not include_traces:
            matched = [e.model_copy(update={"trace": None}) for e in matched]

        return AnrReportList(
            serial=serial,
            package_name=package_name,
            count=len(matched),
            reports=matched,
        )


def _raise_for_dropbox_failure(serial: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell dumpsys dropbox exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})


def _parse_dropbox_entries(output: str) -> list[AnrReport]:
    """Split `dumpsys dropbox --print` output into entries.

    Everything before the first `====` delimiter is DropBox's own preamble
    ("Drop box contents:", "Searching for:", "(No entries found.)") and is
    ignored. A chunk whose first non-blank line isn't a recognizable entry
    header is skipped rather than raising.
    """
    chunks: list[list[str]] = []
    current: list[str] | None = None
    for line in output.splitlines():
        if _DELIMITER_RE.match(line):
            current = []
            chunks.append(current)
            continue
        if current is not None:
            current.append(line)

    reports: list[AnrReport] = []
    for chunk in chunks:
        report = _parse_entry(chunk)
        if report is not None:
            reports.append(report)
    return reports


def _parse_entry(lines: list[str]) -> AnrReport | None:
    idx = 0
    while idx < len(lines) and not lines[idx].strip():
        idx += 1
    if idx >= len(lines):
        return None
    header_match = _ENTRY_HEADER_RE.match(lines[idx].strip())
    if header_match is None:
        return None
    idx += 1

    headers: dict[str, str] = {}
    while idx < len(lines) and lines[idx].strip():
        key, sep, value = lines[idx].partition(":")
        if sep:
            headers[key.strip()] = value.strip()
        idx += 1

    body = "\n".join(lines[idx:]).strip()
    subject_match = _SUBJECT_RE.search(body)

    return AnrReport(
        tag=header_match.group("tag"),
        timestamp=header_match.group("timestamp"),
        process=headers.get("Process") or None,
        package=_package_name(headers.get("Package")),
        pid=_int_or_none(headers.get("PID")),
        uid=_int_or_none(headers.get("UID")),
        flags=headers.get("Flags") or None,
        subject=subject_match.group("subject") if subject_match else None,
        size_bytes=int(header_match.group("bytes")),
        trace=_capped(body) if body else None,
    )


def _package_name(raw: str | None) -> str | None:
    # "Package:" header looks like "com.example.app v123 (1.2.3)".
    if not raw:
        return None
    return raw.split()[0] or None


def _int_or_none(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        return int(raw.strip())
    except ValueError:
        return None


def _capped(text: str) -> str:
    if len(text) <= _TRACE_CAP:
        return text
    return text[:_TRACE_CAP] + "\n...[trace truncated]"
