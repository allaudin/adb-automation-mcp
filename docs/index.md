---
title: "ADB MCP Server for Android Automation"
description: "Install and configure adb-automation-mcp, an MCP server that gives Claude and other AI agents typed, policy-controlled tools for Android devices over ADB."
---

# adb-automation-mcp

**adb-automation-mcp** is a [Model Context Protocol](https://modelcontextprotocol.io)
(MCP) server that lets AI assistants such as Claude work with Android devices and
emulators over the Android Debug Bridge (`adb`).

Rather than handing the assistant a raw shell, the server exposes **111 tools.** Each
one is a specific, named operation with typed parameters, such as installing an APK,
taking a screenshot, reading logcat, or tapping a point on screen. Each tool
documents what it does, what it returns, and how it fails, so an assistant can pick
the right one and act on the result reliably.

## Highlights

- **Broad coverage.** Apps, activities, services, permissions, input, UI inspection,
  screenshots and recordings, logs, files, settings, users, networking, memory,
  tracing, profiling, and more. See the [Tool Reference](reference/index.md).
- **Safe by default.** Tools that can permanently remove data or interrupt a device,
  such as uninstalling an app or rebooting, are hidden unless you opt in. There is
  deliberately no "run any shell command" tool.
- **Controlled file access.** Tools that save files to your computer (screenshots,
  logs, traces, bug reports) can write only inside one folder that you choose.
- **Predictable responses.** Every tool returns the same response shape, with a
  short human-readable message and structured data.

## Requirements

- Python 3.10 or later
- [uv](https://docs.astral.sh/uv/) (recommended) or `pip`
- Android SDK Platform-Tools, which provides `adb`
- An Android device with USB debugging enabled, or a running emulator

## Quick start

Run the server straight from PyPI with `uvx`. No clone or separate install step is
needed:

```bash
uvx adb-automation-mcp
```

Or install it with `pip`:

```bash
pip install adb-automation-mcp
```

The server communicates over standard input/output, so you normally don't run it by
hand. Your MCP client starts it for you.

## Connect it to your MCP client

Add the server to your client's MCP configuration (for example, Claude Desktop's
config file or a Claude Code project's `.mcp.json`):

```json
{
  "mcpServers": {
    "adb-automation-mcp": {
      "command": "uvx",
      "args": ["adb-automation-mcp"],
      "env": {
        "ADB_AUTOMATION_ADB_PATH": "/path/to/platform-tools/adb",
        "ADB_AUTOMATION_LOCAL_ROOT": "/path/to/adb-output"
      }
    }
  }
}
```

!!! tip "Set the full path to `adb`"
    MCP clients usually start servers with a minimal environment that doesn't include
    your shell's `PATH`. Even if `adb` works in your terminal, set
    `ADB_AUTOMATION_ADB_PATH` to its absolute path. You can find it with
    `which adb` on macOS/Linux or `where adb` on Windows.

Other clients use the same `command`/`args`/`env` fields under a different top-level
key. VS Code, for example, uses `servers` instead of `mcpServers`. Check your
client's MCP documentation for the exact format.

## Next steps

- [Configuration](configuration.md): all settings, where saved files go, and
  how to enable destructive tools.
- [Claude Code](integrations/claude-code.md): register the server with one command.
- [AI-Assisted Install](integrations/ai-assisted-install.md): a prompt that lets your
  AI assistant install and configure everything for you.
- [Tool Reference](reference/index.md): every tool, grouped by area.

## License

[MIT](https://github.com/allaudin/adb-automation-mcp/blob/main/LICENSE)
