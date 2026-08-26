"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:logger at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

import os
from pathlib import Path

from adb_mcp.backend.protocol import AdbBackend
from adb_mcp.modules.logger.service import LoggerService
from adb_mcp.modules.logger.tools import (
    clear_logs,
    get_log_buffer_size,
    read_logs,
    read_package_logs,
    start_log_session,
    stop_log_session,
)
from adb_mcp.registry import ModuleManifest


def _service_factory(backend: AdbBackend) -> LoggerService:
    # ADB_MCP_LOCAL_ROOT gates stop_log_session's host-file write — read here
    # (not passed through ModuleManifest.service_factory's single-arg
    # contract, shared by every module) so this stays this module's own
    # concern. No default: unset means stop_log_session refuses to run.
    root = os.environ.get("ADB_MCP_LOCAL_ROOT")
    return LoggerService(backend, local_root=Path(root) if root else None)


MODULE = ModuleManifest(
    name="logger",
    service_factory=_service_factory,
    tools=[
        read_logs,
        clear_logs,
        get_log_buffer_size,
        read_package_logs,
        start_log_session,
        stop_log_session,
    ],
    resources=[],
)
