# binder

Binder IPC call statistics (`adb shell dumpsys binder_calls_stats` and `...
--reset`). `get_binder_call_stats` returns the sampling interval, the
"Summary:" totals, a bounded list of the top per-UID callers, and the
"Exceptions thrown" tally — never the raw per-call rows. Binder-call-stats
collection is often off by default; when it is, `collecting` is false and the
totals are zero (a normal state). `reset_binder_call_stats` zeroes the
counters before a measured flow.

::: adb_automation_mcp.modules.binder.tools
