"""Layer 1 unit tests: ConnectionService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbTimeoutError,
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
)
from adb_automation_mcp.modules.connection.service import (
    AdbServerRestartResult,
    ConnectionService,
    ConnectResult,
    DeviceStateWaitResult,
    DisconnectResult,
    RestartAdbdAsRootResult,
    RestartAdbdAsShellResult,
)


@pytest.mark.asyncio
async def test_restart_adb_server__start_server_succeeds_reports_success_true() -> None:
    service = ConnectionService(FakeBackend())

    result = await service.restart_adb_server()

    assert result.success is True
    assert "daemon started successfully" in result.output


@pytest.mark.asyncio
async def test_restart_adb_server__start_server_fails_reports_success_false_with_output() -> None:
    backend = FakeBackend(
        start_server_result=CommandResult(
            stdout="", stderr="cannot bind to 127.0.0.1:5037", exit_code=1, duration_ms=10.0
        )
    )
    service = ConnectionService(backend)

    result = await service.restart_adb_server()

    assert result.success is False
    assert "cannot bind to 127.0.0.1:5037" in result.output


@pytest.mark.asyncio
async def test_restart_adb_server__adb_unavailable_propagates_as_error() -> None:
    service = ConnectionService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.restart_adb_server()


def test_restart_result_summary_mentions_success() -> None:
    assert "restarted successfully" in AdbServerRestartResult(success=True, output="").summary()


def test_restart_result_summary_includes_output_on_failure() -> None:
    summary = AdbServerRestartResult(success=False, output="cannot bind").summary()
    assert "failed" in summary
    assert "cannot bind" in summary


@pytest.mark.asyncio
async def test_connect__fresh_success_reports_success_true() -> None:
    service = ConnectionService(FakeBackend())

    result = await service.connect("192.168.1.50", 5555)

    assert result.success is True
    assert result.address == "192.168.1.50:5555"
    assert result.output == "connected to 192.168.1.50:5555"


@pytest.mark.asyncio
async def test_connect__already_connected_still_reports_success_true() -> None:
    backend = FakeBackend(
        connect_result=CommandResult(
            stdout="already connected to 192.168.1.50:5555\n", stderr="", exit_code=0, duration_ms=5.0
        )
    )
    service = ConnectionService(backend)

    result = await service.connect("192.168.1.50", 5555)

    assert result.success is True


@pytest.mark.asyncio
async def test_connect__connection_refused_reports_success_false_despite_exit_code_0() -> None:
    # Real adb behavior, verified live: `adb connect` always exits 0.
    backend = FakeBackend(
        connect_result=CommandResult(
            stdout="failed to connect to '192.168.1.50:5555': Connection refused\n",
            stderr="",
            exit_code=0,
            duration_ms=50.0,
        )
    )
    service = ConnectionService(backend)

    result = await service.connect("192.168.1.50", 5555)

    assert result.success is False
    assert result.address == "192.168.1.50:5555"
    assert "Connection refused" in result.output


@pytest.mark.asyncio
async def test_connect__protocol_handshake_failure_reports_success_false() -> None:
    # The other real failure wording observed live: no quotes, no reason, when
    # something answers on the port but doesn't speak the adb protocol.
    backend = FakeBackend(
        connect_result=CommandResult(
            stdout="failed to connect to 192.168.1.50:5555\n", stderr="", exit_code=0, duration_ms=50.0
        )
    )
    service = ConnectionService(backend)

    result = await service.connect("192.168.1.50", 5555)

    assert result.success is False


@pytest.mark.asyncio
async def test_connect__adb_unavailable_propagates_as_error() -> None:
    service = ConnectionService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.connect("192.168.1.50", 5555)


def test_connect_result_summary_mentions_address_on_success() -> None:
    summary = ConnectResult(success=True, address="1.2.3.4:5555", output="connected to 1.2.3.4:5555").summary()
    assert "Connected to 1.2.3.4:5555" in summary


def test_connect_result_summary_includes_output_on_failure() -> None:
    summary = ConnectResult(
        success=False, address="1.2.3.4:5555", output="failed to connect to '1.2.3.4:5555': Connection refused"
    ).summary()
    assert "Failed to connect" in summary
    assert "Connection refused" in summary


@pytest.mark.asyncio
async def test_disconnect__success_reports_success_true() -> None:
    service = ConnectionService(FakeBackend())

    result = await service.disconnect("192.168.1.50", 5555)

    assert result.success is True
    assert result.address == "192.168.1.50:5555"
    assert result.output == "disconnected 192.168.1.50:5555"


@pytest.mark.asyncio
async def test_disconnect__not_connected_reports_success_false() -> None:
    # Real adb behavior, verified live: exit 1, unlike connect's always-0.
    backend = FakeBackend(
        disconnect_result=CommandResult(
            stdout="", stderr="error: no such device '192.168.1.50:5555'", exit_code=1, duration_ms=10.0
        )
    )
    service = ConnectionService(backend)

    result = await service.disconnect("192.168.1.50", 5555)

    assert result.success is False
    assert "no such device" in result.output


@pytest.mark.asyncio
async def test_disconnect__adb_unavailable_propagates_as_error() -> None:
    service = ConnectionService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.disconnect("192.168.1.50", 5555)


def test_disconnect_result_summary_mentions_address_on_success() -> None:
    summary = DisconnectResult(success=True, address="1.2.3.4:5555", output="disconnected 1.2.3.4:5555").summary()
    assert "Disconnected from 1.2.3.4:5555" in summary


def test_disconnect_result_summary_includes_output_on_failure() -> None:
    summary = DisconnectResult(
        success=False, address="1.2.3.4:5555", output="error: no such device '1.2.3.4:5555'"
    ).summary()
    assert "Failed to disconnect" in summary
    assert "no such device" in summary


@pytest.mark.asyncio
async def test_restart_adbd_as_root__fresh_restart_reports_success_true_already_root_false() -> None:
    # FakeBackend's default root_result fixture: real "restarting adbd as root" wording.
    service = ConnectionService(FakeBackend())

    result = await service.restart_adbd_as_root("emulator-5554")

    assert result.success is True
    assert result.already_root is False
    assert result.serial == "emulator-5554"
    assert "restarting adbd as root" in result.output


@pytest.mark.asyncio
async def test_restart_adbd_as_root__already_root_reports_success_true_already_root_true() -> None:
    backend = FakeBackend(
        root_result=CommandResult(
            stdout="adbd is already running as root\n", stderr="", exit_code=0, duration_ms=50.0
        )
    )
    service = ConnectionService(backend)

    result = await service.restart_adbd_as_root("emulator-5554")

    assert result.success is True
    assert result.already_root is True


@pytest.mark.asyncio
async def test_restart_adbd_as_root__production_build_reports_success_false_despite_exit_code_0() -> None:
    # Real adb behavior, verified against documented wording: exits 0 even
    # when the build refuses, the same shape of ambiguity as `adb connect`.
    backend = FakeBackend(
        root_result=CommandResult(
            stdout="adbd cannot run as root in production builds\n", stderr="", exit_code=0, duration_ms=30.0
        )
    )
    service = ConnectionService(backend)

    result = await service.restart_adbd_as_root("emulator-5554")

    assert result.success is False
    assert result.already_root is False
    assert "production builds" in result.output


@pytest.mark.asyncio
async def test_restart_adbd_as_root__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        root_result=CommandResult(
            stdout="", stderr="adb: device 'bogus-serial' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = ConnectionService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.restart_adbd_as_root("bogus-serial")


@pytest.mark.asyncio
async def test_restart_adbd_as_root__adb_unavailable_propagates_as_error() -> None:
    service = ConnectionService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.restart_adbd_as_root("emulator-5554")


def test_restart_adbd_as_root_result_summary_mentions_serial_on_fresh_restart() -> None:
    summary = RestartAdbdAsRootResult(
        serial="emulator-5554", success=True, already_root=False, output="restarting adbd as root"
    ).summary()
    assert "restarted as root" in summary
    assert "emulator-5554" in summary


def test_restart_adbd_as_root_result_summary_mentions_already_root() -> None:
    summary = RestartAdbdAsRootResult(
        serial="emulator-5554", success=True, already_root=True, output="adbd is already running as root"
    ).summary()
    assert "already" in summary
    assert "emulator-5554" in summary


def test_restart_adbd_as_root_result_summary_includes_output_on_rejection() -> None:
    summary = RestartAdbdAsRootResult(
        serial="emulator-5554",
        success=False,
        already_root=False,
        output="adbd cannot run as root in production builds",
    ).summary()
    assert "cannot run as root" in summary
    assert "production builds" in summary


# --- restart_adbd_as_shell -------------------------------------------------


@pytest.mark.asyncio
async def test_restart_adbd_as_shell__fresh_restart_reports_success_already_shell_false() -> None:
    # FakeBackend default unroot fixture: real "restarting adbd as non root" wording,
    # captured from a live rootable car AVD.
    service = ConnectionService(FakeBackend())

    result = await service.restart_adbd_as_shell("emulator-5554")

    assert result.success is True
    assert result.already_shell is False
    assert result.serial == "emulator-5554"
    assert "restarting adbd as non root" in result.output


@pytest.mark.asyncio
async def test_restart_adbd_as_shell__already_non_root_reports_already_shell_true() -> None:
    # Real idempotent wording, captured live: adbd already non-root, exit 0.
    backend = FakeBackend(
        unroot_result=CommandResult(
            stdout="adbd not running as root\n", stderr="", exit_code=0, duration_ms=20.0
        )
    )
    service = ConnectionService(backend)

    result = await service.restart_adbd_as_shell("emulator-5554")

    assert result.success is True
    assert result.already_shell is True


@pytest.mark.asyncio
async def test_restart_adbd_as_shell__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        unroot_result=CommandResult(
            stdout="", stderr="adb: device 'bogus-serial' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = ConnectionService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.restart_adbd_as_shell("bogus-serial")


@pytest.mark.asyncio
async def test_restart_adbd_as_shell__unexpected_nonzero_output_raises_backend_error() -> None:
    backend = FakeBackend(
        unroot_result=CommandResult(
            stdout="", stderr="error: closed\n", exit_code=1, duration_ms=10.0
        )
    )
    service = ConnectionService(backend)

    with pytest.raises(BackendError):
        await service.restart_adbd_as_shell("emulator-5554")


@pytest.mark.asyncio
async def test_restart_adbd_as_shell__unrecognized_zero_exit_output_raises_backend_error() -> None:
    backend = FakeBackend(
        unroot_result=CommandResult(
            stdout="something totally new\n", stderr="", exit_code=0, duration_ms=10.0
        )
    )
    service = ConnectionService(backend)

    with pytest.raises(BackendError):
        await service.restart_adbd_as_shell("emulator-5554")


@pytest.mark.asyncio
async def test_restart_adbd_as_shell__adb_unavailable_propagates_as_error() -> None:
    service = ConnectionService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.restart_adbd_as_shell("emulator-5554")


def test_restart_adbd_as_shell_result_summary_variants() -> None:
    fresh = RestartAdbdAsShellResult(
        serial="emulator-5554", success=True, already_shell=False, output="restarting adbd as non root"
    ).summary()
    assert "restarted as shell" in fresh
    assert "emulator-5554" in fresh

    already = RestartAdbdAsShellResult(
        serial="emulator-5554", success=True, already_shell=True, output="adbd not running as root"
    ).summary()
    assert "already" in already


# --- wait_for_device_state -----------------------------------------------------


class _RecordingBackend(FakeBackend):
    """FakeBackend that remembers the last wait_for_device call args, so a test
    can assert exact command (token) construction.
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.last_wait_call: tuple[str, str, float] | None = None

    async def wait_for_device(
        self, serial: str, wait_token: str, timeout_s: float
    ) -> CommandResult:
        self.last_wait_call = (serial, wait_token, timeout_s)
        return await super().wait_for_device(serial, wait_token, timeout_s)


