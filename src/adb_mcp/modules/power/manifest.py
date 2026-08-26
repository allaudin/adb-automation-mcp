"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:power at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_mcp.modules.power.service import PowerService
from adb_mcp.modules.power.tools import get_power_state
from adb_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="power",
    service_factory=PowerService,
    tools=[get_power_state],
    resources=[],
)
