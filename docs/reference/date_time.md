# date_time

The device's current system date/time (`adb shell date`), read from the
DEVICE clock — never the MCP host's. Kept separate from `settings` (generic
Settings-provider access), `system_properties` (getprop/setprop), and
`power` (reboot/shutdown/sleep/wake). Setting the date/time or time zone
isn't implemented yet.

::: adb_automation_mcp.modules.date_time.tools
