"""Layer 1 unit tests: ConnectionService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import AdbUnavailableError, DeviceNotFoundError
from adb_mcp.modules.connection.service import (
    AdbServerRestartResult,
    ConnectionService,
    ConnectResult,
    DisconnectResult,
    RestartAdbdAsRootResult,
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
