---
title: "Android Services: Start, Stop, Status"
description: "MCP tools to start, start in foreground, stop, and inspect Android services via adb shell am and dumpsys activity services."
---

# android_services

Starting (`adb shell am start-service` / `start-foreground-service`),
stopping (`am stop-service`), and inspecting (`dumpsys activity services`)
Android services on a connected device. Named `android_services` to avoid
colliding with this project's per-module service classes.

::: adb_automation_mcp.modules.android_services.tools
