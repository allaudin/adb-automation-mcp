"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:processes at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_mcp.modules.processes.service import ProcessesService
from adb_mcp.modules.processes.tools import force_stop_app
from adb_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="processes",
    service_factory=ProcessesService,
    tools=[force_stop_app],
    resources=[],
)
