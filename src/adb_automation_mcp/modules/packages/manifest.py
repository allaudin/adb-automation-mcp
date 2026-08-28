"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:packages at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.packages.service import PackagesService
from adb_automation_mcp.modules.packages.tools import (
    install_apk,
    install_existing_for_user,
    list_packages,
    uninstall_package,
)
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="packages",
    service_factory=PackagesService,
    tools=[list_packages, install_apk, uninstall_package, install_existing_for_user],
    resources=[],
)
