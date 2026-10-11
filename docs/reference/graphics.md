---
title: "Graphics: Frame Stats and Jank"
description: "MCP tools to read and reset Android frame rendering and jank statistics via adb shell dumpsys gfxinfo framestats."
---

# graphics

Rendering / jank frame statistics for an app (`adb shell dumpsys gfxinfo
<package> framestats` and `... reset`). `get_frame_stats` parses only the
stable summary block — total frames, janky count / percentage, frame-time
percentiles, and the "Number <x>:" jank counters — and returns the frame-time
HISTOGRAM only on request; the large raw per-frame CSV is never parsed.
`reset_frame_stats` zeroes the counters before a measured flow.

::: adb_automation_mcp.modules.graphics.tools
