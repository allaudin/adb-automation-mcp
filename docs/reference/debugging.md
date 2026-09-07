# debugging

Debugging aids for a connected device.

- `get_process_exit_history` — `adb shell dumpsys activity exit-info <pkg>`:
  ActivityManager's bounded `ApplicationExitInfo` ring, parsed into typed
  records (reason, timestamp, pid, importance, pss/rss, trace availability).
- `set_debug_app` / `clear_debug_app` — `adb shell am set-debug-app [-w]
  [--persistent] <pkg>` / `am clear-debug-app`. Marks (or clears)
  ActivityManager's debug app; does **not** attach a debugger.
- `list_jdwp_processes` — `adb jdwp`: PIDs of processes currently exposing a
  JDWP transport (a snapshot, since `adb jdwp` streams and never exits).
- `capture_native_backtrace` — `adb shell debuggerd -b <pid>`: native thread
  backtraces for a running process, parsed to a per-thread summary plus the
  capped full text. Privileged on production builds.
- `capture_native_tombstone` — `adb shell debuggerd <pid>`: a full native
  tombstone written into `ADB_AUTOMATION_LOCAL_ROOT/tombstones/`; returns
  path + parsed header metadata, not contents.

::: adb_automation_mcp.modules.debugging.tools
