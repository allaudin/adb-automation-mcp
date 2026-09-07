"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:tracing at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

import os
from pathlib import Path

from adb_automation_mcp.backend.protocol import AdbBackend
from adb_automation_mcp.modules.tracing.service import TracingService
from adb_automation_mcp.modules.tracing.tools import capture_system_trace
from adb_automation_mcp.registry import ModuleManifest


def _service_factory(backend: AdbBackend) -> TracingService:
    # ADB_AUTOMATION_LOCAL_ROOT gates capture_system_trace's host-file write —
    # read here (not through ModuleManifest.service_factory's single-arg
    # contract) so it stays this module's own concern, same as files' pull_file
    # and memory's capture_heap_dump. No default: unset means the tool refuses.
    root = os.environ.get("ADB_AUTOMATION_LOCAL_ROOT")
    return TracingService(backend, local_root=Path(root) if root else None)


MODULE = ModuleManifest(
    name="tracing",
    service_factory=_service_factory,
    tools=[capture_system_trace],
    resources=[],
)
