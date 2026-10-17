---
title: "Packages: Install, Uninstall, Inspect Apps"
description: "MCP tools to list, install, uninstall, inspect, and enable or disable Android apps over adb, with semantic options instead of raw pm flags."
---

# Packages

Installed-app management on a connected device: listing (`pm list
packages`), installing (`adb install`), uninstalling (`pm uninstall`),
making an installed package available to another user (`pm
install-existing`), reading a package's APK paths and details, and enabling
or disabling a package or component (`pm enable` / `pm disable`). Options are
semantic rather than raw adb/pm flags — see each tool's Args for how they
map to Android's behavior.

::: adb_automation_mcp.modules.packages.tools
