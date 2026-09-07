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
  (`pull_file`, `stop_log_session`, `take_screenshot`) are allowed to write; unset
  means those tools refuse to write anywhere

## Testing

```bash
uv run pytest        # meta (Layer 0), unit (Layer 1), and e2e (Layer 3) tests
uv run mypy src       # strict type checking
uv run ruff check .   # lint
uv run mkdocs build --strict   # docs site
```

## Tools

**87 tools.** Full signatures, docstrings, and worked examples are in the
[tool reference](https://allaudin.github.io/adb-automation-mcp/reference/diagnostics/).
Tools marked † are `destructive` — not registered unless
`ADB_AUTOMATION_ALLOW_DESTRUCTIVE=1`.

<!-- stats:tools-table -->
| Module | Tools |
|---|---|
| `activities` (3) | `start_activity`, `resolve_activity`, `get_foreground_activity` |
| `android_services` (4) | `start_service`, `start_foreground_service`, `stop_service`, `get_service_status` |
| `anr` (1) | `get_anr_reports` |
| `app_data` (2) | `clear_app_data`†, `clear_app_cache` |
| `broadcasts` (1) | `send_broadcast` |
| `connection` (6) | `restart_adb_server`, `connect_device`, `disconnect_device`, `restart_adbd_as_root`†, `restart_adbd_as_shell`, `wait_for_device_state` |
| `content` (1) | `query_content` |
| `date_time` (1) | `get_date_time` |
| `device_info` (1) | `list_connected_devices` |
| `diagnostics` (2) | `check_adb_available`, `get_adb_version` |
| `displays` (3) | `list_displays`, `get_display_size`, `get_display_density` |
| `files` (2) | `pull_file`, `push_file` |
| `input` (4) | `tap`, `swipe`, `input_text`, `press_key` |
| `instrumentation` (1) | `run_instrumentation` |
| `logger` (6) | `read_logs`, `clear_logs`, `get_log_buffer_size`, `read_package_logs`, `start_log_session`, `stop_log_session` |
| `network` (3) | `list_network_interfaces`, `get_routes`, `get_connectivity_state` |
| `packages` (7) | `list_packages`, `install_apk`, `uninstall_package`†, `install_existing_for_user`, `get_package_path`, `get_package_info`, `set_package_enabled_state` |
| `permissions` (3) | `grant_permission`, `revoke_permission`, `get_package_permissions` |
| `port_forwarding` (6) | `create_forward`, `list_forwards`, `remove_forward`, `create_reverse`, `list_reverses`, `remove_reverse` |
| `power` (3) | `get_power_state`, `reboot_device`†, `wake_device` |
| `processes` (5) | `force_stop_app`, `kill_background_processes`, `list_processes`, `get_process_id`, `get_process_memory` |
| `screen` (2) | `take_screenshot`, `record_screen` |
| `settings` (2) | `get_setting`, `set_setting` |
| `system_properties` (4) | `get_property`, `list_properties`, `get_property_metadata`, `set_property` |
| `ui` (3) | `dump_ui_hierarchy`, `find_ui_elements`, `wait_for_ui_element` |
| `user` (11) | `get_current_user`, `dump_user`, `user_info`, `list_users`, `switch_user`, `create_user`, `remove_user`†, `get_user_capabilities`, `start_user`, `is_user_stopped`, `get_user_state` |
<!-- /stats:tools-table -->

## License

[MIT](LICENSE)
