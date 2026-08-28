"""Domain logic for the broadcasts module: sending Android intent broadcasts
(`adb shell am broadcast`) to a connected device.
"""

from __future__ import annotations

import re
import shlex
from typing import Literal

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    ComponentNotFoundError,
    DeviceNotFoundError,
    PermissionDeniedError,
)

BroadcastExtraType = Literal["string", "int", "long", "float", "bool"]

# am broadcast's scalar extra flags. Array/URI/component-name extras (--eia,
# --eu, --ecn, ...) aren't supported — deliberately minimal per this module's
# initial scope ("simple extras" only).
_EXTRA_FLAG_BY_TYPE: dict[BroadcastExtraType, str] = {
    "string": "--es",
    "int": "--ei",
    "long": "--el",
    "float": "--ef",
    "bool": "--ez",
}


class BroadcastExtra(BaseModel):
    """One `am broadcast` extra: a key/value pair typed via one of `am`'s
    scalar extra flags. `value` is always a string — for "int"/"long"/"float"/
    "bool" types it must already be formatted the way `am` expects (e.g.
    "true"/"false" for a bool extra); this service passes it through
    unconverted rather than re-parsing and re-formatting it.
    """

    key: str
    value: str
    type: BroadcastExtraType = "string"


class BroadcastResult(BaseModel):
    """Outcome of sending an Android intent broadcast
    (`adb shell am broadcast`).

    Not verified live (no device was available in this environment) — shaped
    on `am`'s documented, long-stable output format from AOSP's
    `Am.java`/`runSendBroadcast`: a "Broadcasting: Intent { ... }" line
    followed by "Broadcast completed: result=N[, data="..."][, extras:
    ...]". result_code/result_data/result_extras are parsed out of that
    second line when present; result_code defaults to 0 (Activity.RESULT_OK)
    if no receiver on the device calls setResultCode() itself.

    Sending a broadcast to an explicit component (-n) or package (-p) that
    is well-formed but doesn't match any installed receiver is NOT an error
    — Android resolves broadcast receivers at delivery time, not send time,
    so it completes normally with result_code=0 and simply reaches nobody.
    Only a malformed component *string* (not "package/class" shape) is
    rejected by `am` itself before sending.
    """

    serial: str
    action: str
    component: str | None
    package: str | None
    user_id: int | None
    receiver_permission: str | None
    result_code: int | None
    result_data: str | None
    result_extras: str | None
    output: str

    def summary(self) -> str:
        if self.result_code is not None:
            return f"Broadcast {self.action!r} completed on {self.serial} (result={self.result_code})."
        return f"Broadcast {self.action!r} sent on {self.serial}."


class BroadcastsService:
    """Sends Android intent broadcasts to a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def send_broadcast(
        self,
        serial: str,
        action: str,
        component: str | None = None,
        package: str | None = None,
        user_id: int | None = None,
        receiver_permission: str | None = None,
        extras: list[BroadcastExtra] | None = None,
    ) -> BroadcastResult:
        parts = ["am", "broadcast", "-a", shlex.quote(action)]
        if package is not None:
            parts.extend(["-p", shlex.quote(package)])
        if component is not None:
            parts.extend(["-n", shlex.quote(component)])
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        if receiver_permission is not None:
            parts.extend(["--receiver-permission", shlex.quote(receiver_permission)])
        for extra in extras or []:
            parts.extend([_EXTRA_FLAG_BY_TYPE[extra.type], shlex.quote(extra.key), shlex.quote(extra.value)])

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_broadcast_failure(serial, action, result)

        match = _RESULT_LINE_RE.search(result.stdout)
        if match is None:
            raise BackendError(
                result.stdout.strip() or "am broadcast succeeded but returned unexpected output.",
                details={"serial": serial, "action": action},
            )
        return BroadcastResult(
            serial=serial,
            action=action,
            component=component,
            package=package,
            user_id=user_id,
            receiver_permission=receiver_permission,
            result_code=int(match.group("code")),
            result_data=match.group("data"),
            result_extras=match.group("extras"),
            output=result.stdout,
        )


def _raise_for_broadcast_failure(serial: str, action: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's) — the adb-client rejects an unknown serial
    # before any command reaches a device.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    # `am`'s own component-name parser (Am.java) rejects a malformed -n
    # argument (not "package/class" shape) with this exact prefix before
    # ever calling into ActivityManagerService.
    if "Bad component name" in message:
        raise ComponentNotFoundError(message, details={"serial": serial, "action": action})
    # AMS's SecurityException for a protected action the caller isn't
    # allowed to send always contains this well-known substring.
    if "Permission Denial" in message:
        raise PermissionDeniedError(message, details={"serial": serial, "action": action})
    raise BackendError(message, details={"serial": serial, "action": action, "exit_code": result.exit_code})


# "Broadcast completed: result=0" or, when a receiver sets result data/extras,
# "Broadcast completed: result=0, data="foo", extras: Bundle[...]".
_RESULT_LINE_RE = re.compile(
    r"Broadcast completed: result=(?P<code>-?\d+)"
    r'(?:, data="(?P<data>[^"]*)")?'
    r"(?:, extras: (?P<extras>.*))?"
)
