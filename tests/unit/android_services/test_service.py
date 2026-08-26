"""Layer 1 unit tests: AndroidServicesService against FakeBackend directly —
no MCP registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import (
    BackendError,
    BackgroundServiceRestrictedError,
    ComponentNotFoundError,
    DeviceNotFoundError,
    PermissionDeniedError,
)
from adb_mcp.modules.android_services.service import AndroidServicesService


@pytest.mark.asyncio
async def test_start_service__normal_start_succeeds() -> None:
    service = AndroidServicesService(FakeBackend())

    result = await service.start_service("emulator-5554", "com.example.app/.MyService")

    assert result.serial == "emulator-5554"
    assert result.component == "com.example.app/.MyService"
    assert result.user_id is None


@pytest.mark.asyncio
async def test_start_service__sends_user_id_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = AndroidServicesService(RecordingBackend())

    result = await service.start_service("emulator-5554", "com.example.app/.MyService", user_id=10)

    assert captured["command"] == "am start-service -n com.example.app/.MyService --user 10"
    assert result.user_id == 10


@pytest.mark.asyncio
async def test_start_service__component_does_not_exist_raises_component_not_found() -> None:
    backend = FakeBackend(
        start_service_result=CommandResult(
            stdout="Starting service: Intent { cmp=com.example.app/.Bogus }\n",
            stderr="Error: Not found; no service started.\n",
            exit_code=0,
            duration_ms=40.0,
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(ComponentNotFoundError):
        await service.start_service("emulator-5554", "com.example.app/.Bogus")


@pytest.mark.asyncio
async def test_start_service__malformed_component_raises_component_not_found() -> None:
    backend = FakeBackend(
        start_service_result=CommandResult(
            stdout="", stderr="Error: Bad component name: not-a-component\n", exit_code=1, duration_ms=8.0
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(ComponentNotFoundError):
        await service.start_service("emulator-5554", "not-a-component")


@pytest.mark.asyncio
async def test_start_service__requires_permission_raises_permission_denied() -> None:
    backend = FakeBackend(
        start_service_result=CommandResult(
            stdout="Starting service: Intent { cmp=com.example.app/.MyService }\n",
            stderr="Error: Requires permission com.example.app.permission.BIND_MY_SERVICE\n",
            exit_code=0,
            duration_ms=35.0,
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.start_service("emulator-5554", "com.example.app/.MyService")


@pytest.mark.asyncio
async def test_start_service__security_exception_permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        start_service_result=CommandResult(
            stdout="",
            stderr=(
                "java.lang.SecurityException: Permission Denial: starting Intent "
                "{ cmp=com.example.app/.MyService } from null (pid=1234, uid=2000)\n"
            ),
            exit_code=1,
            duration_ms=12.0,
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.start_service("emulator-5554", "com.example.app/.MyService")


@pytest.mark.asyncio
async def test_start_service__background_restriction_raises_background_service_restricted() -> None:
    backend = FakeBackend(
        start_service_result=CommandResult(
            stdout="Starting service: Intent { cmp=com.example.app/.MyService }\n",
            stderr=(
                "Error: java.lang.IllegalStateException: Not allowed to start service Intent "
                "{ cmp=com.example.app/.MyService }: app is in background uid UidRecord{...}\n"
            ),
            exit_code=0,
            duration_ms=45.0,
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(BackgroundServiceRestrictedError):
        await service.start_service("emulator-5554", "com.example.app/.MyService")


@pytest.mark.asyncio
async def test_start_service__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        start_service_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.start_service("bogus", "com.example.app/.MyService")


@pytest.mark.asyncio
async def test_start_service__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        start_service_result=CommandResult(
            stdout="", stderr="Error: Activity manager has died\n", exit_code=1, duration_ms=5.0
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(BackendError):
        await service.start_service("emulator-5554", "com.example.app/.MyService")


@pytest.mark.asyncio
async def test_start_service__unclassified_business_logic_error_raises_backend_error() -> None:
    backend = FakeBackend(
        start_service_result=CommandResult(
            stdout="Starting service: Intent { cmp=com.example.app/.MyService }\n",
            stderr="Error: some other unclassified failure\n",
            exit_code=0,
            duration_ms=20.0,
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(BackendError):
        await service.start_service("emulator-5554", "com.example.app/.MyService")
