---
title: "System Properties: getprop and setprop"
description: "MCP tools to read, list, inspect, and set Android system properties via adb getprop and setprop."
---

# System Properties

Android system properties on a connected device — read, list (optionally by prefix),
inspect metadata (SELinux context/declared type), and set ordinary mutable ones.
Control-property namespaces (`ctl.*`, `sys.powerctl`) are refused, since they
represent lifecycle/power operations rather than plain property mutation.

::: adb_automation_mcp.modules.system_properties.tools
