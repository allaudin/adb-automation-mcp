"""Domain logic for the power module: the device's current high-level power
state (`adb shell dumpsys power`). `dumpsys power` output is large and
carries many internal, unstable implementation details — this deliberately
extracts only the two fields stable enough to trust: wakefulness and (when
present) interactive state. Nothing else from the dump is modeled or
exposed. Power-related control (reboot/shutdown/sleep/wake) isn't
implemented yet.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    PermissionDeniedError,
    PowerStateUnavailableError,
)

# PowerManagerService.dump()'s field, long-stable across Android versions:
# "  mWakefulness=Awake" (also Asleep/Dreaming/Dozing). The one field this
# module treats as required — everything else in the dump is considered too
# implementation-specific to parse confidently.
_WAKEFULNESS_RE = re.compile(r"^\s*mWakefulness=(?P<value>\S+)\s*$", re.MULTILINE)

# Present on many but not all Android versions/builds (dumpsys power's exact
# internal fields have shifted over releases) — treated as optional and
# best-effort, never required.
_INTERACTIVE_RE = re.compile(r"^\s*mInteractive=(?P<value>true|false)\s*$", re.MULTILINE)


class PowerState(BaseModel):
    """The device's current high-level power state (`adb shell dumpsys
    power`), deliberately minimal.

    Not verified live (no device was available in this environment) —
    shaped on `PowerManagerService.dump()`'s documented, long-stable
    `mWakefulness=...` field. wakefulness is returned as the raw string
    dumpsys reports (e.g. "Awake", "Asleep", "Dreaming", "Dozing") rather
    than a closed enum, since new wakefulness values could appear in future
    Android versions and this module intentionally doesn't try to be the
    authority on the full set. interactive is None when `mInteractive`
    isn't present in this dump (a normal, non-error outcome — see
    PowerService.get_power_state's Error handling).
    """

    serial: str
    wakefulness: str
    interactive: bool | None

    def summary(self) -> str:
        return f"{self.wakefulness} on {self.serial}."


class PowerService:
    """Reads the device's current high-level power state."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def get_power_state(self, serial: str) -> PowerState:
        result = await self._backend.shell(serial, "dumpsys power")
        _raise_for_dumpsys_failure(serial, result)

        wakefulness_match = _WAKEFULNESS_RE.search(result.stdout)
        if wakefulness_match is None:
            raise PowerStateUnavailableError(
                "dumpsys power output did not contain a recognizable mWakefulness field.",
                details={"serial": serial},
            )
        interactive_match = _INTERACTIVE_RE.search(result.stdout)
        interactive = interactive_match.group("value") == "true" if interactive_match else None

        return PowerState(
            serial=serial, wakefulness=wakefulness_match.group("value"), interactive=interactive
        )


def _raise_for_dumpsys_failure(serial: str, result: CommandResult) -> None:
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
