"""Domain logic for the connection module: managing the local adb server's own
lifecycle and how it reaches devices — as opposed to diagnostics/DiagnosticsService,
which only reports on health, and device_info/DeviceInfoService, which only reports
on what's currently connected. Neither of those mutates anything; this module does.
"""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend
from adb_automation_mcp.errors import (
    AdbTimeoutError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
)

# The adb `wait-for-<transport>-<state>` grammar, modeled as two closed enums so
# an invalid value is rejected by the tool's input schema (and again in the
# service, for direct callers) before any adb call — the raw wait-for token is
# never exposed on the MCP surface.
DeviceWaitState = Literal["device", "recovery", "rescue", "sideload", "bootloader", "disconnect"]
DeviceWaitTransport = Literal["any", "usb", "local"]

_VALID_WAIT_STATES = frozenset(get_args(DeviceWaitState))
_VALID_WAIT_TRANSPORTS = frozenset(get_args(DeviceWaitTransport))

# Upper bound on the caller-supplied wait timeout. Generous enough for a cold
# emulator boot; bounded so a bad value can't wedge the server indefinitely.
_MAX_WAIT_TIMEOUT_S = 600.0


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


class RestartAdbdAsShellResult(BaseModel):
    """Outcome of dropping the on-device `adbd` daemon back to non-root
    (`adb -s <serial> unroot`) — the inverse of restart_adbd_as_root. Where
    that one is a privilege escalation (categorized destructive), this is a
    de-escalation: it only ever *removes* root from adbd, so it's a plain write.

    Judged on adb's message text, verified live against a rootable emulator
    (the two wordings both exit 0):

    - "restarting adbd as non root" — adbd was root; it's now restarting as
      shell. success=True, already_shell=False.
    - "adbd not running as root" — adbd was already non-root; nothing to do.
      success=True, already_shell=True.

    Like restart_adbd_as_root, only a transport-level failure that never
    reaches adbd — an unknown serial ("adb: device '<serial>' not found",
    exit 1) or the adb binary being unavailable — raises (DeviceNotFoundError
    / AdbUnavailableError). Restarting adbd briefly drops the device off the
    adb transport; an immediately-following call against the same serial can
    transiently fail with device-not-found — retry rather than assume it's gone.
    """

    serial: str
    success: bool
    already_shell: bool
    output: str

    def summary(self) -> str:
        if self.success and self.already_shell:
            return f"adbd was already running as shell (non-root) on {self.serial}."
        if self.success:
            return f"adbd restarted as shell (non-root) on {self.serial}."
        return f"adbd unroot on {self.serial} returned unexpected output: {self.output or 'none'}"


class DeviceStateWaitResult(BaseModel):
    """Outcome of blocking until a device reaches a requested adb transport state
    (`adb -s <serial> wait-for-<transport>-<state>`).

    `adb wait-for-...` prints nothing and exits 0 the moment the state is
    reached, so success is the exit status and this result is the structured
    stand-in for that empty output: which serial was waited on, the state and
    transport that were requested, and how long the wait actually took. A wait
    that never completes within the caller's timeout is surfaced as a retryable
    TIMEOUT error, not as a result with a false flag.
    """

    serial: str
    state: DeviceWaitState
    transport: DeviceWaitTransport
    waited_ms: float

    def summary(self) -> str:
        via = "" if self.transport == "any" else f" over {self.transport}"
        return (
            f"{self.serial} reached adb state '{self.state}'{via} "
            f"after {self.waited_ms:.0f}ms."
        )


