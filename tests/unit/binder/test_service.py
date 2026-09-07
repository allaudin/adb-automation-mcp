"""Layer 1 unit tests: BinderService against FakeBackend directly."""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.binder.service import BinderService


class RecordingBackend(FakeBackend):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.command: str | None = None

    async def shell(
        self, serial: str, command: str, timeout_s: float | None = None
    ) -> CommandResult:
        self.command = command
        return await super().shell(serial, command, timeout_s)


def _cr(stdout: str = "", stderr: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(stdout=stdout, stderr=stderr, exit_code=exit_code, duration_ms=20.0)


@pytest.mark.asyncio
async def test_get_binder_call_stats__command_and_parse() -> None:
    backend = RecordingBackend()

    result = await BinderService(backend).get_binder_call_stats("emulator-5554")

    assert backend.command == "dumpsys binder_calls_stats"
    assert result.collecting is True
    assert result.start_time == "2026-09-07 07:48:14"
    assert result.sampling_interval_ms == 1000
    assert result.total_cpu_time_micros == 201512
    assert result.calls_count == 722
    assert result.avg_call_cpu_time_micros == 279
    assert len(result.top_callers) == 2
    top = result.top_callers[0]
    assert top.who == "com.android.systemui/10141"
    assert top.cpu_time_micros == 123456
    assert top.percent_of_total == 61.2
    assert top.recorded_call_count == 40
    assert top.call_count == 512
    assert result.exceptions[0].class_name == "java.lang.SecurityException"
    assert result.exceptions[0].count == 3


@pytest.mark.asyncio
async def test_get_binder_call_stats__not_collecting_is_valid() -> None:
    backend = FakeBackend(
        binder_calls_stats_result=_cr(
            stdout=(
                "Start time: 2026-09-07 07:48:14\n"
                "Sampling interval period: 1000\n"
                "Per-UID Summary (top 90% by cpu time) (cpu_time, ...):\n"
                "\n"
                "  Summary: total_cpu_time=0, calls_count=0, avg_call_cpu_time=NaN\n"
            )
        )
    )

    result = await BinderService(backend).get_binder_call_stats("emulator-5554")

    assert result.collecting is False
    assert result.calls_count == 0
    assert result.avg_call_cpu_time_micros is None
    assert result.top_callers == []
    assert "not currently collecting" in result.summary()


@pytest.mark.asyncio
async def test_get_binder_call_stats__limit_caps_callers() -> None:
    rows = "".join(
        f"      {i}000      {i}.0%      {i}      {i}0  pkg{i}/1{i:04d}\n" for i in range(1, 6)
    )
    backend = FakeBackend(
        binder_calls_stats_result=_cr(
            stdout=(
                "Sampling interval period: 1000\n"
                "Per-UID Summary (cpu_time, ...):\n" + rows + "\n"
                "  Summary: total_cpu_time=15000, calls_count=150, avg_call_cpu_time=100\n"
            )
        )
    )

    result = await BinderService(backend).get_binder_call_stats("emulator-5554", limit=2)

    assert len(result.top_callers) == 2


@pytest.mark.asyncio
async def test_get_binder_call_stats__bad_limit_rejected_before_backend() -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await BinderService(Exploding()).get_binder_call_stats("emulator-5554", limit=0)


@pytest.mark.asyncio
async def test_get_binder_call_stats__malformed_output_does_not_crash() -> None:
    backend = FakeBackend(binder_calls_stats_result=_cr(stdout="\x00 garbage }}}\n"))

    result = await BinderService(backend).get_binder_call_stats("emulator-5554")

    assert result.collecting is False
    assert result.top_callers == []
    assert result.calls_count is None


@pytest.mark.asyncio
async def test_get_binder_call_stats__permission_denied() -> None:
    backend = FakeBackend(
        binder_calls_stats_result=_cr(stderr="Permission Denial\n", exit_code=1)
    )
    with pytest.raises(PermissionDeniedError):
        await BinderService(backend).get_binder_call_stats("emulator-5554")


@pytest.mark.asyncio
async def test_get_binder_call_stats__unknown_serial() -> None:
    backend = FakeBackend(
        binder_calls_stats_result=_cr(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )
    with pytest.raises(DeviceNotFoundError):
        await BinderService(backend).get_binder_call_stats("bogus")


@pytest.mark.asyncio
async def test_reset_binder_call_stats__command_and_confirm() -> None:
    backend = RecordingBackend()

    result = await BinderService(backend).reset_binder_call_stats("emulator-5554")

    assert backend.command == "dumpsys binder_calls_stats --reset"
    assert result.reset is True


@pytest.mark.asyncio
async def test_reset_binder_call_stats__unclassified_backend_error() -> None:
    backend = FakeBackend(binder_calls_stats_reset_result=_cr(stderr="broken\n", exit_code=2))
    with pytest.raises(BackendError):
        await BinderService(backend).reset_binder_call_stats("emulator-5554")


@pytest.mark.asyncio
async def test_binder_service__backend_unavailable() -> None:
    with pytest.raises(AdbUnavailableError):
        await BinderService(FakeBackend(unavailable=True)).get_binder_call_stats("emulator-5554")
