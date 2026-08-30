"""Domain logic for the app_data module: clearing an installed package's
full application data (`adb shell pm clear`). This wipes the package's
databases, shared preferences, files *and* cache — the app is reset to a
fresh-install state.

Cache-only clearing (`pm clear --cache-only`) was the module's original
scope but is Android 11+ only and silently unavailable on older devices,
with no reliable cross-version ADB equivalent (`pm trim-caches` is
device-wide and needs a system permission; removing `.../cache` directly
needs root). The unscoped `pm clear` is the only variant supported on
effectively every Android version, so this module runs that instead —
hence the `destructive` category.
"""

from __future__ import annotations

import shlex

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    AndroidRejectionError,
    BackendError,
    DeviceNotFoundError,
    PackageNotFoundError,
    PermissionDeniedError,
)


class ClearAppDataResult(BaseModel):
    """Outcome of clearing a package's full application data
    (`adb shell pm clear`).

    Not verified live (no device was available in this environment) —
    shaped on `PackageManagerShellCommand.runClear()`'s documented
    success/failure text ("Success"/"Failed" at exit code 0) and its
    option-parsing convention for an unresolvable package
    ("Error: Package not found", nonzero exit) — see
    AppDataService.clear_app_data's Error handling for how each outcome is
    classified and raised instead of returned as data; `pm clear` always
    resolves synchronously, so there's no meaningful in-between state to
    represent. success is always True here; it's kept as an explicit field
    since a caller inspecting just the data payload should still see it
    stated, not merely implied by the envelope's status.
    """

    serial: str
    package_name: str
    user_id: int | None
    success: bool
    output: str

    def summary(self) -> str:
        return f"Cleared application data for {self.package_name} on {self.serial}."


class AppDataService:
    """Clears an installed package's full application data on a connected
    device.
    """

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def clear_app_data(
        self, serial: str, package_name: str, user_id: int | None = None
    ) -> ClearAppDataResult:
        parts = ["pm", "clear"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        parts.append(shlex.quote(package_name))

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_clear_data_failure(serial, package_name, result)
        return ClearAppDataResult(
            serial=serial, package_name=package_name, user_id=user_id, success=True, output=result.stdout
        )


def _raise_for_clear_data_failure(serial: str, package_name: str, result: CommandResult) -> None:
    if result.exit_code != 0:
        message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
        # Same "adb: device '<serial>' not found" convention verified live for
        # other modules (e.g. user's) — the adb-client rejects an unknown
        # serial before any command reaches a device.
        if message.startswith("adb:") and "not found" in message:
            raise DeviceNotFoundError(message, details={"serial": serial})
        if "Permission Denial" in message:
            raise PermissionDeniedError(message, details={"serial": serial, "package_name": package_name})
        # A package_name that isn't installed (for the target user, if one
        # was given) fails resolution before the clear is even attempted.
        if "not found" in message or "Unknown package" in message:
            raise PackageNotFoundError(message, details={"serial": serial, "package_name": package_name})
        raise BackendError(
            message, details={"serial": serial, "package_name": package_name, "exit_code": result.exit_code}
        )

    # Exit 0: PackageManagerShellCommand.runClear() prints exactly "Success"
    # or a bare "Failed" — the latter is a genuine on-device rejection (the
    # clear was attempted and declined), not a transport failure.
    if result.stdout.strip() == "Failed":
        raise AndroidRejectionError(
            "pm clear reported Failed.", details={"serial": serial, "package_name": package_name}
        )
