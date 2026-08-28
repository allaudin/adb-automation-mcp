# activities

Launching Android activities (`adb shell am start`) on a connected device.
Only an explicit-component launch is implemented so far; other Intent options
(action, extras, flags, data URI) and interacting with already-running
activities aren't in scope for this module yet.

::: adb_automation_mcp.modules.activities.tools
