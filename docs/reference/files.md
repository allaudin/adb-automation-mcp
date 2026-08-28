# files

Copying files between a connected device and this server's host (`adb pull`
so far — `adb push` isn't implemented yet). Private app-data semantics (e.g.
`run-as` for another app's sandboxed files) aren't handled here.

::: adb_automation_mcp.modules.files.tools
