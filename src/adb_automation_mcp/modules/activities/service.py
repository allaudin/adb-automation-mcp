"""Domain logic for the activities module: launching Android activities
(`adb shell am start`) and resolving which Activity would handle an Intent
without launching it (`adb shell cmd package resolve-activity`).
"""

from __future__ import annotations

import re
import shlex

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    ComponentNotFoundError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)


class StartActivityResult(BaseModel):
    """Outcome of launching an Android activity (`adb shell am start`).

    Not verified live (no device was available in this environment) — shaped
    on `am`'s documented, long-stable output. Two distinct failure shapes
    matter here:

    - A malformed `-n` component (not "package/class" shape) is rejected by
      `am`'s own CLI parser before anything is attempted — exit code 1,
      "Error: Bad component name: ...". That's a bad request, not a launch
      outcome, so the service raises ComponentNotFoundError for it rather
      than returning it as data (see StartActivitiesService.start_activity).
    - A well-formed component that ActivityManager can't resolve or launch
      (e.g. "Error type 3\\nError: Activity class {pkg/cls} does not
      exist.") is a genuine launch outcome, still exit code 0 — that's what
      success/error_type/error_message below represent.

    status/launch_state/total_time_ms/wait_time_ms/activity are only ever
    populated when wait_for_launch=True: without `-W`, `am start` is
    fire-and-forget and returns almost immediately, before Android can
    report whether the activity actually finished launching. Without -W,
    success=True only means "no immediate rejection" — not confirmed launch.
    """

    serial: str
    component: str
    user_id: int | None
    display_id: int | None
    wait_for_launch: bool
    success: bool
    activity: str | None
    status: str | None
    launch_state: str | None
    total_time_ms: int | None
    wait_time_ms: int | None
    error_type: int | None
    error_message: str | None
    output: str

    def summary(self) -> str:
        if self.success:
            return f"Launched {self.component} on {self.serial}."
        return f"Failed to launch {self.component} on {self.serial}: {self.error_message}"


class ResolvedActivity(BaseModel):
    """Which Activity Android would pick for an Intent, from
    `cmd package resolve-activity --brief`. Nothing is launched.

    resolved is False for the "No activity found" outcome (a valid answer, not
    an error) — component and the parsed fields are then null. When resolved is
    True, component is "<package>/<class>" and is_default says whether the
    winner is a default handler (as opposed to the system resolver/chooser
    being what actually matched).
    """

    serial: str
    resolved: bool
    component: str | None
    package_name: str | None
    activity_class: str | None
    is_default: bool | None
    match: str | None
    priority: int | None

    def summary(self) -> str:
        if not self.resolved:
            return f"No activity resolves that intent on {self.serial}."
        default = "" if self.is_default is None else (" (default)" if self.is_default else " (via resolver)")
        return f"{self.component} resolves that intent on {self.serial}{default}."


class DisplayForegroundActivity(BaseModel):
    """The resumed/top Activity on one display."""

    display_id: int
    component: str
    package_name: str
    activity_class: str
    user_id: int | None
    task_id: int | None


class ForegroundActivitySnapshot(BaseModel):
    """The currently resumed/top Activity, parsed from `dumpsys activity
    activities`.

    resolved is False when nothing is resumed anywhere (e.g. the screen is off
    or every app is stopped) — a valid state, not an error. When resolved, the
    top-level component/package_name/activity_class/user_id/display_id/task_id
    describe the single globally-focused Activity, and per_display lists the
    resumed Activity of every display that has one (length > 1 only on a
    multi-display device).
    """

    serial: str
    resolved: bool
    component: str | None
    package_name: str | None
    activity_class: str | None
    user_id: int | None
    display_id: int | None
    task_id: int | None
    per_display: list[DisplayForegroundActivity]

    def summary(self) -> str:
        if not self.resolved:
            return f"No activity is currently resumed on {self.serial}."
        extra = f" (+{len(self.per_display) - 1} more display)" if len(self.per_display) > 1 else ""
        return f"{self.component} is foreground on {self.serial}{extra}."


