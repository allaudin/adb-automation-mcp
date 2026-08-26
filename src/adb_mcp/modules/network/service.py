"""Domain logic for the network module: device network interfaces and their
assigned addresses (`adb shell ip addr show`). Wi-Fi configuration, routing
changes, and adb port forwarding aren't implemented yet.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from adb_mcp.backend.protocol import AdbBackend, CommandResult
from adb_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    NetworkToolUnavailableError,
    PermissionDeniedError,
)

# `ip addr show`'s numbered interface header, e.g.:
#   "2: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000"
# An interface may carry a "@parent" suffix (veth/vlan pairs); that suffix is
# not part of the interface's own name, so it's dropped.
_INTERFACE_HEADER_RE = re.compile(
    r"^\d+:\s+(?P<name>[^:@\s]+)(?:@\S+)?:\s+<(?P<flags>[^>]*)>(?P<rest>.*)$"
)
_STATE_RE = re.compile(r"\bstate\s+(?P<state>\S+)")
_IPV4_ADDRESS_RE = re.compile(r"^\s*inet\s+(?P<address>\S+)")
_IPV6_ADDRESS_RE = re.compile(r"^\s*inet6\s+(?P<address>\S+)")


class NetworkInterface(BaseModel):
    """One network interface and its assigned addresses (`ip addr show`).

    Addresses are kept in CIDR form exactly as `ip` reports them (e.g.
    "192.168.1.100/24"), not split into address/prefix — the least lossy,
    least invented representation of what the device actually returned.
    state is None when the interface's header line didn't carry a
    recognizable "state <VALUE>" token (some `ip` builds omit it) — a
    normal, non-error outcome, not a parsing failure.
    """

    name: str
    state: str | None
    ipv4_addresses: list[str]
    ipv6_addresses: list[str]

    def summary(self) -> str:
        return f"{self.name} ({self.state or 'unknown'})"


class NetworkInterfaceList(BaseModel):
    """Every network interface reported by `adb shell ip addr show`.

    Not verified live (no device was available in this environment) —
    shaped on `ip addr show`'s documented, long-stable iproute2 output
    format. Lines that don't match a recognized interface header or
    address shape are silently skipped rather than raised as errors — this
    parser tolerates partial/malformed output by extracting whatever it
    can, never by failing the whole call over one unrecognized line.
    """

    serial: str
    interfaces: list[NetworkInterface]

    def summary(self) -> str:
        n = len(self.interfaces)
        word = "interface" if n == 1 else "interfaces"
        return f"{n} network {word} on {self.serial}."


class NetworkService:
    """Reads network interfaces and their addresses on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def list_network_interfaces(self, serial: str) -> NetworkInterfaceList:
        result = await self._backend.shell(serial, "ip addr show")
        _raise_for_ip_failure(serial, result)
        return NetworkInterfaceList(serial=serial, interfaces=_parse_interfaces(result.stdout))


def _parse_interfaces(output: str) -> list[NetworkInterface]:
    interfaces: list[NetworkInterface] = []
    name: str | None = None
    state: str | None = None
    ipv4_addresses: list[str] = []
    ipv6_addresses: list[str] = []

    def flush() -> None:
        if name is not None:
            interfaces.append(
                NetworkInterface(
                    name=name,
                    state=state,
                    ipv4_addresses=ipv4_addresses,
                    ipv6_addresses=ipv6_addresses,
                )
            )

    for line in output.splitlines():
        header_match = _INTERFACE_HEADER_RE.match(line)
        if header_match is not None:
            flush()
            name = header_match.group("name")
            state_match = _STATE_RE.search(header_match.group("rest"))
            state = state_match.group("state") if state_match is not None else None
            ipv4_addresses = []
            ipv6_addresses = []
            continue
        if name is None:
            continue  # nothing recognizable yet — ignore until the first interface header
        ipv6_match = _IPV6_ADDRESS_RE.match(line)
        if ipv6_match is not None:
            ipv6_addresses.append(ipv6_match.group("address"))
            continue
        ipv4_match = _IPV4_ADDRESS_RE.match(line)
        if ipv4_match is not None:
            ipv4_addresses.append(ipv4_match.group("address"))
        # anything else (link/ether lines, valid_lft/preferred_lft lines,
        # unrecognized content) is silently skipped

    flush()
    return interfaces


def _raise_for_ip_failure(serial: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's) — the adb-client rejects an unknown serial
    # before any command reaches a device.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    # e.g. "/system/bin/sh: ip: not found" on a build without the `ip`
    # binary/toybox applet.
    if "not found" in message:
        raise NetworkToolUnavailableError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})
