"""Domain logic for the permissions module: granting an Android runtime
permission to an installed package (`adb shell pm grant`). Revoking,
checking, and listing permissions aren't implemented yet.
"""

from __future__ import annotations

import shlex

from pydantic import BaseModel

from adb_mcp.backend.protocol import AdbBackend, CommandResult
from adb_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    NonRuntimePermissionError,
    PackageNotFoundError,
    PermissionDeniedError,
    PermissionNotDeclaredError,
    PermissionPolicyRestrictedError,
)


class GrantPermissionResult(BaseModel):
    """Outcome of granting a runtime permission (`adb shell pm grant`).

    Not verified live (no device was available in this environment) —
    shaped on `PackageManagerShellCommand.runGrantRevokePermission()`'s
    documented behavior: a successful grant produces no stdout at all, and
    every failure mode (unknown package, a permission the package doesn't
    request, a non-runtime permission, a policy-fixed permission state, or
    a plain SecurityException) is reported via an exception message on a
    non-zero exit — see PermissionsService.grant_permission's Error
    handling for how each is classified and raised instead of returned as
    data. success is always True here; it's kept as an explicit field
    since a caller inspecting just the data payload should still see it
    stated, not merely implied by the envelope's status.
    """

    serial: str
    package_name: str
    permission: str
    user_id: int | None
    success: bool
    output: str

    def summary(self) -> str:
        return f"Granted {self.permission} to {self.package_name} on {self.serial}."


class PermissionsService:
    """Grants Android runtime permissions to an installed package."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def grant_permission(
        self, serial: str, package_name: str, permission: str, user_id: int | None = None
    ) -> GrantPermissionResult:
        parts = ["pm", "grant"]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        parts.extend([shlex.quote(package_name), shlex.quote(permission)])

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_grant_failure(serial, package_name, permission, result)
        return GrantPermissionResult(
            serial=serial,
            package_name=package_name,
            permission=permission,
            user_id=user_id,
            success=True,
            output=result.stdout,
        )


def _raise_for_grant_failure(
    serial: str, package_name: str, permission: str, result: CommandResult
) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's) — the adb-client rejects an unknown serial
    # before any command reaches a device.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    # Same "Unknown package" wording used by app_data's `pm clear` handling
    # — grantRuntimePermission resolves the package before anything else.
    if "Unknown package" in message:
        raise PackageNotFoundError(message, details={"serial": serial, "package_name": package_name})
    # The platform's exact wording for a permission whose protection level
    # isn't "dangerous" (normal/signature/install-time permissions aren't
    # dynamically grantable at all).
    if "is not a changeable permission type" in message:
        raise NonRuntimePermissionError(
            message, details={"serial": serial, "package_name": package_name, "permission": permission}
        )
    # Either the permission name is unknown to the platform, or it's real
    # but this package's manifest never requests it — neither has anything
    # to grant against.
    if (
        "isn't requested by package" in message
        or "is not requested by" in message
        or "Unknown permission" in message
    ):
        raise PermissionNotDeclaredError(
            message, details={"serial": serial, "package_name": package_name, "permission": permission}
        )
    lowered = message.lower()
    if "policy" in lowered and ("fixed" in lowered or "restrict" in lowered):
        raise PermissionPolicyRestrictedError(
            message, details={"serial": serial, "package_name": package_name, "permission": permission}
        )
    if "Permission Denial" in message or "SecurityException" in message:
        raise PermissionDeniedError(
            message, details={"serial": serial, "package_name": package_name, "permission": permission}
        )
    raise BackendError(
        message,
        details={
            "serial": serial,
            "package_name": package_name,
            "permission": permission,
            "exit_code": result.exit_code,
        },
    )
