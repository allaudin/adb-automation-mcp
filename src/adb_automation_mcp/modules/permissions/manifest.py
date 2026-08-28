"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:permissions at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.permissions.service import PermissionsService
from adb_automation_mcp.modules.permissions.tools import grant_permission
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="permissions",
    service_factory=PermissionsService,
    tools=[grant_permission],
    resources=[],
)
