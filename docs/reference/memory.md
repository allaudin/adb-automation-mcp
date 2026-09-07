# memory

Structured memory diagnostics for a connected device.

- `get_app_memory_summary` / `get_app_memory_details` — `dumpsys meminfo -s|-a
  <target>`, parsed via the shared `adb_automation_mcp.meminfo` helpers into
  the App Summary totals, the per-mapping table, and the Objects / SQL
  sections (all in kilobytes). The raw dump is never exposed.
- `get_system_memory_summary` — bare `dumpsys meminfo`: RAM totals (Total /
  Free / Used / Lost, ZRAM / swap) plus the top PSS consumers.
- `get_memory_history` — `dumpsys procstats --hours <h> <package>`: the
  "Process summary" min/avg/max PSS/USS/RSS bands per process state. No
  accumulated samples is a valid `has_history=false` result.
- `capture_heap_dump` — `am dumpheap` to a device temp file, `adb pull` into
  `ADB_AUTOMATION_LOCAL_ROOT/heapdumps/`, then delete the temp file (on
  success and on failure). Returns the saved path, not the `.hprof` bytes.

::: adb_automation_mcp.modules.memory.tools
