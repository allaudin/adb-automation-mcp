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
    ForwardList,
    ForwardRemoved,
    PortForwardingService,
    ReverseCreated,
    ReverseList,
    ReverseRemoved,
)


class _RecordingBackend(FakeBackend):
    """FakeBackend that remembers the last call to each port-forwarding backend
    method, so a test can assert exact command construction.
    """

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.last_forward_call: tuple[str, str, str, bool] | None = None
        self.last_forward_remove_call: tuple[str, str] | None = None
        self.forward_list_calls = 0
        self.last_reverse_call: tuple[str, str, str, bool] | None = None
        self.last_reverse_list_call: str | None = None
        self.last_reverse_remove_call: tuple[str, str] | None = None

    async def forward(
        self, serial: str, local: str, remote: str, no_rebind: bool
    ) -> CommandResult:
        self.last_forward_call = (serial, local, remote, no_rebind)
        return await super().forward(serial, local, remote, no_rebind)

    async def forward_list(self) -> CommandResult:
        self.forward_list_calls += 1
        return await super().forward_list()

    async def forward_remove(self, serial: str, local: str) -> CommandResult:
        self.last_forward_remove_call = (serial, local)
        return await super().forward_remove(serial, local)

    async def reverse(
        self, serial: str, remote: str, local: str, no_rebind: bool
    ) -> CommandResult:
        self.last_reverse_call = (serial, remote, local, no_rebind)
        return await super().reverse(serial, remote, local, no_rebind)

    async def reverse_list(self, serial: str) -> CommandResult:
        self.last_reverse_list_call = serial
        return await super().reverse_list(serial)

    async def reverse_remove(self, serial: str, remote: str) -> CommandResult:
        self.last_reverse_remove_call = (serial, remote)
        return await super().reverse_remove(serial, remote)


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


# --- list_forwards -----------------------------------------------------------


@pytest.mark.asyncio
async def test_list_forwards__no_serial_returns_all_rows_parsed() -> None:
    backend = _RecordingBackend()
    service = PortForwardingService(backend)

    result = await service.list_forwards()

    assert backend.forward_list_calls == 1
    assert isinstance(result, ForwardList)
    assert result.serial is None
    # FakeBackend default fixture: two rows, one a non-tcp endpoint kind.
    assert [(m.serial, m.local_spec, m.remote_spec) for m in result.forwards] == [
        ("emulator-5554", "tcp:6100", "tcp:8080"),
        ("emulator-5554", "tcp:43177", "localabstract:foo"),
    ]


