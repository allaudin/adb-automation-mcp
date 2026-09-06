"""Domain logic for the android_services module: starting Android services,
both ordinary (`adb shell am start-service`) and foreground
(`adb shell am start-foreground-service`) — named android_services, not
services, to avoid colliding with this project's own `services` concept (the
per-module domain service instances the registry builds). Stopping a service
isn't implemented yet.
"""

from __future__ import annotations

import re
import shlex

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    BackgroundServiceRestrictedError,
    ComponentNotFoundError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)


class StartServiceResult(BaseModel):
    """Outcome of starting an Android service (`adb shell am start-service`).

    Not verified live (no device was available in this environment) — shaped
    on `am`'s documented, long-stable `Am.java`/`runStartService` output.
    Only ever returned on success: unlike start_activity (which has a
    genuine "request accepted but launch outcome unconfirmed" middle state
    via -W), `am start-service` resolves synchronously to either a started
    service or one of several distinct error conditions — see
    AndroidServicesService.start_service's Error handling for how each of
    those is classified and raised instead of returned as data.
    """

    serial: str
    component: str
    user_id: int | None
    output: str

    def summary(self) -> str:
        return f"Started service {self.component} on {self.serial}."


class StartForegroundServiceResult(BaseModel):
    """Outcome of starting an Android foreground Service
    (`adb shell am start-foreground-service`).

    Kept separate from StartServiceResult because Android's background-execution
    rules differ: a plain start-service from the background is refused on
    Android 8+, whereas start-foreground-service is allowed but the app must
    then call startForeground() within a few seconds or the system kills it (and
    logs an ANR-style "did not then call Service.startForeground()"). This tool
    only reports that `am` accepted and dispatched the start — it can't observe
    that later startForeground() call. Verified live on a car AVD: a successful
    start prints "Starting service: Intent { ... }", exit 0; the failure shapes
    (missing service, permission denial, FGS restriction) are classified and
    raised by _raise_for_start_service_failure, shared with start_service.
    """

    serial: str
    component: str
    user_id: int | None
    output: str

    def summary(self) -> str:
        return f"Started foreground service {self.component} on {self.serial}."


class AndroidServicesService:
    """Starts Android services (ordinary and foreground) on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def start_service(
        self, serial: str, component: str, user_id: int | None = None
    ) -> StartServiceResult:
        result = await self._run_start(
            "am start-service", serial, component, user_id
        )
        return StartServiceResult(
            serial=serial, component=component, user_id=user_id, output=result.stdout
        )

    async def start_foreground_service(
        self, serial: str, component: str, user_id: int | None = None
    ) -> StartForegroundServiceResult:
        result = await self._run_start(
            "am start-foreground-service", serial, component, user_id
        )
        return StartForegroundServiceResult(
            serial=serial, component=component, user_id=user_id, output=result.stdout
        )

    async def _run_start(
        self, verb: str, serial: str, component: str, user_id: int | None
    ) -> CommandResult:
        if not component.strip():
            raise InvalidArgumentError(
                "component must not be empty.", details={"serial": serial}
            )
        if user_id is not None and user_id < 0:
            raise InvalidArgumentError(
                "user_id must be a non-negative integer.",
                details={"serial": serial, "user_id": user_id},
            )

        parts = verb.split() + ["-n", shlex.quote(component)]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_start_service_failure(serial, component, result)
        return result


def _raise_for_start_service_failure(serial: str, component: str, result: CommandResult) -> None:
    combined = f"{result.stdout}\n{result.stderr}"
    # `am`'s own component-name parser (Am.java, shared with `am start`/
    # `am broadcast`) rejects a malformed -n argument (not "package/class"
    # shape) before ever calling ActivityManagerService. On some builds this is
    # exit 1 with "Error: Bad component name: ..."; on this project's car AVD
    # it's a "java.lang.IllegalArgumentException: Bad component name: ..." stack
    # trace at exit 0 — check regardless of exit code.
    if "Bad component name" in combined:
        raise ComponentNotFoundError(
            _first_line_containing(combined, "Bad component name"),
            details={"serial": serial, "component": component},
        )

    # An unknown serial fails at the adb-client layer before `am` runs.
    adb_msg = (result.stderr or result.stdout).strip()
    if adb_msg.startswith("adb:") and "not found" in adb_msg:
        raise DeviceNotFoundError(adb_msg, details={"serial": serial})

    # `am`'s runStartService reports every business-logic outcome — a
    # well-formed component matching no declared service, a missing-permission
    # rejection, a background-start restriction — with an "Error: ..." line. The
    # accompanying exit code varies by build (0 on some, 255 on this project's
    # car AVD), so classify by the message, not the code.
    match = _ERROR_LINE_RE.search(combined)
    if match is not None:
        message = match.group("message").strip()
        if message == "Not found; no service started." or "Not found" in message:
            raise ComponentNotFoundError(message, details={"serial": serial, "component": component})
        permission_match = _REQUIRES_PERMISSION_RE.match(message)
        if permission_match is not None:
            raise PermissionDeniedError(
                message,
                details={
                    "serial": serial,
                    "component": component,
                    "permission": permission_match.group(1),
                },
            )
        if "Not allowed to start service" in message:
            raise BackgroundServiceRestrictedError(
                message, details={"serial": serial, "component": component}
            )
        raise BackendError(message, details={"serial": serial, "component": component})

    # A SecurityException reaching the shell as an uncaught RemoteException
    # (e.g. lacking INTERACT_ACROSS_USERS for --user) — same substring
    # convention as broadcasts/activities.
    if "Permission Denial" in combined:
        raise PermissionDeniedError(
            adb_msg or "Permission Denial", details={"serial": serial, "component": component}
        )

    if result.exit_code != 0:
        raise BackendError(
            adb_msg or "adb shell command exited non-zero.",
            details={"serial": serial, "component": component, "exit_code": result.exit_code},
        )


def _first_line_containing(text: str, needle: str) -> str:
    for raw in text.splitlines():
        if needle in raw:
            return raw.strip()
    return text.strip().splitlines()[0] if text.strip() else needle


_ERROR_LINE_RE = re.compile(r"^Error:\s*(?P<message>.+)$", re.MULTILINE)
_REQUIRES_PERMISSION_RE = re.compile(r"^Requires permission (.+)$")
