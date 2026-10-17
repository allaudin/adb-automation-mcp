---
title: "Diagnostics: ADB Health and Bug Reports"
description: "MCP tools to check adb availability and version, and to capture an Android bug report to the host."
---

# Diagnostics

`check_adb_available` and `get_adb_version` are read-only health checks for
the adb connection itself — they never mutate anything. See
[connection](connection.md) for operations that change the connection
(restarting the server, connecting to a device). `generate_bugreport` runs
the host `adb bugreport`, saving the (usually zipped) archive under
`ADB_AUTOMATION_LOCAL_ROOT/bugreports/` and returning its path and size, not
its contents.

::: adb_automation_mcp.modules.diagnostics.tools
