# AI-Assisted Install

If you're using an AI coding assistant that can run shell commands and edit your MCP
client's configuration (Claude Code, GitHub Copilot in agent mode, etc.), you can hand
it the prompt below instead of following the setup steps by hand. It checks for `uv`
and `adb`, resolves `adb`'s absolute path (important — most MCP clients don't launch
the server with your shell's `PATH`), registers the server against the published
`android-adb-mcp` package, and verifies it starts.

Paste this into your assistant:

```text
Install and configure the ADB MCP Server from:

https://github.com/allaudin/adb-mcp-server

The published Python package is:

`android-adb-mcp`

Please do the following:

1. Check whether `uv` is installed. If not, install it using the official recommended method for this operating system.

2. Check whether Android `adb` is installed by running the appropriate command for this system.

3. If `adb` is available, determine its absolute path. Do not assume the MCP process will inherit my shell `PATH`.

4. Configure this MCP server in the MCP client I am currently using.

Prefer running the published package directly with:

`uvx android-adb-mcp`

rather than cloning the repository.

Configure the server name as:

`adb-mcp-server`

Set:

`ADB_MCP_ADB_PATH`

to the absolute path of the detected `adb` executable.

Do not enable destructive tools unless I explicitly ask you to.

If I want tools that write files to the host later, explain that `ADB_MCP_LOCAL_ROOT` must be configured and ask me which directory should be allowed.

5. After configuration, verify that the MCP server starts successfully and is visible to the current MCP client.

6. If an Android device or emulator is connected, verify the server by using a harmless read-only ADB MCP operation such as listing connected devices or checking ADB availability.

7. If no device is connected, consider the installation successful if the MCP server itself starts correctly. Explain that I can connect a device later.

Do not modify the ADB MCP Server source code.

At the end report:

* whether `uv` was available
* detected `adb` path
* MCP configuration created
* whether the MCP server started successfully
* whether a device/emulator was detected
* any action I still need to take
```

See the [docs home page](../index.md) for the config shape this produces and every
supported env var, and [Integrating with Claude Code](claude-code.md) for the
manual/CLI equivalent.
