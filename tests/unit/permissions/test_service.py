"""Layer 1 unit tests: PermissionsService against FakeBackend directly — no
MCP registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    NonRuntimePermissionError,
    PackageNotFoundError,
    PermissionDeniedError,
    PermissionNotDeclaredError,
    PermissionPolicyRestrictedError,
)
from adb_automation_mcp.modules.permissions.service import PermissionsService


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