@pytest.mark.asyncio
async def test_wait_for_device_state__default_constructs_wait_for_any_device_token() -> None:
    backend = _RecordingBackend()
    service = ConnectionService(backend)

    result = await service.wait_for_device_state("emulator-5554")

    assert backend.last_wait_call == ("emulator-5554", "wait-for-any-device", 60.0)
    assert isinstance(result, DeviceStateWaitResult)
    assert result.serial == "emulator-5554"
    assert result.state == "device"
    assert result.transport == "any"
    assert result.waited_ms == 12.0


@pytest.mark.asyncio
async def test_wait_for_device_state__transport_and_state_map_into_token() -> None:
    backend = _RecordingBackend()
    service = ConnectionService(backend)

    await service.wait_for_device_state(
        "emulator-5554", state="bootloader", transport="usb", timeout_s=5.0
    )

    assert backend.last_wait_call == ("emulator-5554", "wait-for-usb-bootloader", 5.0)


@pytest.mark.asyncio
async def test_wait_for_device_state__disconnect_state_is_accepted() -> None:
    backend = _RecordingBackend()
    service = ConnectionService(backend)

    result = await service.wait_for_device_state("emulator-5554", state="disconnect")

    assert backend.last_wait_call == ("emulator-5554", "wait-for-any-disconnect", 60.0)
    assert result.state == "disconnect"


