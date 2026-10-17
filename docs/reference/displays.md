---
title: "Displays: Size, Density, Logical Displays"
description: "MCP tools to list Android logical displays and read display size and density via adb dumpsys display and wm."
---

# Displays

Reading a device's displays: `list_displays` enumerates every logical
display from `adb shell dumpsys display`, and `get_display_size` /
`get_display_density` read one display's pixel dimensions and dpi from
`adb shell wm size` / `adb shell wm density`, including any active override.
The `display_id` values `list_displays` returns are the ones `-d` /
`--display` on the screenshot, input, and activity-launch tools expect.

::: adb_automation_mcp.modules.displays.tools
