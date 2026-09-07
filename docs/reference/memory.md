# memory

Structured memory diagnostics for a connected device.

- `get_app_memory_summary` / `get_app_memory_details` — `dumpsys meminfo -s|-a
  <target>`, parsed via the shared `adb_automation_mcp.meminfo` helpers.
- `get_system_memory_summary` — bare `dumpsys meminfo`: RAM totals + top PSS
  consumers.
- `get_memory_history` — `dumpsys procstats --hours <h> <package>`: the
  "Process summary" min/avg/max PSS/USS/RSS bands.
- `capture_heap_dump` — `am dumpheap` + `adb pull` into
  `ADB_AUTOMATION_LOCAL_ROOT/heapdumps/`, device temp file cleaned.
- `set_heap_watch` / `clear_heap_watch` — `am set-watch-heap <pkg> <bytes>` /
  `am clear-watch-heap <pkg>`: auto-collect a heap dump when a process's PSS
  crosses a threshold.
- `get_memory_maps` — `cat /proc/<pid>/smaps_rollup`: the kernel's per-process
  Rss/Pss + clean/dirty split + swap aggregates (a fixed compact model, not a
  generic /proc reader).

::: adb_automation_mcp.modules.memory.tools
