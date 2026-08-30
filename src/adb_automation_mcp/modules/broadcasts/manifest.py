"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:broadcasts at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.broadcasts.service import BroadcastsService
from adb_automation_mcp.modules.broadcasts.tools import send_broadcast
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="broadcasts",
    service_factory=BroadcastsService,
    tools=[send_broadcast],
    resources=[],
)
