"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:screen at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

import os
from pathlib import Path

from adb_automation_mcp.backend.protocol import AdbBackend
from adb_automation_mcp.modules.screen.service import ScreenService
from adb_automation_mcp.modules.screen.tools import take_screenshot
from adb_automation_mcp.registry import ModuleManifest


def _service_factory(backend: AdbBackend) -> ScreenService:
    # ADB_AUTOMATION_LOCAL_ROOT gates take_screenshot's optional save= write — read
    # here (not passed through ModuleManifest.service_factory's single-arg
    # contract, shared by every module) so this stays this module's own concern,
    # same as logger's stop_log_session and files' pull_file. No default: unset
    # means save=True refuses to run.
    root = os.environ.get("ADB_AUTOMATION_LOCAL_ROOT")
    return ScreenService(backend, local_root=Path(root) if root else None)


MODULE = ModuleManifest(
    name="screen",
    service_factory=_service_factory,
    tools=[take_screenshot],
    resources=[],
)
