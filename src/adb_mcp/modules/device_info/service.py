"""Domain logic for the device_info module: introspection of connected devices
themselves, as opposed to diagnostics/DiagnosticsService which covers the health
of the adb connection as a whole.
"""

from __future__ import annotations

from pydantic import BaseModel

from adb_mcp.backend.protocol import AdbBackend


class ConnectedDevice(BaseModel):
    """One entry from `adb devices -l`, as exposed via the list_connected_devices tool."""

    serial: str
    state: str
    model: str | None = None
    product: str | None = None


class DeviceInfoService:
    """Read-only introspection of currently connected devices."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def list_devices(self) -> list[ConnectedDevice]:
        devices = await self._backend.list_devices()
        return [
            ConnectedDevice(serial=d.serial, state=d.state, model=d.model, product=d.product)
            for d in devices
        ]
