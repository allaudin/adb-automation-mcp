"""Layer 1 unit tests: ProcessesService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import BackendError, DeviceNotFoundError, PermissionDeniedError
from adb_automation_mcp.modules.processes.service import ProcessesService


@pytest.mark.asyncio
async def test_force_stop_app__success_with_empty_stdout() -> None:
    service = ProcessesService(FakeBackend())

    result = await service.force_stop_app("emulator-5554", "com.example.app")

    assert result.serial == "emulator-5554"
    assert result.package_name == "com.example.app"
    assert result.user_id is None
    assert result.output == ""


@pytest.mark.asyncio
async def test_force_stop_app__sends_user_id_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = ProcessesService(RecordingBackend())

    result = await service.force_stop_app("emulator-5554", "com.example.app", user_id=10)

    assert captured["command"] == "am force-stop --user 10 com.example.app"
    assert result.user_id == 10


@pytest.mark.asyncio
async def test_force_stop_app__nonexistent_package_still_succeeds() -> None:
    # Real, documented am behavior: forceStopPackage() doesn't validate that
    # the package is installed — it's a silent no-op with exit 0/empty
    # stdout when there's nothing to stop, same as a real match.
    service = ProcessesService(FakeBackend())

    result = await service.force_stop_app("emulator-5554", "com.example.does.not.exist")

    assert result.package_name == "com.example.does.not.exist"
    assert result.output == ""


@pytest.mark.asyncio
async def test_force_stop_app__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        force_stop_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = ProcessesService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.force_stop_app("bogus", "com.example.app")


@pytest.mark.asyncio
async def test_force_stop_app__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        force_stop_result=CommandResult(
            stdout="",
            stderr=(
                "java.lang.SecurityException: Permission Denial: forceStopPackage() from "
                "pid=1234, uid=2000 requires android.permission.FORCE_STOP_PACKAGES\n"
            ),
            exit_code=1,
            duration_ms=12.0,
        )
    )
    service = ProcessesService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.force_stop_app("emulator-5554", "com.example.app")


@pytest.mark.asyncio
async def test_force_stop_app__unclassified_backend_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        force_stop_result=CommandResult(
            stdout="", stderr="Error: Activity manager has died\n", exit_code=1, duration_ms=5.0
        )
    )
    service = ProcessesService(backend)

    with pytest.raises(BackendError):
        await service.force_stop_app("emulator-5554", "com.example.app")
