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
        kill_server_result: CommandResult | None = None,
        start_server_result: CommandResult | None = None,
        connect_result: CommandResult | None = None,
        disconnect_result: CommandResult | None = None,
    ) -> None:
        self._devices = devices or []
        self._unavailable = unavailable
        self._kill_server_result = kill_server_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=5.0
        )
        # Real `adb start-server` output when a server needs starting, captured
        # from an actual run — fixtures should be real-shaped, not hand-invented.
        self._start_server_result = start_server_result or CommandResult(
            stdout="",
            stderr="* daemon not running; starting now at tcp:5037\n* daemon started successfully\n",
            exit_code=0,
            duration_ms=180.0,
        )
        # None (the default) means "build a realistic success message from
        # whatever host:port connect() is actually called with" — see connect()
        # below. A fixed override here is for simulating a specific failure.
        self._connect_result = connect_result
        self._disconnect_result = disconnect_result

    def _raise_if_unavailable(self) -> None:
        if self._unavailable:
            raise AdbUnavailableError(
                "Could not find or execute the adb binary (simulated).",
                details={"adb_path": "adb"},
                remediation="Install Android platform-tools and ensure 'adb' is on PATH.",
            )

    async def list_devices(self) -> list[DeviceInfo]:
        self._raise_if_unavailable()
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

    async def kill_server(self) -> CommandResult:
        self._raise_if_unavailable()
        return self._kill_server_result

    async def start_server(self) -> CommandResult:
        self._raise_if_unavailable()
        return self._start_server_result

    async def connect(self, host: str, port: int) -> CommandResult:
        self._raise_if_unavailable()
        if self._connect_result is not None:
            return self._connect_result
        # Real adb wording (AOSP adb_client.cpp) for a fresh successful connect.
        return CommandResult(
            stdout=f"connected to {host}:{port}\n", stderr="", exit_code=0, duration_ms=220.0
        )

    async def disconnect(self, host: str, port: int) -> CommandResult:
        self._raise_if_unavailable()
        if self._disconnect_result is not None:
            return self._disconnect_result
        return CommandResult(
            stdout=f"disconnected {host}:{port}\n", stderr="", exit_code=0, duration_ms=15.0
        )
