"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:network at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_mcp.modules.network.service import NetworkService
from adb_mcp.modules.network.tools import list_network_interfaces
from adb_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="network",
    service_factory=NetworkService,
    tools=[list_network_interfaces],
    resources=[],
)
