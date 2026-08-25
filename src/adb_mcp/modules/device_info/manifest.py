"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:device_info at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_mcp.modules.device_info.service import DeviceInfoService
from adb_mcp.modules.device_info.tools import list_connected_devices
from adb_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="device_info",
    service_factory=DeviceInfoService,
    tools=[list_connected_devices],
    # No resources currently: adb://devices started life as one (ADR-002) but
    # shipped as the list_connected_devices tool above instead, since not every
    # MCP client surfaces resources to the model as readily as tools (confirmed:
    # Claude Desktop couldn't read it, Claude Code could). Registry.register_resources
    # stays available in registry.py for a future read that's a better fit.
    resources=[],
)
