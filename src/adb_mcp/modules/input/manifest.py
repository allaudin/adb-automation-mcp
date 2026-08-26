"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:input at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_mcp.modules.input.service import InputService
from adb_mcp.modules.input.tools import tap
from adb_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="input",
    service_factory=InputService,
    tools=[tap],
    resources=[],
)
