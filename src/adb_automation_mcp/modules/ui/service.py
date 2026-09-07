"""Domain logic for the ui module: retrieving the current Android UI
hierarchy (`uiautomator dump`) and searching it by structured criteria.

`uiautomator dump` only writes its result to a device-side file, and
AdbBackend has no primitive for reading an arbitrary remote file's contents
directly into a `str` (pull() writes to the host filesystem, which would
force every caller to know and manage a temporary device path — exactly
what these tools exist to avoid). So each capture dumps to a temporary path
under `/data/local/tmp`, reads it back with a plain `cat` over the existing
AdbBackend.shell primitive (safe here since the hierarchy is text/XML, not
binary like screen's PNG capture), and always removes the device-side temp
file afterward — success, failure, or anything in between.

`find_ui_elements` and `wait_for_ui_element` build on that same capture:
element matching and (for wait) the polling loop are done here in Python,
never with shell `grep`/`awk` pipelines.
"""

from __future__ import annotations

import asyncio
import re
import shlex
import time
import uuid
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import suppress
from typing import Literal

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    AdbTimeoutError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
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

# Upper bounds for wait_for_ui_element, keeping the polling loop firmly
# bounded (an agent must never be able to ask this tool to block forever).
_MAX_WAIT_TIMEOUT_S = 120.0
_MIN_POLL_INTERVAL_S = 0.1
_MAX_POLL_INTERVAL_S = 30.0

# Hard cap on how many matched elements a single find call serializes back,
# independent of the caller's `limit` — the full hierarchy can be thousands
# of nodes and the point of this tool is a small, targeted answer.
_MAX_RETURNED_ELEMENTS = 500
_DEFAULT_RETURNED_ELEMENTS = 50

_BOUNDS_PATTERN = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

WaitCondition = Literal["present", "absent"]


