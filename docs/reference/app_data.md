# app_data

Clearing an installed package's full application data (`adb shell pm clear`)
on a connected device — its databases, shared preferences, files and cache
are all wiped, resetting the app to a fresh-install state. This is the
unscoped `pm clear`; there is no reliable cross-version ADB way to clear
just the cache (`pm clear --cache-only` is Android 11+ only), so the tool is
`destructive`-category and only registered when the server opts in.

::: adb_automation_mcp.modules.app_data.tools
