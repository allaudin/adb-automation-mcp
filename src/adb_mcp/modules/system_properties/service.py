"""Domain logic for the system_properties module: Android system properties on a
connected device (`adb shell getprop`, `adb shell getprop -Z`, `adb shell setprop`).

Modeled around the property domain, not the underlying binaries: a property is a
name/value pair, optionally with SELinux metadata, that this service reads, lists,
and (subject to validation) writes — callers never see `getprop`/`setprop` shaped
inputs or outputs directly.

Note for maintainers: get_property_metadata's SELinux-context/declared-type fields
(via `getprop -Z`) are based on toybox getprop's documented `-Z` option (the same
context-query convention used across other toybox commands, e.g. `ls -Z`, `ps -Z`)
and the standard `user:role:type:level` SELinux context shape, not verified against
a live device in this environment (no adb/device was available). Treated as
best-effort and degraded gracefully rather than trusted unconditionally — worth a
real-device check before relying on it in production.
"""

from __future__ import annotations

import re
import shlex

from pydantic import BaseModel

from adb_mcp.backend.protocol import AdbBackend, CommandResult
from adb_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    PolicyViolationError,
    PropertyWriteRejectedError,
)

# Property namespaces that represent a distinct semantic operation (starting a
# service, powering off/rebooting the device) rather than ordinary property
# mutation. Rejected before any backend call — see SystemPropertiesService.set_property.
_PROHIBITED_PROPERTY_PREFIXES = ("ctl.",)
_PROHIBITED_PROPERTY_NAMES = frozenset({"sys.powerctl"})


class Property(BaseModel):
    """One Android system property: name and current value.

    An empty value means either the property was explicitly set to "" or it
    doesn't exist at all — `getprop` can't tell those apart, so neither can
    this. An empty value is not a failure; it's a legitimate answer.
    """

    serial: str
    name: str
    value: str

    def summary(self) -> str:
        return f"{self.name}={self.value!r} on {self.serial}."


class PropertyList(BaseModel):
    """Every system property on a device (`adb shell getprop`), optionally
    filtered to those whose name starts with a given prefix.

    Filtering happens here, after parsing — never by shelling out to `grep` or
    building a shell pipeline.
    """

    serial: str
    prefix: str | None
    properties: list[Property]

    def summary(self) -> str:
        n = len(self.properties)
        word = "property" if n == 1 else "properties"
        scoped = f" matching '{self.prefix}'" if self.prefix else ""
        return f"{n} {word}{scoped} on {self.serial}."


class PropertyMetadata(BaseModel):
    """Metadata for one property beyond its bare value.

    selinux_context and declared_type come from `getprop -Z` (the property's
    SELinux security context, and the "type" component parsed out of it, e.g.
    "build_prop" from "u:object_r:build_prop:s0"). Either can be None — not
    every Android version/device build supports `-Z`, and this service treats
    that as a normal, gracefully-degraded answer rather than an internal
    failure.
    """

    serial: str
    name: str
    value: str
    selinux_context: str | None
    declared_type: str | None

    def summary(self) -> str:
        if self.declared_type is None:
            return f"{self.name}={self.value!r} on {self.serial} (no SELinux metadata available)."
        return f"{self.name}={self.value!r} on {self.serial} (type={self.declared_type})."


class SetPropertyResult(BaseModel):
    """Outcome of setting an ordinary mutable Android system property."""

    serial: str
    name: str
    value: str

    def summary(self) -> str:
        return f"Set {self.name}={self.value!r} on {self.serial}."


# One line of `adb shell getprop` output, e.g. "[ro.build.version.release]: [14]"
# or "[dalvik.vm.heapsize]: []" for an empty value. Greedy .* lets the value
# itself contain "]" characters and still match up to the line's final "]".
_PROPERTY_LINE_RE = re.compile(r"^\[(?P<name>[^\]]+)\]:\s*\[(?P<value>.*)\]$")