class UiHierarchyDumpResult(BaseModel):
    """Outcome of dumping the current UI hierarchy (`uiautomator dump`).

    Shaped on `uiautomator dump`'s documented, long-stable output: a
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


class UiElementBounds(BaseModel):
    """A node's on-screen rectangle, parsed from its `bounds="[l,t][r,b]"`
    attribute, plus the rectangle's center point (handy to feed straight
    into the input module's tap/swipe tools).
    """

    left: int
    top: int
    right: int
    bottom: int
    center_x: int
    center_y: int


class UiElement(BaseModel):
    """One matched node from the UI hierarchy, flattened to the attributes
    callers actually act on. All string attributes default to "" when the
    node didn't carry them; bounds is None only if the `bounds` attribute
    was missing or unparseable.
    """

    text: str
    resource_id: str
    class_name: str
    package: str
    content_desc: str
    clickable: bool
    enabled: bool
    focused: bool
    checkable: bool
    checked: bool
    selected: bool
    scrollable: bool
    long_clickable: bool
    password: bool
    bounds: UiElementBounds | None


class UiElementMatchResult(BaseModel):
    """Outcome of `find_ui_elements`: the nodes matching the given criteria.

    match_count is how many nodes matched in total; returned_count is how
    many are in `elements` (fewer when the caller's `limit`, or the hard
    500 cap, truncated the list). truncated says whether that happened.
    match_count=0 with elements=[] is an ordinary, successful "no match"
    result, not an error.
    """

    serial: str
    match_count: int
    returned_count: int
    truncated: bool
    elements: list[UiElement]

    def summary(self) -> str:
        if self.match_count == 0:
            return f"No UI elements matched on {self.serial}."
        shown = "" if not self.truncated else f" (showing {self.returned_count})"
        return f"{self.match_count} UI element(s) matched on {self.serial}{shown}."


class UiWaitResult(BaseModel):
    """Outcome of `wait_for_ui_element` once the condition was met.

    satisfied is always True here — a condition that never comes true
    within timeout_s raises TIMEOUT instead of returning satisfied=False.
    match_count / elements are the state at the moment the condition was
    satisfied (for condition="absent" that's match_count=0, elements=[]).
    waited_s is roughly how long the poll loop ran; poll_count is how many
    hierarchy captures it took.
    """

    serial: str
    condition: WaitCondition
    satisfied: bool
    match_count: int
    waited_s: float
    poll_count: int
    elements: list[UiElement]

    def summary(self) -> str:
        return (
            f"UI condition '{self.condition}' satisfied on {self.serial} after "
            f"{self.waited_s:.1f}s ({self.poll_count} check(s))."
        )


class UiService:
    """Retrieves and searches the current UI hierarchy on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def _capture_hierarchy_xml(self, serial: str) -> tuple[str, str]:
        """Dump the hierarchy to a temp file, read it back, clean up.

        Returns (xml, dump_stdout). Raises the same classified errors
        documented on dump_ui_hierarchy.
        """
        remote_tmp_path = f"{_REMOTE_TMP_DIR}/adb_automation_mcp_ui_dump_{uuid.uuid4().hex}.xml"
        try:
            dump_result = await self._backend.shell(serial, f"uiautomator dump {remote_tmp_path}")
            _raise_for_dump_failure(serial, dump_result)

            cat_result = await self._backend.shell(serial, f"cat {shlex.quote(remote_tmp_path)}")
            _raise_for_cat_failure(serial, remote_tmp_path, cat_result)

            return cat_result.stdout, dump_result.stdout
        finally:
            # Best-effort, unconditional: never leave the temp dump on the
            # device, and never let a cleanup failure mask the real outcome.
            with suppress(Exception):
                await self._backend.shell(serial, f"rm -f {shlex.quote(remote_tmp_path)}")

    async def dump_ui_hierarchy(self, serial: str) -> UiHierarchyDumpResult:
        xml, output = await self._capture_hierarchy_xml(serial)
        return UiHierarchyDumpResult(
            serial=serial,
            xml=xml,
            node_count=_count_nodes(xml),
            success=True,
            output=output,
        )

    async def find_ui_elements(
        self,
        serial: str,
        *,
        text: str | None = None,
        text_contains: str | None = None,
        resource_id: str | None = None,
        content_desc: str | None = None,
        class_name: str | None = None,
        package: str | None = None,
        clickable: bool | None = None,
        enabled: bool | None = None,
        limit: int = _DEFAULT_RETURNED_ELEMENTS,
    ) -> UiElementMatchResult:
        criteria = _Criteria(
            text=text,
            text_contains=text_contains,
            resource_id=resource_id,
            content_desc=content_desc,
            class_name=class_name,
            package=package,
            clickable=clickable,
            enabled=enabled,
        )
        criteria.validate_non_empty()
        effective_limit = _validate_limit(limit)

        xml, _ = await self._capture_hierarchy_xml(serial)
        matches = list(_iter_matching(xml, criteria))
        returned = matches[:effective_limit]
        return UiElementMatchResult(
            serial=serial,
            match_count=len(matches),
            returned_count=len(returned),
            truncated=len(returned) < len(matches),
            elements=returned,
        )

    async def wait_for_ui_element(
        self,
        serial: str,
        *,
        condition: WaitCondition = "present",
        timeout_s: float = 10.0,
        poll_interval_s: float = 1.0,
        text: str | None = None,
        text_contains: str | None = None,
        resource_id: str | None = None,
        content_desc: str | None = None,
        class_name: str | None = None,
        package: str | None = None,
        clickable: bool | None = None,
        enabled: bool | None = None,
    ) -> UiWaitResult:
        if condition not in ("present", "absent"):
            raise InvalidArgumentError(
                "condition must be 'present' or 'absent'.", details={"condition": condition}
            )
        if not 0 < timeout_s <= _MAX_WAIT_TIMEOUT_S:
            raise InvalidArgumentError(
                f"timeout_s must be between 0 (exclusive) and {_MAX_WAIT_TIMEOUT_S:.0f}.",
                details={"timeout_s": timeout_s, "max": _MAX_WAIT_TIMEOUT_S},
            )
        if not _MIN_POLL_INTERVAL_S <= poll_interval_s <= _MAX_POLL_INTERVAL_S:
            raise InvalidArgumentError(
                f"poll_interval_s must be between {_MIN_POLL_INTERVAL_S} and "
                f"{_MAX_POLL_INTERVAL_S}.",
                details={"poll_interval_s": poll_interval_s},
            )
        criteria = _Criteria(
            text=text,
            text_contains=text_contains,
            resource_id=resource_id,
            content_desc=content_desc,
            class_name=class_name,
            package=package,
            clickable=clickable,
            enabled=enabled,
        )
        criteria.validate_non_empty()

        start = time.monotonic()
        deadline = start + timeout_s
        poll_count = 0
        while True:
            xml, _ = await self._capture_hierarchy_xml(serial)
            matches = list(_iter_matching(xml, criteria))
            poll_count += 1
            satisfied = bool(matches) if condition == "present" else not matches
            if satisfied:
                return UiWaitResult(
                    serial=serial,
                    condition=condition,
                    satisfied=True,
                    match_count=len(matches),
                    waited_s=round(time.monotonic() - start, 3),
                    poll_count=poll_count,
                    elements=matches[:_DEFAULT_RETURNED_ELEMENTS],
                )
            now = time.monotonic()
            if now >= deadline:
                raise AdbTimeoutError(
                    f"Timed out after {timeout_s:.0f}s waiting for UI condition "
                    f"'{condition}' on {serial}.",
                    details={
                        "serial": serial,
                        "condition": condition,
                        "timeout_s": timeout_s,
                        "poll_count": poll_count,
                        "last_match_count": len(matches),
                        "criteria": criteria.as_dict(),
                    },
                    remediation=(
                        "The element never reached the requested state in time. A longer "
                        "timeout_s, or looser criteria, may be needed."
                    ),
                )
            await asyncio.sleep(min(poll_interval_s, deadline - now))


class _Criteria:
    """The structured element matchers shared by find_ui_elements and
    wait_for_ui_element. All fields optional; combined with AND.
    """

    __slots__ = (
        "class_name",
        "clickable",
        "content_desc",
        "enabled",
        "package",
        "resource_id",
        "text",
        "text_contains",
    )

    def __init__(
        self,
        *,
        text: str | None,
        text_contains: str | None,
        resource_id: str | None,
        content_desc: str | None,
        class_name: str | None,
        package: str | None,
        clickable: bool | None,
        enabled: bool | None,
    ) -> None:
        self.text = text
        self.text_contains = text_contains
        self.resource_id = resource_id
        self.content_desc = content_desc
        self.class_name = class_name
        self.package = package
        self.clickable = clickable
        self.enabled = enabled

    def as_dict(self) -> dict[str, str | bool]:
        return {
            name: value
            for name in self.__slots__
            if (value := getattr(self, name)) is not None
        }

    def validate_non_empty(self) -> None:
        if not self.as_dict():
            raise InvalidArgumentError(
                "at least one match criterion is required — use dump_ui_hierarchy "
                "to retrieve the whole tree.",
                details={},
            )

    def matches(self, node: ET.Element) -> bool:
        node_text = node.get("text", "")
        node_desc = node.get("content-desc", "")
        node_class = node.get("class", "")
        node_rid = node.get("resource-id", "")

        if self.text is not None and node_text != self.text:
            return False
        if self.text_contains is not None and self.text_contains not in node_text:
            return False
        if self.content_desc is not None and node_desc != self.content_desc:
            return False
        if self.package is not None and node.get("package", "") != self.package:
            return False
        if self.resource_id is not None and not (
            node_rid == self.resource_id or node_rid.endswith(f":id/{self.resource_id}")
        ):
            return False
        if self.class_name is not None and not (
            node_class == self.class_name or node_class.rsplit(".", 1)[-1] == self.class_name
        ):
            return False
        if self.clickable is not None and _bool_attr(node, "clickable") != self.clickable:
            return False
        return self.enabled is None or _bool_attr(node, "enabled") == self.enabled


def _validate_limit(limit: int) -> int:
    if not 1 <= limit <= _MAX_RETURNED_ELEMENTS:
        raise InvalidArgumentError(
            f"limit must be between 1 and {_MAX_RETURNED_ELEMENTS}.",
            details={"limit": limit, "max": _MAX_RETURNED_ELEMENTS},
        )
    return limit


def _bool_attr(node: ET.Element, name: str) -> bool:
    return node.get(name, "false") == "true"


def _parse_bounds(raw: str) -> UiElementBounds | None:
    match = _BOUNDS_PATTERN.match(raw or "")
    if match is None:
        return None
    left, top, right, bottom = (int(v) for v in match.groups())
    return UiElementBounds(
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        center_x=(left + right) // 2,
        center_y=(top + bottom) // 2,
    )


def _node_to_element(node: ET.Element) -> UiElement:
    return UiElement(
        text=node.get("text", ""),
        resource_id=node.get("resource-id", ""),
        class_name=node.get("class", ""),
        package=node.get("package", ""),
        content_desc=node.get("content-desc", ""),
        clickable=_bool_attr(node, "clickable"),
        enabled=_bool_attr(node, "enabled"),
        focused=_bool_attr(node, "focused"),
        checkable=_bool_attr(node, "checkable"),
        checked=_bool_attr(node, "checked"),
        selected=_bool_attr(node, "selected"),
        scrollable=_bool_attr(node, "scrollable"),
        long_clickable=_bool_attr(node, "long-clickable"),
        password=_bool_attr(node, "password"),
        bounds=_parse_bounds(node.get("bounds", "")),
    )


def _iter_matching(xml: str, criteria: _Criteria) -> Iterator[UiElement]:
    if not xml.strip():
        return
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        # Malformed / truncated hierarchy: a valid "nothing to match" outcome,
        # never an unhandled crash.
        return
    for node in root.iter("node"):
        if criteria.matches(node):
            yield _node_to_element(node)


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
