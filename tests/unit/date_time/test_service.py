"""Layer 1 unit tests: DateTimeService against FakeBackend directly — no
MCP registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import BackendError, DeviceClockUnavailableError, DeviceNotFoundError
from adb_mcp.modules.date_time.service import DateTimeService


@pytest.mark.asyncio
async def test_get_date_time__successful_retrieval_returns_timestamp_and_offset() -> None:
    service = DateTimeService(FakeBackend())

    result = await service.get_date_time("emulator-5554")

    assert result.serial == "emulator-5554"
    assert result.timestamp == "2026-08-26T18:23:45"
    assert result.utc_offset == "+0000"


@pytest.mark.asyncio
async def test_get_date_time__negative_utc_offset_is_parsed() -> None:
    backend = FakeBackend(
        device_utc_offset_result=CommandResult(
            stdout="-0700\n", stderr="", exit_code=0, duration_ms=10.0
        )
    )
    service = DateTimeService(backend)

    result = await service.get_date_time("emulator-5554")

    assert result.utc_offset == "-0700"


@pytest.mark.asyncio
async def test_get_date_time__malformed_timestamp_raises_device_clock_unavailable() -> None:
    backend = FakeBackend(
        device_timestamp_result=CommandResult(
            stdout="not a timestamp at all\n", stderr="", exit_code=0, duration_ms=10.0
        )
    )
    service = DateTimeService(backend)

    with pytest.raises(DeviceClockUnavailableError):
        await service.get_date_time("emulator-5554")


@pytest.mark.asyncio
async def test_get_date_time__empty_timestamp_output_raises_device_clock_unavailable() -> None:
    backend = FakeBackend(
        device_timestamp_result=CommandResult(stdout="", stderr="", exit_code=0, duration_ms=5.0)
    )
    service = DateTimeService(backend)

    with pytest.raises(DeviceClockUnavailableError):
        await service.get_date_time("emulator-5554")


@pytest.mark.asyncio
async def test_get_date_time__unsupported_utc_offset_format_degrades_to_none() -> None:
    backend = FakeBackend(
        device_utc_offset_result=CommandResult(
            stdout="%z\n", stderr="", exit_code=0, duration_ms=10.0
        )
    )
    service = DateTimeService(backend)

    result = await service.get_date_time("emulator-5554")

    assert result.timestamp == "2026-08-26T18:23:45"
    assert result.utc_offset is None


@pytest.mark.asyncio
async def test_get_date_time__utc_offset_command_failure_degrades_to_none() -> None:
    backend = FakeBackend(
        device_utc_offset_result=CommandResult(
            stdout="", stderr="date: unrecognized option '%z'\n", exit_code=1, duration_ms=5.0
        )
    )
    service = DateTimeService(backend)

    result = await service.get_date_time("emulator-5554")

    assert result.utc_offset is None


@pytest.mark.asyncio
async def test_get_date_time__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        device_timestamp_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = DateTimeService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.get_date_time("bogus")


@pytest.mark.asyncio
async def test_get_date_time__adb_failure_on_offset_query_raises_device_not_found() -> None:
    backend = FakeBackend(
        device_utc_offset_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = DateTimeService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.get_date_time("bogus")


@pytest.mark.asyncio
async def test_get_date_time__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        device_timestamp_result=CommandResult(
            stdout="", stderr="some other unclassified failure\n", exit_code=1, duration_ms=5.0
        )
    )
    service = DateTimeService(backend)

    with pytest.raises(BackendError):
        await service.get_date_time("emulator-5554")
