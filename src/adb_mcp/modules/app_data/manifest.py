"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:app_data at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_mcp.modules.app_data.service import AppDataService
from adb_mcp.modules.app_data.tools import clear_app_cache
from adb_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="app_data",
    service_factory=AppDataService,
    tools=[clear_app_cache],
    resources=[],
)