@pytest.mark.asyncio
async def test_list_forwards__serial_filters_rows() -> None:
    backend = _RecordingBackend(
        forward_list_result=CommandResult(
            stdout=(
                "emulator-5554 tcp:6100 tcp:8080\n"
                "0A221FDD4001 tcp:5000 tcp:5000\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=5.0,
        )
    )
    service = PortForwardingService(backend)

    result = await service.list_forwards("emulator-5554")

    assert result.serial == "emulator-5554"
    assert [m.serial for m in result.forwards] == ["emulator-5554"]


@pytest.mark.asyncio
async def test_list_forwards__empty_output_is_valid_empty_list() -> None:
    backend = _RecordingBackend(
        forward_list_result=CommandResult(stdout="\n", stderr="", exit_code=0, duration_ms=2.0)
    )
    service = PortForwardingService(backend)

    result = await service.list_forwards()

    assert result.forwards == []


@pytest.mark.asyncio
async def test_list_forwards__malformed_line_is_skipped_not_fatal() -> None:
    backend = _RecordingBackend(
        forward_list_result=CommandResult(
            stdout="garbage-with-no-columns\nemulator-5554 tcp:6100 tcp:8080\n",
            stderr="",
            exit_code=0,
            duration_ms=2.0,
        )
    )
    service = PortForwardingService(backend)

    result = await service.list_forwards()

    assert [m.local_spec for m in result.forwards] == ["tcp:6100"]


@pytest.mark.asyncio
async def test_list_forwards__nonzero_exit_maps_to_backend_error() -> None:
    backend = _RecordingBackend(
        forward_list_result=CommandResult(
            stdout="", stderr="adb: something broke\n", exit_code=1, duration_ms=2.0
        )
    )
    service = PortForwardingService(backend)

    with pytest.raises(BackendError):
        await service.list_forwards()


# --- remove_forward --------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_forward__existing_mapping_reports_removed_true() -> None:
    backend = _RecordingBackend()
    service = PortForwardingService(backend)

    result = await service.remove_forward("emulator-5554", 6100)

    assert backend.last_forward_remove_call == ("emulator-5554", "tcp:6100")
    assert isinstance(result, ForwardRemoved)
    assert result.removed is True
    assert result.local_spec == "tcp:6100"


@pytest.mark.asyncio
async def test_remove_forward__missing_mapping_is_removed_false_not_error() -> None:
    backend = _RecordingBackend(
        forward_remove_result=CommandResult(
            stdout="", stderr="adb: error: listener 'tcp:6100' not found\n", exit_code=1, duration_ms=3.0
        )
    )
    service = PortForwardingService(backend)

    result = await service.remove_forward("emulator-5554", 6100)

    assert result.removed is False


@pytest.mark.asyncio
async def test_remove_forward__unknown_serial_raises_device_not_found() -> None:
    backend = _RecordingBackend(
        forward_remove_result=CommandResult(
            stdout="", stderr="adb: error: device 'bogus' not found\n", exit_code=1, duration_ms=3.0
        )
    )
    service = PortForwardingService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.remove_forward("bogus", 6100)


@pytest.mark.asyncio
async def test_remove_forward__port_zero_rejected_before_backend() -> None:
    backend = _RecordingBackend()
    service = PortForwardingService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.remove_forward("emulator-5554", 0)

    assert backend.last_forward_remove_call is None


# --- create_reverse ------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_reverse__explicit_ports_construct_reverse_specs_in_remote_local_order() -> None:
    backend = _RecordingBackend()
    service = PortForwardingService(backend)

    result = await service.create_reverse("emulator-5554", remote_port=8080, local_port=7000)

    # adb reverse REMOTE LOCAL — device-side first, host-side second.
    assert backend.last_reverse_call == ("emulator-5554", "tcp:8080", "tcp:7000", False)
    assert isinstance(result, ReverseCreated)
    assert result.remote_port == 8080
    assert result.local_port == 7000
    assert result.remote_spec == "tcp:8080"
    assert result.local_spec == "tcp:7000"


@pytest.mark.asyncio
async def test_create_reverse__remote_zero_returns_adb_allocated_device_port() -> None:
    backend = _RecordingBackend()
    service = PortForwardingService(backend)

    result = await service.create_reverse("emulator-5554", remote_port=0, local_port=7000)

    assert backend.last_reverse_call == ("emulator-5554", "tcp:0", "tcp:7000", False)
    assert result.remote_port == 41000


@pytest.mark.asyncio
async def test_create_reverse__local_port_zero_rejected_before_backend() -> None:
    backend = _RecordingBackend()
    service = PortForwardingService(backend)

    with pytest.raises(InvalidArgumentError):
        await service.create_reverse("emulator-5554", remote_port=8080, local_port=0)

    assert backend.last_reverse_call is None


@pytest.mark.asyncio
async def test_create_reverse__no_rebind_conflict_raises_port_forward_conflict() -> None:
    backend = _RecordingBackend(
        reverse_result=CommandResult(
            stdout="", stderr="adb: error: cannot rebind existing socket\n", exit_code=1, duration_ms=3.0
        )
    )
    service = PortForwardingService(backend)

    with pytest.raises(PortForwardConflictError):
        await service.create_reverse(
            "emulator-5554", remote_port=8080, local_port=7000, no_rebind=True
        )


@pytest.mark.asyncio
async def test_create_reverse__offline_device_raises_device_not_found() -> None:
    backend = _RecordingBackend(
        reverse_result=CommandResult(
            stdout="", stderr="adb: device 'emulator-5554' not found\n", exit_code=1, duration_ms=3.0
        )
    )
    service = PortForwardingService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.create_reverse("emulator-5554", remote_port=8080, local_port=7000)


@pytest.mark.asyncio
async def test_create_reverse__auto_remote_with_unparseable_stdout_raises_backend_error() -> None:
    backend = _RecordingBackend(
        reverse_result=CommandResult(stdout="\n", stderr="", exit_code=0, duration_ms=3.0)
    )
    service = PortForwardingService(backend)

    with pytest.raises(BackendError):
        await service.create_reverse("emulator-5554", remote_port=0, local_port=7000)


# --- list_reverses ---------------------------------------------------------


@pytest.mark.asyncio
async def test_list_reverses__parses_remote_and_local_ignoring_transport_token() -> None:
    backend = _RecordingBackend()
    service = PortForwardingService(backend)

    result = await service.list_reverses("emulator-5554")

    assert backend.last_reverse_list_call == "emulator-5554"
    assert isinstance(result, ReverseList)
    assert result.serial == "emulator-5554"
    assert [(m.remote_spec, m.local_spec) for m in result.reverses] == [
        ("tcp:8080", "tcp:7000"),
        ("localabstract:bar", "tcp:7001"),
    ]


@pytest.mark.asyncio
async def test_list_reverses__empty_output_is_valid_empty_list() -> None:
    backend = _RecordingBackend(
        reverse_list_result=CommandResult(stdout="\n", stderr="", exit_code=0, duration_ms=2.0)
    )
    service = PortForwardingService(backend)

    result = await service.list_reverses("emulator-5554")

    assert result.reverses == []


@pytest.mark.asyncio
async def test_list_reverses__unknown_serial_raises_device_not_found() -> None:
    backend = _RecordingBackend(
        reverse_list_result=CommandResult(
            stdout="", stderr="error: device 'bogus' not found\n", exit_code=1, duration_ms=2.0
        )
    )
    service = PortForwardingService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.list_reverses("bogus")


# --- remove_reverse ------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_reverse__existing_mapping_reports_removed_true() -> None:
    backend = _RecordingBackend()
    service = PortForwardingService(backend)

    result = await service.remove_reverse("emulator-5554", 8080)

    assert backend.last_reverse_remove_call == ("emulator-5554", "tcp:8080")
    assert isinstance(result, ReverseRemoved)
    assert result.removed is True
    assert result.remote_spec == "tcp:8080"


@pytest.mark.asyncio
async def test_remove_reverse__missing_mapping_is_removed_false_not_error() -> None:
    backend = _RecordingBackend(
        reverse_remove_result=CommandResult(
            stdout="", stderr="adb: error: listener 'tcp:8080' not found\n", exit_code=1, duration_ms=3.0
        )
    )
    service = PortForwardingService(backend)

    result = await service.remove_reverse("emulator-5554", 8080)

    assert result.removed is False


@pytest.mark.asyncio
async def test_remove_reverse__unknown_serial_raises_device_not_found() -> None:
    backend = _RecordingBackend(
        reverse_remove_result=CommandResult(
            stdout="", stderr="adb: error: device 'bogus' not found\n", exit_code=1, duration_ms=3.0
        )
    )
    service = PortForwardingService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.remove_reverse("bogus", 8080)


def test_list_and_removed_summaries() -> None:
    assert "No active forwards" in ForwardList(serial=None, forwards=[]).summary()
    assert "for emulator-5554" in ForwardList(serial="emulator-5554", forwards=[]).summary()
    assert "No reverse tcp:8080" in ReverseRemoved(
        serial="emulator-5554", remote_spec="tcp:8080", removed=False
    ).summary()
    assert "Reversing emulator-5554 tcp:8080" in ReverseCreated(
        serial="emulator-5554",
        remote_port=8080,
        local_port=7000,
        remote_spec="tcp:8080",
        local_spec="tcp:7000",
    ).summary()
