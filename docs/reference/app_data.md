# app_data

Clearing an installed package's cache (`adb shell pm clear --cache-only`) on a
connected device. Clearing a package's full data (`clear_app_data`) isn't
implemented yet — that has different, destructive semantics, so this module
never falls back to it when `--cache-only` isn't supported.

::: adb_automation_mcp.modules.app_data.tools
