"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:files at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

import os
from pathlib import Path

from adb_mcp.backend.protocol import AdbBackend
from adb_mcp.modules.files.service import FilesService
from adb_mcp.modules.files.tools import pull_file
from adb_mcp.registry import ModuleManifest


def _service_factory(backend: AdbBackend) -> FilesService:
    # ADB_MCP_LOCAL_ROOT gates pull_file's host-file write — read here (not
    # passed through ModuleManifest.service_factory's single-arg contract,
    # shared by every module) so this stays this module's own concern, same
    # as logger's stop_log_session. No default: unset means pull_file
    # refuses to run.
    root = os.environ.get("ADB_MCP_LOCAL_ROOT")
    return FilesService(backend, local_root=Path(root) if root else None)


MODULE = ModuleManifest(
    name="files",
    service_factory=_service_factory,
    tools=[pull_file],
    resources=[],
)
