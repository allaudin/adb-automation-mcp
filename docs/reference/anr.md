# anr

Retrieving Application Not Responding (ANR) reports for a package from the
device's DropBox (`adb shell dumpsys dropbox --print data_app_anr
system_app_anr`) — the same store `adb bugreport` and `DropBoxManager` read.
`get_anr_reports` parses each `====`-delimited entry (timestamp/tag header,
`Key: value` header block, trace body), filters to the entries whose
recorded `Process:` / `Package:` matches the requested package, and returns
them newest first with a bounded `limit`. `include_traces=false` drops the
thread dumps for small headers-only responses. No root required; DropBox is
size-capped and rotates, so an empty result means "none currently stored".

::: adb_automation_mcp.modules.anr.tools
