# processes

Inspecting and stopping processes on a connected device. `list_processes`
returns structured `ps` rows (pid/ppid/user/rss/name) with an optional
server-side name substring filter; `get_process_id` resolves a
process/package name to its PIDs via `pidof` (a list, since one name can
back several processes; "not running" is a normal result, not an error);
`get_process_memory` reads a curated `dumpsys meminfo -s` snapshot (the
stable App Summary Pss categories plus TOTAL PSS/RSS/SWAP, in kilobytes).
`force_stop_app` is the heavy `am force-stop` (stops everything and marks
the package stopped); `kill_background_processes` is the gentler `am kill`
(background-only, leaves package state alone).

::: adb_automation_mcp.modules.processes.tools