def _require_host_port(host: str, port: int) -> None:
    # adb itself rejects a bad host:port (empty host, "bad port number '99999'")
    # but only after a round trip, and connect/disconnect surface that as
    # data.success=False rather than an error. Reject the obviously-invalid
    # cases up front instead, as INVALID_ARGUMENT.
    if not host.strip():
        raise InvalidArgumentError("host must not be empty.", details={"host": host, "port": port})
    if not 1 <= port <= 65535:
        raise InvalidArgumentError(
            "port must be between 1 and 65535.", details={"host": host, "port": port}
        )


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
        _require_host_port(host, port)
        address = f"{host}:{port}"
        result = await self._backend.connect(host, port)
        output = (result.stdout + result.stderr).strip()
        # "connected to <addr>" (fresh) and "already connected to <addr>" (idempotent)
        # are the only two success wordings adb uses; every failure wording observed
        # uses "failed to connect to" instead, which doesn't contain this substring.
        success = "connected to" in output
        return ConnectResult(success=success, address=address, output=output)

    async def disconnect(self, host: str, port: int) -> DisconnectResult:
        _require_host_port(host, port)
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

    async def restart_adbd_as_shell(self, serial: str) -> RestartAdbdAsShellResult:
        result = await self._backend.unroot(serial)
        output = (result.stdout + result.stderr).strip()
        # Known adbd wordings first, regardless of exit code — their presence
        # proves adbd was reached. Both were verified live (rootable car AVD)
        # to exit 0.
        if "adbd not running as root" in output:
            return RestartAdbdAsShellResult(
                serial=serial, success=True, already_shell=True, output=output
            )
        if "restarting adbd as non root" in output:
            return RestartAdbdAsShellResult(
                serial=serial, success=True, already_shell=False, output=output
            )
        # No known wording — adbd was never reached. Classify by transport
        # failure the same way restart_adbd_as_root does.
        if result.exit_code != 0:
            message = output or "adb unroot command exited non-zero."
            if "not found" in message:
                raise DeviceNotFoundError(message, details={"serial": serial})
            raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})
        raise BackendError(
            output or "adb unroot command exited successfully but returned unexpected output.",
            details={"serial": serial},
        )

    async def wait_for_device_state(
        self,
        serial: str,
        state: DeviceWaitState = "device",
        transport: DeviceWaitTransport = "any",
        timeout_s: float = 60.0,
    ) -> DeviceStateWaitResult:
        if state not in _VALID_WAIT_STATES:
            raise InvalidArgumentError(
                f"Unknown wait state {state!r}.",
                details={"state": state, "valid": sorted(_VALID_WAIT_STATES)},
            )
        if transport not in _VALID_WAIT_TRANSPORTS:
            raise InvalidArgumentError(
                f"Unknown wait transport {transport!r}.",
                details={"transport": transport, "valid": sorted(_VALID_WAIT_TRANSPORTS)},
            )
        if not 0 < timeout_s <= _MAX_WAIT_TIMEOUT_S:
            raise InvalidArgumentError(
                f"timeout_s must be between 0 (exclusive) and {_MAX_WAIT_TIMEOUT_S:.0f}.",
                details={"timeout_s": timeout_s, "max": _MAX_WAIT_TIMEOUT_S},
            )

        wait_token = f"wait-for-{transport}-{state}"
        try:
            result = await self._backend.wait_for_device(serial, wait_token, timeout_s)
        except AdbTimeoutError as exc:
            # Re-raise with the automation intent spelled out — the backend's
            # generic "command timed out" doesn't say what was being waited for.
            raise AdbTimeoutError(
                f"Timed out after {timeout_s:.0f}s waiting for {serial} to reach "
                f"adb state {state!r} (transport {transport!r}).",
                details={
                    "serial": serial,
                    "state": state,
                    "transport": transport,
                    "timeout_s": timeout_s,
                },
                remediation=(
                    "The device never reached that state in time. If a reboot or "
                    "mode switch is still in progress, retrying with a longer "
                    "timeout is reasonable."
                ),
            ) from exc

        if result.exit_code != 0:
            output = (result.stderr + result.stdout).strip()
            raise BackendError(
                output or f"adb {wait_token} exited {result.exit_code}.",
                details={"serial": serial, "state": state, "transport": transport},
            )
        return DeviceStateWaitResult(
            serial=serial, state=state, transport=transport, waited_ms=result.duration_ms
        )
