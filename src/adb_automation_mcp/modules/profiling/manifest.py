"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:profiling at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

import os
from pathlib import Path

from adb_automation_mcp.backend.protocol import AdbBackend
from adb_automation_mcp.modules.profiling.service import ProfilingService
from adb_automation_mcp.modules.profiling.tools import start_method_profile, stop_method_profile
from adb_automation_mcp.registry import ModuleManifest


def _service_factory(backend: AdbBackend) -> ProfilingService:
    # ADB_AUTOMATION_LOCAL_ROOT gates stop_method_profile's host-file write —
    # read here (not through ModuleManifest.service_factory's single-arg
    # contract) so it stays this module's own concern, same as memory's
    # capture_heap_dump and tracing's capture_system_trace.
    root = os.environ.get("ADB_AUTOMATION_LOCAL_ROOT")
    return ProfilingService(backend, local_root=Path(root) if root else None)


MODULE = ModuleManifest(
    name="profiling",
    service_factory=_service_factory,
    tools=[start_method_profile, stop_method_profile],
    resources=[],
)
