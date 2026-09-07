"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:graphics at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.graphics.service import GraphicsService
from adb_automation_mcp.modules.graphics.tools import get_frame_stats, reset_frame_stats
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="graphics",
    service_factory=GraphicsService,
    tools=[get_frame_stats, reset_frame_stats],
    resources=[],
)
