# android-adb-mcp

<!-- mcp-name: io.github.allaudin/adb-mcp-server -->

[![CI](https://github.com/allaudin/adb-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/allaudin/adb-mcp-server/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/android-adb-mcp.svg?cacheSeconds=3600)](https://pypi.org/project/android-adb-mcp/)

An MCP server exposing Android Debug Bridge (ADB) capabilities as typed, documented
tools and resources.

**[Full documentation](https://allaudin.github.io/adb-mcp-server/)** — architecture,
decision log, per-tool reference, and client integration guides.

## Install

```bash
uvx android-adb-mcp
# or
pip install android-adb-mcp
```

## Quickstart

```bash
uv sync
uv run adb-mcp-server
```

Talks to the `adb` binary on `PATH` by default. For real-device setup, the fake
backend, the full tool list, and per-client integration guides (Claude Code, Claude
Desktop, ...), see the [docs site](https://allaudin.github.io/adb-mcp-server/).

## Installation prompt

Prefer not to configure this by hand? Hand the
[AI-assisted install prompt](https://allaudin.github.io/adb-mcp-server/integrations/ai-assisted-install/)
to an AI coding assistant that can run shell commands and edit MCP config (Claude
Code, GitHub Copilot in agent mode, ...) — it detects/installs `uv`, resolves `adb`'s
absolute path, and registers this server for you.

## MCP client configuration

Add this to your client's `mcp.json` (e.g. Claude Desktop's config, or a Claude Code
project's `.mcp.json`). Every real-device env var is shown below — all are optional,
see the [full reference](https://allaudin.github.io/adb-mcp-server/#running-it) for
defaults and details (including `ADB_MCP_BACKEND`, a testing-only switch to the fake
in-memory backend, not something a real client config needs):

```json
{
  "mcpServers": {
    "adb-mcp-server": {
      "command": "uvx",
      "args": ["android-adb-mcp"],
      "env": {
        "ADB_MCP_ADB_PATH": "/path/to/platform-tools/adb",
        "ADB_MCP_TIMEOUT_S": "10",
        "ADB_MCP_ALLOW_DESTRUCTIVE": "1",
        "ADB_MCP_LOCAL_ROOT": "/path/to/local/root"
      }
    }
  }
}
```

- `ADB_MCP_ADB_PATH` — explicit path to the `adb` binary; MCP clients usually launch
  the server with a minimal environment that doesn't include your shell's `PATH`
  customizations, so set this explicitly rather than relying on `PATH` resolution
- `ADB_MCP_TIMEOUT_S` — per-command timeout in seconds
- `ADB_MCP_ALLOW_DESTRUCTIVE=1` — allow `destructive`-category tools (e.g.
  `remove_user`); denied by default
- `ADB_MCP_LOCAL_ROOT` — the folder on this machine where file-saving tools
  (`pull_file`, `take_screenshot`, `stop_log_session`) are allowed to write; unset
  means those tools refuse to write anywhere

## Testing

```bash
uv run pytest        # meta (Layer 0), unit (Layer 1), and e2e (Layer 3) tests
uv run mypy src       # strict type checking
uv run ruff check .   # lint
uv run mkdocs build --strict   # docs site
```

## License

[MIT](LICENSE)
