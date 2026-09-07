"""The entry_points target for this module — pyproject.toml points
adb_automation_mcp.modules:content at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_automation_mcp.modules.content.service import ContentService
from adb_automation_mcp.modules.content.tools import query_content
from adb_automation_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="content",
    service_factory=ContentService,
    tools=[query_content],
    resources=[],
)
