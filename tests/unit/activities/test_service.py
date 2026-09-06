"""Layer 1 unit tests: ActivitiesService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    ComponentNotFoundError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.activities.service import ActivitiesService, ResolvedActivity


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


# --- resolve_activity ------------------------------------------------------


class _ShellRecordingBackend(FakeBackend):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.last_shell_command: str | None = None

    async def shell(self, serial: str, command: str) -> CommandResult:
        self.last_shell_command = command
        return await super().shell(serial, command)


@pytest.mark.asyncio
async def test_resolve_activity__action_and_category_map_to_brief_command() -> None:
    backend = _ShellRecordingBackend()
    service = ActivitiesService(backend)

    result = await service.resolve_activity(
        "emulator-5554",
        action="android.intent.action.MAIN",
        categories=["android.intent.category.HOME"],
    )

    assert backend.last_shell_command == (
        "cmd package resolve-activity --brief -a android.intent.action.MAIN "
        "-c android.intent.category.HOME"
    )
    assert isinstance(result, ResolvedActivity)
    assert result.resolved is True
    assert result.component == "com.android.car.carlauncher/.CarLauncher"
    assert result.package_name == "com.android.car.carlauncher"
    assert result.activity_class == ".CarLauncher"
    assert result.is_default is True
    assert result.match == "0x108000"
    assert result.priority == 0


@pytest.mark.asyncio
async def test_resolve_activity__all_intent_fields_map_to_flags_in_order() -> None:
    backend = _ShellRecordingBackend()
    service = ActivitiesService(backend)

    await service.resolve_activity(
        "emulator-5554",
        action="android.intent.action.VIEW",
        data_uri="https://example.com",
        mime_type="text/html",
        categories=["c1", "c2"],
        component="com.x/.Y",
        package_name="com.x",
        user_id=10,
    )

    assert backend.last_shell_command == (
        "cmd package resolve-activity --brief --user 10 "
        "-a android.intent.action.VIEW -d https://example.com -t text/html "
        "-c c1 -c c2 -n com.x/.Y -p com.x"
    )


@pytest.mark.asyncio
async def test_resolve_activity__no_intent_fields_rejected_before_backend() -> None:
    backend = _ShellRecordingBackend()
    service = ActivitiesService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.resolve_activity("emulator-5554")

    assert backend.last_shell_command is None


@pytest.mark.asyncio
async def test_resolve_activity__negative_user_id_rejected_before_backend() -> None:
    backend = _ShellRecordingBackend()
    service = ActivitiesService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.resolve_activity("emulator-5554", action="a", user_id=-1)

    assert backend.last_shell_command is None


@pytest.mark.asyncio
async def test_resolve_activity__no_match_is_resolved_false_not_error() -> None:
    backend = FakeBackend(
        resolve_activity_result=CommandResult(
            stdout="No activity found\n", stderr="", exit_code=0, duration_ms=5.0
        )
    )
    service = ActivitiesService(backend)

    result = await service.resolve_activity("emulator-5554", action="com.bogus.NOPE")

    assert result.resolved is False
    assert result.component is None
    assert result.is_default is None


@pytest.mark.asyncio
async def test_resolve_activity__explicit_component_that_exists_parses_non_default() -> None:
    backend = FakeBackend(
        resolve_activity_result=CommandResult(
            stdout=(
                "priority=0 preferredOrder=0 match=0x0 specificIndex=-1 isDefault=false\n"
                "com.android.car.carlauncher/.CarLauncher\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=5.0,
        )
    )
    service = ActivitiesService(backend)

    result = await service.resolve_activity(
        "emulator-5554", component="com.android.car.carlauncher/.CarLauncher"
    )

    assert result.resolved is True
    assert result.is_default is False
    assert result.match == "0x0"


@pytest.mark.asyncio
async def test_resolve_activity__bad_component_name_raises_invalid_argument() -> None:
    backend = FakeBackend(
        resolve_activity_result=CommandResult(
            stdout="",
            stderr=(
                "\nException occurred while executing 'resolve-activity':\n"
                "java.lang.IllegalArgumentException: Bad component name: notacomponent\n"
                "\tat android.content.Intent.parseCommandArgs(Intent.java:9232)\n"
            ),
            exit_code=0,
            duration_ms=5.0,
        )
    )
    service = ActivitiesService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.resolve_activity("emulator-5554", component="notacomponent")


@pytest.mark.asyncio
async def test_resolve_activity__unknown_option_raises_backend_error() -> None:
    backend = FakeBackend(
        resolve_activity_result=CommandResult(
            stdout="",
            stderr=(
                "\nException occurred while executing 'resolve-activity':\n"
                "java.lang.IllegalArgumentException: Unknown option: --brief\n"
            ),
            exit_code=0,
            duration_ms=5.0,
        )
    )
    service = ActivitiesService(backend)

    with pytest.raises(BackendError):
        await service.resolve_activity("emulator-5554", action="a")


@pytest.mark.asyncio
async def test_resolve_activity__unrecognized_output_raises_backend_error() -> None:
    backend = FakeBackend(
        resolve_activity_result=CommandResult(
            stdout="totally unexpected blah\n", stderr="", exit_code=0, duration_ms=5.0
        )
    )
    service = ActivitiesService(backend)

    with pytest.raises(BackendError):
        await service.resolve_activity("emulator-5554", action="a")


@pytest.mark.asyncio
async def test_resolve_activity__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        resolve_activity_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    service = ActivitiesService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.resolve_activity("bogus", action="a")


@pytest.mark.asyncio
async def test_resolve_activity__adb_unavailable_propagates() -> None:
    service = ActivitiesService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.resolve_activity("emulator-5554", action="a")


def test_resolved_activity_summary_variants() -> None:
    assert "No activity resolves" in ResolvedActivity(
        serial="emulator-5554",
        resolved=False,
        component=None,
        package_name=None,
        activity_class=None,
        is_default=None,
        match=None,
        priority=None,
    ).summary()

    s = ResolvedActivity(
        serial="emulator-5554",
        resolved=True,
        component="com.x/.Y",
        package_name="com.x",
        activity_class=".Y",
        is_default=True,
        match="0x108000",
        priority=0,
    ).summary()
    assert "com.x/.Y" in s
    assert "(default)" in s
