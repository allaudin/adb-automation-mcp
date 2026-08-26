"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:logger at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_mcp.modules.logger.service import LoggerService
from adb_mcp.modules.logger.tools import (
    clear_logs,
    get_log_buffer_size,
    read_logs,
    read_package_logs,
)
from adb_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="logger",
    service_factory=LoggerService,
    tools=[read_logs, clear_logs, get_log_buffer_size, read_package_logs],
    resources=[],
)
