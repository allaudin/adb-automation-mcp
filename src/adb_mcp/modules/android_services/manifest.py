"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:android_services at MODULE below, which the registry discovers
and registers at server startup.
"""

from __future__ import annotations

from adb_mcp.modules.android_services.service import AndroidServicesService
from adb_mcp.modules.android_services.tools import start_service
from adb_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="android_services",
    service_factory=AndroidServicesService,
    tools=[start_service],
    resources=[],
)
