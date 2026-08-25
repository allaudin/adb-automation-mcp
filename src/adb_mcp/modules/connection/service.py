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
