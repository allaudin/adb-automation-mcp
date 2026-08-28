"""Domain logic for the app_data module: clearing an installed package's
cache only (`adb shell pm clear --cache-only`). Clearing a package's full
data (`pm clear` without `--cache-only`) is deliberately out of scope for
now — that has different, destructive semantics (wipes app data, not just
cache), so this module never falls back to it.
"""

from __future__ import annotations

import shlex

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    AndroidRejectionError,
    BackendError,
    CacheOnlyUnsupportedError,
    DeviceNotFoundError,
    PackageNotFoundError,
    PermissionDeniedError,
)


class ClearAppCacheResult(BaseModel):
    """Outcome of clearing a package's cache only
    (`adb shell pm clear --cache-only`).

    Not verified live (no device was available in this environment) —
    shaped on `PackageManagerShellCommand.runClear()`'s documented
    success/failure text ("Success"/"Failed" at exit code 0) and its
    option-parsing convention for an option the connected device's `pm`
    doesn't recognize ("Error: Unknown option: --cache-only", nonzero
    exit) — see AppDataService.clear_app_cache's Error handling for how
    each outcome is classified and raised instead of returned as data;
    `pm clear` always resolves synchronously, so there's no meaningful
    in-between state to represent. success is always True here; it's kept
    as an explicit field since a caller inspecting just the data payload
    should still see it stated, not merely implied by the envelope's status.
    """

    serial: str
    package_name: str
    user_id: int | None
    success: bool
    output: str

    def summary(self) -> str:
        return f"Cleared cache for {self.package_name} on {self.serial}."


class AppDataService:
    """Clears an installed package's cache on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def clear_app_cache(
        self, serial: str, package_name: str, user_id: int | None = None
    ) -> ClearAppCacheResult:
        parts = ["pm", "clear", "--cache-only"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        parts.append(shlex.quote(package_name))

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_clear_cache_failure(serial, package_name, result)
        return ClearAppCacheResult(
            serial=serial, package_name=package_name, user_id=user_id, success=True, output=result.stdout
        )


def _raise_for_clear_cache_failure(serial: str, package_name: str, result: CommandResult) -> None:
    if result.exit_code != 0:
        message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
        # Same "adb: device '<serial>' not found" convention verified live for
        # other modules (e.g. user's) — the adb-client rejects an unknown
        # serial before any command reaches a device.
        if message.startswith("adb:") and "not found" in message:
            raise DeviceNotFoundError(message, details={"serial": serial})
        # PackageManagerShellCommand's generic option-parsing loop rejects an
        # option it doesn't recognize with this shape before ever attempting
        # the clear — the well-defined signal that this device's `pm`
        # predates --cache-only support. Never fall back to a full (non
        # --cache-only) clear here; that has different, destructive
        # semantics the caller didn't ask for.
        if "Unknown option" in message and "cache-only" in message:
            raise CacheOnlyUnsupportedError(message, details={"serial": serial, "package_name": package_name})
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
            "pm clear --cache-only reported Failed.", details={"serial": serial, "package_name": package_name}
        )
