# network

Read-only views of a device's network state: `list_network_interfaces`
(interfaces and their addresses, `adb shell ip addr show`), `get_routes`
(the kernel routing table, `adb shell ip route`), and
`get_connectivity_state` (a curated snapshot from `adb shell dumpsys
connectivity` — the active default network plus, per network, its
transports and the INTERNET / VALIDATED / CAPTIVE_PORTAL capability flags).
Wi-Fi configuration, routing changes, and adb port forwarding aren't
implemented here.

::: adb_automation_mcp.modules.network.tools
