"""Module-level, statically-introspectable tool functions for the network module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.network.service import NetworkInterfaceList, NetworkService
from adb_automation_mcp.registry import category


@category("read")
async def list_network_interfaces(ctx: Context, serial: str) -> NetworkInterfaceList:
    """List the device's network interfaces and their addresses: `adb shell ip addr show`.

    Parses `ip addr show`'s structured output into per-interface records
    rather than exposing the raw text. Tolerates multiple IPv4/IPv6
    addresses per interface, and any line it doesn't recognize is skipped
    rather than failing the whole call. Wi-Fi configuration, routing
    changes, and adb port forwarding aren't implemented here.

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial and every network interface found, each with its name,
        state (None when not reliably reported), and IPv4/IPv6 addresses
        in CIDR form (e.g. "192.168.1.100/24"). An interface with no
        addresses at all (e.g. a down interface) is included with empty
        address lists, not omitted.

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. The `ip` command not being
        available on this device raises NETWORK_TOOL_UNAVAILABLE. A
        permission rejection raises PERMISSION_DENIED; any other failure
        raises a generic BACKEND_ERROR. Malformed or partial output is not
        an error — unrecognized lines are simply skipped, and interfaces
        that do parse are still returned.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "2 network interfaces on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "interfaces": [
              {"name": "lo", "state": "UNKNOWN", "ipv4_addresses": ["127.0.0.1/8"], "ipv6_addresses": ["::1/128"]},
              {"name": "wlan0", "state": "UP", "ipv4_addresses": ["192.168.1.100/24"], "ipv6_addresses": ["fe80::abcd:1234:5678:9abc/64"]}
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    network = cast(NetworkService, services["network"])
    return await network.list_network_interfaces(serial)
