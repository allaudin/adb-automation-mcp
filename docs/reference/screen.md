# screen

Capturing the device's current screen as a PNG and returning the raw image
bytes. Runs `adb exec-out screencap -p` (the `exec_out` backend primitive,
which streams stdout as raw bytes with no PTY/CRLF translation), so the PNG
comes back intact in one round-trip — no device-side temp file, no `adb pull`.
The registry emits the bytes to the client as an MCP image content block, with
width/height/size metadata alongside.

Pass `save=true` to *also* write the PNG to
`<ADB_AUTOMATION_LOCAL_ROOT>/screenshots/` (auto-named, or `filename=` for a
specific name) — the same host-filesystem gate `pull_file`/`stop_log_session`
use. The inline image block is returned either way.

::: adb_automation_mcp.modules.screen.tools
