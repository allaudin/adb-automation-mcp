"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:debugging at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.debugging.service import DebuggingService
from adb_automation_mcp.modules.debugging.tools import get_process_exit_history
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="debugging",
    service_factory=DebuggingService,
    tools=[get_process_exit_history],
    resources=[],
)
