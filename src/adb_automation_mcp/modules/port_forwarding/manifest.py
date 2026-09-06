"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:port_forwarding at MODULE below, which the registry discovers
and registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.port_forwarding.service import PortForwardingService
from adb_automation_mcp.modules.port_forwarding.tools import (
    create_forward,
    create_reverse,
    list_forwards,
    list_reverses,
    remove_forward,
    remove_reverse,
)
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="port_forwarding",
    service_factory=PortForwardingService,
    tools=[
        create_forward,
        list_forwards,
        remove_forward,
        create_reverse,
        list_reverses,
        remove_reverse,
    ],
    resources=[],
)
