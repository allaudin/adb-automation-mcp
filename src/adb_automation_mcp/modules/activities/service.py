"""Domain logic for the activities module: launching Android activities
(`adb shell am start`) on a connected device.
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


class ActivitiesService:
    """Launches Android activities on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

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


_ERROR_TYPE_RE = re.compile(r"^Error type (?P<type>\d+)\s*$", re.MULTILINE)
_ERROR_MESSAGE_RE = re.compile(r"^Error:\s*(?P<message>.+)$", re.MULTILINE)
# The following four are only ever present with `-W` (wait_for_launch=True).
_STATUS_RE = re.compile(r"^Status:\s*(?P<status>\S+)\s*$", re.MULTILINE)
_LAUNCH_STATE_RE = re.compile(r"^LaunchState:\s*(?P<state>\S+)\s*$", re.MULTILINE)
_ACTIVITY_RE = re.compile(r"^Activity:\s*(?P<activity>\S+)\s*$", re.MULTILINE)
_TOTAL_TIME_RE = re.compile(r"^TotalTime:\s*(?P<ms>\d+)\s*$", re.MULTILINE)
_WAIT_TIME_RE = re.compile(r"^WaitTime:\s*(?P<ms>\d+)\s*$", re.MULTILINE)
