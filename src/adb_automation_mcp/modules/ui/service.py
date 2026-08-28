"""Domain logic for the ui module: retrieving the current Android UI
hierarchy (`uiautomator dump`) as inline XML. Finding/targeting individual
elements and injecting input actions aren't implemented here — see the
input module for touch injection.

`uiautomator dump` only writes its result to a device-side file, and
AdbBackend has no primitive for reading an arbitrary remote file's contents
directly into a `str` (pull() writes to the host filesystem, which would
force every caller to know and manage a temporary device path — exactly
what this tool exists to avoid). So this dumps to a temporary path under
`/data/local/tmp`, reads it back with a plain `cat` over the existing
AdbBackend.shell primitive (safe here since the hierarchy is text/XML, not
binary like screen's PNG capture), and always removes the device-side temp
file afterward — success, failure, or anything in between.
"""

from __future__ import annotations

import shlex
import uuid
import xml.etree.ElementTree as ET
from contextlib import suppress

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    PermissionDeniedError,
    RemoteFileNotFoundError,
    UiAutomatorFailedError,
    UiHierarchyUnavailableError,
)

# Same rationale as screen's _REMOTE_TMP_DIR: writable by the shell user
# without storage permissions, and not subject to scoped-storage/MediaStore
# scanning like /sdcard.
_REMOTE_TMP_DIR = "/data/local/tmp"

_NULL_ROOT_NODE_MESSAGE = "ERROR: null root node returned by UiTestAutomationBridge."


class UiHierarchyDumpResult(BaseModel):
    """Outcome of dumping the current UI hierarchy (`uiautomator dump`).

    Not verified live (no device was available in this environment) —
    shaped on `uiautomator dump`'s documented, long-stable output: a
    "UI hierarchy dumped to: <path>" stdout line on success, and the XML
    schema (`<hierarchy>` root, nested `<node>` elements) unchanged since
    its introduction. Only ever returned on success — see
    UiService.dump_ui_hierarchy's Error handling for how each failure kind
    is classified and raised instead of returned as data. An empty
    hierarchy (no window content to capture, but not an error) is
    represented as xml="" and node_count=0, not raised.
    """

    serial: str
    xml: str
    node_count: int
    success: bool
    output: str

    def summary(self) -> str:
        if self.node_count == 0:
            return f"Dumped an empty UI hierarchy from {self.serial}."
        return f"Dumped UI hierarchy ({self.node_count} nodes) from {self.serial}."


class UiService:
    """Retrieves the current UI hierarchy from a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def dump_ui_hierarchy(self, serial: str) -> UiHierarchyDumpResult:
        remote_tmp_path = f"{_REMOTE_TMP_DIR}/adb_automation_mcp_ui_dump_{uuid.uuid4().hex}.xml"
        try:
            dump_result = await self._backend.shell(serial, f"uiautomator dump {remote_tmp_path}")
            _raise_for_dump_failure(serial, dump_result)

            cat_result = await self._backend.shell(serial, f"cat {shlex.quote(remote_tmp_path)}")
            _raise_for_cat_failure(serial, remote_tmp_path, cat_result)

            xml = cat_result.stdout
            return UiHierarchyDumpResult(
                serial=serial,
                xml=xml,
                node_count=_count_nodes(xml),
                success=True,
                output=dump_result.stdout,
            )
        finally:
            # Best-effort, unconditional: never leave the temp dump on the
            # device, whether the dump, the cat, both, or neither failed —
            # and never let a cleanup failure mask the real outcome above.
            with suppress(Exception):
                await self._backend.shell(serial, f"rm -f {shlex.quote(remote_tmp_path)}")


def _raise_for_dump_failure(serial: str, result: CommandResult) -> None:
    combined = f"{result.stdout}\n{result.stderr}"
    # DumpCommand prints this exact line (and nothing indicating success)
    # when UiTestAutomationBridge can't obtain a root node — the
    # "screen off / locked / nothing to inspect" case — regardless of exit
    # code, so check for it before branching on exit_code at all.
    if _NULL_ROOT_NODE_MESSAGE in combined:
        raise UiHierarchyUnavailableError(_NULL_ROOT_NODE_MESSAGE, details={"serial": serial})

    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    # Same "adb: device '<serial>' not found" convention verified live for
    # other modules (e.g. user's) — the adb-client rejects an unknown serial
    # before any command reaches a device.
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    # e.g. "/system/bin/sh: uiautomator: not found" on a build that lacks
    # the uiautomator binary/shell tool entirely.
    if "not found" in message:
        raise UiAutomatorFailedError(message, details={"serial": serial})
    raise UiAutomatorFailedError(message, details={"serial": serial, "exit_code": result.exit_code})


def _raise_for_cat_failure(serial: str, remote_path: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    # Well-known toybox/toolbox `cat` wording for a missing path — the dump
    # file vanishing (or never being created) before it could be read back.
    if "No such file or directory" in message:
        raise RemoteFileNotFoundError(message, details={"serial": serial, "remote_path": remote_path})
    if "Permission denied" in message or "Permission Denial" in message:
        raise PermissionDeniedError(message, details={"serial": serial, "remote_path": remote_path})
    raise BackendError(
        message, details={"serial": serial, "remote_path": remote_path, "exit_code": result.exit_code}
    )


def _count_nodes(xml: str) -> int:
    if not xml.strip():
        return 0
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return 0
    return sum(1 for _ in root.iter("node"))
