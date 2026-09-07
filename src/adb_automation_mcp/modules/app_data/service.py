"""Domain logic for the app_data module: clearing an installed package's data.

Two scopes:

- `clear_app_data` — the unscoped `adb shell pm clear`: wipes databases, shared
  preferences, files *and* cache; the app is reset to a fresh-install state.
  Supported on effectively every Android version; `destructive` category.
- `clear_app_cache` — deletes only the cache / code-cache, leaving normal app
  data intact. Prefers `adb shell pm clear --cache-only` (Android 11+); when
  that's unsupported or hangs (a known emulator-image bug) it removes the
  per-user cache directories directly via `rm -rf` (needs root adbd). Never
  falls back to the unscoped clear. `write` category.
"""

from __future__ import annotations

import shlex

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    AdbTimeoutError,
    AndroidRejectionError,
    BackendError,
    CacheOnlyUnsupportedError,
    DeviceNotFoundError,
    PackageNotFoundError,
    PermissionDeniedError,
)

# The per-user cache directories `pm clear --cache-only` would empty — used by
# the fallback when that command is unsupported or hangs. Both the
# credential-encrypted (/data/user) and device-encrypted (/data/user_de) trees,
# and both cache/ and code_cache/.
_CACHE_DIR_TEMPLATES = (
    "/data/user/{uid}/{pkg}/cache",
    "/data/user/{uid}/{pkg}/code_cache",
    "/data/user_de/{uid}/{pkg}/cache",
    "/data/user_de/{uid}/{pkg}/code_cache",
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


class ClearAppCacheResult(BaseModel):
    """Outcome of clearing only a package's cache.

    method is how it was done:

    - "pm_clear_cache_only" — `pm clear --cache-only` worked (Android 11+).
    - "rm_cache_dirs" — that command was unsupported *or* hung (a known bug on
      some emulator images), so the per-user cache directories were removed
      directly instead. This needs adbd running as root; if it isn't,
      CACHE_ONLY_UNSUPPORTED is raised rather than silently doing nothing.

    Either way only cache is touched — never the app's normal data. user_id is
    the user whose cache was cleared (the current user when the caller didn't
    specify one). success is always True (an explicit field for the same
    reason as ClearAppDataResult.success).
    """

    serial: str
    package_name: str
    user_id: int
    method: str
    success: bool
    output: str

    def summary(self) -> str:
        via = " (via rm)" if self.method == "rm_cache_dirs" else ""
        return f"Cleared cache for {self.package_name} (user {self.user_id}) on {self.serial}{via}."


class AppDataService:
    """Clears an installed package's data (full, or cache-only) on a connected
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

    async def clear_app_cache(
        self, serial: str, package_name: str, user_id: int | None = None
    ) -> ClearAppCacheResult:
        resolved_user = user_id if user_id is not None else await self._current_user(serial)

        parts = ["pm", "clear", "--cache-only"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        parts.append(shlex.quote(package_name))

        try:
            result = await self._backend.shell(serial, " ".join(parts))
        except AdbTimeoutError:
            # A known bug on some AOSP emulator images: `pm clear --cache-only`
            # never returns. Fall back to removing the cache dirs directly.
            return await self._clear_cache_via_rm(serial, package_name, resolved_user)

        combined = f"{result.stdout}\n{result.stderr}"
        if "cache-only" in combined and (
            "Unknown option" in combined or "Unrecognized option" in combined
        ):
            return await self._clear_cache_via_rm(serial, package_name, resolved_user)

        _raise_for_clear_data_failure(serial, package_name, result)
        return ClearAppCacheResult(
            serial=serial,
            package_name=package_name,
            user_id=resolved_user,
            method="pm_clear_cache_only",
            success=True,
            output=result.stdout,
        )

    async def _current_user(self, serial: str) -> int:
        result = await self._backend.shell(serial, "am get-current-user")
        _raise_for_clear_data_failure(serial, "", result)
        text = result.stdout.strip()
        return int(text) if text.isdigit() else 0

    async def _clear_cache_via_rm(
        self, serial: str, package_name: str, user_id: int
    ) -> ClearAppCacheResult:
        targets = [
            t.format(uid=user_id, pkg=package_name) for t in _CACHE_DIR_TEMPLATES
        ]
        command = "rm -rf " + " ".join(shlex.quote(t) for t in targets)
        result = await self._backend.shell(serial, command)

        message = (result.stderr or result.stdout).strip()
        if result.exit_code != 0:
            if message.startswith("adb:") and "not found" in message:
                raise DeviceNotFoundError(message, details={"serial": serial})
            if "Permission denied" in message or "Read-only" in message:
                raise CacheOnlyUnsupportedError(
                    "`pm clear --cache-only` is unavailable on this device and the "
                    "direct cache-dir removal was denied — adbd must be running as "
                    "root for the fallback (see restart_adbd_as_root).",
                    details={"serial": serial, "package_name": package_name, "user_id": user_id},
                )
            raise BackendError(
                message or "rm of cache dirs exited non-zero.",
                details={"serial": serial, "package_name": package_name, "user_id": user_id},
            )

        return ClearAppCacheResult(
            serial=serial,
            package_name=package_name,
            user_id=user_id,
            method="rm_cache_dirs",
            success=True,
            output=f"removed: {', '.join(targets)}",
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
