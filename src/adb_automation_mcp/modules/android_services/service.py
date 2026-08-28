"""Domain logic for the android_services module: starting Android services
(`adb shell am start-service`) — named android_services, not services, to
avoid colliding with this project's own `services` concept (the per-module
domain service instances the registry builds). Stopping a service and
foreground-service support aren't implemented yet.
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


class AndroidServicesService:
    """Starts Android services on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def start_service(
        self, serial: str, component: str, user_id: int | None = None
    ) -> StartServiceResult:
        parts = ["am", "start-service", "-n", shlex.quote(component)]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_start_service_failure(serial, component, result)
        return StartServiceResult(serial=serial, component=component, user_id=user_id, output=result.stdout)


def _raise_for_start_service_failure(serial: str, component: str, result: CommandResult) -> None:
    if result.exit_code != 0:
        message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
        # Same "adb: device '<serial>' not found" convention verified live for
        # other modules (e.g. user's) — the adb-client rejects an unknown
        # serial before any command reaches a device. An ADB-layer failure
        # like this, or anything else non-zero here, is a transport/ADB
        # failure, not a service-start outcome.
        if message.startswith("adb:") and "not found" in message:
            raise DeviceNotFoundError(message, details={"serial": serial})
        # `am`'s own component-name parser (Am.java, shared with `am start`/
        # `am broadcast`) rejects a malformed -n argument (not "package/class"
        # shape) with this exact prefix before ever calling ActivityManagerService.
        if "Bad component name" in message:
            raise ComponentNotFoundError(message, details={"serial": serial, "component": component})
        # A SecurityException reaching the shell as an uncaught RemoteException
        # (e.g. the caller lacking INTERACT_ACROSS_USERS for --user) always
        # contains this well-known substring, same convention as broadcasts/
        # activities.
        if "Permission Denial" in message:
            raise PermissionDeniedError(message, details={"serial": serial, "component": component})
        raise BackendError(
            message, details={"serial": serial, "component": component, "exit_code": result.exit_code}
        )

    # Am.java's runStartService reports every business-logic outcome — a
    # well-formed component that doesn't match any declared service,
    # a missing-permission rejection, or a background-start restriction —
    # to stderr with an "Error: ..." prefix, still at exit code 0.
    text = result.stderr or result.stdout
    match = _ERROR_LINE_RE.search(text)
    if match is None:
        return
    message = match.group("message").strip()
    if message == "Not found; no service started.":
        raise ComponentNotFoundError(message, details={"serial": serial, "component": component})
    permission_match = _REQUIRES_PERMISSION_RE.match(message)
    if permission_match is not None:
        raise PermissionDeniedError(
            message, details={"serial": serial, "component": component, "permission": permission_match.group(1)}
        )
    if "Not allowed to start service" in message:
        raise BackgroundServiceRestrictedError(message, details={"serial": serial, "component": component})
    raise BackendError(message, details={"serial": serial, "component": component})


_ERROR_LINE_RE = re.compile(r"^Error:\s*(?P<message>.+)$", re.MULTILINE)
_REQUIRES_PERMISSION_RE = re.compile(r"^Requires permission (.+)$")