class ActivitiesService:
    """Launches Android activities on a connected device, resolves intents to
    activities without launching, and reports the foreground Activity.
    """

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def get_foreground_activity(self, serial: str) -> ForegroundActivitySnapshot:
        result = await self._backend.shell(serial, "dumpsys activity activities")
        if result.exit_code != 0:
            message = (
                result.stderr or result.stdout
            ).strip() or "dumpsys activity activities exited non-zero."
            if message.startswith("adb:") and "not found" in message:
                raise DeviceNotFoundError(message, details={"serial": serial})
            raise BackendError(
                message, details={"serial": serial, "exit_code": result.exit_code}
            )
        return _parse_foreground_activity(serial, result.stdout)

    async def resolve_activity(
        self,
        serial: str,
        action: str | None = None,
        data_uri: str | None = None,
        mime_type: str | None = None,
        categories: list[str] | None = None,
        component: str | None = None,
        package_name: str | None = None,
        user_id: int | None = None,
    ) -> ResolvedActivity:
        categories = categories or []
        if not any([action, data_uri, mime_type, component, package_name]) and not categories:
            raise InvalidArgumentError(
                "Specify at least one of: action, data_uri, mime_type, categories, "
                "component, package_name.",
                details={"serial": serial},
            )
        if user_id is not None and user_id < 0:
            raise InvalidArgumentError(
                "user_id must be a non-negative integer.",
                details={"serial": serial, "user_id": user_id},
            )

        parts = ["cmd", "package", "resolve-activity", "--brief"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        if action is not None:
            parts.extend(["-a", shlex.quote(action)])
        if data_uri is not None:
            parts.extend(["-d", shlex.quote(data_uri)])
        if mime_type is not None:
            parts.extend(["-t", shlex.quote(mime_type)])
        for category in categories:
            parts.extend(["-c", shlex.quote(category)])
        if component is not None:
            parts.extend(["-n", shlex.quote(component)])
        if package_name is not None:
            parts.extend(["-p", shlex.quote(package_name)])

        result = await self._backend.shell(serial, " ".join(parts))
        return _parse_resolve_activity(serial, result)

    async def start_activity(
        self,
        serial: str,
        component: str,
        user_id: int | None = None,
        display_id: int | None = None,
        wait_for_launch: bool = False,
    ) -> StartActivityResult:
        parts = ["am", "start", "-n", shlex.quote(component)]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        if display_id is not None:
            parts.extend(["--display", str(display_id)])
        if wait_for_launch:
            parts.append("-W")

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_start_activity_failure(serial, component, result)
        return _parse_start_activity_result(serial, component, user_id, display_id, wait_for_launch, result)


def _raise_for_start_activity_failure(serial: str, component: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's) — the adb-client rejects an unknown serial
    # before any command reaches a device.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    # `am`'s own component-name parser (Am.java, shared with `am broadcast`)
    # rejects a malformed -n argument (not "package/class" shape) with this
    # exact prefix before ever calling into ActivityManagerService.
    if "Bad component name" in message:
        raise ComponentNotFoundError(message, details={"serial": serial, "component": component})
    # AMS's SecurityException for a protected activity the caller isn't
    # allowed to start always contains this well-known substring.
    if "Permission Denial" in message:
        raise PermissionDeniedError(message, details={"serial": serial, "component": component})
    raise BackendError(
        message, details={"serial": serial, "component": component, "exit_code": result.exit_code}
    )


def _parse_start_activity_result(
    serial: str,
    component: str,
    user_id: int | None,
    display_id: int | None,
    wait_for_launch: bool,
    result: CommandResult,
) -> StartActivityResult:
    # A well-formed component ActivityManager can't resolve/launch (e.g. a
    # class that doesn't exist) fails at exit code 0 with "Error type N" and
    # an "Error: ..." line — a genuine launch outcome, not a bad request, so
    # this is reported as success=False data rather than raised.
    error_type_match = _ERROR_TYPE_RE.search(result.stdout)
    error_message_match = _ERROR_MESSAGE_RE.search(result.stdout)
    if error_message_match is not None:
        return StartActivityResult(
            serial=serial,
            component=component,
            user_id=user_id,
            display_id=display_id,
            wait_for_launch=wait_for_launch,
            success=False,
            activity=None,
            status=None,
            launch_state=None,
            total_time_ms=None,
            wait_time_ms=None,
            error_type=int(error_type_match.group("type")) if error_type_match else None,
            error_message=error_message_match.group("message").strip(),
            output=result.stdout,
        )

    status_match = _STATUS_RE.search(result.stdout)
    launch_state_match = _LAUNCH_STATE_RE.search(result.stdout)
    activity_match = _ACTIVITY_RE.search(result.stdout)
    total_time_match = _TOTAL_TIME_RE.search(result.stdout)
    wait_time_match = _WAIT_TIME_RE.search(result.stdout)
    return StartActivityResult(
        serial=serial,
        component=component,
        user_id=user_id,
        display_id=display_id,
        wait_for_launch=wait_for_launch,
        success=True,
        activity=activity_match.group("activity") if activity_match else None,
        status=status_match.group("status") if status_match else None,
        launch_state=launch_state_match.group("state") if launch_state_match else None,
        total_time_ms=int(total_time_match.group("ms")) if total_time_match else None,
        wait_time_ms=int(wait_time_match.group("ms")) if wait_time_match else None,
        error_type=None,
        error_message=None,
        output=result.stdout,
    )


_RESOLVE_COMPONENT_RE = re.compile(r"^\s*(?P<pkg>[\w.]+)/(?P<cls>[\w.$]+)\s*$", re.MULTILINE)
_RESOLVE_META_RE = re.compile(r"(\w+)=(\S+)")

# ActivityRecord{<hex> u<userId> <package>/<class> [t<taskId>]}
_ACT_RECORD_RE = re.compile(
    r"ActivityRecord\{[0-9a-f]+ u(?P<user>\d+) (?P<comp>[^\s}]+)(?: t(?P<task>\d+))?\}"
)
_DISPLAY_HEADER_RE = re.compile(r"^Display #(?P<id>\d+)\b")
_TOP_RESUMED_RE = re.compile(r"(?:topResumedActivity|mResumedActivity|ResumedActivity)=")


def _split_component(comp: str) -> tuple[str, str]:
    pkg, _, cls = comp.partition("/")
    return pkg, cls


def _activity_from_line(line: str) -> tuple[str, str, str, int | None, int | None] | None:
    """(component, package, class, user_id, task_id) from the first
    ActivityRecord{...} on a line, or None.
    """
    m = _ACT_RECORD_RE.search(line)
    if m is None:
        return None
    comp = m.group("comp")
    pkg, cls = _split_component(comp)
    if not pkg or not cls:
        return None
    user = int(m.group("user")) if m.group("user") is not None else None
    task = int(m.group("task")) if m.group("task") is not None else None
    return comp, pkg, cls, user, task


def _parse_foreground_activity(serial: str, text: str) -> ForegroundActivitySnapshot:
    per_display: dict[int, DisplayForegroundActivity] = {}
    current_display: int | None = None
    root_resumed: tuple[str, str, str, int | None, int | None] | None = None
    focused_app: tuple[str, str, str, int | None, int | None] | None = None

    for raw in text.splitlines():
        header = _DISPLAY_HEADER_RE.match(raw)
        if header is not None:
            current_display = int(header.group("id"))
            continue
        if raw and not raw[0].isspace() and not raw.startswith("Display #"):
            # a new top-level section — no longer inside a Display block
            current_display = None

        if "topResumedActivity=" in raw and "=null" not in raw and current_display is not None:
            if current_display not in per_display:
                parsed = _activity_from_line(raw)
                if parsed is not None:
                    comp, pkg, cls, user, task = parsed
                    per_display[current_display] = DisplayForegroundActivity(
                        display_id=current_display,
                        component=comp,
                        package_name=pkg,
                        activity_class=cls,
                        user_id=user,
                        task_id=task,
                    )
        elif raw.lstrip().startswith(("ResumedActivity:", "mResumedActivity:")):
            parsed = _activity_from_line(raw)
            if parsed is not None:
                root_resumed = parsed
        elif "mFocusedApp=" in raw:
            parsed = _activity_from_line(raw)
            if parsed is not None:
                focused_app = parsed

    displays_sorted = [per_display[k] for k in sorted(per_display)]

    primary = (
        root_resumed
        or focused_app
        or (
            (
                per_display[0].component,
                per_display[0].package_name,
                per_display[0].activity_class,
                per_display[0].user_id,
                per_display[0].task_id,
            )
            if 0 in per_display
            else None
        )
        or (
            (
                displays_sorted[0].component,
                displays_sorted[0].package_name,
                displays_sorted[0].activity_class,
                displays_sorted[0].user_id,
                displays_sorted[0].task_id,
            )
            if displays_sorted
            else None
        )
    )

    if primary is None:
        return ForegroundActivitySnapshot(
            serial=serial,
            resolved=False,
            component=None,
            package_name=None,
            activity_class=None,
            user_id=None,
            display_id=None,
            task_id=None,
            per_display=[],
        )

    comp, pkg, cls, user, task = primary
    # Which display is the primary on? Match by component against per_display.
    display_id = next(
        (d.display_id for d in displays_sorted if d.component == comp),
        displays_sorted[0].display_id if displays_sorted else None,
    )
    return ForegroundActivitySnapshot(
        serial=serial,
        resolved=True,
        component=comp,
        package_name=pkg,
        activity_class=cls,
        user_id=user,
        display_id=display_id,
        task_id=task,
        per_display=displays_sorted,
    )


def _parse_resolve_activity(serial: str, result: CommandResult) -> ResolvedActivity:
    combined = f"{result.stdout}\n{result.stderr}"
    message = (result.stderr or result.stdout).strip()

    # `cmd` exits 0 for everything; failures are text-only.
    if result.exit_code != 0 and message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Bad component name" in combined:
        # cmd's own Intent parser rejected a malformed -n before resolving.
        raise InvalidArgumentError(
            _first_exception_line(combined), details={"serial": serial}
        )
    if "Unknown option" in combined:
        raise BackendError(
            f"this device's `cmd package resolve-activity` rejected an option: "
            f"{_first_exception_line(combined)}",
            details={"serial": serial},
        )

    if "No activity found" in combined:
        return ResolvedActivity(
            serial=serial,
            resolved=False,
            component=None,
            package_name=None,
            activity_class=None,
            is_default=None,
            match=None,
            priority=None,
        )

    comp_match = _RESOLVE_COMPONENT_RE.search(result.stdout)
    if comp_match is None:
        raise BackendError(
            "cmd package resolve-activity returned unrecognized output.",
            details={"serial": serial, "stdout": result.stdout.strip()[:200]},
        )

    meta: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if "priority=" in line and "match=" in line:
            meta = dict(_RESOLVE_META_RE.findall(line))
            break

    pkg, cls = comp_match.group("pkg"), comp_match.group("cls")
    is_default_raw = meta.get("isDefault")
    priority_raw = meta.get("priority")
    return ResolvedActivity(
        serial=serial,
        resolved=True,
        component=f"{pkg}/{cls}",
        package_name=pkg,
        activity_class=cls,
        is_default=None if is_default_raw is None else is_default_raw == "true",
        match=meta.get("match"),
        priority=int(priority_raw) if priority_raw is not None and priority_raw.isdigit() else None,
    )


def _first_exception_line(text: str) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("java.") and ":" in line:
            return line
    for raw in text.splitlines():
        line = raw.strip()
        if line and not line.startswith("at ") and "Exception occurred" not in line:
            return line
    return text.strip().splitlines()[0] if text.strip() else "no detail"


_ERROR_TYPE_RE = re.compile(r"^Error type (?P<type>\d+)\s*$", re.MULTILINE)
_ERROR_MESSAGE_RE = re.compile(r"^Error:\s*(?P<message>.+)$", re.MULTILINE)
# The following four are only ever present with `-W` (wait_for_launch=True).
_STATUS_RE = re.compile(r"^Status:\s*(?P<status>\S+)\s*$", re.MULTILINE)
_LAUNCH_STATE_RE = re.compile(r"^LaunchState:\s*(?P<state>\S+)\s*$", re.MULTILINE)
_ACTIVITY_RE = re.compile(r"^Activity:\s*(?P<activity>\S+)\s*$", re.MULTILINE)
_TOTAL_TIME_RE = re.compile(r"^TotalTime:\s*(?P<ms>\d+)\s*$", re.MULTILINE)
_WAIT_TIME_RE = re.compile(r"^WaitTime:\s*(?P<ms>\d+)\s*$", re.MULTILINE)
