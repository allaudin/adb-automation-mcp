# debugging

Debugging aids for a connected device.

- `get_process_exit_history` — `adb shell dumpsys activity exit-info <pkg>`:
  ActivityManager's bounded `ApplicationExitInfo` ring, parsed into typed
  records (reason, timestamp, pid, importance, pss/rss, trace availability).
  No retained history is a valid empty result.
- `set_debug_app` / `clear_debug_app` — `adb shell am set-debug-app [-w]
  [--persistent] <pkg>` / `am clear-debug-app`. Marks (or clears)
  ActivityManager's debug app; does **not** attach a debugger. `clear` is
  idempotent.
- `list_jdwp_processes` — `adb jdwp`: PIDs of processes currently exposing a
  JDWP transport (a snapshot, since `adb jdwp` streams and never exits).

::: adb_automation_mcp.modules.debugging.tools