# A standard SELinux context: user:role:type:level (sensitivity/category
# optional but the first three colon-separated fields are always present).
_SELINUX_CONTEXT_RE = re.compile(r"^[^:\s]+:[^:\s]+:(?P<type>[^:\s]+):[^\s]+$")


def _parse_property_list(output: str) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line in output.splitlines():
        match = _PROPERTY_LINE_RE.match(line.strip())
        if match is None:
            continue  # blank lines or anything not shaped like "[name]: [value]"
        entries.append((match.group("name"), match.group("value")))
    return entries


def _is_prohibited_property(name: str) -> bool:
    if name in _PROHIBITED_PROPERTY_NAMES:
        return True
    return any(name.startswith(prefix) for prefix in _PROHIBITED_PROPERTY_PREFIXES)


class SystemPropertiesService:
    """Reads and mutates Android system properties on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    @staticmethod
    def _raise_for_shell_failure(serial: str, result: CommandResult) -> None:
        if result.exit_code == 0:
            return
        # Same adb-client-level failure shape used by every other module: an
        # unknown serial fails before reaching any device with
        # "adb: device '<serial>' not found", exit 1.
        message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
        if "not found" in message:
            raise DeviceNotFoundError(message, details={"serial": serial})
        raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})

    async def get_property(self, serial: str, name: str) -> Property:
        result = await self._backend.shell(serial, f"getprop {shlex.quote(name)}")
        self._raise_for_shell_failure(serial, result)
        return Property(serial=serial, name=name, value=result.stdout.strip())

    async def list_properties(self, serial: str, prefix: str | None = None) -> PropertyList:
        result = await self._backend.shell(serial, "getprop")
        self._raise_for_shell_failure(serial, result)
        entries = _parse_property_list(result.stdout)
        if prefix:
            entries = [(name, value) for name, value in entries if name.startswith(prefix)]
        properties = [Property(serial=serial, name=name, value=value) for name, value in entries]
        return PropertyList(serial=serial, prefix=prefix, properties=properties)

    async def get_property_metadata(self, serial: str, name: str) -> PropertyMetadata:
        value_result = await self._backend.shell(serial, f"getprop {shlex.quote(name)}")
        self._raise_for_shell_failure(serial, value_result)
        value = value_result.stdout.strip()

        context_result = await self._backend.shell(serial, f"getprop -Z {shlex.quote(name)}")
        selinux_context: str | None = None
        declared_type: str | None = None
        if context_result.exit_code == 0:
            candidate = context_result.stdout.strip()
            match = _SELINUX_CONTEXT_RE.match(candidate)
            if match is not None:
                selinux_context = candidate
                declared_type = match.group("type")
            # else: unrecognized output shape — treat as unsupported, not an error.
        else:
            message = (context_result.stderr or context_result.stdout).strip()
            if "not found" in message:
                # A genuinely disconnected/unreachable device is a real failure,
                # not merely "this metadata field is unsupported here".
                raise DeviceNotFoundError(message, details={"serial": serial})
            # Any other non-zero exit (e.g. "-Z" not recognized on this
            # device's toybox build) is a missing capability, not a failure —
            # selinux_context/declared_type simply stay None.

        return PropertyMetadata(
            serial=serial,
            name=name,
            value=value,
            selinux_context=selinux_context,
            declared_type=declared_type,
        )

    async def set_property(self, serial: str, name: str, value: str) -> SetPropertyResult:
        if _is_prohibited_property(name):
            raise PolicyViolationError(
                f"'{name}' is a control property, not an ordinary mutable one — "
                "set_property refuses to tunnel lifecycle/power operations through "
                "a plain property write.",
                details={"serial": serial, "name": name},
            )

        result = await self._backend.shell(serial, f"setprop {shlex.quote(name)} {shlex.quote(value)}")
        if result.exit_code != 0:
            message = (result.stderr or result.stdout).strip() or "setprop exited non-zero."
            if "not found" in message:
                raise DeviceNotFoundError(message, details={"serial": serial})
            raise PropertyWriteRejectedError(message, details={"serial": serial, "name": name, "value": value})
        return SetPropertyResult(serial=serial, name=name, value=value)
