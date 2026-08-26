"""Module-level, statically-introspectable tool functions for the files module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.files.service import FilesService, PullFileResult
from adb_mcp.registry import category


@category("read")
async def pull_file(ctx: Context, serial: str, remote_path: str, local_path: str) -> PullFileResult:
    """Copy one file from a device to this server's host: `adb pull`.

    Uses the existing AdbBackend.pull primitive directly — no raw shell
    command is run. Private app-data semantics (e.g. `run-as` to read
    another app's sandboxed files) aren't handled here; remote_path is
    passed to `adb pull` exactly as given, so pulling a path the shell user
    can't read fails the same way a plain `adb pull` would.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        remote_path: The device-side path to copy, e.g. "/sdcard/test.txt".
        local_path: Where to write the file on this server's host, relative
            to (or, if absolute, still required to resolve inside) the
            server's configured local_root.

    Returns:
        The serial, remote_path, the resolved local_path actually written,
        success (always True — see Error handling), and the raw adb pull
        output. Only returned on success.

    Error handling:
        local_path is checked before any device round-trip: if the server
        has no local_root configured at all, or local_path resolves outside
        it (including via ".." or an absolute path elsewhere on the host),
        the call is refused rather than writing anywhere — there is no
        default local_root; an operator must set ADB_MCP_LOCAL_ROOT
        explicitly (POLICY_DENIED). Beyond that: an unknown serial or an
        unresponsive adb binary raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE; a
        remote_path that doesn't exist on the device raises
        REMOTE_FILE_NOT_FOUND; a remote_path the shell user can't read
        raises PERMISSION_DENIED; any other `adb pull` failure raises a
        generic BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", remote_path="/sdcard/test.txt",
        local_path="test.txt". A typical response:

        ```json
        {
          "status": "success",
          "message": "Pulled /sdcard/test.txt from emulator-5554 to /var/adb-files/test.txt.",
          "data": {
            "serial": "emulator-5554",
            "remote_path": "/sdcard/test.txt",
            "local_path": "/var/adb-files/test.txt",
            "success": true,
            "output": "/sdcard/test.txt: 1 file pulled, 0 skipped. 4.2 MB/s (1024 bytes in 0.002s)\\n"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    files = cast(FilesService, services["files"])
    return await files.pull_file(serial, remote_path, local_path)
