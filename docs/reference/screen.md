# screen

Capturing the device's current screen as a PNG (`screencap -p`) and pulling
it to this server's host. AdbBackend has no primitive for streaming binary
output, so this captures to a temporary device-side path and pulls it with
the existing `adb pull` primitive, always removing the temp file afterward.

::: adb_automation_mcp.modules.screen.tools
