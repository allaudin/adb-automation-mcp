"""Module-level, statically-introspectable tool functions for the settings
module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.settings.service import SettingsNamespace, SettingsService, SettingValue
from adb_mcp.registry import category


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
