"""Module-level, statically-introspectable tool functions for the settings
module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.settings.service import (
    SettingsNamespace,
    SettingsService,
    SettingValue,
    SettingWriteResult,
)
from adb_automation_mcp.registry import category


@category("read")
async def get_setting(
    ctx: Context, serial: str, namespace: SettingsNamespace, key: str, user_id: int | None = None
) -> SettingValue:
    """Read one Android Settings-provider value: `adb shell settings get NAMESPACE KEY`.

    namespace is restricted to "system", "secure", or "global" — the only
    namespaces `settings get` recognizes — by the tool's own input schema,
    so an invalid namespace is rejected before this tool (or any adb
    command) ever runs. Deliberately distinct from system_properties'
    get_property: Settings (SettingsProvider) and system properties
    (`getprop`/`setprop`) are unrelated Android subsystems. Writing a
    setting (`put`/`delete`) isn't implemented yet.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        namespace: Which Settings namespace to read from: "system",
            "secure", or "global".
        key: The setting's key, e.g. "screen_brightness".
        user_id: Read the setting for one specific Android user (`--user`,
            see list_users). Omit to use settings' default user.

    Returns:
        The serial, namespace, key, user_id, and the setting's value.
        value is None when the key has no value in that namespace for the
        target user — see Error handling below for why that's returned as
        data, not raised.

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. `settings get` reports a key with
        no value by printing the literal text "null" at exit code 0, not
        by failing — this tool returns that as value=None, ordinary
        success data, rather than an error (the one, rare ambiguity: a
        value that's coincidentally the literal string "null" is
        indistinguishable from "no value", the same class of caveat as
        get_property's empty-string case). A permission rejection raises
        PERMISSION_DENIED; any other failure raises a generic
        BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", namespace="system",
        key="screen_brightness". A typical response:

        ```json
        {
          "status": "success",
          "message": "system:screen_brightness='128' on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "namespace": "system",
            "key": "screen_brightness",
            "value": "128",
            "user_id": null
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    settings = cast(SettingsService, services["settings"])
    return await settings.get_setting(serial, namespace, key, user_id=user_id)


@category("write")
async def set_setting(
    ctx: Context,
    serial: str,
    namespace: SettingsNamespace,
    key: str,
    value: str,
    user_id: int | None = None,
) -> SettingWriteResult:
    """Write one Android Settings-provider value: `adb shell settings put NAMESPACE KEY VALUE`.

    namespace is restricted to "system", "secure", or "global" by the
    tool's own input schema, so an invalid namespace is rejected before any
    adb command runs. The key is read once before the write and once after,
    so the result carries both previous_value (keep it to restore the
    original when your scenario is done) and new_value (what the provider
    reports now). Deliberately distinct from system_properties' set_property
    — Settings and system properties are unrelated Android subsystems.
    Deleting a setting (`settings delete`) isn't implemented yet.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        namespace: Which Settings namespace to write to: "system", "secure",
            or "global".
        key: The setting's key, e.g. "screen_brightness".
        value: The value to write, as a string (numeric settings are still
            passed as their decimal text, e.g. "128"). Passed as a single
            shell-quoted argument.
        user_id: Write the setting for one specific Android user (`--user`,
            see list_users). Omit to use settings' default user.

    Returns:
        The serial, namespace, key, user_id, requested_value, previous_value
        (None if the key had no value before), new_value (None if it has
        none now), and changed (whether previous_value and new_value
        differ). new_value != requested_value is returned as-is, not raised
        — Android normalizes some values and silently ignores some
        protected keys, and that's a real device outcome worth seeing.

    Error handling:
        An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A namespace/key the device refuses
        to let the shell user write (SecurityException / "Permission
        Denial") raises PERMISSION_DENIED. `settings put` reaching
        SettingsProvider and being declined there (a Java stack trace /
        "Exception occurred while executing 'put'") raises ANDROID_REJECTED.
        Any other non-zero exit raises a generic BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554", namespace="system",
        key="screen_brightness", value="200". A typical response:

        ```json
        {
          "status": "success",
          "message": "Set system:screen_brightness = '200' on emulator-5554 (was '128').",
          "data": {
            "serial": "emulator-5554",
            "namespace": "system",
            "key": "screen_brightness",
            "requested_value": "200",
            "previous_value": "128",
            "new_value": "200",
            "user_id": null,
            "changed": true
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    settings = cast(SettingsService, services["settings"])
    return await settings.set_setting(serial, namespace, key, value, user_id=user_id)
