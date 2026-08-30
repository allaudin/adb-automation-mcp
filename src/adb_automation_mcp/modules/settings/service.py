"""Domain logic for the settings module: reading Android `Settings`
provider values (`adb shell settings get NAMESPACE KEY`). Writing
(`put`/`delete`) isn't implemented yet.

Deliberately distinct from the system_properties module: `Settings`
(system/secure/global, backed by SettingsProvider, `settings get/put`) and
system properties (the flat `getprop`/`setprop` property-service namespace)
are two unrelated Android subsystems that happen to look similar from a
shell — this module never touches `getprop`/`setprop`, and
system_properties never touches `settings`.
"""

from __future__ import annotations

import shlex
from typing import Literal

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import BackendError, DeviceNotFoundError, PermissionDeniedError

# The only three namespaces SettingsProvider recognizes for `settings get`.
# Typed as a Literal (not a plain str) so an invalid namespace is rejected by
# schema validation before this service — or even the tool function's body —
# ever runs, and so no arbitrary string ever reaches the shell command as a
# positional argument.
SettingsNamespace = Literal["system", "secure", "global"]

# SettingsCmd's exact, long-stable wording for a key with no value in the
# requested namespace — printed as the literal four-character string "null"
# to stdout, at exit code 0 (not an error, not empty output).
_NULL_VALUE_TEXT = "null"


class SettingValue(BaseModel):
    """One Android Settings-provider value (`adb shell settings get
    NAMESPACE KEY`).

    Not verified live (no device was available in this environment) —
    shaped on `SettingsCmd`'s documented, long-stable behavior: `get`
    prints the value as-is on success, or the literal text "null" (exit
    code 0, not an error) when the key has no value in that namespace for
    the target user. value is None in that case — same "can't distinguish
    a real absence from a coincidentally identical value" caveat as
    system_properties' Property.value (there, an empty string; here, the
    literal text "null"), so the same design choice: represent the
    ambiguous case as ordinary success data, not an error.
    """

    serial: str
    namespace: SettingsNamespace
    key: str
    value: str | None
    user_id: int | None

    def summary(self) -> str:
        if self.value is None:
            return f"{self.namespace}:{self.key} has no value on {self.serial}."
        return f"{self.namespace}:{self.key}={self.value!r} on {self.serial}."


class SettingsService:
    """Reads Android Settings-provider values on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def get_setting(
        self, serial: str, namespace: SettingsNamespace, key: str, user_id: int | None = None
    ) -> SettingValue:
        parts = ["settings"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        parts.extend(["get", shlex.quote(namespace), shlex.quote(key)])

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_get_setting_failure(serial, namespace, key, result)

        raw = result.stdout.strip()
        value = None if raw == _NULL_VALUE_TEXT else raw
        return SettingValue(
            serial=serial, namespace=namespace, key=key, value=value, user_id=user_id
        )


def _raise_for_get_setting_failure(
    serial: str, namespace: SettingsNamespace, key: str, result: CommandResult
) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's) — the adb-client rejects an unknown serial
    # before any command reaches a device.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(
            message, details={"serial": serial, "namespace": namespace, "key": key}
        )
    raise BackendError(
        message,
        details={
            "serial": serial,
            "namespace": namespace,
            "key": key,
            "exit_code": result.exit_code,
        },
    )
