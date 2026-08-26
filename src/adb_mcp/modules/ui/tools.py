"""Module-level, statically-introspectable tool functions for the ui module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.ui.service import UiHierarchyDumpResult, UiService
from adb_mcp.registry import category


@category("read")
async def dump_ui_hierarchy(ctx: Context, serial: str) -> UiHierarchyDumpResult:
    """Retrieve the device's current UI hierarchy: `uiautomator dump`.

    `uiautomator dump` only writes its result to a file on the device, so
    this dumps to a temporary path under `/data/local/tmp`, reads the XML
    back inline over `adb shell` (no host filesystem write, no local_root
    needed — the caller never has to know or manage the device-side path),
    and always removes the temporary file afterward. Finding/targeting
    individual elements within the hierarchy isn't implemented yet, and
    this module doesn't inject any input actions (see the input module for
    that).

    Args:
        serial: The target device's adb serial (see list_connected_devices).

    Returns:
        The serial, the full hierarchy xml (the raw `<hierarchy>` document,
        empty string if there was nothing to capture), node_count (a
        best-effort count of `<node>` elements — 0 for an empty hierarchy
        or if the XML couldn't be parsed), success (always True — see
        Error handling), and the raw `uiautomator dump` output.

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. `uiautomator dump` itself failing
        to run (e.g. the uiautomator binary is missing on this build)
        raises UIAUTOMATOR_FAILED. The command running but finding no
        inspectable window content right now (screen off, locked, or
        otherwise no accessible root node) raises
        UI_HIERARCHY_UNAVAILABLE — distinct from an empty-but-successful
        hierarchy, which is returned as data with node_count=0, not raised.
        A permission rejection raises PERMISSION_DENIED; the dumped temp
        file vanishing before it could be read back raises
        REMOTE_FILE_NOT_FOUND; any other failure raises a generic
        BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "Dumped UI hierarchy (2 nodes) from emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "xml": "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\\"0\\">...</hierarchy>",
            "node_count": 2,
            "success": true,
            "output": "UI hierarchy dumped to: /data/local/tmp/adb_mcp_ui_dump_....xml\\n"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    ui = cast(UiService, services["ui"])
    return await ui.dump_ui_hierarchy(serial)
