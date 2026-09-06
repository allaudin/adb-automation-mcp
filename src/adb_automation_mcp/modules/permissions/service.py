"""Domain logic for the permissions module: granting (`adb shell pm grant`) and
revoking (`adb shell pm revoke`) an Android runtime permission for an installed
package, and reading a package's full permission picture from
`adb shell dumpsys package` (get_package_permissions).
"""

from __future__ import annotations

import shlex

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.dumpsys_package import (
    find_package_block,
    package_present,
    parse_declared_permissions,
    parse_install_permissions,
    parse_requested_permissions,
    parse_runtime_permissions_by_user,
)
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
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


class RevokePermissionResult(BaseModel):
    """Outcome of revoking a runtime permission (`adb shell pm revoke`).

    The natural counterpart to GrantPermissionResult. Verified live on a car
    AVD: a successful revoke produces no stdout and exits 0, and it's
    idempotent — revoking a permission that's already denied (or one the
    package doesn't request at all) is also a silent exit 0. Genuine failures
    (unknown package, a non-runtime permission, an unknown permission name, a
    policy-fixed state, a SecurityException) come back on a non-zero exit and
    are classified by _raise_for_grant_failure, shared with grant. success is
    always True here for the same reason as GrantPermissionResult.success.
    """

    serial: str
    package_name: str
    permission: str
    user_id: int | None
    success: bool
    output: str

    def summary(self) -> str:
        return f"Revoked {self.permission} from {self.package_name} on {self.serial}."


class PermissionGrant(BaseModel):
    """One permission and whether it's currently granted, plus any per-grant
    flags dumpsys reports (USER_SET, SYSTEM_FIXED, POLICY_FIXED,
    GRANTED_BY_DEFAULT, RESTRICTION_UPGRADE_EXEMPT, …). flags is empty for
    install-time permissions, which dumpsys prints without one.
    """

    name: str
    granted: bool
    flags: list[str] = []


class DeclaredPermission(BaseModel):
    """A permission the package's own manifest defines (not one it uses)."""

    name: str
    protection: str | None


class PackageUserPermissions(BaseModel):
    """Runtime permission grant state for one Android user."""

    user_id: int
    permissions: list[PermissionGrant]


class PackagePermissions(BaseModel):
    """A package-focused permission snapshot parsed from `dumpsys package`.

    Read-only companion to grant_permission / revoke_permission: what a package
    asks for, what it defines, and what's actually granted — install-time
    (package-wide) and runtime (per Android user, with flags). Every list is
    best-effort and may be empty on a build whose dumpsys omits that section.
    """

    serial: str
    package_name: str
    requested_permissions: list[str]
    declared_permissions: list[DeclaredPermission]
    install_permissions: list[PermissionGrant]
    runtime_permissions: list[PackageUserPermissions]

    def summary(self) -> str:
        runtime_granted = sum(
            1 for u in self.runtime_permissions for p in u.permissions if p.granted
        )
        install_granted = sum(1 for p in self.install_permissions if p.granted)
        return (
            f"{self.package_name} on {self.serial}: {len(self.requested_permissions)} requested, "
            f"{install_granted} install-time granted, {runtime_granted} runtime granted "
            f"across {len(self.runtime_permissions)} user(s)."
        )


class PermissionsService:
    """Grants and revokes Android runtime permissions for an installed package,
    and reports a package's full permission picture.
    """

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def get_package_permissions(
        self, serial: str, package_name: str
    ) -> PackagePermissions:
        if not package_name.strip():
            raise InvalidArgumentError(
                "package_name must not be empty.", details={"serial": serial}
            )

        result = await self._backend.shell(serial, f"dumpsys package {shlex.quote(package_name)}")
        _raise_for_shell_failure(serial, result)

        text = result.stdout
        if not package_present(text, package_name):
            raise PackageNotFoundError(
                f"dumpsys package has no record of {package_name} on {serial}.",
                details={"serial": serial, "package_name": package_name},
            )

        block = find_package_block(text, package_name) or []
        runtime_by_user = parse_runtime_permissions_by_user(text)
        return PackagePermissions(
            serial=serial,
            package_name=package_name,
            requested_permissions=parse_requested_permissions(block),
            declared_permissions=[
                DeclaredPermission(name=n, protection=p)
                for n, p in parse_declared_permissions(block)
            ],
            install_permissions=[
                PermissionGrant(name=n, granted=g) for n, g in parse_install_permissions(block)
            ],
            runtime_permissions=[
                PackageUserPermissions(
                    user_id=uid,
                    permissions=[
                        PermissionGrant(name=n, granted=g, flags=f)
                        for n, g, f in runtime_by_user[uid]
                    ],
                )
                for uid in sorted(runtime_by_user)
            ],
        )

    async def grant_permission(
        self, serial: str, package_name: str, permission: str, user_id: int | None = None
    ) -> GrantPermissionResult:
        result = await self._run_grant_revoke("grant", serial, package_name, permission, user_id)
        return GrantPermissionResult(
            serial=serial,
            package_name=package_name,
            permission=permission,
            user_id=user_id,
            success=True,
            output=result.stdout,
        )

    async def revoke_permission(
        self, serial: str, package_name: str, permission: str, user_id: int | None = None
    ) -> RevokePermissionResult:
        result = await self._run_grant_revoke("revoke", serial, package_name, permission, user_id)
        return RevokePermissionResult(
            serial=serial,
            package_name=package_name,
            permission=permission,
            user_id=user_id,
            success=True,
            output=result.stdout,
        )

    async def _run_grant_revoke(
        self,
        action: str,
        serial: str,
        package_name: str,
        permission: str,
        user_id: int | None,
    ) -> CommandResult:
        if not package_name.strip():
            raise InvalidArgumentError("package_name must not be empty.", details={"serial": serial})
        if not permission.strip():
            raise InvalidArgumentError("permission must not be empty.", details={"serial": serial})
        if user_id is not None and user_id < 0:
            raise InvalidArgumentError(
                "user_id must be a non-negative integer.",
                details={"serial": serial, "user_id": user_id},
            )

        parts = ["pm", action]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        parts.extend([shlex.quote(package_name), shlex.quote(permission)])

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_grant_failure(serial, package_name, permission, result)
        return result


def _raise_for_shell_failure(serial: str, result: CommandResult) -> None:
    """Transport-level classification for a plain `adb shell` command (used by
    get_package_permissions, whose `dumpsys package` failures aren't the
    grant/revoke Failure-line shape).
    """
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})


def _raise_for_grant_failure(
    serial: str, package_name: str, permission: str, result: CommandResult
) -> None:
    combined = f"{result.stdout}\n{result.stderr}"
    # `pm grant`/`pm revoke` sometimes report a failure on a *zero* exit too
    # (verified live: "Failure [package not found]" with exit 0 when the package
    # resolves to a different Android user). Treat any Failure/Exception marker
    # as a failure regardless of exit code.
    has_failure_marker = "Failure [" in combined or "Exception occurred while executing" in combined
    if result.exit_code == 0 and not has_failure_marker:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's) — the adb-client rejects an unknown serial
    # before any command reaches a device.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    # "Unknown package" is the wording app_data's `pm clear` handling sees;
    # this build's `pm grant`/`pm revoke` instead print "Failure [package not
    # found]" / "Error: package not found" (verified live on a car AVD).
    if (
        "Unknown package" in message
        or "package not found" in message.lower()
    ):
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
