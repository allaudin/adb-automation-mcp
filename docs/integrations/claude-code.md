---
title: "Use the ADB MCP Server with Claude Code"
description: "Register adb-automation-mcp with Claude Code using claude mcp add, choose a scope, and verify the Android ADB MCP server is connected."
---

# Claude Code

## Add the server

Register the server with a single command. Replace the `adb` path with your own (see
[The `adb` path](../configuration.md#the-adb-path)):

```bash
claude mcp add adb-automation-mcp \
  -e ADB_AUTOMATION_ADB_PATH=/path/to/platform-tools/adb \
  -e ADB_AUTOMATION_LOCAL_ROOT=/path/to/adb-output \
  -- uvx adb-automation-mcp
```

Add more `-e NAME=value` flags for any other setting in
[Configuration](../configuration.md). For example, add
`-e ADB_AUTOMATION_ALLOW_DESTRUCTIVE=1` to enable destructive tools.

## Choose a scope

By default the server is added with **local** scope: it's private to you and
available only in the current project directory. Use the `-s` flag to change this:

| Flag | Available in | Stored in |
|---|---|---|
| *(none)* or `-s local` | This project, for you only | Your Claude Code settings |
| `-s user` | Every project, for you only | Your Claude Code settings |
| `-s project` | This project, for everyone who uses the repository | `.mcp.json` in the project |

## Verify the connection

Claude Code loads MCP servers when a session starts, so **start a new session** after
adding the server. Then check that it's connected:

```bash
claude mcp list                       # all servers and their connection status
claude mcp get adb-automation-mcp     # this server's configuration and status
```

Try it by asking Claude something like *"List the connected Android devices."*

## Remove the server

```bash
claude mcp remove adb-automation-mcp
```
