"""Domain logic for the processes module: force-stopping an Android package
(`adb shell am force-stop`), killing only a package's killable background
processes (`adb shell am kill`), listing running processes (`adb shell ps`),
resolving a name to its PIDs (`adb shell pidof`), and reading a curated
memory snapshot for a process (`adb shell dumpsys meminfo -s`).

`ps` and `dumpsys meminfo` are parsed in Python (no shell `grep`/`awk`):
`ps` is run with a fixed `-o` column set and split positionally; `dumpsys
meminfo` is read in summary mode and only its stable "App Summary" / "TOTAL
PSS" markers are extracted. Killing an individual process by pid isn't
implemented — `am kill` (package-scoped, background-only) is the closest
safe primitive and is what kill_background_processes exposes.
"""

from __future__ import annotations

import shlex

from pydantic import BaseModel

from adb_automation_mcp import meminfo
from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PackageNotRunningError,
    PermissionDeniedError,
    ProcessMemoryUnavailableError,
)


class ForceStopResult(BaseModel):
    """Outcome of force-stopping a package (`adb shell am force-stop`).

    `am force-stop` reaches ActivityManagerService's forceStopPackage(),
    which doesn't validate that the package is actually installed or
    currently running — it forcibly stops every process/component of that
    package if any exist, and is a silent no-op otherwise. So a
    package_name that doesn't correspond to any installed app is NOT an
    error (this call still succeeds), and `am force-stop` normally produces
    no stdout at all on success — see ProcessesService.force_stop_app, which
    determines outcome from the command's exit code, never from output
    content.
    """

    serial: str
    package_name: str
    user_id: int | None
    output: str

    def summary(self) -> str:
        return f"Force-stopped {self.package_name} on {self.serial}."


class KillBackgroundResult(BaseModel):
    """Outcome of `adb shell am kill [--user N] PACKAGE`.

    `am kill` is deliberately gentler than force-stop: ActivityManager only
    kills the package's processes it currently considers safe to kill
    (cached/background), and leaves a foreground process running. It doesn't
    reset the package's stopped-state flag. Like force-stop it doesn't
    validate the package and is silent on success — a package with nothing
    killable (not installed, or currently foreground) is NOT an error, it's
    a no-op with exit 0. output is am's raw stdout (normally empty).
    """

    serial: str
    package_name: str
    user_id: int | None
    output: str

    def summary(self) -> str:
        scope = "" if self.user_id is None else f" for user {self.user_id}"
        return (
            f"Requested background-process kill of {self.package_name} "
            f"on {self.serial}{scope}."
        )


class ProcessInfo(BaseModel):
    """One row from `adb shell ps -A -o PID,PPID,USER,RSS,NAME`.

    rss_kb is resident set size in kilobytes as `ps` reports it (0 for
    kernel threads). name is the process's `comm`/cmdline name — an app's
    package-style process name (e.g. "com.android.systemui") or a bracketed
    kernel-thread name (e.g. "[kthreadd]").
    """

    pid: int
    ppid: int
    user: str
    rss_kb: int
    name: str


class ProcessList(BaseModel):
    """The device's running processes (`adb shell ps`).

    processes is in the order `ps` returned them (roughly ascending pid).
    When name_filter was given, only processes whose name contains that
    substring are included; an empty list is then a valid result (nothing
    matched), not an error.
    """

    serial: str
    name_filter: str | None
    processes: list[ProcessInfo]

    def summary(self) -> str:
        n = len(self.processes)
        noun = "process" if n == 1 else "processes"
        if self.name_filter is not None:
            return f"{n} {noun} matching '{self.name_filter}' on {self.serial}."
        return f"{n} {noun} on {self.serial}."


class ProcessIds(BaseModel):
    """PIDs currently backing a process/package name (`adb shell pidof`).

    A name can map to more than one PID (an app with several `android:process`
    entries), hence a list. running is False with an empty pids list when
    nothing is running under that name — `pidof` can't tell "not installed"
    from "installed but not running", so neither can this, and that case is a
    normal result rather than an error.
    """

    serial: str
    name: str
    pids: list[int]
    running: bool

    def summary(self) -> str:
        if not self.running:
            return f"No running process named '{self.name}' on {self.serial}."
        pids = ", ".join(str(p) for p in self.pids)
        return f"'{self.name}' on {self.serial}: pid {pids}."


class ProcessMemory(BaseModel):
    """A curated memory snapshot for a process (`adb shell dumpsys meminfo
    -s PACKAGE_OR_PID`), in kilobytes.

    pid/process_name come from meminfo's "MEMINFO in pid N [name]" header.
    The `*_pss_kb` category fields are the Pss column of meminfo's "App
    Summary" table (None when a given row wasn't present in this build's
    output). total_pss_kb/total_rss_kb/total_swap_kb are the table's "TOTAL"
    line and are None on older builds whose meminfo doesn't print it. Every
    value is a raw kilobyte integer exactly as meminfo reports it — no unit
    conversion is applied.
    """

    serial: str
    target: str
    pid: int | None
    process_name: str | None
    java_heap_pss_kb: int | None
    native_heap_pss_kb: int | None
    code_pss_kb: int | None
    stack_pss_kb: int | None
    graphics_pss_kb: int | None
    private_other_pss_kb: int | None
    system_pss_kb: int | None
    total_pss_kb: int | None
    total_rss_kb: int | None
    total_swap_kb: int | None

    def summary(self) -> str:
        who = self.process_name or self.target
        if self.total_pss_kb is not None:
            return f"{who} on {self.serial}: {self.total_pss_kb} KB total PSS."
        return f"Memory snapshot for {who} on {self.serial}."


