# tracing

Perfetto system traces and ActivityManager Binder/IPC transaction traces.

- `capture_system_trace` — `adb shell perfetto ...` + `adb pull`. Semantic
  presets (`cpu`, `scheduling`, `graphics`, `app_startup`, `memory`,
  `binder`), bounded duration 1–120s, optional package scope. Pulled into
  `ADB_AUTOMATION_LOCAL_ROOT/traces/`; device file removed afterwards.
- `start_ipc_trace` / `stop_ipc_trace` — `adb shell am trace-ipc start` /
  `am trace-ipc stop --dump-file <dev>` + `adb pull`. `start` returns session
  state only; `stop` dumps the Binder transaction log into
  `ADB_AUTOMATION_LOCAL_ROOT/ipc_traces/` and cleans up the device file.

All three return artifact path/size, never the trace contents.

::: adb_automation_mcp.modules.tracing.tools
