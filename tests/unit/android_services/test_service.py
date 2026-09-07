"""Layer 1 unit tests: AndroidServicesService against FakeBackend directly —
no MCP registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    BackgroundServiceRestrictedError,
    ComponentNotFoundError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.android_services.service import (
    AndroidServicesService,
    StartForegroundServiceResult,
    StopServiceResult,
)


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


# --- start_foreground_service --------------------------------------------------


class _ShellRecordingBackend(FakeBackend):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.last_shell_command: str | None = None

    async def shell(self, serial: str, command: str) -> CommandResult:
        self.last_shell_command = command
        return await super().shell(serial, command)


@pytest.mark.asyncio
async def test_start_foreground_service__constructs_command_and_succeeds() -> None:
    backend = _ShellRecordingBackend()
    service = AndroidServicesService(backend)

    result = await service.start_foreground_service(
        "emulator-5554", "com.example.app/.MyFgService"
    )

    assert backend.last_shell_command == (
        "am start-foreground-service -n com.example.app/.MyFgService"
    )
    assert isinstance(result, StartForegroundServiceResult)
    assert result.component == "com.example.app/.MyFgService"
    assert result.user_id is None
    assert "Starting service:" in result.output


@pytest.mark.asyncio
async def test_start_foreground_service__sends_user_id_flag() -> None:
    backend = _ShellRecordingBackend()
    service = AndroidServicesService(backend)

    result = await service.start_foreground_service(
        "emulator-5554", "com.example.app/.MyFgService", user_id=10
    )

    assert backend.last_shell_command == (
        "am start-foreground-service -n com.example.app/.MyFgService --user 10"
    )
    assert result.user_id == 10


@pytest.mark.asyncio
async def test_start_foreground_service__empty_component_rejected_before_backend() -> None:
    backend = _ShellRecordingBackend()
    service = AndroidServicesService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.start_foreground_service("emulator-5554", "  ")

    assert backend.last_shell_command is None


@pytest.mark.asyncio
async def test_start_foreground_service__negative_user_id_rejected_before_backend() -> None:
    backend = _ShellRecordingBackend()
    service = AndroidServicesService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.start_foreground_service(
            "emulator-5554", "com.example.app/.MyFgService", user_id=-1
        )

    assert backend.last_shell_command is None


@pytest.mark.asyncio
async def test_start_foreground_service__bad_component_stack_trace_exit_zero_raises_component_not_found() -> (
    None
):
    # Verified live on a car AVD: exit 0 with a Java stack trace, not exit 1.
    backend = FakeBackend(
        start_foreground_service_result=CommandResult(
            stdout="",
            stderr=(
                "\nException occurred while executing 'start-foreground-service':\n"
                "java.lang.IllegalArgumentException: Bad component name: notacomponent\n"
            ),
            exit_code=0,
            duration_ms=5.0,
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(ComponentNotFoundError):
        await service.start_foreground_service("emulator-5554", "notacomponent")


@pytest.mark.asyncio
async def test_start_foreground_service__not_found_no_service_started_raises_component_not_found() -> (
    None
):
    backend = FakeBackend(
        start_foreground_service_result=CommandResult(
            stdout=(
                "Starting service: Intent { cmp=com.example.nope/.NoService }\n"
                "Error: Not found; no service started.\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=5.0,
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(ComponentNotFoundError):
        await service.start_foreground_service("emulator-5554", "com.example.nope/.NoService")


@pytest.mark.asyncio
async def test_start_foreground_service__fgs_restriction_raises_background_service_restricted() -> None:
    backend = FakeBackend(
        start_foreground_service_result=CommandResult(
            stdout=(
                "Starting service: Intent { cmp=com.example.app/.MyFgService }\n"
                "Error: Not allowed to start service Intent { cmp=com.example.app/.MyFgService }: "
                "app is in background uid ...\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=5.0,
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(BackgroundServiceRestrictedError):
        await service.start_foreground_service("emulator-5554", "com.example.app/.MyFgService")


@pytest.mark.asyncio
async def test_start_foreground_service__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        start_foreground_service_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.start_foreground_service("bogus", "com.example.app/.MyFgService")


@pytest.mark.asyncio
async def test_start_foreground_service__adb_unavailable_propagates() -> None:
    service = AndroidServicesService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.start_foreground_service("emulator-5554", "com.example.app/.MyFgService")


def test_start_foreground_service_result_summary() -> None:
    s = StartForegroundServiceResult(
        serial="emulator-5554",
        component="com.x/.Y",
        user_id=None,
        output="Starting service: Intent { cmp=com.x/.Y }\n",
    ).summary()
    assert s == "Started foreground service com.x/.Y on emulator-5554."


# --- stop_service -----------------------------------------------------------


@pytest.mark.asyncio
async def test_stop_service__running_service_stopped_true() -> None:
    backend = _ShellRecordingBackend()
    service = AndroidServicesService(backend)

    result = await service.stop_service("emulator-5554", "com.example.app/.MyService")

    assert backend.last_shell_command == "am stop-service -n com.example.app/.MyService"
    assert isinstance(result, StopServiceResult)
    assert result.stopped is True
    assert result.was_running is True


@pytest.mark.asyncio
async def test_stop_service__sends_user_id_flag() -> None:
    backend = _ShellRecordingBackend()
    service = AndroidServicesService(backend)

    result = await service.stop_service(
        "emulator-5554", "com.example.app/.MyService", user_id=10
    )

    assert backend.last_shell_command == "am stop-service -n com.example.app/.MyService --user 10"
    assert result.user_id == 10


@pytest.mark.asyncio
async def test_stop_service__not_running_exit_255_is_stopped_false_not_error() -> None:
    # Verified live on a car AVD: "was not running." comes with exit 255.
    backend = FakeBackend(
        stop_service_result=CommandResult(
            stdout=(
                "Stopping service: Intent { cmp=com.example.app/.MyService }\n"
                "Service not stopped: was not running.\n"
            ),
            stderr="",
            exit_code=255,
            duration_ms=5.0,
        )
    )
    service = AndroidServicesService(backend)

    result = await service.stop_service("emulator-5554", "com.example.app/.MyService")

    assert result.stopped is False
    assert result.was_running is False


@pytest.mark.asyncio
async def test_stop_service__unknown_component_reports_was_not_running_not_error() -> None:
    # `am stop-service` can't tell "no such component" from "not running".
    backend = FakeBackend(
        stop_service_result=CommandResult(
            stdout=(
                "Stopping service: Intent { cmp=com.example.nope/.NoService }\n"
                "Service not stopped: was not running.\n"
            ),
            stderr="",
            exit_code=255,
            duration_ms=5.0,
        )
    )
    service = AndroidServicesService(backend)

    result = await service.stop_service("emulator-5554", "com.example.nope/.NoService")

    assert result.stopped is False
    assert result.was_running is False


@pytest.mark.asyncio
async def test_stop_service__empty_component_rejected_before_backend() -> None:
    backend = _ShellRecordingBackend()
    service = AndroidServicesService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.stop_service("emulator-5554", "  ")

    assert backend.last_shell_command is None


@pytest.mark.asyncio
async def test_stop_service__negative_user_id_rejected_before_backend() -> None:
    backend = _ShellRecordingBackend()
    service = AndroidServicesService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.stop_service("emulator-5554", "com.example.app/.MyService", user_id=-1)

    assert backend.last_shell_command is None


@pytest.mark.asyncio
async def test_stop_service__malformed_component_raises_component_not_found() -> None:
    backend = FakeBackend(
        stop_service_result=CommandResult(
            stdout="",
            stderr=(
                "\nException occurred while executing 'stop-service':\n"
                "java.lang.IllegalArgumentException: Bad component name: notacomponent\n"
            ),
            exit_code=0,
            duration_ms=5.0,
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(ComponentNotFoundError):
        await service.stop_service("emulator-5554", "notacomponent")


@pytest.mark.asyncio
async def test_stop_service__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        stop_service_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.stop_service("bogus", "com.example.app/.MyService")


@pytest.mark.asyncio
async def test_stop_service__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        stop_service_result=CommandResult(
            stdout="",
            stderr=(
                "java.lang.SecurityException: Permission Denial: stopService "
                "from pid=1234, uid=2000\n"
            ),
            exit_code=1,
            duration_ms=5.0,
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.stop_service("emulator-5554", "com.example.app/.MyService")


@pytest.mark.asyncio
async def test_stop_service__unrecognized_error_line_raises_backend_error() -> None:
    backend = FakeBackend(
        stop_service_result=CommandResult(
            stdout="Error: something entirely unexpected\n", stderr="", exit_code=1, duration_ms=5.0
        )
    )
    service = AndroidServicesService(backend)

    with pytest.raises(BackendError):
        await service.stop_service("emulator-5554", "com.example.app/.MyService")


@pytest.mark.asyncio
async def test_stop_service__unrecognized_outcome_no_markers_is_was_running_none() -> None:
    backend = FakeBackend(
        stop_service_result=CommandResult(
            stdout="Stopping service: Intent { cmp=com.example.app/.MyService }\n",
            stderr="",
            exit_code=0,
            duration_ms=5.0,
        )
    )
    service = AndroidServicesService(backend)

    result = await service.stop_service("emulator-5554", "com.example.app/.MyService")

    assert result.stopped is False
    assert result.was_running is None


@pytest.mark.asyncio
async def test_stop_service__adb_unavailable_propagates() -> None:
    service = AndroidServicesService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.stop_service("emulator-5554", "com.example.app/.MyService")


def test_stop_service_result_summary_variants() -> None:
    stopped = StopServiceResult(
        serial="emulator-5554",
        component="com.x/.Y",
        user_id=None,
        stopped=True,
        was_running=True,
        output="",
    ).summary()
    assert stopped == "Stopped service com.x/.Y on emulator-5554."

    not_running = StopServiceResult(
        serial="emulator-5554",
        component="com.x/.Y",
        user_id=None,
        stopped=False,
        was_running=False,
        output="",
    ).summary()
    assert "was not running" in not_running
