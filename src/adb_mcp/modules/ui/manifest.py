"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:ui at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_mcp.modules.ui.service import UiService
from adb_mcp.modules.ui.tools import dump_ui_hierarchy
from adb_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="ui",
    service_factory=UiService,
    tools=[dump_ui_hierarchy],
    resources=[],
)
