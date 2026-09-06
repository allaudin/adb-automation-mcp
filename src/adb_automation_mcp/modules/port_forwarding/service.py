"""Domain logic for the port_forwarding module: host-to-device socket forwards
set up through the local adb server (`adb forward`), as opposed to the connection
module, which manages the adb server's own lifecycle and its device connections.

This first cut models TCP endpoints only — a host TCP port forwarded to a device
TCP port, the overwhelmingly common case. The other documented endpoint kinds
(`localabstract:`, `jdwp:`, `vsock:`, …) are a deliberate later addition, not a
generic free-form spec string.
"""

from __future__ import annotations

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PortForwardConflictError,
)

_MIN_PORT = 1
_MAX_PORT = 65535


class ForwardCreated(BaseModel):
    """Outcome of creating a host→device TCP forward (`adb forward tcp:L tcp:R`).

    `adb forward` echoes the resolved host port on stdout — the number you
    passed for an explicit local port, or the port adb picked when local_port
    was 0 — so local_port here is always the concrete, connectable host port,
    never 0. Feed it straight into a client that needs to reach the device
    endpoint.
    """

    serial: str
    local_port: int
    remote_port: int
    local_spec: str
    remote_spec: str

    def summary(self) -> str:
        return (
            f"Forwarding host tcp:{self.local_port} → {self.serial} "
            f"tcp:{self.remote_port}."
        )


def _require_port(value: int, *, name: str, allow_zero: bool) -> None:
    low = 0 if allow_zero else _MIN_PORT
    if not low <= value <= _MAX_PORT:
        raise InvalidArgumentError(
            f"{name} must be between {low} and {_MAX_PORT}"
            + (" (0 = let adb pick a free host port)" if allow_zero else "")
            + f", got {value}.",
            details={name: value},
        )


class PortForwardingService:
    """Host-to-device socket forwards managed through the local adb server."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def create_forward(
        self,
        serial: str,
        remote_port: int,
        local_port: int = 0,
        no_rebind: bool = False,
    ) -> ForwardCreated:
        _require_port(local_port, name="local_port", allow_zero=True)
        _require_port(remote_port, name="remote_port", allow_zero=False)

        local_spec = f"tcp:{local_port}"
        remote_spec = f"tcp:{remote_port}"
        result = await self._backend.forward(serial, local_spec, remote_spec, no_rebind)

        if result.exit_code != 0:
            message = (result.stderr + result.stdout).strip() or "adb forward exited non-zero."
            lowered = message.lower()
            if "not found" in lowered:
                raise DeviceNotFoundError(message, details={"serial": serial})
            if "rebind" in lowered:
                raise PortForwardConflictError(
                    message,
                    details={"serial": serial, "local_port": local_port},
                    remediation=(
                        "A forward already exists on that host port. Remove it first, "
                        "or call again without no_rebind to take it over."
                    ),
                )
            if "bad port" in lowered or "cannot bind listener" in lowered:
                raise InvalidArgumentError(
                    message, details={"serial": serial, "local_port": local_port}
                )
            raise BackendError(
                message, details={"serial": serial, "exit_code": result.exit_code}
            )

        resolved = _parse_resolved_local_port(result.stdout)
        if resolved is None:
            if local_port == 0:
                raise BackendError(
                    "adb forward succeeded but did not report the allocated host port.",
                    details={"serial": serial, "stdout": result.stdout.strip()},
                )
            resolved = local_port

        return ForwardCreated(
            serial=serial,
            local_port=resolved,
            remote_port=remote_port,
            local_spec=f"tcp:{resolved}",
            remote_spec=remote_spec,
        )


def _parse_resolved_local_port(stdout: str) -> int | None:
    """`adb forward` prints just the host port number (e.g. "6100" or an
    adb-allocated "44467") on success. Anything that isn't a lone integer is
    treated as "not reported" rather than raising.
    """
    text = stdout.strip()
    if not text.isdigit():
        return None
    port = int(text)
    return port if _MIN_PORT <= port <= _MAX_PORT else None
