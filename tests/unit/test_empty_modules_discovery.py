"""Confirms the one remaining skeleton module (displays) participates
correctly in the normal discovery/registration mechanism despite declaring
zero tools and zero resources — entry_points discovery finds it, the
registry doesn't choke registering an empty tool/resource list, and
build_services still produces a service instance for it from the shared
backend. (packages, broadcasts, activities, android_services, processes,
permissions, settings, power, network, and date_time used to be among
these but now have list_packages, send_broadcast, start_activity,
start_service, force_stop_app, grant_permission, get_setting,
get_power_state, list_network_interfaces, and get_date_time respectively,
so they're covered by their own module tests instead.)
"""

from __future__ import annotations

from fastmcp import FastMCP

from adb_mcp.backend.testing import FakeBackend
from adb_mcp.policy import PolicyConfig, PolicyEngine
from adb_mcp.registry import Registry, discover_modules

_SKELETON_MODULES = {
    "displays",
}


def test_skeleton_modules_are_discovered_via_entry_points() -> None:
    discovered = {manifest.name for manifest in discover_modules()}

    assert _SKELETON_MODULES <= discovered


def test_skeleton_modules_declare_no_tools_or_resources() -> None:
    manifests = {manifest.name: manifest for manifest in discover_modules()}

    for name in _SKELETON_MODULES:
        assert manifests[name].tools == []
        assert manifests[name].resources == []


def test_registering_skeleton_modules_does_not_raise() -> None:
    manifests = [m for m in discover_modules() if m.name in _SKELETON_MODULES]
    registry = Registry(policy=PolicyEngine(PolicyConfig()))
    mcp = FastMCP("test-server")

    registry.register_tools(mcp, manifests)
    registry.register_resources(mcp, manifests)


def test_build_services_constructs_an_instance_per_skeleton_module() -> None:
    manifests = [m for m in discover_modules() if m.name in _SKELETON_MODULES]
    registry = Registry(policy=PolicyEngine(PolicyConfig()))

    services = registry.build_services(FakeBackend(), manifests)

    assert set(services) == _SKELETON_MODULES
    assert all(service is not None for service in services.values())
