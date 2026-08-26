"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:connection at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_mcp.modules.connection.service import ConnectionService
from adb_mcp.modules.connection.tools import connect_device, disconnect_device, restart_adb_server
from adb_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="connection",
    service_factory=ConnectionService,
    tools=[restart_adb_server, connect_device, disconnect_device],
    resources=[],
)
