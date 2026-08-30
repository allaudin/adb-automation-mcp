"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:displays at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.displays.service import DisplaysService
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="displays",
    service_factory=DisplaysService,
    tools=[],
    resources=[],
)
