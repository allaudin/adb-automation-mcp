---
title: "Configuration"
description: "Configure adb-automation-mcp with environment variables: the adb path, command timeout, where saved files go, and which tools are enabled."
---

# Configuration

The server is configured entirely through environment variables. Set them in the
`env` block of your MCP client's configuration. All of them are optional.

| Variable | What it does | Default |
|---|---|---|
| `ADB_AUTOMATION_ADB_PATH` | Absolute path to the `adb` executable. | Found on `PATH` |
| `ADB_AUTOMATION_TIMEOUT_S` | Timeout for each `adb` command, in seconds. | `10` |
| `ADB_AUTOMATION_LOCAL_ROOT` | Folder on your computer where tools may save files. See [Saved files](#saved-files). | Not set: file-saving tools return an error |
| `ADB_AUTOMATION_ALLOW_DESTRUCTIVE` | Set to `1` to enable destructive tools. See [Safety controls](#safety-controls). | Not set: destructive tools are hidden |
| `ADB_AUTOMATION_BACKEND` | Set to `fake` to run against a built-in simulated device. Useful for trying the server or testing a client integration without real hardware. | Not set: uses real `adb` |

## The `adb` path

MCP clients such as Claude Desktop and Claude Code usually start servers with a
minimal environment that doesn't include your shell's `PATH` customizations. Even if
`adb` works in your terminal, the server may not find it. Set
`ADB_AUTOMATION_ADB_PATH` to the absolute path:

| Platform | Typical location |
|---|---|
| macOS | `~/Library/Android/sdk/platform-tools/adb` |
| Linux | `~/Android/Sdk/platform-tools/adb` |
| Windows | `%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe` |

Run `which adb` (macOS/Linux) or `where adb` (Windows) to find yours.

## Saved files

Some tools produce files on your computer, such as screenshots, logs, traces, and
bug reports. They write only inside the folder named by `ADB_AUTOMATION_LOCAL_ROOT`.
There is no fallback location: until this variable is set, these tools return an
error instead of writing anywhere.

| Tool | Saves to (inside `ADB_AUTOMATION_LOCAL_ROOT`) |
|---|---|
| `pull_file` | The `local_path` you give |
| `push_file` | Reads the `local_path` you give (it must also be inside this folder) |
| `stop_log_session` | The `local_path` you give |
| `take_screenshot` | `screenshots/` |
| `record_screen` | `recordings/` |
| `generate_bugreport` | `bugreports/` |
| `capture_heap_dump` | `heapdumps/` |
| `capture_native_tombstone` | `tombstones/` |
| `stop_method_profile` | `profiles/` |
| `capture_system_trace` | `traces/` |
| `stop_ipc_trace` | `ipc_traces/` |

Paths you pass to these tools are relative to this folder. For example, with
`ADB_AUTOMATION_LOCAL_ROOT=/home/you/adb-output`:

- `pull_file(..., local_path="ui-dump.xml")` writes `/home/you/adb-output/ui-dump.xml`.
- `take_screenshot(...)` writes
  `/home/you/adb-output/screenshots/screenshot-<serial>-<timestamp>.png` and returns
  that absolute path. The image itself is not included in the response.

A path that tries to leave the folder, such as `../elsewhere` or an absolute path
somewhere else, is rejected.

## Safety controls

Every tool belongs to one of three categories:

| Category | Meaning | Enabled by default |
|---|---|---|
| Read | Only inspects the device. | Yes |
| Write | Changes device state in a way you can normally undo, such as launching an app or changing a setting. | Yes |
| Destructive | Can permanently remove data or interrupt the device. | No |

The destructive tools are `clear_app_data`, `uninstall_package`, `remove_user`,
`reboot_device`, and `restart_adbd_as_root`. They are marked **Destructive** in the
[Tool Reference](reference/index.md).

Destructive tools stay hidden from your MCP client until you set
`ADB_AUTOMATION_ALLOW_DESTRUCTIVE=1`. The client doesn't see them at all, so an AI
assistant can't call them by mistake.

The server has no general-purpose "run a shell command" tool. Every action is a
specific tool with typed parameters, so the configuration above determines exactly
what an assistant can do.

## Response format

Every tool returns the same JSON shape:

```json
{
  "status": "success",
  "message": "One-line summary of what happened.",
  "data": { "...": "tool-specific result" },
  "error": null
}
```

When something goes wrong, for example because the device is offline, a package
isn't installed, or a command times out, `status` is `"error"` and `error` explains
why:

```json
{
  "status": "error",
  "message": "adb command timed out after 10000ms.",
  "data": null,
  "error": {
    "code": "TIMEOUT",
    "details": { "timeout_ms": 10000.0, "command": "-s emulator-5554 shell dumpsys power" },
    "retryable": true,
    "remediation": "The device or adb server may be busy or unresponsive. Retrying is reasonable."
  }
}
```

- `code` is a stable identifier, such as `DEVICE_NOT_FOUND`, `DEVICE_OFFLINE`,
  `PACKAGE_NOT_FOUND`, `TIMEOUT`, or `POLICY_DENIED`.
- `retryable` says whether trying again might succeed.
- `remediation`, when present, suggests what to do next.

Each tool's page in the [Tool Reference](reference/index.md) describes its specific
result data and error cases.
