"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:diagnostics at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.diagnostics.service import DiagnosticsService
from adb_automation_mcp.modules.diagnostics.tools import check_adb_available
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="diagnostics",
    service_factory=DiagnosticsService,
    tools=[check_adb_available],
    resources=[],
)
