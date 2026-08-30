"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:activities at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.activities.service import ActivitiesService
from adb_automation_mcp.modules.activities.tools import start_activity
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="activities",
    service_factory=ActivitiesService,
    tools=[start_activity],
    resources=[],
)
