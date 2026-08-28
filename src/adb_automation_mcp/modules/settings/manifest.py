"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:settings at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.settings.service import SettingsService
from adb_automation_mcp.modules.settings.tools import get_setting
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="settings",
    service_factory=SettingsService,
    tools=[get_setting],
    resources=[],
)
