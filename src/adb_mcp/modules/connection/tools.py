"""Module-level, statically-introspectable tool functions for the connection module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.connection.service import AdbServerRestartResult, ConnectionService
from adb_mcp.registry import category


@category("write")
async def restart_adb_server(ctx: Context) -> AdbServerRestartResult:
    """Restart the local adb server: run `adb kill-server` followed by `adb start-server`.

    Use this when adb is misbehaving in ways check_adb_available can't diagnose —
    stale device state, a wedged server process, or devices adb no longer sees
    despite being physically connected. This is a global, non-device-scoped
    operation: it affects every device this host's adb currently talks to, not
    just one, which is why it isn't safely re-invocable without disrupting
    whatever else might be mid-command against adb right now. In particular, it
    drops any device connected over TCP (`adb connect host:port`) without
    reconnecting it automatically — unlike a USB device or a standard local
    emulator, which do reappear on their own. Confirm the connection style before
    calling this against a device you can't easily physically reconnect.

    Returns:
        Whether start-server reported success, plus its combined stdout/stderr
        for diagnostic context. kill-server's own result isn't surfaced since
        it's idempotent and essentially always reports success.

    Raises:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, that surfaces
        as an actual tool error rather than success: false — a caller trying to
        restart adb who gets "adb doesn't exist" needs that as an error, not data.

    Example:
        Called with no arguments. A typical response:

        {
          "status": "success",
          "message": "adb server restarted successfully.",
          "data": {
            "success": true,
            "output": "* daemon not running; starting now at tcp:5037\n* daemon started successfully"
          },
          "error": null
        }
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    connection = cast(ConnectionService, services["connection"])
    return await connection.restart_adb_server()
