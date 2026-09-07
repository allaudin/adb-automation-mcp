"""Module-level, statically-introspectable tool functions for the ui module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.ui.service import (
    UiElementMatchResult,
    UiHierarchyDumpResult,
    UiService,
    UiWaitResult,
    WaitCondition,
)
from adb_automation_mcp.registry import category


@category("read")
async def dump_ui_hierarchy(ctx: Context, serial: str) -> UiHierarchyDumpResult:
    """Retrieve the device's current UI hierarchy: `uiautomator dump`.

    `uiautomator dump` only writes its result to a file on the device, so
    this dumps to a temporary path under `/data/local/tmp`, reads the XML
    back inline over `adb shell` (no host filesystem write, no local_root
    needed — the caller never has to know or manage the device-side path),
    and always removes the temporary file afterward. To search the
    hierarchy without handling XML yourself, use find_ui_elements; this
    module doesn't inject any input actions (see the input module for that).

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
            "output": "UI hierarchy dumped to: /data/local/tmp/adb_automation_mcp_ui_dump_....xml\\n"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    ui = cast(UiService, services["ui"])
    return await ui.dump_ui_hierarchy(serial)


@category("read")
async def find_ui_elements(
    ctx: Context,
    serial: str,
    text: str | None = None,
    text_contains: str | None = None,
    resource_id: str | None = None,
    content_desc: str | None = None,
    class_name: str | None = None,
    package: str | None = None,
    clickable: bool | None = None,
    enabled: bool | None = None,
    limit: int = 50,
) -> UiElementMatchResult:
    """Search the current UI hierarchy for nodes matching structured criteria.

    Captures the hierarchy the same way dump_ui_hierarchy does, then
    filters `<node>` elements in Python and returns each match flattened to
    the attributes callers act on (text, resource_id, class, bounds + the
    bounds' center point, and the usual boolean state flags). At least one
    criterion must be given; all supplied criteria are combined with AND.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        text: Match nodes whose `text` attribute equals this exactly.
        text_contains: Match nodes whose `text` contains this substring
            (case-sensitive).
        resource_id: Match nodes by resource-id — either the full
            "package:id/name" or just the bare "name" (which also matches a
            Compose testTag surfaced as a prefix-less resource-id).
        content_desc: Match nodes whose `content-desc` equals this exactly.
        class_name: Match nodes by class — either the fully-qualified name
            ("android.widget.Button") or just the final segment ("Button").
        package: Match nodes whose `package` equals this exactly.
        clickable: Match nodes whose `clickable` flag equals this bool.
        enabled: Match nodes whose `enabled` flag equals this bool.
        limit: Maximum number of matched elements to return (1-500, default
            50). match_count still reports the true total; truncated says
            whether the list was cut.

    Returns:
        The serial, match_count (total matches), returned_count (how many
        are in elements), truncated, and elements — each an object with
        text / resource_id / class_name / package / content_desc, the
        boolean flags (clickable, enabled, focused, checkable, checked,
        selected, scrollable, long_clickable, password), and bounds
        ({left, top, right, bottom, center_x, center_y} or null). Zero
        matches is a normal success result.

    Error handling:
        No criteria at all, or a limit outside 1-500, is rejected before
        any device round-trip (INVALID_ARGUMENT). An unknown serial or
        unresponsive adb binary raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE;
        uiautomator failing raises UIAUTOMATOR_FAILED; no inspectable
        window content right now raises UI_HIERARCHY_UNAVAILABLE. A
        malformed / truncated hierarchy is treated as zero matches, not a
        crash. Other failures raise PERMISSION_DENIED / REMOTE_FILE_NOT_FOUND
        / BACKEND_ERROR as for dump_ui_hierarchy.

    Example:
        Called with serial="emulator-5554", text="Phone". A typical
        response:

        ```json
        {
          "status": "success",
          "message": "1 UI element(s) matched on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "match_count": 1,
            "returned_count": 1,
            "truncated": false,
            "elements": [
              {
                "text": "Phone",
                "resource_id": "com.android.launcher3:id/icon",
                "class_name": "android.widget.TextView",
                "package": "com.android.launcher3",
                "content_desc": "Phone",
                "clickable": true,
                "enabled": true,
                "focused": false,
                "checkable": false,
                "checked": false,
                "selected": false,
                "scrollable": false,
                "long_clickable": true,
                "password": false,
                "bounds": {"left": 100, "top": 200, "right": 300, "bottom": 400, "center_x": 200, "center_y": 300}
              }
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    ui = cast(UiService, services["ui"])
    return await ui.find_ui_elements(
        serial,
        text=text,
        text_contains=text_contains,
        resource_id=resource_id,
        content_desc=content_desc,
        class_name=class_name,
        package=package,
        clickable=clickable,
        enabled=enabled,
        limit=limit,
    )


@category("read")
async def wait_for_ui_element(
    ctx: Context,
    serial: str,
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
    """Poll the UI hierarchy until an element appears or disappears.

    Re-captures the hierarchy every poll_interval_s and re-checks the same
    structured criteria as find_ui_elements, until the condition holds or
    timeout_s elapses. Replaces blind `sleep`s in automation. The loop is
    always bounded — timeout_s is capped at 120s and poll_interval_s at
    30s. At least one criterion must be given (AND-combined).

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        condition: "present" (default) waits until at least one node
            matches; "absent" waits until no node matches.
        timeout_s: Maximum seconds to keep polling (0 exclusive to 120).
            Default 10.
        poll_interval_s: Seconds between hierarchy captures (0.1 to 30).
            Default 1.
        text: Match nodes whose `text` equals this exactly.
        text_contains: Match nodes whose `text` contains this substring.
        resource_id: Match by full "package:id/name" or bare "name".
        content_desc: Match nodes whose `content-desc` equals this exactly.
        class_name: Match by fully-qualified class or final segment.
        package: Match nodes whose `package` equals this exactly.
        clickable: Match nodes whose `clickable` flag equals this bool.
        enabled: Match nodes whose `enabled` flag equals this bool.

    Returns:
        The serial, condition, satisfied (always True on return),
        match_count and elements at the moment the condition held (for
        "absent" that's 0 / []), waited_s (roughly how long the loop ran),
        and poll_count (how many captures it took).

    Error handling:
        No criteria, an out-of-range timeout_s / poll_interval_s, or a bad
        condition is rejected before any device round-trip
        (INVALID_ARGUMENT). The condition never holding within timeout_s
        raises TIMEOUT (retryable), with the last seen match count in its
        details. An unknown serial / adb failure raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE; uiautomator or hierarchy failures
        raise UIAUTOMATOR_FAILED / UI_HIERARCHY_UNAVAILABLE /
        PERMISSION_DENIED / BACKEND_ERROR as for dump_ui_hierarchy.

    Example:
        Called with serial="emulator-5554", text="Success", timeout_s=5.
        A typical response:

        ```json
        {
          "status": "success",
          "message": "UI condition 'present' satisfied on emulator-5554 after 1.2s (2 check(s)).",
          "data": {
            "serial": "emulator-5554",
            "condition": "present",
            "satisfied": true,
            "match_count": 1,
            "waited_s": 1.2,
            "poll_count": 2,
            "elements": [{"text": "Success", "resource_id": "", "class_name": "android.widget.TextView", "package": "com.example.app", "content_desc": "", "clickable": false, "enabled": true, "focused": false, "checkable": false, "checked": false, "selected": false, "scrollable": false, "long_clickable": false, "password": false, "bounds": null}]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    ui = cast(UiService, services["ui"])
    return await ui.wait_for_ui_element(
        serial,
        condition=condition,
        timeout_s=timeout_s,
        poll_interval_s=poll_interval_s,
        text=text,
        text_contains=text_contains,
        resource_id=resource_id,
        content_desc=content_desc,
        class_name=class_name,
        package=package,
        clickable=clickable,
        enabled=enabled,
    )
