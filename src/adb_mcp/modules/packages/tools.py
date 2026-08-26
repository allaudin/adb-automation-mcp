"""Module-level, statically-introspectable tool functions for the packages module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.packages.service import PackageFilter, PackageList, PackagesService
from adb_mcp.registry import category


@category("read")
async def list_packages(
    ctx: Context,
    serial: str,
    user_id: int | None = None,
    package_filter: PackageFilter | None = None,
) -> PackageList:
    """List installed Android packages on a device: `adb shell pm list packages`.

    Returns parsed package names only, not pm's raw text output.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        user_id: Restrict the listing to one Android user's package view
            (`--user ID`, see list_users). Omit to use pm's default user.
        package_filter: Restrict to "system" packages (`-s`) or
            "third_party" packages (`-3`) — pm's own mutually exclusive
            filter flags. Omit to list every package regardless of origin.

    Returns:
        The serial and every matching package name. An empty list is a
        normal result (e.g. no third-party apps installed), not an error.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error.

    Example:
        Called with serial="emulator-5554", package_filter="third_party". A
        typical response:

        ```json
        {
          "status": "success",
          "message": "2 packages on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "packages": ["com.example.app", "com.example.other"]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    packages = cast(PackagesService, services["packages"])
    return await packages.list_packages(serial, user_id=user_id, package_filter=package_filter)