class ProcessesService:
    """Inspects and stops processes on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def force_stop_app(
        self, serial: str, package_name: str, user_id: int | None = None
    ) -> ForceStopResult:
        _require_non_blank("package_name", package_name)
        parts = ["am", "force-stop"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        parts.append(shlex.quote(package_name))

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_force_stop_failure(serial, package_name, result)
        return ForceStopResult(
            serial=serial, package_name=package_name, user_id=user_id, output=result.stdout
        )

    async def kill_background_processes(
        self, serial: str, package_name: str, user_id: int | None = None
    ) -> KillBackgroundResult:
        _require_non_blank("package_name", package_name)
        parts = ["am", "kill"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        parts.append(shlex.quote(package_name))

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_shell_failure(serial, result)
        return KillBackgroundResult(
            serial=serial,
            package_name=package_name,
            user_id=user_id,
            output=result.stdout.strip(),
        )

    async def list_processes(
        self, serial: str, name_filter: str | None = None
    ) -> ProcessList:
        if name_filter is not None and not name_filter.strip():
            raise InvalidArgumentError(
                "name_filter must be a non-empty substring, or omitted entirely.",
                details={"serial": serial},
            )

        result = await self._backend.shell(serial, "ps -A -o PID,PPID,USER,RSS,NAME")
        _raise_for_shell_failure(serial, result)

        processes = _parse_ps(result.stdout)
        if name_filter is not None:
            processes = [p for p in processes if name_filter in p.name]
        return ProcessList(serial=serial, name_filter=name_filter, processes=processes)

    async def get_process_id(self, serial: str, name: str) -> ProcessIds:
        _require_non_blank("name", name)
        result = await self._backend.shell(serial, f"pidof {shlex.quote(name)}")

        if result.exit_code != 0:
            # `pidof` exits 1 with no output when nothing matches — a valid
            # "not running" result. Any other non-zero exit (with output, e.g.
            # "adb: device 'x' not found" on stderr) is a real failure.
            if not result.stdout.strip() and not result.stderr.strip():
                return ProcessIds(serial=serial, name=name, pids=[], running=False)
            _raise_for_shell_failure(serial, result)

        pids = [int(tok) for tok in result.stdout.split() if tok.isdigit()]
        return ProcessIds(serial=serial, name=name, pids=pids, running=bool(pids))

    async def get_process_memory(self, serial: str, target: str) -> ProcessMemory:
        _require_non_blank("target", target)
        result = await self._backend.shell(
            serial, f"dumpsys meminfo -s {shlex.quote(target)}"
        )
        _raise_for_shell_failure(serial, result)

        text = result.stdout
        if meminfo.NOT_RUNNING_MARKER in text:
            raise PackageNotRunningError(
                f"No running process found for '{target}' on {serial}.",
                details={"serial": serial, "target": target},
            )

        pid, process_name = meminfo.parse_pid_header(text)
        summary = meminfo.parse_app_summary(text)
        if pid is None and summary["total_pss_kb"] is None:
            raise ProcessMemoryUnavailableError(
                "dumpsys meminfo produced no recognizable 'MEMINFO in pid' header "
                "or 'TOTAL PSS' summary line.",
                details={"serial": serial, "target": target, "output_head": text[:400]},
            )

        return ProcessMemory(
            serial=serial,
            target=target,
            pid=pid,
            process_name=process_name,
            **summary,
        )


def _require_non_blank(field: str, value: str) -> None:
    if not value.strip():
        raise InvalidArgumentError(
            f"{field} must be a non-empty string.", details={field: value}
        )


def _parse_ps(output: str) -> list[ProcessInfo]:
    """Split `ps -A -o PID,PPID,USER,RSS,NAME` output into rows.

    The header line ("PID PPID USER RSS NAME") and any line that doesn't
    have three leading integer columns is skipped, so malformed or
    version-variant output yields fewer rows rather than an exception.
    """
    rows: list[ProcessInfo] = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        pid_s, ppid_s, user, rss_s, name = parts
        try:
            pid, ppid, rss_kb = int(pid_s), int(ppid_s), int(rss_s)
        except ValueError:
            continue
        rows.append(
            ProcessInfo(pid=pid, ppid=ppid, user=user, rss_kb=rss_kb, name=name.strip())
        )
    return rows


def _raise_for_shell_failure(serial: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})


def _raise_for_force_stop_failure(serial: str, package_name: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's) — the adb-client rejects an unknown serial
    # before any command reaches a device.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    # forceStopPackage() requires the caller hold FORCE_STOP_PACKAGES; adb
    # shell is granted this by default, so a rejection here is unusual (e.g.
    # a locked-down build) but reaches the shell the same well-known way as
    # every other SecurityException in this server: a "Permission Denial"
    # substring.
    if "Permission Denial" in message:
        raise PermissionDeniedError(message, details={"serial": serial, "package_name": package_name})
    raise BackendError(
        message, details={"serial": serial, "package_name": package_name, "exit_code": result.exit_code}
    )
