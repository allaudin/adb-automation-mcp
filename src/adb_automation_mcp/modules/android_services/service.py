"""Domain logic for the android_services module: starting Android services,
both ordinary (`adb shell am start-service`) and foreground
(`adb shell am start-foreground-service`), and stopping one
(`adb shell am stop-service`) — named android_services, not services, to
avoid colliding with this project's own `services` concept (the per-module
domain service instances the registry builds).
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


class StopServiceResult(BaseModel):
    """Outcome of stopping an Android Service (`adb shell am stop-service`).

    `am` prints "Stopping service: Intent { ... }" then one of "Service
    stopped" or "Service not stopped: was not running." — the latter at a
    non-zero exit on some builds (verified live: exit 255 on a car AVD), but
    still a valid answer, not a tool error. stopped is True only for the first;
    was_running mirrors it (True stopped it, False it wasn't running, None if
    `am` gave an outcome this parser doesn't recognize).

    Note `am stop-service` cannot distinguish "no such service component" from
    "known component, not currently running" — both report "was not running." —
    so an unknown component comes back as stopped=False/was_running=False, not
    COMPONENT_NOT_FOUND (only a malformed component name does).
    """

    serial: str
    component: str
    user_id: int | None
    stopped: bool
    was_running: bool | None
    output: str

    def summary(self) -> str:
        if self.stopped:
            return f"Stopped service {self.component} on {self.serial}."
        if self.was_running is False:
            return f"Service {self.component} on {self.serial} was not running."
        return f"Service {self.component} on {self.serial}: stop dispatched, outcome unrecognized."


class ServiceInstance(BaseModel):
    """One running instance of a Service (there's one per Android user it's
    active for), parsed from a `dumpsys activity services` ServiceRecord block.
    Any field this Android version's dump omits is null.
    """

    user_id: int
    pid: int | None
    process_name: str | None
    package_name: str | None
    is_foreground: bool | None
    foreground_id: int | None
    start_requested: bool | None
    last_start_id: int | None
    created_from_fg: bool | None
    start_foreground_count: int | None


class ServiceStatus(BaseModel):
    """A focused status snapshot for one Service component
    (`dumpsys activity services <component>`).

    running is False — with an empty instances list — when the service is not
    active anywhere; `dumpsys` reports that ("No services match: ...") and still
    exits 0, so it's a normal result, not an error. `dumpsys activity services`
    can't distinguish a stopped service from an unknown/malformed component, so
    none of those raise here.
    """

    serial: str
    component: str
    running: bool
    instances: list[ServiceInstance]

    def summary(self) -> str:
        if not self.running:
            return f"Service {self.component} is not running on {self.serial}."
        fg = sum(1 for i in self.instances if i.is_foreground)
        return (
            f"{self.component} is running on {self.serial}: {len(self.instances)} instance(s)"
            + (f", {fg} foreground" if fg else "")
            + "."
        )


class AndroidServicesService:
    """Starts Android services (ordinary and foreground), stops them, and
    reports one Service's status on a connected device.
    """

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def get_service_status(
        self, serial: str, component: str
    ) -> ServiceStatus:
        if not component.strip():
            raise InvalidArgumentError(
                "component must not be empty.", details={"serial": serial}
            )

        result = await self._backend.shell(
            serial, f"dumpsys activity services {shlex.quote(component)}"
        )
        if result.exit_code != 0:
            message = (
                result.stderr or result.stdout
            ).strip() or "dumpsys activity services exited non-zero."
            if message.startswith("adb:") and "not found" in message:
                raise DeviceNotFoundError(message, details={"serial": serial})
            raise BackendError(
                message, details={"serial": serial, "component": component, "exit_code": result.exit_code}
            )

        instances = _parse_service_records(result.stdout)
        return ServiceStatus(
            serial=serial,
            component=component,
            running=bool(instances),
            instances=instances,
        )

    async def stop_service(
        self, serial: str, component: str, user_id: int | None = None
    ) -> StopServiceResult:
        if not component.strip():
            raise InvalidArgumentError(
                "component must not be empty.", details={"serial": serial}
            )
        if user_id is not None and user_id < 0:
            raise InvalidArgumentError(
                "user_id must be a non-negative integer.",
                details={"serial": serial, "user_id": user_id},
            )

        parts = ["am", "stop-service", "-n", shlex.quote(component)]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])

        result = await self._backend.shell(serial, " ".join(parts))
        combined = _check_common_service_errors(serial, component, result)

        lowered = combined.lower()
        if "service stopped" in lowered:
            stopped, was_running = True, True
        elif "was not running" in lowered:
            stopped, was_running = False, False
        else:
            error_line = _ERROR_LINE_RE.search(combined)
            if error_line is not None:
                raise BackendError(
                    error_line.group("message").strip(),
                    details={"serial": serial, "component": component},
                )
            if result.exit_code != 0 and "Stopping service:" not in combined:
                raise BackendError(
                    (result.stderr or result.stdout).strip() or "am stop-service failed.",
                    details={
                        "serial": serial,
                        "component": component,
                        "exit_code": result.exit_code,
                    },
                )
            stopped, was_running = False, None

        return StopServiceResult(
            serial=serial,
            component=component,
            user_id=user_id,
            stopped=stopped,
            was_running=was_running,
            output=result.stdout,
        )

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


def _check_common_service_errors(
    serial: str, component: str, result: CommandResult
) -> str:
    """Raise for the failure shapes shared by `am start-service` /
    `am start-foreground-service` / `am stop-service`. Returns the combined
    stdout+stderr for the caller to inspect the command-specific outcome.
    """
    combined = f"{result.stdout}\n{result.stderr}"
    # `am`'s own component-name parser (Am.java, shared across am subcommands)
    # rejects a malformed -n argument before ever calling ActivityManagerService.
    # On some builds this is exit 1 with "Error: Bad component name: ..."; on
    # this project's car AVD it's a "java.lang.IllegalArgumentException: Bad
    # component name: ..." stack trace at exit 0 — check regardless of exit code.
    if "Bad component name" in combined:
        raise ComponentNotFoundError(
            _first_line_containing(combined, "Bad component name"),
            details={"serial": serial, "component": component},
        )
    # An unknown serial fails at the adb-client layer before `am` runs.
    adb_msg = (result.stderr or result.stdout).strip()
    if adb_msg.startswith("adb:") and "not found" in adb_msg:
        raise DeviceNotFoundError(adb_msg, details={"serial": serial})
    # A SecurityException reaching the shell as an uncaught RemoteException
    # (e.g. lacking INTERACT_ACROSS_USERS for --user) — same substring
    # convention as broadcasts/activities.
    if "Permission Denial" in combined:
        raise PermissionDeniedError(
            adb_msg or "Permission Denial", details={"serial": serial, "component": component}
        )
    return combined


def _raise_for_start_service_failure(serial: str, component: str, result: CommandResult) -> None:
    combined = _check_common_service_errors(serial, component, result)

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

    if result.exit_code != 0:
        raise BackendError(
            (result.stderr or result.stdout).strip() or "adb shell command exited non-zero.",
            details={"serial": serial, "component": component, "exit_code": result.exit_code},
        )


def _first_line_containing(text: str, needle: str) -> str:
    for raw in text.splitlines():
        if needle in raw:
            return raw.strip()
    return text.strip().splitlines()[0] if text.strip() else needle


_ERROR_LINE_RE = re.compile(r"^Error:\s*(?P<message>.+)$", re.MULTILINE)
_REQUIRES_PERMISSION_RE = re.compile(r"^Requires permission (.+)$")

_SERVICE_RECORD_RE = re.compile(r"ServiceRecord\{[0-9a-f]+ u(?P<uid>\d+) (?P<comp>\S+) ")
_APP_PROC_RE = re.compile(r"app=ProcessRecord\{[0-9a-f]+ (?P<pid>\d+):")
_KV_TOKEN_RE = re.compile(r"(\w+)=(\S+)")


def _parse_bool(value: str | None) -> bool | None:
    return None if value is None else value == "true"


def _parse_int(value: str | None) -> int | None:
    if value is None or not value.lstrip("-").isdigit():
        return None
    return int(value)


def _parse_service_records(stdout: str) -> list[ServiceInstance]:
    """Split `dumpsys activity services <component>` into per-ServiceRecord
    blocks and pull the stable status fields out of each.
    """
    lines = stdout.splitlines()
    starts = [i for i, ln in enumerate(lines) if _SERVICE_RECORD_RE.search(ln)]
    instances: list[ServiceInstance] = []
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else len(lines)
        block = lines[start:end]
        header = _SERVICE_RECORD_RE.search(block[0])
        if header is None:
            continue

        kv: dict[str, str] = {}
        pid: int | None = None
        for raw in block:
            app = _APP_PROC_RE.search(raw)
            if app is not None:
                pid = int(app.group("pid"))
            for key, val in _KV_TOKEN_RE.findall(raw):
                kv.setdefault(key, val)  # first occurrence wins

        instances.append(
            ServiceInstance(
                user_id=int(header.group("uid")),
                pid=pid,
                process_name=kv.get("processName"),
                package_name=kv.get("packageName"),
                is_foreground=_parse_bool(kv.get("isForeground")),
                foreground_id=_parse_int(kv.get("foregroundId")),
                start_requested=_parse_bool(kv.get("startRequested")),
                last_start_id=_parse_int(kv.get("lastStartId")),
                created_from_fg=_parse_bool(kv.get("createdFromFg")),
                start_foreground_count=_parse_int(kv.get("startForegroundCount")),
            )
        )
    return instances
