"""Layer 1 unit tests: DiagnosticsService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import DeviceInfo
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.modules.diagnostics.service import DiagnosticsService


@pytest.mark.asyncio
async def test_check_adb_available__adb_reachable_with_devices_reports_available_true() -> None:
    backend = FakeBackend(devices=[DeviceInfo(serial="emulator-5554", state="device")])
    service = DiagnosticsService(backend)

    result = await service.check_adb_available()

    assert result.available is True
    assert result.device_count == 1
    assert result.reason is None


@pytest.mark.asyncio
async def test_check_adb_available__adb_reachable_with_no_devices_still_available_true() -> None:
    backend = FakeBackend(devices=[])
    service = DiagnosticsService(backend)

    result = await service.check_adb_available()

    assert result.available is True
    assert result.device_count == 0


@pytest.mark.asyncio
async def test_check_adb_available__adb_missing_reports_available_false_not_an_error() -> None:
    backend = FakeBackend(unavailable=True)
    service = DiagnosticsService(backend)

    result = await service.check_adb_available()

    assert result.available is False
    assert result.reason is not None
    assert result.device_count is None


def test_summary_mentions_device_count_when_available() -> None:
    from adb_mcp.modules.diagnostics.service import AdbAvailability

    assert "2 devices" in AdbAvailability(available=True, device_count=2).summary()
    assert "1 device " in AdbAvailability(available=True, device_count=1).summary() + " "


def test_summary_explains_reason_when_unavailable() -> None:
    from adb_mcp.modules.diagnostics.service import AdbAvailability

    summary = AdbAvailability(available=False, reason="adb not on PATH").summary()
    assert "not available" in summary
    assert "adb not on PATH" in summary
