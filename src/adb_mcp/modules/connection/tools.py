"""Module-level, statically-introspectable tool functions for the connection module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.connection.service import (
    AdbServerRestartResult,
    ConnectionService,
    ConnectResult,
    DisconnectResult,
)
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

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, that surfaces
        as an actual tool error rather than success: false — a caller trying to
        restart adb who gets "adb doesn't exist" needs that as an error, not data.

    Example:
        Called with no arguments. A typical response:

        ```json
        {
          "status": "success",
          "message": "adb server restarted successfully.",
          "data": {
            "success": true,
            "output": "* daemon not running; starting now at tcp:5037\\n* daemon started successfully"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    connection = cast(ConnectionService, services["connection"])
    return await connection.restart_adb_server()


@category("write")
async def connect_device(ctx: Context, host: str, port: int = 5555) -> ConnectResult:
    """Connect to a device over TCP/IP: `adb connect host:port`.

    Use this for devices reached over the network rather than USB — e.g. a
    device already switched into TCP/IP mode (`adb tcpip <port>` while it was
    on USB), or a remote/cloud emulator.

    Args:
        host: Hostname or IP address of the device's adb-over-TCP listener.
        port: TCP port adb is listening on. Defaults to 5555, the port `adb
            tcpip` uses when none is given.

    Returns:
        Whether adb reported the connection as successful, the "host:port"
        address that was targeted, and adb's raw output. Success is judged on
        the message text ("connected to ..." / "already connected to ..." vs
        "failed to connect to ..."), not the exit code — adb's connect
        subcommand exits 0 whether or not the connection actually succeeded
        (verified live), so the exit code alone can't tell you anything here.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, that surfaces
        as an actual tool error.

    Example:
        Called with host="192.168.1.50". A typical response:

        ```json
        {
          "status": "success",
          "message": "Connected to 192.168.1.50:5555.",
          "data": {
            "success": true,
            "address": "192.168.1.50:5555",
            "output": "connected to 192.168.1.50:5555"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    connection = cast(ConnectionService, services["connection"])
    return await connection.connect(host, port)


@category("write")
async def disconnect_device(ctx: Context, host: str, port: int = 5555) -> DisconnectResult:
    """Disconnect a device connected over TCP/IP: `adb disconnect host:port`.

    The opposite of connect_device — use it to cleanly drop a TCP/IP connection
    instead of leaving it dangling.

    Args:
        host: Hostname or IP address of the device to disconnect.
        port: TCP port it's connected on. Defaults to 5555, matching
            connect_device's default.

    Returns:
        Whether adb reported the disconnect as successful, the "host:port"
        address targeted, and adb's raw output. Unlike connect_device, this is
        judged on the exit code — adb disconnect's exit code was verified live
        to be reliable (1 with "error: no such device" for an address that
        isn't connected).

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, that surfaces
        as an actual tool error.

    Example:
        Called with host="192.168.1.50". A typical response:

        ```json
        {
          "status": "success",
          "message": "Disconnected from 192.168.1.50:5555.",
          "data": {
            "success": true,
            "address": "192.168.1.50:5555",
            "output": "disconnected 192.168.1.50:5555"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    connection = cast(ConnectionService, services["connection"])
    return await connection.disconnect(host, port)
