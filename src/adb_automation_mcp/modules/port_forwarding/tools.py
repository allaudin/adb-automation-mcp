"""Module-level, statically-introspectable tool functions for the port_forwarding module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.port_forwarding.service import (
    ForwardCreated,
    ForwardList,
    ForwardRemoved,
    PortForwardingService,
    ReverseCreated,
    ReverseList,
    ReverseRemoved,
)
from adb_automation_mcp.registry import category


def _svc(ctx: Context) -> PortForwardingService:
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    return cast(PortForwardingService, services["port_forwarding"])


@category("write")
async def create_forward(
    ctx: Context,
    serial: str,
    remote_port: int,
    local_port: int = 0,
    no_rebind: bool = False,
) -> ForwardCreated:
    """Forward a host TCP port to a device TCP port: `adb -s serial forward tcp:L tcp:R`.

    Sets up a tunnel so a client on this host can reach a server listening
    inside the device — e.g. exposing the device's `tcp:8080` as host
    `tcp:6100` for a local integration test. The mapping lives in the local adb
    server until removed or until adb restarts.

    Args:
        serial: The target device's serial number, as reported by
            list_connected_devices.
        remote_port: The device-side TCP port to forward to, 1-65535.
        local_port: The host-side TCP port to listen on, 1-65535, or 0 (the
            default) to let adb allocate a free port — the chosen port is
            returned in local_port either way.
        no_rebind: If true, fail instead of silently taking over a host port
            that already has a forward on it. Default false (rebind allowed).

    Returns:
        The serial, the resolved local_port (always a concrete, connectable
        host port — never 0), remote_port, and the "tcp:<n>" local_spec /
        remote_spec strings adb was given.

    Error handling:
        An unknown serial raises DEVICE_NOT_FOUND; an unreachable adb binary
        raises ADB_UNAVAILABLE. A port outside its valid range raises
        INVALID_ARGUMENT before any adb call. no_rebind hitting an existing
        forward raises PORT_FORWARD_CONFLICT.

    Example:
        Called with serial="emulator-5554", remote_port=8080, local_port=6100.
        A typical response:

        ```json
        {
          "status": "success",
          "message": "Forwarding host tcp:6100 → emulator-5554 tcp:8080.",
          "data": {
            "serial": "emulator-5554",
            "local_port": 6100,
            "remote_port": 8080,
            "local_spec": "tcp:6100",
            "remote_spec": "tcp:8080"
          },
          "error": null
        }
        ```
    """
    return await _svc(ctx).create_forward(
        serial, remote_port, local_port=local_port, no_rebind=no_rebind
    )


@category("read")
async def list_forwards(ctx: Context, serial: str | None = None) -> ForwardList:
    """List active host→device forwards: `adb forward --list`.

    `adb forward --list` is server-global — it reports forwards for every
    connected device. Pass serial to narrow the result to one device.

    Args:
        serial: Optional device serial to filter by. Omit to list forwards for
            all connected devices.

    Returns:
        The serial filter that was applied (null if none), and a list of
        forwards, each with its serial, local_spec (host side), and remote_spec
        (device side). An endpoint kind other than tcp: (e.g. localabstract:)
        created elsewhere is returned verbatim.

    Error handling:
        An unreachable adb binary raises ADB_UNAVAILABLE. `adb forward --list`
        does not fail for an unknown serial — it just returns nothing for it —
        so a bogus serial yields an empty list, not an error.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "1 active forward(s) for emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "forwards": [
              {
                "serial": "emulator-5554",
                "local_spec": "tcp:6100",
                "remote_spec": "tcp:8080"
              }
            ]
          },
          "error": null
        }
        ```
    """
    return await _svc(ctx).list_forwards(serial)


@category("write")
async def remove_forward(ctx: Context, serial: str, local_port: int) -> ForwardRemoved:
    """Remove one host→device forward: `adb -s serial forward --remove tcp:L`.

    Tears down a forward previously created with create_forward, identified by
    its host-side port. Idempotent: removing a forward that isn't there is
    reported as success (removed=false), not an error — the intended end state
    is reached either way.

    Args:
        serial: The target device's serial number, as reported by
            list_connected_devices.
        local_port: The host-side TCP port of the forward to remove, 1-65535.

    Returns:
        The serial, the local_spec that was targeted, and removed — true if a
        forward was actually torn down, false if there was none on that port.

    Error handling:
        An unknown serial raises DEVICE_NOT_FOUND; an unreachable adb binary
        raises ADB_UNAVAILABLE. A port outside 1-65535 raises INVALID_ARGUMENT
        before any adb call.

    Example:
        Called with serial="emulator-5554", local_port=6100. A typical response:

        ```json
        {
          "status": "success",
          "message": "Removed forward tcp:6100 on emulator-5554.",
          "data": {"serial": "emulator-5554", "local_spec": "tcp:6100", "removed": true},
          "error": null
        }
        ```
    """
    return await _svc(ctx).remove_forward(serial, local_port)


@category("write")
async def create_reverse(
    ctx: Context,
    serial: str,
    remote_port: int = 0,
    local_port: int = 0,
    no_rebind: bool = False,
) -> ReverseCreated:
    """Reverse-forward a device TCP port to a host TCP port: `adb -s serial reverse tcp:R tcp:L`.

    The mirror image of create_forward — lets a process on the device reach a
    server running on this host, e.g. so an app under test on the emulator can
    call a mock HTTP server on `localhost:7000` of the host.

    Args:
        serial: The target device's serial number, as reported by
            list_connected_devices.
        remote_port: The device-side TCP port the device will listen on,
            1-65535, or 0 (the default) to let adb allocate one on the device —
            the chosen port is returned in remote_port either way.
        local_port: The host-side TCP port to send the device's traffic to,
            1-65535. Required (0 is not valid here — it must point at a real
            host listener).
        no_rebind: If true, fail instead of taking over a device port that
            already has a reverse on it. Default false.

    Returns:
        The serial, the resolved remote_port (always concrete, never 0),
        local_port, and the "tcp:<n>" remote_spec / local_spec strings.

    Error handling:
        An unknown/offline serial raises DEVICE_NOT_FOUND; an unreachable adb
        binary raises ADB_UNAVAILABLE. A port outside its valid range raises
        INVALID_ARGUMENT before any adb call. no_rebind hitting an existing
        reverse raises PORT_FORWARD_CONFLICT.

    Example:
        Called with serial="emulator-5554", remote_port=8080, local_port=7000.
        A typical response:

        ```json
        {
          "status": "success",
          "message": "Reversing emulator-5554 tcp:8080 → host tcp:7000.",
          "data": {
            "serial": "emulator-5554",
            "remote_port": 8080,
            "local_port": 7000,
            "remote_spec": "tcp:8080",
            "local_spec": "tcp:7000"
          },
          "error": null
        }
        ```
    """
    return await _svc(ctx).create_reverse(
        serial, remote_port=remote_port, local_port=local_port, no_rebind=no_rebind
    )


@category("read")
async def list_reverses(ctx: Context, serial: str) -> ReverseList:
    """List active device→host reverses for one device: `adb -s serial reverse --list`.

    Unlike forwards, reverse tunnels are device-scoped, so this needs a serial.

    Args:
        serial: The target device's serial number, as reported by
            list_connected_devices.

    Returns:
        The serial queried, and a list of reverses, each with its remote_spec
        (device side) and local_spec (host side). An endpoint kind other than
        tcp: is returned verbatim.

    Error handling:
        An unknown/offline serial raises DEVICE_NOT_FOUND; an unreachable adb
        binary raises ADB_UNAVAILABLE. No reverses is a valid empty list, not
        an error.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "1 active reverse(s) for emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "reverses": [{"remote_spec": "tcp:8080", "local_spec": "tcp:7000"}]
          },
          "error": null
        }
        ```
    """
    return await _svc(ctx).list_reverses(serial)


@category("write")
async def remove_reverse(ctx: Context, serial: str, remote_port: int) -> ReverseRemoved:
    """Remove one device→host reverse: `adb -s serial reverse --remove tcp:R`.

    Tears down a reverse previously created with create_reverse, identified by
    its device-side port. Idempotent: removing one that isn't there is reported
    as success (removed=false), not an error.

    Args:
        serial: The target device's serial number, as reported by
            list_connected_devices.
        remote_port: The device-side TCP port of the reverse to remove, 1-65535.

    Returns:
        The serial, the remote_spec that was targeted, and removed — true if a
        reverse was actually torn down, false if there was none on that port.

    Error handling:
        An unknown/offline serial raises DEVICE_NOT_FOUND; an unreachable adb
        binary raises ADB_UNAVAILABLE. A port outside 1-65535 raises
        INVALID_ARGUMENT before any adb call.

    Example:
        Called with serial="emulator-5554", remote_port=8080. A typical response:

        ```json
        {
          "status": "success",
          "message": "Removed reverse tcp:8080 on emulator-5554.",
          "data": {"serial": "emulator-5554", "remote_spec": "tcp:8080", "removed": true},
          "error": null
        }
        ```
    """
    return await _svc(ctx).remove_reverse(serial, remote_port)
