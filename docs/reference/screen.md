# screen

Capturing the device's current screen as a PNG, saving it to this server's
host, and returning the saved path. Runs `adb exec-out screencap -p` (the
`exec_out` backend primitive, which streams stdout as raw bytes with no
PTY/CRLF translation), so the PNG comes back intact in one round-trip — no
device-side temp file, no `adb pull`.

The bytes are written to `<ADB_AUTOMATION_LOCAL_ROOT>/screenshots/` (auto-named,
or `filename=` for a specific name) — the same host-filesystem gate
`pull_file`/`stop_log_session` use — and the tool returns the absolute
`local_path` plus width/height/size. No image bytes are returned inline; the
caller reads the file from `local_path`. `take_screenshot` fails with
`POLICY_DENIED` if `ADB_AUTOMATION_LOCAL_ROOT` is unset.

::: adb_automation_mcp.modules.screen.tools
