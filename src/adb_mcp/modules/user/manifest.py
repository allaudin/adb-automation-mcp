"""The entry_points target for this module — pyproject.toml points
adb_mcp.modules:user at MODULE below, which the registry discovers and
registers at server startup.
"""

from __future__ import annotations

from adb_mcp.modules.user.service import UserService
from adb_mcp.modules.user.tools import (
    create_user,
    dump_user,
    get_current_user,
    get_user_capabilities,
    list_users,
    remove_user,
    switch_user,
    user_info,
)
from adb_mcp.registry import ModuleManifest

MODULE = ModuleManifest(
    name="user",
    service_factory=UserService,
    tools=[
        get_current_user,
        dump_user,
        user_info,
        list_users,
        switch_user,
        create_user,
        remove_user,
        get_user_capabilities,
    ],
    resources=[],
)
