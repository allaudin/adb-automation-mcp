---
title: "Logcat: Read and Capture Android Logs"
description: "MCP tools to read, filter, clear, and capture Android logcat output, including per-package logs and log sessions."
---

# logger

Pulls diagnostic logs off a connected device via `adb shell logcat`, in dump-and-exit
mode — a snapshot of what's already in the buffer, not a live tail.

::: adb_automation_mcp.modules.logger.tools
