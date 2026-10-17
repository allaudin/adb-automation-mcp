---
title: "Screen: Screenshots and Screen Recording"
description: "MCP tools to capture Android screenshots (PNG) and screen recordings (MP4) via adb and save them to the host."
---

# Screenshots & Recording

Capturing the device screen and saving it to this server's host.
`take_screenshot` runs `adb exec-out screencap -p` and writes a PNG to
`<ADB_AUTOMATION_LOCAL_ROOT>/screenshots/`; `record_screen` runs
`adb shell screenrecord` for a bounded duration and saves the MP4. Both
return the saved path and metadata, never the file bytes inline, and fail
with `POLICY_DENIED` if `ADB_AUTOMATION_LOCAL_ROOT` is unset.

::: adb_automation_mcp.modules.screen.tools
