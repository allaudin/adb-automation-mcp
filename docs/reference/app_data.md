---
title: "App Data: Clear Data and Cache"
description: "MCP tools to clear an Android app's full data via adb shell pm clear, or only its cache while leaving data intact."
---

# App Data

Clearing an installed package's data on a connected device.
`clear_app_data` runs the unscoped `adb shell pm clear`, wiping databases,
shared preferences, files and cache; it is `destructive` and only registered
when the server opts in. `clear_app_cache` clears only the cache
(`pm clear --cache-only` on Android 11+, falling back to removing the cache
directories as root) and never touches app data.

::: adb_automation_mcp.modules.app_data.tools
