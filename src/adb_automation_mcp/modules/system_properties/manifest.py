"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:system_properties at MODULE below, which the registry discovers
and registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.system_properties.service import SystemPropertiesService
from adb_automation_mcp.modules.system_properties.tools import (
    get_property,
    get_property_metadata,
    list_properties,
    set_property,
)
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="system_properties",
    service_factory=SystemPropertiesService,
    tools=[
        get_property,
        list_properties,
        get_property_metadata,
        set_property,
    ],
    resources=[],
)
