"""Layer 1 unit tests: PermissionsService against FakeBackend directly — no
MCP registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    NonRuntimePermissionError,
    PackageNotFoundError,
    PermissionDeniedError,
    PermissionNotDeclaredError,
    PermissionPolicyRestrictedError,
)
from adb_automation_mcp.modules.permissions.service import (
    PackagePermissions,
    PackageUserPermissions,
    PermissionGrant,
    PermissionsService,
    RevokePermissionResult,
)


@pytest.mark.asyncio
async def test_grant_permission__succeeds_with_no_stdout() -> None:
    service = PermissionsService(FakeBackend())

    result = await service.grant_permission(
        "emulator-5554", "com.example.app", "android.permission.CAMERA"
    )

    assert result.serial == "emulator-5554"
    assert result.package_name == "com.example.app"
    assert result.permission == "android.permission.CAMERA"
    assert result.user_id is None
    assert result.success is True
    assert result.output == ""


@pytest.mark.asyncio
async def test_grant_permission__sends_user_id_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PermissionsService(RecordingBackend())

    result = await service.grant_permission(
        "emulator-5554", "com.example.app", "android.permission.CAMERA", user_id=10
    )

    assert captured["command"] == (
        "pm grant --user 10 com.example.app android.permission.CAMERA"
    )
    assert result.user_id == 10


@pytest.mark.asyncio
async def test_grant_permission__omits_user_flag_when_not_given() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PermissionsService(RecordingBackend())

    await service.grant_permission("emulator-5554", "com.example.app", "android.permission.CAMERA")

    assert captured["command"] == "pm grant com.example.app android.permission.CAMERA"


@pytest.mark.asyncio
async def test_grant_permission__unknown_package_raises_package_not_found() -> None:
    backend = FakeBackend(
        grant_permission_result=CommandResult(
            stdout="",
            stderr="Error: java.lang.IllegalArgumentException: Unknown package: com.example.bogus\n",
            exit_code=1,
            duration_ms=20.0,
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(PackageNotFoundError):
        await service.grant_permission("emulator-5554", "com.example.bogus", "android.permission.CAMERA")


@pytest.mark.asyncio
async def test_grant_permission__not_requested_by_package_raises_permission_not_declared() -> None:
    backend = FakeBackend(
        grant_permission_result=CommandResult(
            stdout="",
            stderr=(
                "Error: java.lang.SecurityException: Permission android.permission.CAMERA "
                "isn't requested by package com.example.app\n"
            ),
            exit_code=1,
            duration_ms=20.0,
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(PermissionNotDeclaredError):
        await service.grant_permission("emulator-5554", "com.example.app", "android.permission.CAMERA")


@pytest.mark.asyncio
async def test_grant_permission__unknown_permission_raises_permission_not_declared() -> None:
    backend = FakeBackend(
        grant_permission_result=CommandResult(
            stdout="",
            stderr="Error: java.lang.IllegalArgumentException: Unknown permission: com.example.BOGUS\n",
            exit_code=1,
            duration_ms=15.0,
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(PermissionNotDeclaredError):
        await service.grant_permission("emulator-5554", "com.example.app", "com.example.BOGUS")


@pytest.mark.asyncio
async def test_grant_permission__non_runtime_permission_raises_non_runtime_permission() -> None:
    backend = FakeBackend(
        grant_permission_result=CommandResult(
            stdout="",
            stderr=(
                "Error: java.lang.SecurityException: android.permission.INTERNET "
                "is not a changeable permission type\n"
            ),
            exit_code=1,
            duration_ms=15.0,
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(NonRuntimePermissionError):
        await service.grant_permission("emulator-5554", "com.example.app", "android.permission.INTERNET")


@pytest.mark.asyncio
async def test_grant_permission__policy_fixed_raises_permission_policy_restricted() -> None:
    backend = FakeBackend(
        grant_permission_result=CommandResult(
            stdout="",
            stderr=(
                "Error: java.lang.SecurityException: Cannot grant permission "
                "android.permission.CAMERA to com.example.app: policy fixed\n"
            ),
            exit_code=1,
            duration_ms=15.0,
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(PermissionPolicyRestrictedError):
        await service.grant_permission("emulator-5554", "com.example.app", "android.permission.CAMERA")


@pytest.mark.asyncio
async def test_grant_permission__generic_security_exception_raises_permission_denied() -> None:
    backend = FakeBackend(
        grant_permission_result=CommandResult(
            stdout="",
            stderr=(
                "Error: java.lang.SecurityException: Neither user 2000 nor current process has "
                "android.permission.GRANT_RUNTIME_PERMISSIONS\n"
            ),
            exit_code=1,
            duration_ms=15.0,
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.grant_permission("emulator-5554", "com.example.app", "android.permission.CAMERA")


@pytest.mark.asyncio
async def test_grant_permission__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        grant_permission_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.grant_permission("bogus", "com.example.app", "android.permission.CAMERA")


@pytest.mark.asyncio
async def test_grant_permission__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        grant_permission_result=CommandResult(
            stdout="", stderr="Error: some other unclassified failure\n", exit_code=1, duration_ms=5.0
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(BackendError):
        await service.grant_permission("emulator-5554", "com.example.app", "android.permission.CAMERA")


# --- revoke_permission ------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_permission__succeeds_with_no_stdout() -> None:
    service = PermissionsService(FakeBackend())

    result = await service.revoke_permission(
        "emulator-5554", "com.example.app", "android.permission.CAMERA"
    )

    assert isinstance(result, RevokePermissionResult)
    assert result.success is True
    assert result.output == ""
    assert result.permission == "android.permission.CAMERA"


@pytest.mark.asyncio
async def test_revoke_permission__constructs_pm_revoke_command_with_user_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PermissionsService(RecordingBackend())

    await service.revoke_permission(
        "emulator-5554", "com.example.app", "android.permission.CAMERA", user_id=10
    )

    assert captured["command"] == "pm revoke --user 10 com.example.app android.permission.CAMERA"


@pytest.mark.asyncio
async def test_revoke_permission__omits_user_flag_when_not_given() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PermissionsService(RecordingBackend())

    await service.revoke_permission("emulator-5554", "com.example.app", "android.permission.CAMERA")

    assert captured["command"] == "pm revoke com.example.app android.permission.CAMERA"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "pkg,perm", [("", "android.permission.CAMERA"), ("com.example.app", "  ")]
)
async def test_revoke_permission__empty_args_rejected_before_backend(pkg: str, perm: str) -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PermissionsService(RecordingBackend())

    with pytest.raises(InvalidArgumentError):
        await service.revoke_permission("emulator-5554", pkg, perm)

    assert "command" not in captured


@pytest.mark.asyncio
async def test_revoke_permission__negative_user_id_rejected_before_backend() -> None:
    service = PermissionsService(FakeBackend())

    with pytest.raises(InvalidArgumentError):
        await service.revoke_permission(
            "emulator-5554", "com.example.app", "android.permission.CAMERA", user_id=-1
        )


@pytest.mark.asyncio
async def test_revoke_permission__failure_marker_on_zero_exit_is_still_a_failure() -> None:
    # Verified live: `pm revoke` can print "Failure [package not found]" with
    # exit 0 when the package resolves to a different Android user.
    backend = FakeBackend(
        revoke_permission_result=CommandResult(
            stdout="Failure [package not found]\nError: package not found\n",
            stderr="",
            exit_code=0,
            duration_ms=5.0,
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(PackageNotFoundError):
        await service.revoke_permission("emulator-5554", "com.example.app", "android.permission.CAMERA")


@pytest.mark.asyncio
async def test_revoke_permission__non_runtime_permission_raises_non_runtime_permission() -> None:
    backend = FakeBackend(
        revoke_permission_result=CommandResult(
            stdout="",
            stderr=(
                "\nException occurred while executing 'revoke':\n"
                "java.lang.SecurityException: Permission android.permission.INTERNET requested by "
                "package com.example.app is not a changeable permission type\n"
            ),
            exit_code=255,
            duration_ms=5.0,
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(NonRuntimePermissionError):
        await service.revoke_permission("emulator-5554", "com.example.app", "android.permission.INTERNET")


@pytest.mark.asyncio
async def test_revoke_permission__unknown_permission_raises_permission_not_declared() -> None:
    backend = FakeBackend(
        revoke_permission_result=CommandResult(
            stdout="",
            stderr=(
                "\nException occurred while executing 'revoke':\n"
                "java.lang.IllegalArgumentException: Unknown permission android.permission.NOT_REAL\n"
            ),
            exit_code=255,
            duration_ms=5.0,
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(PermissionNotDeclaredError):
        await service.revoke_permission("emulator-5554", "com.example.app", "android.permission.NOT_REAL")


@pytest.mark.asyncio
async def test_revoke_permission__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        revoke_permission_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.revoke_permission("bogus", "com.example.app", "android.permission.CAMERA")


@pytest.mark.asyncio
async def test_revoke_permission__adb_unavailable_propagates() -> None:
    service = PermissionsService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.revoke_permission("emulator-5554", "com.example.app", "android.permission.CAMERA")


def test_revoke_permission_result_summary() -> None:
    s = RevokePermissionResult(
        serial="emulator-5554",
        package_name="com.x",
        permission="android.permission.CAMERA",
        user_id=None,
        success=True,
        output="",
    ).summary()
    assert s == "Revoked android.permission.CAMERA from com.x on emulator-5554."


# --- get_package_permissions -----------------------------------------------


class _ShellRecordingBackend(FakeBackend):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.last_shell_command: str | None = None

    async def shell(self, serial: str, command: str) -> CommandResult:
        self.last_shell_command = command
        return await super().shell(serial, command)


@pytest.mark.asyncio
async def test_get_package_permissions__constructs_dumpsys_command_and_parses_fixture() -> None:
    backend = _ShellRecordingBackend()
    service = PermissionsService(backend)

    info = await service.get_package_permissions("emulator-5554", "com.example.thirdparty")

    assert backend.last_shell_command == "dumpsys package com.example.thirdparty"
    assert isinstance(info, PackagePermissions)
    assert info.requested_permissions == [
        "android.permission.INTERNET",
        "android.permission.ACCESS_NETWORK_STATE",
        "android.permission.CAMERA",
        "android.permission.ACCESS_FINE_LOCATION",
    ]
    assert [(d.name, d.protection) for d in info.declared_permissions] == [
        ("com.example.thirdparty.CUSTOM", "signature")
    ]
    assert [(p.name, p.granted) for p in info.install_permissions] == [
        ("android.permission.INTERNET", True),
        ("android.permission.ACCESS_NETWORK_STATE", True),
    ]


@pytest.mark.asyncio
async def test_get_package_permissions__runtime_permissions_grouped_by_user_with_flags() -> None:
    service = PermissionsService(FakeBackend())

    info = await service.get_package_permissions("emulator-5554", "com.example.thirdparty")

    assert [u.user_id for u in info.runtime_permissions] == [0]
    perms = {p.name: p for p in info.runtime_permissions[0].permissions}
    assert perms["android.permission.CAMERA"].granted is True
    assert perms["android.permission.CAMERA"].flags == ["USER_SET"]
    assert perms["android.permission.ACCESS_FINE_LOCATION"].granted is False
    assert perms["android.permission.ACCESS_FINE_LOCATION"].flags == []


@pytest.mark.asyncio
async def test_get_package_permissions__unknown_package_raises_package_not_found() -> None:
    backend = FakeBackend(
        dumpsys_package_result=CommandResult(
            stdout="Unable to find package: com.zzz.nope\n", stderr="", exit_code=0, duration_ms=5.0
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(PackageNotFoundError):
        await service.get_package_permissions("emulator-5554", "com.zzz.nope")


@pytest.mark.asyncio
async def test_get_package_permissions__empty_package_rejected_before_backend() -> None:
    backend = _ShellRecordingBackend()
    service = PermissionsService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.get_package_permissions("emulator-5554", "   ")

    assert backend.last_shell_command is None


@pytest.mark.asyncio
async def test_get_package_permissions__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        dumpsys_package_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    service = PermissionsService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.get_package_permissions("bogus", "com.example.app")


@pytest.mark.asyncio
async def test_get_package_permissions__malformed_block_does_not_crash() -> None:
    backend = FakeBackend(
        dumpsys_package_result=CommandResult(
            stdout="Packages:\n  Package [com.example.app] (aa):\n    <<< junk >>>\n",
            stderr="",
            exit_code=0,
            duration_ms=5.0,
        )
    )
    service = PermissionsService(backend)

    info = await service.get_package_permissions("emulator-5554", "com.example.app")

    assert info.requested_permissions == []
    assert info.install_permissions == []
    assert info.runtime_permissions == []


@pytest.mark.asyncio
async def test_get_package_permissions__adb_unavailable_propagates() -> None:
    service = PermissionsService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.get_package_permissions("emulator-5554", "com.example.app")


def test_package_permissions_summary_counts_grants() -> None:
    s = PackagePermissions(
        serial="emulator-5554",
        package_name="com.x",
        requested_permissions=["a", "b", "c"],
        declared_permissions=[],
        install_permissions=[PermissionGrant(name="a", granted=True)],
        runtime_permissions=[
            PackageUserPermissions(
                user_id=0,
                permissions=[
                    PermissionGrant(name="b", granted=True, flags=["USER_SET"]),
                    PermissionGrant(name="c", granted=False),
                ],
            )
        ],
    ).summary()
    assert "3 requested" in s
    assert "1 install-time granted" in s
    assert "1 runtime granted across 1 user(s)" in s
