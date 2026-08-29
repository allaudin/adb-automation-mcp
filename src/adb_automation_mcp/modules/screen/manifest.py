"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:screen at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.screen.service import ScreenService
from adb_automation_mcp.modules.screen.tools import take_screenshot
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="screen",
    service_factory=ScreenService,
    tools=[take_screenshot],
    resources=[],
)
