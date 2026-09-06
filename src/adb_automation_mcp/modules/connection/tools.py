"""Module-level, statically-introspectable tool functions for the connection module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.connection.service import (
    AdbServerRestartResult,
    ConnectionService,
    ConnectResult,
    DeviceStateWaitResult,
    DeviceWaitState,
    DeviceWaitTransport,
    DisconnectResult,
    RestartAdbdAsRootResult,
    RestartAdbdAsShellResult,
)
from adb_automation_mcp.registry import category


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
            Must not be empty.
        port: TCP port adb is listening on, 1-65535. Defaults to 5555, the
            port `adb tcpip` uses when none is given.

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
        as an actual tool error. An empty host or an out-of-range port raises
        INVALID_ARGUMENT before any adb call. A reachable-but-refused host is
        not an error — it comes back as success with data.success=false.

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
        host: Hostname or IP address of the device to disconnect. Must not
            be empty.
        port: TCP port it's connected on, 1-65535. Defaults to 5555,
            matching connect_device's default.

    Returns:
        Whether adb reported the disconnect as successful, the "host:port"
        address targeted, and adb's raw output. Unlike connect_device, this is
        judged on the exit code — adb disconnect's exit code was verified live
        to be reliable (1 with "error: no such device" for an address that
        isn't connected).

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, that surfaces
        as an actual tool error. An empty host or an out-of-range port raises
        INVALID_ARGUMENT before any adb call. An address that simply isn't
        connected is not an error — it comes back as success with
        data.success=false.

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


@category("destructive")
async def restart_adbd_as_root(ctx: Context, serial: str) -> RestartAdbdAsRootResult:
    """Restart the on-device `adbd` daemon as root: `adb -s serial root`.

    This is the device-side equivalent of `adb root` — a privilege
    escalation of the daemon running *on the device*, not this host's own
    adb client/server process (that's restart_adb_server; the two are
    unrelated operations, and one restarting doesn't restart the other).
    Once adbd is running as root, subsequent shell commands against this
    serial run with root privileges until adbd is restarted again (e.g. via
    `adb unroot`, a device reboot, or another root call) — categorized
    destructive, and therefore denied by default, because it's a genuine
    privilege escalation on the device, not merely a write. Restarting adbd
    also briefly drops the device off the adb transport (it disconnects and
    reconnects on its own): an immediately-following tool call against the
    same serial can transiently fail with a device-not-found error — retry
    it rather than assuming the device is actually gone.

    Args:
        serial: The target device's serial number, as reported by
            list_connected_devices.

    Returns:
        Whether adbd is now running as root (true for both a fresh restart
        and the idempotent "already root" case), whether it was already root
        before this call, and adb's raw output for diagnostic context.
        Judged primarily on the message text, not the exit code — `adb -s
        serial root` is documented to behave like `adb connect`, which is
        known to exit 0 unconditionally: exiting 0 whether adbd actually
        ended up running as root or the device's build refused ("adbd cannot
        run as root in production builds") — not independently verified live
        in this environment, so known-wording checks are applied before
        exit-code checks either way.
        The production-build refusal is a normal, expected answer on a
        non-debuggable build, so it's returned as success: false rather than
        raised as an error.

    Error handling:
        Propagates the same way most tools do: an unknown serial never
        reaches adbd at all (`adb: device '<serial>' not found`, exit
        non-zero) and surfaces as a DeviceNotFoundError, and an unreachable
        adb binary surfaces as AdbUnavailableError — both actual tool errors,
        unlike the production-build refusal above. adbd responding with
        neither a known wording nor a recognizable failure is also a real
        error (BackendError) rather than being guessed at.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "adbd restarted as root on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "success": true,
            "already_root": false,
            "output": "restarting adbd as root"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    connection = cast(ConnectionService, services["connection"])
    return await connection.restart_adbd_as_root(serial)


@category("write")
async def restart_adbd_as_shell(ctx: Context, serial: str) -> RestartAdbdAsShellResult:
    """Restart the on-device `adbd` daemon as non-root (shell): `adb -s serial unroot`.

    The inverse of restart_adbd_as_root — use it to drop adbd's privileges back
    to shell after a setup step that needed root, so later automation runs with
    normal permissions. Because it only ever *removes* root, it's a plain write,
    not destructive (unlike restart_adbd_as_root). It has no effect on this
    host's own adb client/server process — that's restart_adb_server, an
    unrelated operation. Restarting adbd briefly drops the device off the adb
    transport (it disconnects and reconnects on its own): an
    immediately-following tool call against the same serial can transiently fail
    with a device-not-found error — retry it rather than assuming the device is
    actually gone.

    Args:
        serial: The target device's serial number, as reported by
            list_connected_devices.

    Returns:
        Whether adbd is now running as shell (true for both a fresh restart and
        the idempotent "was already non-root" case), whether it was already
        non-root before this call, and adb's raw output for diagnostic context.
        Judged on the message text ("restarting adbd as non root" vs "adbd not
        running as root"), both verified live to exit 0.

    Error handling:
        Propagates the same way most tools do: an unknown serial never reaches
        adbd (`adb: device '<serial>' not found`, exit non-zero) and surfaces as
        DeviceNotFoundError; an unreachable adb binary surfaces as
        AdbUnavailableError. adbd responding with neither a known wording nor a
        recognizable failure is a BackendError rather than being guessed at.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "adbd restarted as shell (non-root) on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "success": true,
            "already_shell": false,
            "output": "restarting adbd as non root"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    connection = cast(ConnectionService, services["connection"])
    return await connection.restart_adbd_as_shell(serial)


@category("read")
async def wait_for_device_state(
    ctx: Context,
    serial: str,
    state: DeviceWaitState = "device",
    transport: DeviceWaitTransport = "any",
    timeout_s: float = 60.0,
) -> DeviceStateWaitResult:
    """Block until a device reaches a given adb transport state: `adb -s serial wait-for-...`.

    The right call to gate automation on a device transition instead of a blind
    sleep — e.g. after rebooting an emulator, wait until it's back to "device"
    before starting tests; after `adb reboot bootloader`, wait for "bootloader".
    Returns as soon as the state is reached; changes nothing on the device.

    Args:
        serial: The target device's serial number, as reported by
            list_connected_devices.
        state: The adb transport state to wait for. One of "device" (fully
            booted and online — the default), "recovery", "rescue", "sideload",
            "bootloader", or "disconnect" (wait for this serial to go away).
        transport: Which connection to wait on: "any" (default), "usb", or
            "local" (emulator/TCP).
        timeout_s: How long to wait before giving up, in seconds. Must be
            greater than 0 and at most 600. Defaults to 60.

    Returns:
        The serial, the state and transport that were requested, and waited_ms —
        how long the wait actually took before the state was reached.

    Error handling:
        A wait that doesn't complete in time surfaces as a retryable TIMEOUT
        error (this also covers an unknown serial, which adb waits on
        indefinitely rather than rejecting). An unknown state or transport, or a
        timeout_s outside (0, 600], raises INVALID_ARGUMENT before any adb call.
        An unreachable adb binary raises ADB_UNAVAILABLE.

    Example:
        Called with serial="emulator-5554", state="device". A typical response:

        ```json
        {
          "status": "success",
          "message": "emulator-5554 reached adb state 'device' after 34ms.",
          "data": {
            "serial": "emulator-5554",
            "state": "device",
            "transport": "any",
            "waited_ms": 34.0
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    connection = cast(ConnectionService, services["connection"])
    return await connection.wait_for_device_state(
        serial, state=state, transport=transport, timeout_s=timeout_s
    )
