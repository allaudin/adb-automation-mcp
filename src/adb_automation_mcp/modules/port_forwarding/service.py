"""Domain logic for the port_forwarding module: host↔device socket forwards set
up through the local adb server (`adb forward` / `adb reverse`), as opposed to the
connection module, which manages the adb server's own lifecycle and its device
connections.

`forward` maps a host socket to a device socket (a host client reaches a server
inside the device). `reverse` is the mirror image — a device socket to a host
socket (an app on the device reaches a server on the host). This module models
TCP endpoints for the create tools (host/device port pairs, the overwhelmingly
common case); the list tools return whatever endpoint kind adb reports, verbatim,
so an `localabstract:`/`jdwp:`/`vsock:` mapping created elsewhere still shows up.
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


# --- models ------------------------------------------------------------------


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
        return f"Forwarding host tcp:{self.local_port} → {self.serial} tcp:{self.remote_port}."


class ForwardMapping(BaseModel):
    """One active host→device forward, as reported by `adb forward --list`."""

    serial: str
    local_spec: str
    remote_spec: str


class ForwardList(BaseModel):
    """Active host→device forwards. `adb forward --list` is server-global; when
    serial is set, forwards is filtered to that device, otherwise it's every
    device's forwards.
    """

    serial: str | None
    forwards: list[ForwardMapping]

    def summary(self) -> str:
        scope = f" for {self.serial}" if self.serial else ""
        if not self.forwards:
            return f"No active forwards{scope}."
        return f"{len(self.forwards)} active forward(s){scope}."


class ForwardRemoved(BaseModel):
    """Outcome of `adb forward --remove`. removed is False when there was no
    forward on that host endpoint to begin with — reported as success (the
    desired end state is reached) rather than an error.
    """

    serial: str
    local_spec: str
    removed: bool

    def summary(self) -> str:
        if self.removed:
            return f"Removed forward {self.local_spec} on {self.serial}."
        return f"No forward {self.local_spec} on {self.serial} to remove."


class ReverseCreated(BaseModel):
    """Outcome of creating a device→host TCP reverse (`adb reverse tcp:R tcp:L`).

    Like ForwardCreated but mirrored: remote_port is the device-side port (the
    one adb echoes back, and the one it allocates when you pass 0), local_port
    is the host-side port the device's traffic lands on.
    """

    serial: str
    remote_port: int
    local_port: int
    remote_spec: str
    local_spec: str

    def summary(self) -> str:
        return f"Reversing {self.serial} tcp:{self.remote_port} → host tcp:{self.local_port}."


class ReverseMapping(BaseModel):
    """One active device→host reverse, as reported by `adb reverse --list`."""

    remote_spec: str
    local_spec: str


class ReverseList(BaseModel):
    """Active device→host reverses for one device (`adb reverse --list` is
    device-scoped). serial is the device that was queried — `adb reverse --list`
    prints an internal transport token in that column, not the serial, so it's
    echoed from the request instead.
    """

    serial: str
    reverses: list[ReverseMapping]

    def summary(self) -> str:
        if not self.reverses:
            return f"No active reverses for {self.serial}."
        return f"{len(self.reverses)} active reverse(s) for {self.serial}."


class ReverseRemoved(BaseModel):
    """Outcome of `adb reverse --remove`. removed is False when there was no
    reverse on that device endpoint to begin with — reported as success.
    """

    serial: str
    remote_spec: str
    removed: bool

    def summary(self) -> str:
        if self.removed:
            return f"Removed reverse {self.remote_spec} on {self.serial}."
        return f"No reverse {self.remote_spec} on {self.serial} to remove."


# --- helpers ---------------------------------------------------------------


def _require_port(value: int, *, name: str, allow_zero: bool) -> None:
    low = 0 if allow_zero else _MIN_PORT
    if not low <= value <= _MAX_PORT:
        raise InvalidArgumentError(
            f"{name} must be between {low} and {_MAX_PORT}"
            + (" (0 = let adb pick a free port)" if allow_zero else "")
            + f", got {value}.",
            details={name: value},
        )


def _raise_for_create_failure(
    message: str, *, serial: str, kind: str, port_field: str, port_value: int
) -> None:
    """Shared error translation for `adb forward` / `adb reverse` create
    failures — both use the identical wordings.
    """
    lowered = message.lower()
    if "listener" in lowered and "not found" in lowered:
        # Shouldn't reach a create path, but classify defensively as a bad arg.
        raise InvalidArgumentError(message, details={"serial": serial})
    if "not found" in lowered:
        # "adb: error: device '<serial>' not found" / "adb: device '<serial>' not found"
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "rebind" in lowered:
        raise PortForwardConflictError(
            message,
            details={"serial": serial, port_field: port_value},
            remediation=(
                f"A {kind} already exists on that endpoint. Remove it first, or "
                "call again without no_rebind to take it over."
            ),
        )
    if "bad port" in lowered or "cannot bind listener" in lowered:
        raise InvalidArgumentError(message, details={"serial": serial, port_field: port_value})
    raise BackendError(message, details={"serial": serial})


def _raise_for_remove_or_list_failure(message: str, *, serial: str) -> bool:
    """Error translation for `--remove` / `--list`. Returns True to mean "a
    listener-not-found was seen" (caller turns that into removed=False);
    otherwise raises.
    """
    lowered = message.lower()
    if "listener" in lowered and "not found" in lowered:
        return True
    if "not found" in lowered:
        raise DeviceNotFoundError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial})


def _parse_resolved_port(stdout: str) -> int | None:
    """`adb forward`/`adb reverse` print just the resolved port number on
    success. Anything that isn't a lone in-range integer is "not reported".
    """
    text = stdout.strip()
    if not text.isdigit():
        return None
    port = int(text)
    return port if _MIN_PORT <= port <= _MAX_PORT else None


def _parse_forward_list(stdout: str, serial_filter: str | None) -> list[ForwardMapping]:
    """`adb forward --list` lines are "<serial> <local> <remote>". Lines with
    fewer than three whitespace-separated tokens are skipped, not fatal.
    """
    mappings: list[ForwardMapping] = []
    for raw in stdout.splitlines():
        parts = raw.split()
        if len(parts) < 3:
            continue
        serial, local_spec, remote_spec = parts[0], parts[1], parts[2]
        if serial_filter is not None and serial != serial_filter:
            continue
        mappings.append(
            ForwardMapping(serial=serial, local_spec=local_spec, remote_spec=remote_spec)
        )
    return mappings


def _parse_reverse_list(stdout: str) -> list[ReverseMapping]:
    """`adb reverse --list` lines are "<transport-token> <remote> <local>" —
    column 0 is an internal token, not the serial, so it's ignored.
    """
    mappings: list[ReverseMapping] = []
    for raw in stdout.splitlines():
        parts = raw.split()
        if len(parts) < 3:
            continue
        mappings.append(ReverseMapping(remote_spec=parts[1], local_spec=parts[2]))
    return mappings


# --- service -------------------------------------------------------------------


class PortForwardingService:
    """Host↔device socket forwards managed through the local adb server."""

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
            _raise_for_create_failure(
                message,
                serial=serial,
                kind="forward",
                port_field="local_port",
                port_value=local_port,
            )

        resolved = _parse_resolved_port(result.stdout)
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

    async def list_forwards(self, serial: str | None = None) -> ForwardList:
        result = await self._backend.forward_list()
        if result.exit_code != 0:
            message = (result.stderr + result.stdout).strip() or "adb forward --list exited non-zero."
            raise BackendError(message, details={"exit_code": result.exit_code})
        return ForwardList(
            serial=serial, forwards=_parse_forward_list(result.stdout, serial)
        )

    async def remove_forward(self, serial: str, local_port: int) -> ForwardRemoved:
        _require_port(local_port, name="local_port", allow_zero=False)
        local_spec = f"tcp:{local_port}"
        result = await self._backend.forward_remove(serial, local_spec)

        removed = True
        if result.exit_code != 0:
            message = (
                result.stderr + result.stdout
            ).strip() or "adb forward --remove exited non-zero."
            listener_absent = _raise_for_remove_or_list_failure(message, serial=serial)
            removed = not listener_absent

        return ForwardRemoved(serial=serial, local_spec=local_spec, removed=removed)

    async def create_reverse(
        self,
        serial: str,
        remote_port: int = 0,
        local_port: int = 0,
        no_rebind: bool = False,
    ) -> ReverseCreated:
        # Mirror image of create_forward: the device-side (remote) port may be 0
        # for adb to allocate; the host-side (local) port must be a real port.
        _require_port(remote_port, name="remote_port", allow_zero=True)
        _require_port(local_port, name="local_port", allow_zero=False)

        remote_spec = f"tcp:{remote_port}"
        local_spec = f"tcp:{local_port}"
        result = await self._backend.reverse(serial, remote_spec, local_spec, no_rebind)

        if result.exit_code != 0:
            message = (result.stderr + result.stdout).strip() or "adb reverse exited non-zero."
            _raise_for_create_failure(
                message,
                serial=serial,
                kind="reverse",
                port_field="remote_port",
                port_value=remote_port,
            )

        resolved = _parse_resolved_port(result.stdout)
        if resolved is None:
            if remote_port == 0:
                raise BackendError(
                    "adb reverse succeeded but did not report the allocated device port.",
                    details={"serial": serial, "stdout": result.stdout.strip()},
                )
            resolved = remote_port

        return ReverseCreated(
            serial=serial,
            remote_port=resolved,
            local_port=local_port,
            remote_spec=f"tcp:{resolved}",
            local_spec=local_spec,
        )

    async def list_reverses(self, serial: str) -> ReverseList:
        result = await self._backend.reverse_list(serial)
        if result.exit_code != 0:
            message = (
                result.stderr + result.stdout
            ).strip() or "adb reverse --list exited non-zero."
            _raise_for_remove_or_list_failure(message, serial=serial)
        return ReverseList(serial=serial, reverses=_parse_reverse_list(result.stdout))

    async def remove_reverse(self, serial: str, remote_port: int) -> ReverseRemoved:
        _require_port(remote_port, name="remote_port", allow_zero=False)
        remote_spec = f"tcp:{remote_port}"
        result = await self._backend.reverse_remove(serial, remote_spec)

        removed = True
        if result.exit_code != 0:
            message = (
                result.stderr + result.stdout
            ).strip() or "adb reverse --remove exited non-zero."
            listener_absent = _raise_for_remove_or_list_failure(message, serial=serial)
            removed = not listener_absent

        return ReverseRemoved(serial=serial, remote_spec=remote_spec, removed=removed)
