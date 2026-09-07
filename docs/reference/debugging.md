# debugging

Recent process-exit history for a package
(`adb shell dumpsys activity exit-info <package>`). `get_process_exit_history`
parses ActivityManager's bounded `ApplicationExitInfo` ring into typed records
— reason (crash / ANR / low-memory kill / self-exit / signalled), timestamp,
pid, importance, pss/rss, and whether a trace was captured — so an agent can
explain why an app died without reading the dump. No retained history is a
valid empty result.

::: adb_automation_mcp.modules.debugging.tools
