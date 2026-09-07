"""Domain logic for the network module: read-only views of a device's
network state —

- interfaces and their addresses (`adb shell ip addr show`),
- the kernel routing table (`adb shell ip route`),
- a curated connectivity snapshot (`adb shell dumpsys connectivity`):
  the active default network and, per network, its transports and the
  capability flags stable enough to trust (INTERNET / VALIDATED /
  CAPTIVE_PORTAL).

Wi-Fi configuration, routing *changes*, and adb port forwarding aren't
implemented here.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    ConnectivityStateUnavailableError,
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


# `ip route` lines: "<dest> [key value]..." where dest is "default" or a
# CIDR, and the trailing key/value pairs are via/dev/proto/scope/src/metric/
# mtu/table. Only a line whose first token is "default" or starts with a
# digit (an address/CIDR) is treated as a route; anything else is skipped.
_ROUTE_DEST_RE = re.compile(r"^(default|\d[\w./:]*)")


class Route(BaseModel):
    """One kernel routing-table entry (`ip route`).

    destination is "default" for the default route, otherwise the CIDR the
    route covers. gateway is the `via` address (None for an on-link route),
    dev the outgoing interface, source the preferred `src` address, and
    metric the route priority when present. raw is the exact line `ip`
    printed, so nothing the parser didn't model is lost.
    """

    destination: str
    is_default: bool
    gateway: str | None
    dev: str | None
    source: str | None
    proto: str | None
    scope: str | None
    metric: int | None
    raw: str

    def summary(self) -> str:
        via = f" via {self.gateway}" if self.gateway else ""
        dev = f" dev {self.dev}" if self.dev else ""
        return f"{self.destination}{via}{dev}"


class RouteTable(BaseModel):
    """The device's kernel routing table (`adb shell ip route`).

    routes is in the order `ip` printed them and may be empty (a device
    with no configured routes is a valid state, not an error). Lines that
    don't look like a route are skipped rather than raised.
    """

    serial: str
    routes: list[Route]

    def summary(self) -> str:
        n = len(self.routes)
        has_default = any(r.is_default for r in self.routes)
        default = ", has default route" if has_default else ", no default route"
        return f"{n} route{'s' if n != 1 else ''} on {self.serial}{default}."


class NetworkSnapshot(BaseModel):
    """One network from `dumpsys connectivity`'s "Current Networks:" section.

    network_id is ConnectivityManager's netId. network_type/detailed_state
    come from the `ni{TYPE STATE ...}` field (e.g. "WIFI"/"MOBILE",
    "CONNECTED"). transports and capabilities are the raw token lists from
    `nc{[ Transports: ... Capabilities: ... ]}`. has_internet / validated /
    captive_portal are convenience booleans derived from the capability
    tokens — the three stable enough to rely on across Android versions.
    """

    network_id: int
    network_type: str | None
    detailed_state: str | None
    transports: list[str]
    capabilities: list[str]
    has_internet: bool
    validated: bool
    captive_portal: bool


class ConnectivityState(BaseModel):
    """A curated snapshot of Android connectivity (`adb shell dumpsys
    connectivity`).

    `dumpsys connectivity` is large and its format drifts between releases,
    so this models only a small, comparatively stable slice: which network
    is the active default (active_network_id / has_active_network), that
    network's details (active_network — None if there's no default network,
    or its entry couldn't be found), and every network in the "Current
    Networks:" section (networks).
    """

    serial: str
    has_active_network: bool
    active_network_id: int | None
    active_network: NetworkSnapshot | None
    networks: list[NetworkSnapshot]

    def summary(self) -> str:
        if not self.has_active_network:
            return f"No active default network on {self.serial}."
        an = self.active_network
        if an is None:
            return f"Active default network {self.active_network_id} on {self.serial}."
        transports = "+".join(an.transports) or "unknown"
        valid = "validated" if an.validated else "not validated"
        return f"Active {transports} network on {self.serial} ({valid})."


class NetworkService:
    """Read-only views of a connected device's network state: interfaces and
    addresses, the routing table, and a curated connectivity snapshot.
    """

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def list_network_interfaces(self, serial: str) -> NetworkInterfaceList:
        result = await self._backend.shell(serial, "ip addr show")
        _raise_for_ip_failure(serial, result)
        return NetworkInterfaceList(serial=serial, interfaces=_parse_interfaces(result.stdout))

    async def get_routes(self, serial: str) -> RouteTable:
        result = await self._backend.shell(serial, "ip route")
        _raise_for_ip_failure(serial, result)
        return RouteTable(serial=serial, routes=_parse_routes(result.stdout))

    async def get_connectivity_state(self, serial: str) -> ConnectivityState:
        result = await self._backend.shell(serial, "dumpsys connectivity")
        _raise_for_dumpsys_failure(serial, result)

        text = result.stdout
        active_id = _parse_active_network_id(text)
        networks = _parse_connectivity_networks(text)
        if active_id is None and not networks and "Current Networks:" not in text:
            raise ConnectivityStateUnavailableError(
                "dumpsys connectivity produced none of the expected markers.",
                details={"serial": serial, "output_head": text[:400]},
            )
        active = next((n for n in networks if n.network_id == active_id), None)
        return ConnectivityState(
            serial=serial,
            has_active_network=active_id is not None,
            active_network_id=active_id,
            active_network=active,
            networks=networks,
        )


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


def _raise_for_dumpsys_failure(serial: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})


def _parse_routes(output: str) -> list[Route]:
    routes: list[Route] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or not _ROUTE_DEST_RE.match(line):
            continue
        tokens = line.split()
        destination = tokens[0]
        fields: dict[str, str] = {}
        i = 1
        while i < len(tokens) - 1:
            fields[tokens[i]] = tokens[i + 1]
            i += 2
        metric_raw = fields.get("metric")
        try:
            metric = int(metric_raw) if metric_raw is not None else None
        except ValueError:
            metric = None
        routes.append(
            Route(
                destination=destination,
                is_default=destination == "default",
                gateway=fields.get("via"),
                dev=fields.get("dev"),
                source=fields.get("src"),
                proto=fields.get("proto"),
                scope=fields.get("scope"),
                metric=metric,
                raw=line,
            )
        )
    return routes


_ACTIVE_NETWORK_RE = re.compile(r"^Active default network:\s*(?P<id>\S+)\s*$", re.MULTILINE)
_NETWORK_AGENT_RE = re.compile(r"NetworkAgentInfo\{network\{(?P<id>\d+)\}")
_NI_RE = re.compile(r"\bni\{(?P<body>[^}]*)\}")
_TRANSPORTS_RE = re.compile(r"\bTransports:\s*(?P<v>[A-Za-z0-9_|]+)")
_CAPABILITIES_RE = re.compile(r"\bCapabilities:\s*(?P<v>[A-Za-z0-9_&]+)")


def _parse_active_network_id(text: str) -> int | None:
    match = _ACTIVE_NETWORK_RE.search(text)
    if match is None:
        return None
    raw = match.group("id")
    return int(raw) if raw.isdigit() else None


def _parse_connectivity_networks(text: str) -> list[NetworkSnapshot]:
    networks: list[NetworkSnapshot] = []
    for line in text.splitlines():
        agent_match = _NETWORK_AGENT_RE.search(line)
        if agent_match is None:
            continue

        network_type: str | None = None
        detailed_state: str | None = None
        ni_match = _NI_RE.search(line)
        if ni_match is not None:
            ni_tokens = ni_match.group("body").split()
            if ni_tokens:
                # "MOBILE[NR]" -> "MOBILE"; the state is the next token.
                network_type = re.sub(r"\[.*?\]", "", ni_tokens[0]) or None
            if len(ni_tokens) > 1:
                detailed_state = ni_tokens[1]

        transports_match = _TRANSPORTS_RE.search(line)
        transports = transports_match.group("v").split("|") if transports_match else []
        caps_match = _CAPABILITIES_RE.search(line)
        capabilities = caps_match.group("v").split("&") if caps_match else []

        networks.append(
            NetworkSnapshot(
                network_id=int(agent_match.group("id")),
                network_type=network_type,
                detailed_state=detailed_state,
                transports=transports,
                capabilities=capabilities,
                has_internet="INTERNET" in capabilities,
                validated="VALIDATED" in capabilities,
                captive_portal="CAPTIVE_PORTAL" in capabilities,
            )
        )
    return networks
