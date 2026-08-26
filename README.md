# adb-mcp-server

<!-- mcp-name: io.github.allaudin/adb-mcp-server -->

[![CI](https://github.com/allaudin/adb-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/allaudin/adb-mcp-server/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/android-adb-mcp.svg?cacheSeconds=3600)](https://pypi.org/project/android-adb-mcp/)

An MCP server exposing Android Debug Bridge (ADB) capabilities as typed, documented
tools and resources.

**Full documentation: <https://allaudin.github.io/adb-mcp-server/>** — architecture,
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
backend, environment variables, the full tool list, and integrating with an MCP
client (Claude Code, Claude Desktop, ...), see the
[docs site](https://allaudin.github.io/adb-mcp-server/).

## Testing

```bash
uv run pytest        # meta (Layer 0), unit (Layer 1), and e2e (Layer 3) tests
uv run mypy src       # strict type checking
uv run ruff check .   # lint
uv run mkdocs build --strict   # docs site
```

## License

[MIT](LICENSE)
