# tracing

Capturing a bounded Perfetto system trace with safe semantic presets
(`adb shell perfetto -o <dev> -t <N>s -b 32mb <cats>` + `adb pull`).
`capture_system_trace` takes a preset (`cpu`, `scheduling`, `graphics`,
`app_startup`, `memory`, `binder`) — not an arbitrary Perfetto config — plus a
bounded duration (1–120s) and an optional package scope. The trace is pulled
into `ADB_AUTOMATION_LOCAL_ROOT/traces/` and the device-side file is deleted
afterwards (on success and on failure). Returns the saved path and sizes, not
the trace bytes.

::: adb_automation_mcp.modules.tracing.tools
