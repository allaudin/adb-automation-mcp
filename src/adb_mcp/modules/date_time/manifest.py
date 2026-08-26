"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:date_time at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_mcp.modules.date_time.service import DateTimeService
from adb_mcp.modules.date_time.tools import get_date_time
from adb_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="date_time",
    service_factory=DateTimeService,
    tools=[get_date_time],
    resources=[],
)
