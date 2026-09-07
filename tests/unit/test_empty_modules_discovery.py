"""Every built-in module now declares at least one tool (displays, the last
skeleton, graduated with list_displays). This keeps a light check that the
discovery/registration machinery still tolerates a module declaring zero
*resources* — no module declares any yet — so register_resources over the
full manifest set stays exercised and can't silently start throwing.
"""

from __future__ import annotations

from fastmcp import FastMCP

from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.policy import PolicyConfig, PolicyEngine
from adb_automation_mcp.registry import Registry, discover_modules


def test_every_discovered_module_declares_at_least_one_tool() -> None:
    manifests = discover_modules()

    assert manifests, "no modules discovered via entry_points — is the package installed?"
    empty = [m.name for m in manifests if not m.tools]
    assert not empty, f"modules with zero tools (add tools or a skeleton carve-out): {empty}"


def test_no_module_declares_resources_yet() -> None:
    for manifest in discover_modules():
        assert manifest.resources == []


def test_registering_all_modules_with_no_resources_does_not_raise() -> None:
    manifests = discover_modules()
    registry = Registry(policy=PolicyEngine(PolicyConfig()))
    mcp = FastMCP("test-server")

    registry.register_tools(mcp, manifests)
    registry.register_resources(mcp, manifests)


def test_build_services_constructs_an_instance_per_module() -> None:
    manifests = discover_modules()
    registry = Registry(policy=PolicyEngine(PolicyConfig()))

    services = registry.build_services(FakeBackend(), manifests)

    assert set(services) == {m.name for m in manifests}
    assert all(service is not None for service in services.values())
