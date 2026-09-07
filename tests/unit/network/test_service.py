"""Layer 1 unit tests: NetworkService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    BackendError,
    ConnectivityStateUnavailableError,
    DeviceNotFoundError,
    NetworkToolUnavailableError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.network.service import NetworkService


def _routes(stdout: str) -> FakeBackend:
    return FakeBackend(
        ip_route_result=CommandResult(stdout=stdout, stderr="", exit_code=0, duration_ms=20.0)
    )


def _conn(stdout: str) -> FakeBackend:
    return FakeBackend(
        dumpsys_connectivity_result=CommandResult(
            stdout=stdout, stderr="", exit_code=0, duration_ms=120.0
        )
    )


@pytest.mark.asyncio
async def test_list_network_interfaces__parses_multiple_interfaces_and_addresses() -> None:
    service = NetworkService(FakeBackend())

    result = await service.list_network_interfaces("emulator-5554")

    assert result.serial == "emulator-5554"
    names = [iface.name for iface in result.interfaces]
    assert names == ["lo", "wlan0", "rmnet_data0"]

    lo = result.interfaces[0]
    assert lo.state == "UNKNOWN"
    assert lo.ipv4_addresses == ["127.0.0.1/8"]
    assert lo.ipv6_addresses == ["::1/128"]

    wlan0 = result.interfaces[1]
    assert wlan0.state == "UP"
    assert wlan0.ipv4_addresses == ["192.168.1.100/24"]
    assert wlan0.ipv6_addresses == ["fe80::abcd:1234:5678:9abc/64"]


@pytest.mark.asyncio
async def test_list_network_interfaces__interface_with_no_addresses() -> None:
    service = NetworkService(FakeBackend())

    result = await service.list_network_interfaces("emulator-5554")

    down_iface = result.interfaces[2]
    assert down_iface.name == "rmnet_data0"
    assert down_iface.state == "DOWN"
    assert down_iface.ipv4_addresses == []
    assert down_iface.ipv6_addresses == []


@pytest.mark.asyncio
async def test_list_network_interfaces__loopback_only() -> None:
    backend = FakeBackend(
        ip_addr_show_result=CommandResult(
            stdout=(
                "1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN group default qlen 1000\n"
                "    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00\n"
                "    inet 127.0.0.1/8 scope host lo\n"
                "       valid_lft forever preferred_lft forever\n"
                "    inet6 ::1/128 scope host \n"
                "       valid_lft forever preferred_lft forever\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=30.0,
        )
    )
    service = NetworkService(backend)

    result = await service.list_network_interfaces("emulator-5554")

    assert len(result.interfaces) == 1
    assert result.interfaces[0].name == "lo"
    assert result.interfaces[0].ipv4_addresses == ["127.0.0.1/8"]
    assert result.interfaces[0].ipv6_addresses == ["::1/128"]


@pytest.mark.asyncio
async def test_list_network_interfaces__ipv6_only_interface() -> None:
    backend = FakeBackend(
        ip_addr_show_result=CommandResult(
            stdout=(
                "4: rmnet_data1: <UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000\n"
                "    link/none \n"
                "    inet6 fe80::1234:5678:9abc:def0/64 scope link \n"
                "       valid_lft forever preferred_lft forever\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=30.0,
        )
    )
    service = NetworkService(backend)

    result = await service.list_network_interfaces("emulator-5554")

    assert len(result.interfaces) == 1
    assert result.interfaces[0].ipv4_addresses == []
    assert result.interfaces[0].ipv6_addresses == ["fe80::1234:5678:9abc:def0/64"]


@pytest.mark.asyncio
async def test_list_network_interfaces__malformed_output_returns_empty_list_not_error() -> None:
    backend = FakeBackend(
        ip_addr_show_result=CommandResult(
            stdout="this is not anything ip addr show would produce\ntotally garbage text\n",
            stderr="",
            exit_code=0,
            duration_ms=5.0,
        )
    )
    service = NetworkService(backend)

    result = await service.list_network_interfaces("emulator-5554")

    assert result.interfaces == []


@pytest.mark.asyncio
async def test_list_network_interfaces__partial_output_still_parses_recognizable_interfaces() -> (
    None
):
    backend = FakeBackend(
        ip_addr_show_result=CommandResult(
            stdout=(
                "garbage preamble that shouldn't be here\n"
                "2: wlan0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP group default qlen 1000\n"
                "    link/ether 02:00:00:00:00:00 brd ff:ff:ff:ff:ff:ff\n"
                "    inet 10.0.0.5/24 brd 10.0.0.255 scope global wlan0\n"
                "       valid_lft forever preferred_lft forever\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=5.0,
        )
    )
    service = NetworkService(backend)

    result = await service.list_network_interfaces("emulator-5554")

    assert len(result.interfaces) == 1
    assert result.interfaces[0].name == "wlan0"
    assert result.interfaces[0].ipv4_addresses == ["10.0.0.5/24"]


@pytest.mark.asyncio
async def test_list_network_interfaces__command_unavailable_raises_network_tool_unavailable() -> (
    None
):
    backend = FakeBackend(
        ip_addr_show_result=CommandResult(
            stdout="", stderr="/system/bin/sh: ip: not found\n", exit_code=127, duration_ms=5.0
        )
    )
    service = NetworkService(backend)

    with pytest.raises(NetworkToolUnavailableError):
        await service.list_network_interfaces("emulator-5554")


@pytest.mark.asyncio
async def test_list_network_interfaces__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        ip_addr_show_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    service = NetworkService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.list_network_interfaces("bogus")


@pytest.mark.asyncio
async def test_list_network_interfaces__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        ip_addr_show_result=CommandResult(
            stdout="", stderr="some other unclassified failure\n", exit_code=1, duration_ms=5.0
        )
    )
    service = NetworkService(backend)

    with pytest.raises(BackendError):
        await service.list_network_interfaces("emulator-5554")


# --- get_routes ----------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_routes__sends_ip_route() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command, timeout_s)

    await NetworkService(RecordingBackend()).get_routes("emulator-5554")

    assert captured["command"] == "ip route"


@pytest.mark.asyncio
async def test_get_routes__parses_default_fixture_single_on_link_route() -> None:
    result = await NetworkService(FakeBackend()).get_routes("emulator-5554")

    assert result.serial == "emulator-5554"
    assert len(result.routes) == 1
    route = result.routes[0]
    assert route.destination == "10.0.2.0/24"
    assert route.is_default is False
    assert route.gateway is None
    assert route.dev == "eth0"
    assert route.source == "10.0.2.15"
    assert route.proto == "kernel"
    assert route.scope == "link"
    assert route.metric is None


@pytest.mark.asyncio
async def test_get_routes__parses_default_route_and_metric() -> None:
    result = await NetworkService(
        _routes(
            "default via 192.168.1.1 dev wlan0 proto static metric 600\n"
            "192.168.1.0/24 dev wlan0 proto kernel scope link src 192.168.1.42 metric 600\n"
        )
    ).get_routes("emulator-5554")

    assert [r.destination for r in result.routes] == ["default", "192.168.1.0/24"]
    default = result.routes[0]
    assert default.is_default is True
    assert default.gateway == "192.168.1.1"
    assert default.dev == "wlan0"
    assert default.metric == 600
    assert result.routes[1].metric == 600
    assert result.routes[1].source == "192.168.1.42"


@pytest.mark.asyncio
async def test_get_routes__no_routes_is_valid_empty_result() -> None:
    result = await NetworkService(_routes("")).get_routes("emulator-5554")

    assert result.routes == []


@pytest.mark.asyncio
async def test_get_routes__malformed_lines_are_skipped_not_raised() -> None:
    result = await NetworkService(
        _routes(
            "this is not a route at all\n"
            "\n"
            "10.0.0.0/8 dev eth0 scope link\n"
            "Error: garbage from a broken build\n"
        )
    ).get_routes("emulator-5554")

    assert [r.destination for r in result.routes] == ["10.0.0.0/8"]
    assert result.routes[0].dev == "eth0"


@pytest.mark.asyncio
async def test_get_routes__ip_missing_raises_network_tool_unavailable() -> None:
    backend = FakeBackend(
        ip_route_result=CommandResult(
            stdout="", stderr="/system/bin/sh: ip: not found\n", exit_code=127, duration_ms=5.0
        )
    )
    with pytest.raises(NetworkToolUnavailableError):
        await NetworkService(backend).get_routes("emulator-5554")


@pytest.mark.asyncio
async def test_get_routes__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        ip_route_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    with pytest.raises(DeviceNotFoundError):
        await NetworkService(backend).get_routes("bogus")


# --- get_connectivity_state --------------------------------------------------


@pytest.mark.asyncio
async def test_get_connectivity_state__sends_dumpsys_connectivity() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command, timeout_s)

    await NetworkService(RecordingBackend()).get_connectivity_state("emulator-5554")

    assert captured["command"] == "dumpsys connectivity"


@pytest.mark.asyncio
async def test_get_connectivity_state__parses_default_fixture_validated_cellular() -> None:
    result = await NetworkService(FakeBackend()).get_connectivity_state("emulator-5554")

    assert result.serial == "emulator-5554"
    assert result.has_active_network is True
    assert result.active_network_id == 100
    assert result.active_network is not None
    an = result.active_network
    assert an.network_id == 100
    assert an.network_type == "MOBILE"
    assert an.detailed_state == "CONNECTED"
    assert an.transports == ["CELLULAR"]
    assert an.has_internet is True
    assert an.validated is True
    assert an.captive_portal is False
    assert [n.network_id for n in result.networks] == [100]


@pytest.mark.asyncio
async def test_get_connectivity_state__no_active_default_network_is_success() -> None:
    result = await NetworkService(
        _conn("Active default network: none\n\nCurrent Networks:\n")
    ).get_connectivity_state("emulator-5554")

    assert result.has_active_network is False
    assert result.active_network_id is None
    assert result.active_network is None
    assert result.networks == []


@pytest.mark.asyncio
async def test_get_connectivity_state__wifi_transport_and_multiple_networks() -> None:
    result = await NetworkService(
        _conn(
            "Active default network: 205\n"
            "Current Networks:\n"
            "  NetworkAgentInfo{network{205}  ni{WIFI CONNECTED} "
            "nc{[ Transports: WIFI Capabilities: INTERNET&VALIDATED&NOT_METERED ]}  x}\n"
            "  NetworkAgentInfo{network{201}  ni{MOBILE DISCONNECTED} "
            "nc{[ Transports: CELLULAR Capabilities: INTERNET ]}  x}\n"
        )
    ).get_connectivity_state("emulator-5554")

    assert [n.network_id for n in result.networks] == [205, 201]
    assert result.active_network is not None
    assert result.active_network.transports == ["WIFI"]
    assert result.active_network.validated is True
    assert result.networks[1].validated is False
    assert result.networks[1].detailed_state == "DISCONNECTED"


@pytest.mark.asyncio
async def test_get_connectivity_state__active_id_present_but_entry_missing() -> None:
    result = await NetworkService(
        _conn(
            "Active default network: 999\n"
            "Current Networks:\n"
            "  NetworkAgentInfo{network{100}  ni{WIFI CONNECTED} "
            "nc{[ Transports: WIFI Capabilities: INTERNET ]}  x}\n"
        )
    ).get_connectivity_state("emulator-5554")

    assert result.has_active_network is True
    assert result.active_network_id == 999
    assert result.active_network is None
    assert [n.network_id for n in result.networks] == [100]


@pytest.mark.asyncio
async def test_get_connectivity_state__unrecognized_output_raises_unavailable() -> None:
    with pytest.raises(ConnectivityStateUnavailableError):
        await NetworkService(_conn("Can't find service: connectivity\n")).get_connectivity_state(
            "emulator-5554"
        )


@pytest.mark.asyncio
async def test_get_connectivity_state__garbage_output_does_not_crash_parser() -> None:
    with pytest.raises(ConnectivityStateUnavailableError):
        await NetworkService(
            _conn("\x00 ]]]}}} NetworkAgentInfo{network{ oops no id")
        ).get_connectivity_state("emulator-5554")


@pytest.mark.asyncio
async def test_get_connectivity_state__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        dumpsys_connectivity_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    with pytest.raises(DeviceNotFoundError):
        await NetworkService(backend).get_connectivity_state("bogus")


@pytest.mark.asyncio
async def test_get_connectivity_state__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        dumpsys_connectivity_result=CommandResult(
            stdout="", stderr="Permission Denial: dump connectivity\n", exit_code=1, duration_ms=5.0
        )
    )
    with pytest.raises(PermissionDeniedError):
        await NetworkService(backend).get_connectivity_state("emulator-5554")
