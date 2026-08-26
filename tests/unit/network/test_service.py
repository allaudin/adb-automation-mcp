"""Layer 1 unit tests: NetworkService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import BackendError, DeviceNotFoundError, NetworkToolUnavailableError
from adb_mcp.modules.network.service import NetworkService


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
