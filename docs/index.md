# adb-mcp-server

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
uv run adb-mcp-server
```

By default this talks to the `adb` binary found on `PATH`. Configure it with env vars:

| Env var | Purpose | Default |
|---|---|---|
| `ADB_MCP_BACKEND=fake` | Use the deterministic fake backend instead of real adb — no `adb` binary or device needed | unset (real backend) |
| `ADB_MCP_ADB_PATH` | Explicit path to the `adb` binary | unset (resolved via `PATH`) |
| `ADB_MCP_TIMEOUT_S` | Per-command timeout, in seconds | `10` |
| `ADB_MCP_ALLOW_DESTRUCTIVE=1` | Opt in to `destructive`-category tools | unset (denied by default) — no destructive tools exist yet, so this currently has no effect |

`ADB_MCP_ADB_PATH` matters more than it might seem: an MCP client (Claude Code, Claude
Desktop, ...) launches this server with a minimal environment that usually does **not**
include your shell's `PATH` customizations, so `adb` resolving fine in your terminal
doesn't mean it'll resolve inside the launched server. Set the path explicitly when
integrating with a client (see [Integrations](integrations/claude-code.md)).

```bash
# real device/emulator, explicit adb path
ADB_MCP_ADB_PATH=/path/to/platform-tools/adb uv run adb-mcp-server

# deterministic fake backend, no adb required
ADB_MCP_BACKEND=fake uv run adb-mcp-server
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

[MIT](https://github.com/allaudin/adb-mcp-server/blob/main/LICENSE)
