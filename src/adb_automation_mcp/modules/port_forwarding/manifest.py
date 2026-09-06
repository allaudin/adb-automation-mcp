"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:port_forwarding at MODULE below, which the registry discovers
and registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.port_forwarding.service import PortForwardingService
from adb_automation_mcp.modules.port_forwarding.tools import create_forward
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="port_forwarding",
    service_factory=PortForwardingService,
    tools=[create_forward],
    resources=[],
)
