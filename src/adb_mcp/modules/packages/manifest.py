"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:packages at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_mcp.modules.packages.service import PackagesService
from adb_mcp.modules.packages.tools import list_packages
from adb_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="packages",
    service_factory=PackagesService,
    tools=[list_packages],
    resources=[],
)
