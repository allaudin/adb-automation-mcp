"""Domain logic for the connection module: managing the local adb server's own
lifecycle and how it reaches devices — as opposed to diagnostics/DiagnosticsService,
which only reports on health, and device_info/DeviceInfoService, which only reports
on what's currently connected. Neither of those mutates anything; this module does.
"""

from __future__ import annotations

from pydantic import BaseModel

from adb_mcp.backend.protocol import AdbBackend


class AdbServerRestartResult(BaseModel):
    """Outcome of restarting the local adb server: `adb kill-server` followed by
    `adb start-server`. kill-server's own result isn't surfaced — it's idempotent
    and essentially always reports success even if nothing was running — so
    success is judged purely on whether start-server came back up cleanly.
    """

    success: bool
    output: str

    def summary(self) -> str:
        if self.success:
            return "adb server restarted successfully."
        return f"adb server restart failed: {self.output or 'start-server exited non-zero'}"


class ConnectResult(BaseModel):
    """Outcome of connecting to a device over TCP/IP (`adb connect host:port`).

    success is judged on adb's message text, not its exit code: `adb connect`
    was verified live to exit 0 unconditionally, whether or not the connection
    actually succeeded — "failed to connect to '1.2.3.4:1': Connection refused"
    and "failed to connect to 1.2.3.4:1" (protocol handshake failure, no reason
    given) were both observed with exit_code 0.
    """

    success: bool
    address: str
    output: str

    def summary(self) -> str:
        if self.success:
            return f"Connected to {self.address}."
        return f"Failed to connect to {self.address}: {self.output or 'unknown reason'}"


class DisconnectResult(BaseModel):
    """Outcome of disconnecting a TCP/IP-connected device (`adb disconnect host:port`).

    Unlike connect, disconnect's exit code is reliable — verified live: exit 1
    with "error: no such device '<addr>'" for an address that wasn't connected.
    """

    success: bool
    address: str
    output: str

    def summary(self) -> str:
        if self.success:
            return f"Disconnected from {self.address}."
        return f"Failed to disconnect from {self.address}: {self.output or 'unknown reason'}"


class ConnectionService:
    """Operations that change how this host's adb server runs or what it's
    connected to — global and non-device-scoped, unlike most other modules.
    """

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def restart_adb_server(self) -> AdbServerRestartResult:
        await self._backend.kill_server()
        start_result = await self._backend.start_server()
        output = (start_result.stdout + start_result.stderr).strip()
        return AdbServerRestartResult(success=start_result.exit_code == 0, output=output)

    async def connect(self, host: str, port: int) -> ConnectResult:
        address = f"{host}:{port}"
        result = await self._backend.connect(host, port)
        output = (result.stdout + result.stderr).strip()
        # "connected to <addr>" (fresh) and "already connected to <addr>" (idempotent)
        # are the only two success wordings adb uses; every failure wording observed
        # uses "failed to connect to" instead, which doesn't contain this substring.
        success = "connected to" in output
        return ConnectResult(success=success, address=address, output=output)

    async def disconnect(self, host: str, port: int) -> DisconnectResult:
        address = f"{host}:{port}"
        result = await self._backend.disconnect(host, port)
        output = (result.stdout + result.stderr).strip()
        return DisconnectResult(success=result.exit_code == 0, address=address, output=output)
