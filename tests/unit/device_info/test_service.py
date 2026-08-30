"""Layer 1 unit tests: DeviceInfoService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import DeviceInfo
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import AdbUnavailableError
from adb_automation_mcp.modules.device_info.service import DeviceInfoService


@pytest.mark.asyncio
async def test_list_devices__maps_backend_device_info_to_connected_device() -> None:
    backend = FakeBackend(
        devices=[DeviceInfo(serial="emulator-5554", state="device", model="Pixel", product="redfin")]
    )
    service = DeviceInfoService(backend)

    result = await service.list_devices()

    assert len(result) == 1
    assert result[0].serial == "emulator-5554"
    assert result[0].state == "device"
    assert result[0].model == "Pixel"
    assert result[0].product == "redfin"


@pytest.mark.asyncio
async def test_list_devices__empty_when_no_devices_connected() -> None:
    service = DeviceInfoService(FakeBackend(devices=[]))

    assert await service.list_devices() == []


@pytest.mark.asyncio
async def test_list_devices__adb_unavailable_propagates() -> None:
    service = DeviceInfoService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.list_devices()
