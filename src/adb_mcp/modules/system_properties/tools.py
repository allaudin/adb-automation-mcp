"""Module-level, statically-introspectable tool functions for the
system_properties module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.system_properties.service import (
    Property,
    PropertyList,
    PropertyMetadata,
    SetPropertyResult,
    SystemPropertiesService,
)
from adb_mcp.registry import category


@category("read")
async def get_property(ctx: Context, serial: str, name: str) -> Property:
    """Get the value of one Android system property: `adb shell getprop NAME`.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        name: The property name to look up, e.g. "ro.build.version.release".

    Returns:
        The property's name and value. An empty value does not necessarily
        mean the property was set to empty — see Error handling below.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error. `getprop` itself can't distinguish "property exists and
        is set to an empty string" from "property doesn't exist at all" — both
        produce identical empty output, exit code 0 — so this tool returns an
        empty value as ordinary success data in both cases rather than
        guessing which one happened or raising an error.

    Example:
        Called with serial="emulator-5554", name="ro.build.version.release".
        A typical response:

        ```json
        {
          "status": "success",
          "message": "ro.build.version.release='14' on emulator-5554.",
          "data": {"serial": "emulator-5554", "name": "ro.build.version.release", "value": "14"},
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    system_properties = cast(SystemPropertiesService, services["system_properties"])
    return await system_properties.get_property(serial, name)


@category("read")
async def list_properties(ctx: Context, serial: str, prefix: str | None = None) -> PropertyList:
    """List Android system properties as structured data: `adb shell getprop`.

    Parses `getprop`'s "[name]: [value]" output into individual name/value
    entries rather than exposing the raw text. Optionally scoped to
    properties whose name starts with a given prefix — filtering happens
    after parsing, inside this tool's service, not via a shell pipeline or
    `grep`.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        prefix: If set, only properties whose name starts with this string
            are returned, e.g. "ro.build." for build-identity properties.
            None (the default) returns every property on the device.

    Returns:
        The serial, the prefix requested (if any), and every matching
        property as name/value pairs.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error. A prefix that matches nothing is not an error — it comes
        back as an empty properties list.

    Example:
        Called with serial="emulator-5554", prefix="ro.build.". A typical
        response:

        ```json
        {
          "status": "success",
          "message": "2 properties matching 'ro.build.' on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "prefix": "ro.build.",
            "properties": [
              {"serial": "emulator-5554", "name": "ro.build.version.release", "value": "14"},
              {"serial": "emulator-5554", "name": "ro.build.version.sdk", "value": "34"}
            ]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    system_properties = cast(SystemPropertiesService, services["system_properties"])
    return await system_properties.list_properties(serial, prefix=prefix)


@category("read")
async def get_property_metadata(ctx: Context, serial: str, name: str) -> PropertyMetadata:
    """Get metadata for one Android system property: value plus (where
    supported) its SELinux security context and declared type, via
    `adb shell getprop NAME` and `adb shell getprop -Z NAME`.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        name: The property name to look up.

    Returns:
        The property's name, value, SELinux context (e.g.
        "u:object_r:build_prop:s0"), and declared type (the "type" component
        of that context, e.g. "build_prop"). selinux_context and
        declared_type are both None when this device/Android version doesn't
        support the underlying capability — see Error handling below.

    Error handling:
        Propagates the same way most tools do (unlike check_adb_available): if
        the adb binary itself can't be found or is unresponsive, or the
        serial doesn't match a connected device, that surfaces as an actual
        tool error. If the SELinux-context lookup specifically isn't
        supported on this device/Android version (rather than the device
        being unreachable), that's not treated as an internal failure — this
        tool falls back to selinux_context=None, declared_type=None and still
        returns the property's value.

    Example:
        Called with serial="emulator-5554", name="ro.build.version.release".
        A typical response:

        ```json
        {
          "status": "success",
          "message": "ro.build.version.release='14' on emulator-5554 (type=build_prop).",
          "data": {
            "serial": "emulator-5554",
            "name": "ro.build.version.release",
            "value": "14",
            "selinux_context": "u:object_r:build_prop:s0",
            "declared_type": "build_prop"
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    system_properties = cast(SystemPropertiesService, services["system_properties"])
    return await system_properties.get_property_metadata(serial, name)


@category("write")
async def set_property(ctx: Context, serial: str, name: str, value: str) -> SetPropertyResult:
    """Set an ordinary mutable Android system property: `adb shell setprop NAME VALUE`.

    Refuses to touch control-property namespaces that represent a distinct
    semantic operation rather than a plain property mutation — at minimum
    "ctl.*" (service start/stop/restart) and "sys.powerctl" (device
    shutdown/reboot). Those belong to dedicated lifecycle/power tools, not
    this one. Beyond that, this does not attempt to work around any
    Android/SELinux/property-service restriction — if the device itself
    refuses the write (e.g. an already-set read-only property), that failure
    is surfaced as a real tool error, not silently bypassed.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        name: The property name to set. Rejected up front if it falls under
            a control namespace (see above) — never sent to the device at all.
        value: The value to set the property to.

    Returns:
        The serial, name, and value that were set. Only returned on success —
        see Error handling below.

    Error handling:
        A prohibited namespace (`ctl.*`, `sys.powerctl`) is a tool error
        raised before any adb call is made, not success:false data. Beyond
        that, this propagates the same way most tools do: if the adb binary
        itself can't be found or is unresponsive, or the serial doesn't match
        a connected device, that's an actual tool error. If the device/
        property-service/SELinux rejects an otherwise-permitted write (e.g. a
        read-only property that's already been set), that's also a tool
        error — the underlying adb/setprop failure message is preserved
        rather than hidden.

    Example:
        Called with serial="emulator-5554", name="debug.myapp.loglevel",
        value="verbose". A typical response:

        ```json
        {
          "status": "success",
          "message": "Set debug.myapp.loglevel='verbose' on emulator-5554.",
          "data": {"serial": "emulator-5554", "name": "debug.myapp.loglevel", "value": "verbose"},
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    system_properties = cast(SystemPropertiesService, services["system_properties"])
    return await system_properties.set_property(serial, name, value)
