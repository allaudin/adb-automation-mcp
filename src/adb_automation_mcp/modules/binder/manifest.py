"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:binder at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.binder.service import BinderService
from adb_automation_mcp.modules.binder.tools import get_binder_call_stats, reset_binder_call_stats
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="binder",
    service_factory=BinderService,
    tools=[get_binder_call_stats, reset_binder_call_stats],
    resources=[],
)
