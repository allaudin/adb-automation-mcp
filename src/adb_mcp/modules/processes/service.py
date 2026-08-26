"""Domain logic for the processes module: force-stopping an Android package
(`adb shell am force-stop`) on a connected device. Killing an individual
process by pid (`am kill`) and other process inspection aren't implemented
yet.
"""

from __future__ import annotations

import shlex

from pydantic import BaseModel

from adb_mcp.backend.protocol import AdbBackend, CommandResult
from adb_mcp.errors import BackendError, DeviceNotFoundError, PermissionDeniedError


class ForceStopResult(BaseModel):
    """Outcome of force-stopping a package (`adb shell am force-stop`).

    Not verified live (no device was available in this environment) —
    shaped on `am`'s documented, long-stable behavior: `force-stop` reaches
    ActivityManagerService's forceStopPackage(), which doesn't validate that
    the package is actually installed or currently running — it simply
    forcibly stops every process/component of that package if any exist,
    and is a silent no-op otherwise. So a package_name that doesn't
    correspond to any installed app is NOT an error (this call still
    succeeds), and `am force-stop` normally produces no stdout at all on
    success — see ProcessesService.force_stop_app, which determines outcome
    from the command's exit code, never from output content.
    """

    serial: str
    package_name: str
    user_id: int | None
    output: str

    def summary(self) -> str:
        return f"Force-stopped {self.package_name} on {self.serial}."


class ProcessesService:
    """Force-stops Android packages on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def force_stop_app(
        self, serial: str, package_name: str, user_id: int | None = None
    ) -> ForceStopResult:
        parts = ["am", "force-stop"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        parts.append(shlex.quote(package_name))

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_force_stop_failure(serial, package_name, result)
        return ForceStopResult(
            serial=serial, package_name=package_name, user_id=user_id, output=result.stdout
        )


def _raise_for_force_stop_failure(serial: str, package_name: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's) — the adb-client rejects an unknown serial
    # before any command reaches a device.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    # forceStopPackage() requires the caller hold FORCE_STOP_PACKAGES; adb
    # shell is granted this by default, so a rejection here is unusual (e.g.
    # a locked-down build) but reaches the shell the same well-known way as
    # every other SecurityException in this server: a "Permission Denial"
    # substring.
    if "Permission Denial" in message:
        raise PermissionDeniedError(message, details={"serial": serial, "package_name": package_name})
    raise BackendError(
        message, details={"serial": serial, "package_name": package_name, "exit_code": result.exit_code}
    )
