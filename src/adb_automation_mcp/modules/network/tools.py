"""Module-level, statically-introspectable tool functions for the network module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.network.service import (
    ConnectivityState,
    NetworkInterfaceList,
    NetworkService,
    RouteTable,
)
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


@category("read")
async def get_routes(ctx: Context, serial: str) -> RouteTable:
    """List the device's kernel routing table: `adb shell ip route`.

    Use this to diagnose why a device with an IP address still can't reach
    a host — a missing default route, or traffic leaving the wrong
    interface. Each line `ip` prints is parsed into destination / gateway /
    dev / src / proto / scope / metric, with the original line kept as
    `raw`. Changing routes isn't implemented here.

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial and routes: one entry per routing-table line, in the
        order `ip` printed them. destination is "default" or a CIDR;
        is_default flags the default route; gateway/dev/source/proto/scope
        are None when that field wasn't on the line; metric is an int or
        None. An empty list is a valid result (device with no routes), not
        an error.

    Error handling:
        An unknown serial or unresponsive adb binary raises DEVICE_NOT_FOUND/
        ADB_UNAVAILABLE. The `ip` command not being present raises
        NETWORK_TOOL_UNAVAILABLE. A permission rejection raises
        PERMISSION_DENIED; any other non-zero exit raises BACKEND_ERROR.
        Lines that don't look like a route are skipped, not raised.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "2 routes on emulator-5554, has default route.",
          "data": {
            "serial": "emulator-5554",
            "routes": [
              {
                "destination": "default", "is_default": true, "gateway": "10.0.2.2",
                "dev": "eth0", "source": null, "proto": null, "scope": null,
                "metric": null, "raw": "default via 10.0.2.2 dev eth0"
              },
              {
                "destination": "10.0.2.0/24", "is_default": false, "gateway": null,
                "dev": "eth0", "source": "10.0.2.15", "proto": "kernel", "scope": "link",
                "metric": null,
                "raw": "10.0.2.0/24 dev eth0 proto kernel scope link src 10.0.2.15"
              }
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    network = cast(NetworkService, services["network"])
    return await network.get_routes(serial)


@category("read")
async def get_connectivity_state(ctx: Context, serial: str) -> ConnectivityState:
    """Curated connectivity snapshot: `adb shell dumpsys connectivity`.

    The right check before a test that needs the internet — confirm there's
    an active default network and that it's validated. `dumpsys
    connectivity` is huge and its format drifts between Android versions, so
    this reads only a small stable slice: the active default network id and,
    per network in the "Current Networks:" section, its transports and the
    capability flags worth trusting (INTERNET / VALIDATED / CAPTIVE_PORTAL).

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial; has_active_network and active_network_id (None when
        there's no default network); active_network (that network's entry,
        or None if absent); and networks — every parsed network, each with
        network_id, network_type ("WIFI"/"MOBILE"/…), detailed_state
        ("CONNECTED"/…), transports, capabilities (raw token list), and the
        has_internet / validated / captive_portal booleans.

    Error handling:
        An unknown serial or unresponsive adb binary raises DEVICE_NOT_FOUND/
        ADB_UNAVAILABLE. A permission rejection raises PERMISSION_DENIED.
        Output carrying none of the expected markers raises
        CONNECTIVITY_STATE_UNAVAILABLE; any other non-zero exit raises
        BACKEND_ERROR. "No active default network" is a normal success
        result, not an error.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "Active WIFI network on emulator-5554 (validated).",
          "data": {
            "serial": "emulator-5554",
            "has_active_network": true,
            "active_network_id": 100,
            "active_network": {
              "network_id": 100, "network_type": "WIFI", "detailed_state": "CONNECTED",
              "transports": ["WIFI"], "capabilities": ["INTERNET", "VALIDATED", "NOT_METERED"],
              "has_internet": true, "validated": true, "captive_portal": false
            },
            "networks": [
              {
                "network_id": 100, "network_type": "WIFI", "detailed_state": "CONNECTED",
                "transports": ["WIFI"], "capabilities": ["INTERNET", "VALIDATED", "NOT_METERED"],
                "has_internet": true, "validated": true, "captive_portal": false
              }
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    network = cast(NetworkService, services["network"])
    return await network.get_connectivity_state(serial)
