"""Layer 1 unit tests: BroadcastsService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    BackendError,
    ComponentNotFoundError,
    DeviceNotFoundError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.broadcasts.service import BroadcastExtra, BroadcastsService


@pytest.mark.asyncio
async def test_send_broadcast__minimal_success_reports_result_code() -> None:
    service = BroadcastsService(FakeBackend())

    result = await service.send_broadcast("emulator-5554", "android.intent.action.MY_ACTION")

    assert result.serial == "emulator-5554"
    assert result.action == "android.intent.action.MY_ACTION"
    assert result.component is None
    assert result.package is None
    assert result.user_id is None
    assert result.receiver_permission is None
    assert result.result_code == 0
    assert result.result_data is None
    assert result.result_extras is None


@pytest.mark.asyncio
async def test_send_broadcast__parses_result_data_and_extras_when_present() -> None:
    backend = FakeBackend(
        send_broadcast_result=CommandResult(
            stdout=(
                "Broadcasting: Intent { act=com.example.ACTION_FOO cmp=com.example/.Receiver }\n"
                'Broadcast completed: result=1, data="payload", extras: Bundle[{key=value}]\n'
            ),
            stderr="",
            exit_code=0,
            duration_ms=180.0,
        )
    )
    service = BroadcastsService(backend)

    result = await service.send_broadcast(
        "emulator-5554",
        "com.example.ACTION_FOO",
        component="com.example/.Receiver",
    )

    assert result.result_code == 1
    assert result.result_data == "payload"
    assert result.result_extras == "Bundle[{key=value}]"


@pytest.mark.asyncio
async def test_send_broadcast__sends_package_user_id_and_extras_flags() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = BroadcastsService(RecordingBackend())

    await service.send_broadcast(
        "emulator-5554",
        "com.example.ACTION_FOO",
        package="com.example",
        user_id=10,
        extras=[
            BroadcastExtra(key="count", value="3", type="int"),
            BroadcastExtra(key="enabled", value="true", type="bool"),
        ],
    )

    assert captured["command"] == (
        "am broadcast -a com.example.ACTION_FOO -p com.example --user 10 "
        "--ei count 3 --ez enabled true"
    )


@pytest.mark.asyncio
async def test_send_broadcast__sends_receiver_permission_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = BroadcastsService(RecordingBackend())

    result = await service.send_broadcast(
        "emulator-5554",
        "com.example.MY_ACTION",
        receiver_permission="com.example.MY_PERMISSION",
    )

    assert captured["command"] == (
        "am broadcast -a com.example.MY_ACTION --receiver-permission com.example.MY_PERMISSION"
    )
    assert result.receiver_permission == "com.example.MY_PERMISSION"


@pytest.mark.asyncio
async def test_send_broadcast__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        send_broadcast_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = BroadcastsService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.send_broadcast("bogus", "android.intent.action.MY_ACTION")


@pytest.mark.asyncio
async def test_send_broadcast__bad_component_raises_component_not_found() -> None:
    backend = FakeBackend(
        send_broadcast_result=CommandResult(
            stdout="", stderr="Error: Bad component name: not-a-component\n", exit_code=1, duration_ms=8.0
        )
    )
    service = BroadcastsService(backend)

    with pytest.raises(ComponentNotFoundError):
        await service.send_broadcast(
            "emulator-5554", "android.intent.action.MY_ACTION", component="not-a-component"
        )


@pytest.mark.asyncio
async def test_send_broadcast__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        send_broadcast_result=CommandResult(
            stdout="",
            stderr=(
                "java.lang.SecurityException: Permission Denial: not allowed to send broadcast "
                "android.intent.action.MY_ACTION from pid=1234, uid=2000\n"
            ),
            exit_code=1,
            duration_ms=12.0,
        )
    )
    service = BroadcastsService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.send_broadcast("emulator-5554", "android.intent.action.MY_ACTION")


@pytest.mark.asyncio
async def test_send_broadcast__unclassified_activity_manager_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        send_broadcast_result=CommandResult(
            stdout="", stderr="Error: Activity manager has died\n", exit_code=1, duration_ms=5.0
        )
    )
    service = BroadcastsService(backend)

    with pytest.raises(BackendError):
        await service.send_broadcast("emulator-5554", "android.intent.action.MY_ACTION")


@pytest.mark.asyncio
async def test_send_broadcast__unexpected_success_output_raises_backend_error() -> None:
    backend = FakeBackend(
        send_broadcast_result=CommandResult(stdout="", stderr="", exit_code=0, duration_ms=5.0)
    )
    service = BroadcastsService(backend)

    with pytest.raises(BackendError):
        await service.send_broadcast("emulator-5554", "android.intent.action.MY_ACTION")