@pytest.mark.asyncio
async def test_wait_for_device_state__invalid_state_rejected_before_backend_call() -> None:
    backend = _RecordingBackend()
    service = ConnectionService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.wait_for_device_state("emulator-5554", state="banana")  # type: ignore[arg-type]

    assert backend.last_wait_call is None


@pytest.mark.asyncio
async def test_wait_for_device_state__invalid_transport_rejected_before_backend_call() -> None:
    backend = _RecordingBackend()
    service = ConnectionService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.wait_for_device_state(
            "emulator-5554", transport="bluetooth"  # type: ignore[arg-type]
        )

    assert backend.last_wait_call is None


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_timeout", [0.0, -1.0, 601.0])
async def test_wait_for_device_state__out_of_range_timeout_rejected(bad_timeout: float) -> None:
    service = ConnectionService(_RecordingBackend())

    with pytest.raises(InvalidArgumentError):
        await service.wait_for_device_state("emulator-5554", timeout_s=bad_timeout)


@pytest.mark.asyncio
async def test_wait_for_device_state__timeout_surfaces_as_adb_timeout_with_context() -> None:
    service = ConnectionService(FakeBackend(wait_for_device_timeout=True))

    with pytest.raises(AdbTimeoutError) as excinfo:
        await service.wait_for_device_state("emulator-5554", state="device", timeout_s=3.0)

    assert excinfo.value.details["state"] == "device"
    assert excinfo.value.details["serial"] == "emulator-5554"
    assert "waiting for emulator-5554" in str(excinfo.value)


