# profiling

Android method profiling for a process (`adb shell am profile start|stop` +
`adb pull`). `start_method_profile` begins a profile (instrumented by
default, or the sampling / streaming profiler) writing to a device-side path
derived from the package. `stop_method_profile` finalizes it, pulls the
`.trace` into `ADB_AUTOMATION_LOCAL_ROOT/profiles/`, and deletes the device
file (on success and on failure). The two calls agree on the device path from
the package name, so it isn't a caller parameter. Returns artifact
path/size, not the trace bytes.

::: adb_automation_mcp.modules.profiling.tools
