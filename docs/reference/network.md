---
title: "Network: Interfaces, Routes, Connectivity"
description: "MCP tools to read Android network interfaces, routing table, and connectivity state via adb shell ip and dumpsys connectivity."
---

# network

Read-only views of a device's network state: `list_network_interfaces`
(interfaces and their addresses, `adb shell ip addr show`), `get_routes`
(the kernel routing table, `adb shell ip route`), and
`get_connectivity_state` (a curated snapshot from `adb shell dumpsys
connectivity` — the active default network plus, per network, its
transports and the INTERNET / VALIDATED / CAPTIVE_PORTAL capability flags).
For adb port forwarding, see [port_forwarding](port_forwarding.md).

::: adb_automation_mcp.modules.network.tools