@pytest.mark.asyncio
async def test_wait_for_device_state__nonzero_exit_translated_to_backend_error() -> None:
    backend = FakeBackend(
        wait_for_device_result=CommandResult(
            stdout="", stderr="error: bad wait-for- state: any-device\n", exit_code=1, duration_ms=4.0
        )
    )
    service = ConnectionService(backend)

    with pytest.raises(BackendError) as excinfo:
        await service.wait_for_device_state("emulator-5554")

    assert "bad wait-for-" in str(excinfo.value)


@pytest.mark.asyncio
async def test_wait_for_device_state__adb_unavailable_propagates() -> None:
    service = ConnectionService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.wait_for_device_state("emulator-5554")


def test_device_state_wait_result_summary_mentions_state_and_transport() -> None:
    any_summary = DeviceStateWaitResult(
        serial="emulator-5554", state="device", transport="any", waited_ms=34.0
    ).summary()
    assert "emulator-5554" in any_summary
    assert "'device'" in any_summary
    assert "over" not in any_summary

    usb_summary = DeviceStateWaitResult(
        serial="emulator-5554", state="recovery", transport="usb", waited_ms=1200.0
    ).summary()
    assert "over usb" in usb_summary


@pytest.mark.asyncio
async def test_connect__out_of_range_port_raises_invalid_argument() -> None:
    calls: list[tuple[str, int]] = []

    class RecordingBackend(FakeBackend):
        async def connect(self, host: str, port: int) -> CommandResult:
            calls.append((host, port))
            return await super().connect(host, port)

    service = ConnectionService(RecordingBackend())

    for bad_port in (0, 99999, -1):
        with pytest.raises(InvalidArgumentError):
            await service.connect("127.0.0.1", bad_port)
    assert calls == []  # rejected before any adb connect


@pytest.mark.asyncio
async def test_connect__empty_host_raises_invalid_argument() -> None:
    service = ConnectionService(FakeBackend())

    with pytest.raises(InvalidArgumentError):
        await service.connect("   ", 5555)


@pytest.mark.asyncio
async def test_disconnect__out_of_range_port_raises_invalid_argument() -> None:
    service = ConnectionService(FakeBackend())

    with pytest.raises(InvalidArgumentError):
        await service.disconnect("127.0.0.1", 70000)


@pytest.mark.asyncio
async def test_connect__valid_port_boundaries_are_accepted() -> None:
    service = ConnectionService(FakeBackend())

    for ok_port in (1, 5555, 65535):
        result = await service.connect("127.0.0.1", ok_port)
        assert result.address == f"127.0.0.1:{ok_port}"
