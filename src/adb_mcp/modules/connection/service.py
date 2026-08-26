"""Domain logic for the connection module: managing the local adb server's own
lifecycle and how it reaches devices — as opposed to diagnostics/DiagnosticsService,
which only reports on health, and device_info/DeviceInfoService, which only reports
on what's currently connected. Neither of those mutates anything; this module does.
"""

from __future__ import annotations

from pydantic import BaseModel

from adb_mcp.backend.protocol import AdbBackend
from adb_mcp.errors import BackendError, DeviceNotFoundError


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


class RestartAdbdAsRootResult(BaseModel):
    """Outcome of restarting the on-device `adbd` daemon as root
    (`adb -s <serial> root`) — the device-side equivalent of
    restart_adb_server, which only restarts the *host's* adb client/server
    process and never touches privilege on the device at all.

    Like `adb connect`, this is assumed to have the same shape of ambiguity —
    based on documented `adb root` behavior, not independently verified live
    in this environment (no rootable device was available) — so
    success/already_root are judged primarily on adb's message text rather
    than the exit code, on the theory that a known wording being present
    proves adbd was actually reached regardless of what exit code that adb
    version happens to use:

    - "restarting adbd as root" — freshly restarted as root this call.
    - "adbd is already running as root" — idempotent case, no-op restart.
    - "adbd cannot run as root in production builds" — a normal, expected
      answer on a non-debuggable build, not a tool error; surfaced as
      success=False, already_root=False, same as ConnectResult.success=False
      is data rather than a raised exception.

    Only a transport-level failure that never reaches adbd at all — an
    unknown serial ("adb: device '<serial>' not found", exit 1, the same
    client-level check every other per-device command hits) or the adb
    binary being unavailable — raises an actual error (DeviceNotFoundError /
    AdbUnavailableError respectively).
    """

    serial: str
    success: bool
    already_root: bool
    output: str

    def summary(self) -> str:
        if self.success and self.already_root:
            return f"adbd was already running as root on {self.serial}."
        if self.success:
            return f"adbd restarted as root on {self.serial}."
        return f"adbd cannot run as root on {self.serial}: {self.output or 'unknown reason'}"


class ConnectionService:
    """Operations that change how this host's adb reaches a device: the local
    adb server's own lifecycle and its connections (global, non-device-scoped
    — restart_adb_server/connect/disconnect), plus the device-side transport
    endpoint itself (device-scoped — restart_adbd_as_root, which restarts
    adbd, the daemon adb actually talks to on the device).
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

    async def restart_adbd_as_root(self, serial: str) -> RestartAdbdAsRootResult:
        result = await self._backend.root(serial)
        output = (result.stdout + result.stderr).strip()
        # Check known adbd wordings first, regardless of exit code: their
        # presence proves adbd was actually reached, which is the real signal
        # — unlike `adb connect` (verified live, ADR-017, to exit 0
        # unconditionally), this hasn't been independently verified live, so
        # this doesn't assume any particular exit code accompanies these.
        if "adbd is already running as root" in output:
            return RestartAdbdAsRootResult(serial=serial, success=True, already_root=True, output=output)
        if "restarting adbd as root" in output:
            return RestartAdbdAsRootResult(serial=serial, success=True, already_root=False, output=output)
        if "adbd cannot run as root in production builds" in output:
            # A normal, expected Android answer on a non-debuggable build,
            # not an error.
            return RestartAdbdAsRootResult(serial=serial, success=False, already_root=False, output=output)
        # No known adbd wording present — adbd was never reached at all.
        # Classify by transport failure the same way shell-routed commands do
        # (see user/service.py's _raise_for_shell_failure): an unknown serial
        # fails at the adb-client level with "adb: device '<serial>' not
        # found", exit 1.
        if result.exit_code != 0:
            message = output or "adb root command exited non-zero."
            if "not found" in message:
                raise DeviceNotFoundError(message, details={"serial": serial})
            raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})
        raise BackendError(
            output or "adb root command exited successfully but returned unexpected output.",
            details={"serial": serial},
        )
