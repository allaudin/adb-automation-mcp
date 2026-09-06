"""Layer 1 unit tests: PortForwardingService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
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
    PortForwardConflictError,
)
from adb_automation_mcp.modules.port_forwarding.service import (
    ForwardCreated,
    PortForwardingService,
)


class _RecordingBackend(FakeBackend):
    """FakeBackend that remembers the last forward() call, so a test can assert
    exact command construction.
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.last_forward_call: tuple[str, str, str, bool] | None = None

    async def forward(
        self, serial: str, local: str, remote: str, no_rebind: bool
    ) -> CommandResult:
        self.last_forward_call = (serial, local, remote, no_rebind)
        return await super().forward(serial, local, remote, no_rebind)


@pytest.mark.asyncio
async def test_create_forward__explicit_local_port_constructs_tcp_specs() -> None:
    backend = _RecordingBackend()
    service = PortForwardingService(backend)

    result = await service.create_forward("emulator-5554", remote_port=8080, local_port=6100)

    assert backend.last_forward_call == ("emulator-5554", "tcp:6100", "tcp:8080", False)
    assert isinstance(result, ForwardCreated)
    assert result.local_port == 6100
    assert result.remote_port == 8080
    assert result.local_spec == "tcp:6100"
    assert result.remote_spec == "tcp:8080"


@pytest.mark.asyncio
async def test_create_forward__local_port_zero_returns_adb_allocated_port() -> None:
    backend = _RecordingBackend()
    service = PortForwardingService(backend)

    result = await service.create_forward("emulator-5554", remote_port=8080)

    assert backend.last_forward_call == ("emulator-5554", "tcp:0", "tcp:8080", False)
    # FakeBackend's deterministic stand-in for an adb-allocated ephemeral port.
    assert result.local_port == 41000
    assert result.local_spec == "tcp:41000"


@pytest.mark.asyncio
async def test_create_forward__no_rebind_flag_is_passed_through() -> None:
    backend = _RecordingBackend()
    service = PortForwardingService(backend)

    await service.create_forward(
        "emulator-5554", remote_port=8080, local_port=6100, no_rebind=True
    )

    assert backend.last_forward_call == ("emulator-5554", "tcp:6100", "tcp:8080", True)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_local", [-1, 70000])
async def test_create_forward__out_of_range_local_port_rejected_before_backend(
    bad_local: int,
) -> None:
    backend = _RecordingBackend()
    service = PortForwardingService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.create_forward("emulator-5554", remote_port=8080, local_port=bad_local)

    assert backend.last_forward_call is None


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_remote", [0, 65536])
async def test_create_forward__remote_port_zero_or_oversize_rejected(bad_remote: int) -> None:
    service = PortForwardingService(_RecordingBackend())

    with pytest.raises(InvalidArgumentError):
        await service.create_forward("emulator-5554", remote_port=bad_remote, local_port=6100)


@pytest.mark.asyncio
async def test_create_forward__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        forward_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=4.0
        )
    )
    service = PortForwardingService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.create_forward("bogus", remote_port=8080, local_port=6100)


@pytest.mark.asyncio
async def test_create_forward__no_rebind_conflict_raises_port_forward_conflict() -> None:
    backend = FakeBackend(
        forward_result=CommandResult(
            stdout="", stderr="adb: error: cannot rebind existing socket\n", exit_code=1, duration_ms=4.0
        )
    )
    service = PortForwardingService(backend)

    with pytest.raises(PortForwardConflictError):
        await service.create_forward(
            "emulator-5554", remote_port=9999, local_port=6100, no_rebind=True
        )


@pytest.mark.asyncio
async def test_create_forward__adb_side_bad_port_maps_to_invalid_argument() -> None:
    backend = FakeBackend(
        forward_result=CommandResult(
            stdout="",
            stderr="adb: error: cannot bind listener: bad port number '70000'\n",
            exit_code=1,
            duration_ms=4.0,
        )
    )
    service = PortForwardingService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.create_forward("emulator-5554", remote_port=8080, local_port=6100)


@pytest.mark.asyncio
async def test_create_forward__unclassified_nonzero_exit_maps_to_backend_error() -> None:
    backend = FakeBackend(
        forward_result=CommandResult(
            stdout="", stderr="adb: something entirely new went wrong\n", exit_code=1, duration_ms=4.0
        )
    )
    service = PortForwardingService(backend)

    with pytest.raises(BackendError):
        await service.create_forward("emulator-5554", remote_port=8080, local_port=6100)


@pytest.mark.asyncio
async def test_create_forward__auto_port_with_unparseable_stdout_raises_backend_error() -> None:
    backend = FakeBackend(
        forward_result=CommandResult(stdout="\n", stderr="", exit_code=0, duration_ms=4.0)
    )
    service = PortForwardingService(backend)

    with pytest.raises(BackendError):
        await service.create_forward("emulator-5554", remote_port=8080, local_port=0)


@pytest.mark.asyncio
async def test_create_forward__explicit_port_with_empty_stdout_falls_back_to_requested() -> None:
    backend = FakeBackend(
        forward_result=CommandResult(stdout="", stderr="", exit_code=0, duration_ms=4.0)
    )
    service = PortForwardingService(backend)

    result = await service.create_forward("emulator-5554", remote_port=8080, local_port=6100)

    assert result.local_port == 6100


@pytest.mark.asyncio
async def test_create_forward__adb_unavailable_propagates() -> None:
    service = PortForwardingService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.create_forward("emulator-5554", remote_port=8080, local_port=6100)


def test_forward_created_summary_mentions_both_ports_and_serial() -> None:
    summary = ForwardCreated(
        serial="emulator-5554",
        local_port=6100,
        remote_port=8080,
        local_spec="tcp:6100",
        remote_spec="tcp:8080",
    ).summary()
    assert "tcp:6100" in summary
    assert "tcp:8080" in summary
    assert "emulator-5554" in summary
