"""Domain logic for the settings module: reading and writing Android
`Settings` provider values (`adb shell settings get/put NAMESPACE KEY`).
Deleting (`settings delete`) isn't implemented yet.

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
from adb_automation_mcp.errors import (
    AndroidRejectionError,
    BackendError,
    DeviceNotFoundError,
    PermissionDeniedError,
)

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


class SettingWriteResult(BaseModel):
    """Outcome of writing one Android Settings-provider value (`adb shell
    settings put NAMESPACE KEY VALUE`).

    `settings put` is silent on success (exit 0) and reports nothing about
    what the value was before, so set_setting reads the key once *before*
    the write (`previous_value`) and once *after* (`new_value`) — giving a
    caller everything it needs to restore the original afterwards, and to
    see when a write didn't actually take. requested_value is the string
    that was asked for; new_value is what the provider reports now (usually
    identical, but Android normalizes some values and silently ignores some
    protected keys — new_value != requested_value surfaces that without an
    error, since it's a real, observable device outcome, not a failure).
    previous_value / new_value are None when the key had / has no value in
    that namespace (the literal "null"), same convention as
    SettingValue.value.
    """

    serial: str
    namespace: SettingsNamespace
    key: str
    requested_value: str
    previous_value: str | None
    new_value: str | None
    user_id: int | None
    changed: bool

    def summary(self) -> str:
        scope = f" for user {self.user_id}" if self.user_id is not None else ""
        if not self.changed:
            return (
                f"{self.namespace}:{self.key} already {self.new_value!r} on "
                f"{self.serial}{scope} — unchanged."
            )
        return (
            f"Set {self.namespace}:{self.key} = {self.new_value!r} on {self.serial}{scope} "
            f"(was {self.previous_value!r})."
        )


class SettingsService:
    """Reads and writes Android Settings-provider values on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def get_setting(
        self, serial: str, namespace: SettingsNamespace, key: str, user_id: int | None = None
    ) -> SettingValue:
        value = await self._read_value(serial, namespace, key, user_id)
        return SettingValue(
            serial=serial, namespace=namespace, key=key, value=value, user_id=user_id
        )

    async def set_setting(
        self,
        serial: str,
        namespace: SettingsNamespace,
        key: str,
        value: str,
        user_id: int | None = None,
    ) -> SettingWriteResult:
        previous_value = await self._read_value(serial, namespace, key, user_id)

        parts = ["settings"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        parts.extend(["put", shlex.quote(namespace), shlex.quote(key), shlex.quote(value)])
        put_result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_put_setting_failure(serial, namespace, key, put_result)

        new_value = await self._read_value(serial, namespace, key, user_id)
        return SettingWriteResult(
            serial=serial,
            namespace=namespace,
            key=key,
            requested_value=value,
            previous_value=previous_value,
            new_value=new_value,
            user_id=user_id,
            changed=previous_value != new_value,
        )

    async def _read_value(
        self, serial: str, namespace: SettingsNamespace, key: str, user_id: int | None
    ) -> str | None:
        parts = ["settings"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        parts.extend(["get", shlex.quote(namespace), shlex.quote(key)])

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_get_setting_failure(serial, namespace, key, result)

        raw = result.stdout.strip()
        return None if raw == _NULL_VALUE_TEXT else raw


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


def _raise_for_put_setting_failure(
    serial: str, namespace: SettingsNamespace, key: str, result: CommandResult
) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell settings put exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if (
        "Permission Denial" in message
        or "Permission denied" in message
        or "SecurityException" in message
    ):
        raise PermissionDeniedError(
            message, details={"serial": serial, "namespace": namespace, "key": key}
        )
    # `settings put` reaching SettingsProvider and being refused there surfaces
    # as a Java stack trace / "Exception occurred while executing 'put'" — the
    # device processed the request and declined it, distinct from a bad call.
    if "Exception occurred" in message or "at com.android." in message:
        raise AndroidRejectionError(
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
