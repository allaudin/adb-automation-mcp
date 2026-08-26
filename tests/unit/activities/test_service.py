"""Layer 1 unit tests: ActivitiesService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import (
    BackendError,
    ComponentNotFoundError,
    DeviceNotFoundError,
    PermissionDeniedError,
)
from adb_mcp.modules.activities.service import ActivitiesService


@pytest.mark.asyncio
async def test_start_activity__normal_launch_reports_success() -> None:
    service = ActivitiesService(FakeBackend())

    result = await service.start_activity("emulator-5554", "com.example.app/.MainActivity")

    assert result.serial == "emulator-5554"
    assert result.component == "com.example.app/.MainActivity"
    assert result.success is True
    assert result.user_id is None
    assert result.display_id is None
    assert result.wait_for_launch is False
    assert result.activity is None
    assert result.status is None
    assert result.error_type is None
    assert result.error_message is None


@pytest.mark.asyncio
async def test_start_activity__display_specific_launch_sends_display_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = ActivitiesService(RecordingBackend())

    result = await service.start_activity(
        "emulator-5554", "com.example.app/.MainActivity", display_id=2
    )

    assert captured["command"] == "am start -n com.example.app/.MainActivity --display 2"
    assert result.display_id == 2
    assert result.success is True


@pytest.mark.asyncio
async def test_start_activity__user_specific_launch_sends_user_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = ActivitiesService(RecordingBackend())

    result = await service.start_activity(
        "emulator-5554", "com.example.app/.MainActivity", user_id=10
    )

    assert captured["command"] == "am start -n com.example.app/.MainActivity --user 10"
    assert result.user_id == 10
    assert result.success is True


@pytest.mark.asyncio
async def test_start_activity__wait_for_launch_parses_status_detail() -> None:
    backend = FakeBackend(
        start_activity_result=CommandResult(
            stdout=(
                "Starting: Intent { cmp=com.example.app/.MainActivity }\n"
                "Status: ok\n"
                "LaunchState: COLD\n"
                "Activity: com.example.app/.MainActivity\n"
                "TotalTime: 123\n"
                "WaitTime: 130\n"
                "Complete\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=250.0,
        )
    )
    service = ActivitiesService(backend)

    result = await service.start_activity(
        "emulator-5554", "com.example.app/.MainActivity", wait_for_launch=True
    )

    assert result.success is True
    assert result.status == "ok"
    assert result.launch_state == "COLD"
    assert result.activity == "com.example.app/.MainActivity"
    assert result.total_time_ms == 123
    assert result.wait_time_ms == 130


@pytest.mark.asyncio
async def test_start_activity__activity_manager_error_reports_failure_without_raising() -> None:
    backend = FakeBackend(
        start_activity_result=CommandResult(
            stdout=(
                "Starting: Intent { cmp=com.example.app/.Bogus }\n"
                "Error type 3\n"
                "Error: Activity class {com.example.app/com.example.app.Bogus} does not exist.\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=60.0,
        )
    )
    service = ActivitiesService(backend)

    result = await service.start_activity("emulator-5554", "com.example.app/.Bogus")

    assert result.success is False
    assert result.error_type == 3
    assert result.error_message == "Activity class {com.example.app/com.example.app.Bogus} does not exist."
    assert result.activity is None


@pytest.mark.asyncio
async def test_start_activity__malformed_component_raises_component_not_found() -> None:
    backend = FakeBackend(
        start_activity_result=CommandResult(
            stdout="", stderr="Error: Bad component name: not-a-component\n", exit_code=1, duration_ms=8.0
        )
    )
    service = ActivitiesService(backend)

    with pytest.raises(ComponentNotFoundError):
        await service.start_activity("emulator-5554", "not-a-component")


@pytest.mark.asyncio
async def test_start_activity__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        start_activity_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = ActivitiesService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.start_activity("bogus", "com.example.app/.MainActivity")


@pytest.mark.asyncio
async def test_start_activity__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        start_activity_result=CommandResult(
            stdout="",
            stderr=(
                "java.lang.SecurityException: Permission Denial: starting Intent "
                "{ cmp=com.example.app/.MainActivity } from null (pid=1234, uid=2000)\n"
            ),
            exit_code=1,
            duration_ms=12.0,
        )
    )
    service = ActivitiesService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.start_activity("emulator-5554", "com.example.app/.MainActivity")


@pytest.mark.asyncio
async def test_start_activity__unclassified_activity_manager_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        start_activity_result=CommandResult(
            stdout="", stderr="Error: Activity manager has died\n", exit_code=1, duration_ms=5.0
        )
    )
    service = ActivitiesService(backend)

    with pytest.raises(BackendError):
        await service.start_activity("emulator-5554", "com.example.app/.MainActivity")
