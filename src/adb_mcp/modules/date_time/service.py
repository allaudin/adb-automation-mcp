"""Domain logic for the date_time module: the device's current system
date/time (`adb shell date`). Always reads the DEVICE clock — never the
MCP host's. Uses an explicit, machine-readable `+FORMAT` (never `date`'s
locale-dependent default human-readable output) so the result is
predictable to parse rather than a localized string this server would then
have to guess the shape of. set_date_time and time zone modification
aren't implemented yet. Kept separate from settings (generic
SettingsProvider access), system_properties (getprop/setprop), and power
(reboot/shutdown/sleep/wake) — see those modules for those concerns.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from adb_mcp.backend.protocol import AdbBackend, CommandResult
from adb_mcp.errors import (
    BackendError,
    DeviceClockUnavailableError,
    DeviceNotFoundError,
    PermissionDeniedError,
)

# ISO-8601-shaped, locale-independent: no weekday/month names, no AM/PM.
_TIMESTAMP_COMMAND = "date +%Y-%m-%dT%H:%M:%S"
_TIMESTAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$")

# Queried separately from the timestamp: some `date` builds don't support
# %z, and that's a normal degrade-to-None outcome, not a reason to fail the
# whole call (see get_date_time's Error handling).
_UTC_OFFSET_COMMAND = "date +%z"
_UTC_OFFSET_RE = re.compile(r"^[+-]\d{4}$")


class DeviceDateTime(BaseModel):
    """The device's current system date/time (`adb shell date`), read from
    the device's own clock — never the MCP host's.

    Not verified live (no device was available in this environment) —
    shaped on toybox `date`'s documented strftime-style `+FORMAT` support.
    timestamp is always present (ISO-8601 shaped, no time zone) — see
    DateTimeService.get_date_time's Error handling for how an unparsable
    primary result is raised, not returned. utc_offset is None when the
    device's `date` doesn't support `%z`, which is not treated as a
    failure of the call as a whole.
    """

    serial: str
    timestamp: str
    utc_offset: str | None

    def summary(self) -> str:
        if self.utc_offset is None:
            return f"Device time on {self.serial}: {self.timestamp} (UTC offset unknown)."
        return f"Device time on {self.serial}: {self.timestamp}{self.utc_offset}."


class DateTimeService:
    """Reads the device's current system date/time."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def get_date_time(self, serial: str) -> DeviceDateTime:
        result = await self._backend.shell(serial, _TIMESTAMP_COMMAND)
        _raise_for_date_failure(serial, result)

        timestamp = result.stdout.strip()
        if _TIMESTAMP_RE.match(timestamp) is None:
            raise DeviceClockUnavailableError(
                f"Unexpected `date` output: {timestamp!r}",
                details={"serial": serial, "output": timestamp},
            )

        utc_offset = await self._get_utc_offset(serial)
        return DeviceDateTime(serial=serial, timestamp=timestamp, utc_offset=utc_offset)

    async def _get_utc_offset(self, serial: str) -> str | None:
        result = await self._backend.shell(serial, _UTC_OFFSET_COMMAND)
        if result.exit_code != 0:
            message = (result.stderr or result.stdout).strip()
            if message.startswith("adb:") and "not found" in message:
                # A genuinely disconnected/unreachable device is a real
                # failure, not merely "this format specifier is unsupported".
                raise DeviceNotFoundError(message, details={"serial": serial})
            # Any other non-zero exit (e.g. this `date` build rejects "%z")
            # is a missing capability, not a failure — utc_offset stays None.
            return None
        candidate = result.stdout.strip()
        if _UTC_OFFSET_RE.match(candidate) is None:
            # e.g. "%z" echoed back unexpanded on a `date` build without
            # offset-format support — unrecognized shape, not an error.
            return None
        return candidate


def _raise_for_date_failure(serial: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's) — the adb-client rejects an unknown serial
    # before any command reaches a device.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})
