"""Module-level, statically-introspectable tool functions for the port_forwarding module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.port_forwarding.service import ForwardCreated, PortForwardingService
from adb_automation_mcp.registry import category


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
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    port_forwarding = cast(PortForwardingService, services["port_forwarding"])
    return await port_forwarding.create_forward(
        serial, remote_port, local_port=local_port, no_rebind=no_rebind
    )
