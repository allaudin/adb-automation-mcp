# settings

Reading and writing Android `Settings` provider values (`adb shell settings
get/put NAMESPACE KEY`) — distinct from the system_properties module's
`getprop`/`setprop`. Deleting (`settings delete`) isn't implemented yet.

::: adb_automation_mcp.modules.settings.tools
