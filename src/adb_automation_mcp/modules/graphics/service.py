"""Domain logic for the graphics module: rendering / jank frame statistics
for an app (`adb shell dumpsys gfxinfo <package> framestats` and `... reset`).

get_frame_stats parses only gfxinfo's stable per-process summary block
(totals, jank, latency percentiles, the "Number <x>:" counters, and
optionally the frame-time HISTOGRAM). The large `---PROFILEDATA---` per-frame
CSV that `framestats` also emits is deliberately not parsed or returned.
reset_frame_stats zeroes the counters before a measured flow.
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
    PackageNotRunningError,
    PermissionDeniedError,
)

_NOT_RUNNING_MARKER = "No process found for:"
_PID_HEADER_RE = re.compile(r"\*\*\s*Graphics info for pid\s+(?P<pid>\d+)\s+\[(?P<name>[^\]]+)\]")
_STATS_SINCE_RE = re.compile(r"^Stats since:\s*(\d+)ns", re.MULTILINE)
_TOTAL_FRAMES_RE = re.compile(r"^Total frames rendered:\s*(\d+)", re.MULTILINE)
_JANKY_RE = re.compile(r"^Janky frames:\s*(\d+)\s*\(([\d.]+)%\)", re.MULTILINE)
_JANKY_LEGACY_RE = re.compile(r"^Janky frames \(legacy\):\s*(\d+)\s*\(([\d.]+)%\)", re.MULTILINE)
_PERCENTILE_RE = re.compile(r"^(\d+)th percentile:\s*(\d+)ms", re.MULTILINE)
_NUMBER_RE = re.compile(r"^Number ([A-Za-z][\w ()]*?):\s*(\d+)\s*$", re.MULTILINE)
_HISTOGRAM_RE = re.compile(r"^HISTOGRAM:\s*(?P<body>.+)$", re.MULTILINE)
_HISTOGRAM_BUCKET_RE = re.compile(r"(\d+)ms=(\d+)")


class FrameStats(BaseModel):
    """Rendering / jank statistics for one app (`adb shell dumpsys gfxinfo
    <package> framestats`).

    Percentiles are frame render times in milliseconds. counters holds the
    "Number <x>:" lines (missed_vsync, high_input_latency, slow_ui_thread,
    ...). histogram is the frame-time bucket map ("<ms>" -> frame count) and
    is null unless include_histogram was set. The raw per-frame CSV is never
    returned.
    """

    serial: str
    package: str
    pid: int | None
    process_name: str | None
    stats_since_ns: int | None
    total_frames_rendered: int | None
    janky_frames: int | None
    janky_percent: float | None
    janky_frames_legacy: int | None
    janky_percent_legacy: float | None
    p50_ms: int | None
    p90_ms: int | None
    p95_ms: int | None
    p99_ms: int | None
    counters: dict[str, int]
    histogram: dict[str, int] | None

    def summary(self) -> str:
        frames = self.total_frames_rendered
        if frames is None:
            return f"gfxinfo for {self.package} on {self.serial} (no frame totals)."
        jank = f", {self.janky_frames} janky ({self.janky_percent}%)" if self.janky_frames else ""
        return f"{self.package} on {self.serial}: {frames} frames rendered{jank}."


class ResetFrameStatsResult(BaseModel):
    """Confirmation that `adb shell dumpsys gfxinfo <package> reset` ran.

    gfxinfo's reset produces only a (re-dumped) textual blob, so this is a
    minimal structured acknowledgement — reset is read from the command's
    exit code.
    """

    serial: str
    package: str
    reset: bool

    def summary(self) -> str:
        return f"Reset frame stats for {self.package} on {self.serial}."


class GraphicsService:
    """Reads and resets an app's graphics frame statistics."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def get_frame_stats(
        self, serial: str, package: str, include_histogram: bool = False
    ) -> FrameStats:
        _require_non_blank(package)
        result = await self._backend.shell(
            serial, f"dumpsys gfxinfo {shlex.quote(package)} framestats"
        )
        _raise_for_shell_failure(serial, result)
        text = result.stdout
        if _NOT_RUNNING_MARKER in text:
            raise PackageNotRunningError(
                f"No running process found for '{package}' on {serial}.",
                details={"serial": serial, "package": package},
            )

        pid_match = _PID_HEADER_RE.search(text)
        janky = _JANKY_RE.search(text)
        janky_legacy = _JANKY_LEGACY_RE.search(text)
        percentiles = {int(p): int(v) for p, v in _PERCENTILE_RE.findall(text)}
        counters = {
            _counter_key(name): int(value) for name, value in _NUMBER_RE.findall(text)
        }
        histogram: dict[str, int] | None = None
        if include_histogram:
            hist_match = _HISTOGRAM_RE.search(text)
            if hist_match:
                histogram = {
                    f"{ms}ms": int(count)
                    for ms, count in _HISTOGRAM_BUCKET_RE.findall(hist_match.group("body"))
                }

        stats_since = _STATS_SINCE_RE.search(text)
        total_frames = _TOTAL_FRAMES_RE.search(text)
        return FrameStats(
            serial=serial,
            package=package,
            pid=int(pid_match.group("pid")) if pid_match else None,
            process_name=pid_match.group("name") if pid_match else None,
            stats_since_ns=int(stats_since.group(1)) if stats_since else None,
            total_frames_rendered=int(total_frames.group(1)) if total_frames else None,
            janky_frames=int(janky.group(1)) if janky else None,
            janky_percent=float(janky.group(2)) if janky else None,
            janky_frames_legacy=int(janky_legacy.group(1)) if janky_legacy else None,
            janky_percent_legacy=float(janky_legacy.group(2)) if janky_legacy else None,
            p50_ms=percentiles.get(50),
            p90_ms=percentiles.get(90),
            p95_ms=percentiles.get(95),
            p99_ms=percentiles.get(99),
            counters=counters,
            histogram=histogram,
        )

    async def reset_frame_stats(self, serial: str, package: str) -> ResetFrameStatsResult:
        _require_non_blank(package)
        result = await self._backend.shell(
            serial, f"dumpsys gfxinfo {shlex.quote(package)} reset"
        )
        _raise_for_shell_failure(serial, result)
        if _NOT_RUNNING_MARKER in result.stdout:
            raise PackageNotRunningError(
                f"No running process found for '{package}' on {serial}.",
                details={"serial": serial, "package": package},
            )
        return ResetFrameStatsResult(serial=serial, package=package, reset=True)


def _require_non_blank(package: str) -> None:
    if not package.strip():
        raise InvalidArgumentError(
            "package must be a non-empty package name.", details={"package": package}
        )


def _counter_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def _raise_for_shell_failure(serial: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})
