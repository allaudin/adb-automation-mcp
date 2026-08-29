# adb-automation-mcp

An MCP server exposing Android Debug Bridge (ADB) capabilities as typed, documented
tools and resources. See [Architecture](ARCHITECTURE.md) for how the system is put
together.

## Requirements

- Python ≥ 3.10
- [uv](https://docs.astral.sh/uv/)
- Android platform-tools (`adb`) — only needed for the real backend; the fake backend
  (below) needs nothing device-related installed.

## Running it

```bash
uv sync
uv run adb-automation-mcp
```

By default this talks to the `adb` binary found on `PATH`. Configure it with env vars:

| Env var | Purpose | Default |
|---|---|---|
| `ADB_AUTOMATION_BACKEND=fake` | Use the deterministic fake backend instead of real adb — no `adb` binary or device needed | unset (real backend) |
| `ADB_AUTOMATION_ADB_PATH` | Explicit path to the `adb` binary | unset (resolved via `PATH`) |
| `ADB_AUTOMATION_TIMEOUT_S` | Per-command timeout, in seconds | `10` |
| `ADB_AUTOMATION_ALLOW_DESTRUCTIVE=1` | Opt in to `destructive`-category tools (e.g. `uninstall_package`, `remove_user`, `restart_adbd_as_root`) | unset (denied by default) |
| `ADB_AUTOMATION_LOCAL_ROOT` | The folder on this machine where file-saving tools are allowed to write | unset — those tools refuse to write anywhere until set |

`ADB_AUTOMATION_ADB_PATH` matters more than it might seem: an MCP client (Claude Code, Claude
Desktop, ...) launches this server with a minimal environment that usually does **not**
include your shell's `PATH` customizations, so `adb` resolving fine in your terminal
doesn't mean it'll resolve inside the launched server. Set the path explicitly when
integrating with a client (see [Integrations](integrations/claude-code.md)).

```bash
# real device/emulator, explicit adb path
ADB_AUTOMATION_ADB_PATH=/path/to/platform-tools/adb uv run adb-automation-mcp

# deterministic fake backend, no adb required
ADB_AUTOMATION_BACKEND=fake uv run adb-automation-mcp
```

### Where saved files go (`ADB_AUTOMATION_LOCAL_ROOT`)

A few tools save a file to this machine when you ask them to: `pull_file` (copies a
file off the device), `stop_log_session` (saves a captured log), and
`take_screenshot` when called with `save=true` (it always returns the PNG inline;
`save=true` *also* writes it to disk). `ADB_AUTOMATION_LOCAL_ROOT` is the one folder
these tools are allowed to write into — there's no fallback location, so they refuse
to save until it's set.

Each tool's `local_path` argument is a path *inside* that folder. With
`ADB_AUTOMATION_LOCAL_ROOT=/home/you/adb-downloads` set:

- `pull_file(..., local_path="ui-dump.xml")` writes to
  `/home/you/adb-downloads/ui-dump.xml`
- `stop_log_session(..., local_path="session1.log")` writes to
  `/home/you/adb-downloads/session1.log`
- `take_screenshot(..., save=true)` writes to
  `/home/you/adb-downloads/screenshots/screenshot-<serial>-<timestamp>.png`
  (or `screenshots/<filename>.png` when `filename=` is given)

A `local_path` that tries to escape that folder — `../elsewhere`, or an absolute path
pointing somewhere else — is rejected rather than written anywhere.

```bash
ADB_AUTOMATION_LOCAL_ROOT=/home/you/adb-downloads uv run adb-automation-mcp
```

## MCP client configuration

Add this to your client's `mcp.json` (e.g. Claude Desktop's config, or a Claude Code
project's `.mcp.json` — see [Integrations](integrations/claude-code.md)). Other
clients use a similar `command`/`args`/`env` shape but a different top-level key (VS
Code Copilot's `.vscode/mcp.json`, for instance, uses `servers` instead of
`mcpServers`) — check your client's own MCP docs for the exact wrapper. Every env var
from the table above is optional; shown here with example values:

```json
{
  "mcpServers": {
    "adb-automation-mcp": {
      "command": "uvx",
      "args": ["adb-automation-mcp"],
      "env": {
        "ADB_AUTOMATION_ADB_PATH": "/path/to/platform-tools/adb",
        "ADB_AUTOMATION_TIMEOUT_S": "10",
        "ADB_AUTOMATION_ALLOW_DESTRUCTIVE": "1",
        "ADB_AUTOMATION_LOCAL_ROOT": "/path/to/local/root"
      }
    }
  }
}
```

## Available tools

See the [Tool Reference](reference/diagnostics.md) for every tool's full signature,
docstring, and worked example — generated directly from source, so it can't drift out
of sync with what the server actually exposes.

## Testing

```bash
uv run pytest        # meta (Layer 0), unit (Layer 1), and e2e (Layer 3) tests
uv run mypy src       # strict type checking
uv run ruff check .   # lint
```

## License

[MIT](https://github.com/allaudin/adb-automation-mcp/blob/main/LICENSE)
