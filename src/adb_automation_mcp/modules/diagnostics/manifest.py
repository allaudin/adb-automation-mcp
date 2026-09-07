"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:diagnostics at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

import os
from pathlib import Path

from adb_automation_mcp.backend.protocol import AdbBackend
from adb_automation_mcp.modules.diagnostics.service import DiagnosticsService
from adb_automation_mcp.modules.diagnostics.tools import (
    check_adb_available,
    generate_bugreport,
    get_adb_version,
)
from adb_automation_mcp.registry import ModuleManifest


def _service_factory(backend: AdbBackend) -> DiagnosticsService:
    # ADB_AUTOMATION_LOCAL_ROOT gates generate_bugreport's host-file write —
    # read here (not through ModuleManifest.service_factory's single-arg
    # contract) so it stays this module's own concern, same as files' pull_file.
    # No default: unset means generate_bugreport refuses to run. The other two
    # diagnostics tools don't touch the host and don't care.
    root = os.environ.get("ADB_AUTOMATION_LOCAL_ROOT")
    return DiagnosticsService(backend, local_root=Path(root) if root else None)


MODULE = ModuleManifest(
    name="diagnostics",
    service_factory=_service_factory,
    tools=[check_adb_available, get_adb_version, generate_bugreport],
    resources=[],
)
