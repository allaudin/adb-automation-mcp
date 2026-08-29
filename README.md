# adb-automation-mcp

<!-- mcp-name: io.github.allaudin/adb-automation-mcp -->

[![CI](https://github.com/allaudin/adb-automation-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/allaudin/adb-automation-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/adb-automation-mcp.svg?cacheSeconds=3600)](https://pypi.org/project/adb-automation-mcp/)

An MCP server exposing Android Debug Bridge (ADB) capabilities as typed, documented
tools and resources.

**[Full documentation](https://allaudin.github.io/adb-automation-mcp/)** — architecture,
decision log, per-tool reference, and client integration guides.

## Install

```bash
uvx adb-automation-mcp
# or
pip install adb-automation-mcp
```

## Quickstart

```bash
uv sync
uv run adb-automation-mcp
```

Talks to the `adb` binary on `PATH` by default. For real-device setup, the fake
backend, the full tool list, and per-client integration guides (Claude Code, Claude
Desktop, ...), see the [docs site](https://allaudin.github.io/adb-automation-mcp/).

## Installation prompt

Prefer not to configure this by hand? Hand the
[AI-assisted install prompt](https://allaudin.github.io/adb-automation-mcp/integrations/ai-assisted-install/)
to an AI coding assistant that can run shell commands and edit MCP config (Claude
Code, GitHub Copilot in agent mode, ...) — it detects/installs `uv`, resolves `adb`'s
absolute path, and registers this server for you.

## MCP client configuration

Add this to your client's `mcp.json` (e.g. Claude Desktop's config, or a Claude Code
project's `.mcp.json`). Every real-device env var is shown below — all are optional,
see the [full reference](https://allaudin.github.io/adb-automation-mcp/#running-it) for
defaults and details (including `ADB_AUTOMATION_BACKEND`, a testing-only switch to the fake
in-memory backend, not something a real client config needs):

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

- `ADB_AUTOMATION_ADB_PATH` — explicit path to the `adb` binary; MCP clients usually launch
  the server with a minimal environment that doesn't include your shell's `PATH`
  customizations, so set this explicitly rather than relying on `PATH` resolution
- `ADB_AUTOMATION_TIMEOUT_S` — per-command timeout in seconds
- `ADB_AUTOMATION_ALLOW_DESTRUCTIVE=1` — allow `destructive`-category tools (e.g.
  `remove_user`); denied by default
- `ADB_AUTOMATION_LOCAL_ROOT` — the folder on this machine where file-saving tools
  (`pull_file`, `stop_log_session`, and `take_screenshot` with `save=true`) are
  allowed to write; unset means those tools refuse to write anywhere

## Testing

```bash
uv run pytest        # meta (Layer 0), unit (Layer 1), and e2e (Layer 3) tests
uv run mypy src       # strict type checking
uv run ruff check .   # lint
uv run mkdocs build --strict   # docs site
```

## License

[MIT](LICENSE)
