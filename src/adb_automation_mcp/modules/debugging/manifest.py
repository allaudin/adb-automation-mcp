"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:debugging at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

import os
from pathlib import Path

from adb_automation_mcp.backend.protocol import AdbBackend
from adb_automation_mcp.modules.debugging.service import DebuggingService
from adb_automation_mcp.modules.debugging.tools import (
    capture_native_backtrace,
    capture_native_tombstone,
    clear_debug_app,
    get_process_exit_history,
    list_jdwp_processes,
    set_debug_app,
)
from adb_automation_mcp.registry import ModuleManifest


def _service_factory(backend: AdbBackend) -> DebuggingService:
    # ADB_AUTOMATION_LOCAL_ROOT gates capture_native_tombstone's host-file write
    # — read here (not through ModuleManifest.service_factory's single-arg
    # contract) so it stays this module's own concern, same as memory's
    # capture_heap_dump. The other debugging tools don't touch the host.
    root = os.environ.get("ADB_AUTOMATION_LOCAL_ROOT")
    return DebuggingService(backend, local_root=Path(root) if root else None)


MODULE = ModuleManifest(
    name="debugging",
    service_factory=_service_factory,
    tools=[
        get_process_exit_history,
        set_debug_app,
        clear_debug_app,
        list_jdwp_processes,
        capture_native_backtrace,
        capture_native_tombstone,
    ],
    resources=[],
)
