"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:instrumentation at MODULE below, which the registry
discovers and registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.instrumentation.service import InstrumentationService
from adb_automation_mcp.modules.instrumentation.tools import run_instrumentation
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="instrumentation",
    service_factory=InstrumentationService,
    tools=[run_instrumentation],
    resources=[],
)
