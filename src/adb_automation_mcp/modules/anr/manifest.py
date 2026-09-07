"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:anr at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.anr.service import AnrService
from adb_automation_mcp.modules.anr.tools import get_anr_reports
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="anr",
    service_factory=AnrService,
    tools=[get_anr_reports],
    resources=[],
)
