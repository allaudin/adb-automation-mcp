# Integrating with Claude Code

```bash
claude mcp add adb-automation-mcp \
  -e ADB_AUTOMATION_ADB_PATH=/path/to/platform-tools/adb \
  -- uv run --directory /absolute/path/to/adb-automation-mcp adb-automation-mcp
```

Add `-e ADB_AUTOMATION_BACKEND=fake` instead of `ADB_AUTOMATION_ADB_PATH` to test without a real
device. This registers the server with **local** scope (private to you, tied to the
current project directory); use `-s user` to make it available in every project, or
`-s project` to write it to `.mcp.json` for the repo to share with collaborators.

MCP servers are loaded when a Claude Code session starts, so **start a new session**
after adding the server before expecting it to show up.

```bash
claude mcp list                     # everything registered, with live health status
claude mcp get adb-automation-mcp       # this server's config + connection status
claude mcp remove adb-automation-mcp    # tear down
```
