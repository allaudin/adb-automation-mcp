"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:memory at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

import os
from pathlib import Path

from adb_automation_mcp.backend.protocol import AdbBackend
from adb_automation_mcp.modules.memory.service import MemoryService
from adb_automation_mcp.modules.memory.tools import (
    capture_heap_dump,
    clear_heap_watch,
    get_app_memory_details,
    get_app_memory_summary,
    get_memory_history,
    get_memory_maps,
    get_system_memory_summary,
    set_heap_watch,
)
from adb_automation_mcp.registry import ModuleManifest


def _service_factory(backend: AdbBackend) -> MemoryService:
    # ADB_AUTOMATION_LOCAL_ROOT gates capture_heap_dump's host-file write — read
    # here (not through ModuleManifest.service_factory's single-arg contract,
    # shared by every module) so it stays this module's own concern, same as
    # files' pull_file and screen's take_screenshot. No default: unset means
    # capture_heap_dump refuses to run.
    root = os.environ.get("ADB_AUTOMATION_LOCAL_ROOT")
    return MemoryService(backend, local_root=Path(root) if root else None)


MODULE = ModuleManifest(
    name="memory",
    service_factory=_service_factory,
    tools=[
        get_app_memory_summary,
        get_app_memory_details,
        get_system_memory_summary,
        get_memory_history,
        capture_heap_dump,
        set_heap_watch,
        clear_heap_watch,
        get_memory_maps,
    ],
    resources=[],
)
