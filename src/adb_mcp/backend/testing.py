"""A deterministic, in-memory AdbBackend implementation for tests.

Fixture values passed in must be realistic once methods beyond list_devices are
implemented — a test is only a trustworthy predictor of real behavior if it's
exercised against real-shaped data. For now the unimplemented methods raise
NotImplementedError loudly rather than returning silently-wrong fake data.
"""

from __future__ import annotations

from adb_mcp.backend.protocol import CommandResult, DeviceInfo
from adb_mcp.errors import AdbUnavailableError


class FakeBackend:
    """AdbBackend implementation backed by in-memory fixtures instead of a real
    device or adb install — deterministic, fast, and usable in any environment.
    """

    def __init__(
        self,
        devices: list[DeviceInfo] | None = None,
        unavailable: bool = False,
    ) -> None:
        self._devices = devices or []
        self._unavailable = unavailable

    async def list_devices(self) -> list[DeviceInfo]:
        if self._unavailable:
            raise AdbUnavailableError(
                "Could not find or execute the adb binary (simulated).",
                details={"adb_path": "adb"},
                remediation="Install Android platform-tools and ensure 'adb' is on PATH.",
            )
        return list(self._devices)

    async def shell(self, serial: str, command: str) -> CommandResult:
        raise NotImplementedError("FakeBackend.shell: no module needs this yet")

    async def install(self, serial: str, apk_path: str, flags: list[str]) -> CommandResult:
        raise NotImplementedError("FakeBackend.install: no module needs this yet")

    async def uninstall(self, serial: str, package: str, keep_data: bool) -> CommandResult:
        raise NotImplementedError("FakeBackend.uninstall: no module needs this yet")

    async def push(self, serial: str, local_path: str, remote_path: str) -> CommandResult:
        raise NotImplementedError("FakeBackend.push: no module needs this yet")

    async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
        raise NotImplementedError("FakeBackend.pull: no module needs this yet")
