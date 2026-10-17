---
title: "Tool Reference"
description: "Every tool exposed by adb-automation-mcp, grouped by area, with a one-line summary and links to full parameter and response documentation."
---

# Tool Reference

Every tool the server exposes, grouped by area. Select a tool name for its full
parameters, response format, error behavior, and a worked example.

Tools marked **Destructive** can permanently remove data or interrupt the device. They
are hidden from clients unless the server is started with
`ADB_AUTOMATION_ALLOW_DESTRUCTIVE=1` (see [Configuration](../configuration.md#safety-controls)).

## Devices & Connection

Find devices, manage the adb connection, forward ports, and control power.

### [Device Info](device_info.md)

| Tool | What it does |
|---|---|
| [`list_connected_devices`](device_info.md#adb_automation_mcp.modules.device_info.tools.list_connected_devices) | List currently connected adb devices, as reported by `adb devices -l`. |

### [Connection](connection.md)

| Tool | What it does |
|---|---|
| [`restart_adb_server`](connection.md#adb_automation_mcp.modules.connection.tools.restart_adb_server) | Restart the local adb server. |
| [`connect_device`](connection.md#adb_automation_mcp.modules.connection.tools.connect_device) | Connect to a device over TCP/IP. |
| [`disconnect_device`](connection.md#adb_automation_mcp.modules.connection.tools.disconnect_device) | Disconnect a device connected over TCP/IP. |
| [`restart_adbd_as_root`](connection.md#adb_automation_mcp.modules.connection.tools.restart_adbd_as_root) | Restart the on-device `adbd` daemon as root. **Destructive** |
| [`restart_adbd_as_shell`](connection.md#adb_automation_mcp.modules.connection.tools.restart_adbd_as_shell) | Restart the on-device `adbd` daemon as non-root (shell). |
| [`wait_for_device_state`](connection.md#adb_automation_mcp.modules.connection.tools.wait_for_device_state) | Block until a device reaches a given adb transport state. |

### [Diagnostics](diagnostics.md)

| Tool | What it does |
|---|---|
| [`check_adb_available`](diagnostics.md#adb_automation_mcp.modules.diagnostics.tools.check_adb_available) | Check whether the adb binary is reachable and able to list connected devices. |
| [`get_adb_version`](diagnostics.md#adb_automation_mcp.modules.diagnostics.tools.get_adb_version) | Report the version of the adb client this server is driving. |
| [`generate_bugreport`](diagnostics.md#adb_automation_mcp.modules.diagnostics.tools.generate_bugreport) | Generate a full Android bugreport and save it to the host. |

### [Port Forwarding](port_forwarding.md)

| Tool | What it does |
|---|---|
| [`create_forward`](port_forwarding.md#adb_automation_mcp.modules.port_forwarding.tools.create_forward) | Forward a host TCP port to a device TCP port. |
| [`list_forwards`](port_forwarding.md#adb_automation_mcp.modules.port_forwarding.tools.list_forwards) | List active host→device forwards. |
| [`remove_forward`](port_forwarding.md#adb_automation_mcp.modules.port_forwarding.tools.remove_forward) | Remove one host→device forward. |
| [`create_reverse`](port_forwarding.md#adb_automation_mcp.modules.port_forwarding.tools.create_reverse) | Reverse-forward a device TCP port to a host TCP port. |
| [`list_reverses`](port_forwarding.md#adb_automation_mcp.modules.port_forwarding.tools.list_reverses) | List active device→host reverses for one device. |
| [`remove_reverse`](port_forwarding.md#adb_automation_mcp.modules.port_forwarding.tools.remove_reverse) | Remove one device→host reverse. |

### [Power](power.md)

| Tool | What it does |
|---|---|
| [`get_power_state`](power.md#adb_automation_mcp.modules.power.tools.get_power_state) | Get the device's current high-level power state. |
| [`reboot_device`](power.md#adb_automation_mcp.modules.power.tools.reboot_device) | Reboot a device into its normal system image. **Destructive** |
| [`wake_device`](power.md#adb_automation_mcp.modules.power.tools.wake_device) | Wake a sleeping device's screen. |

### [Date & Time](date_time.md)

| Tool | What it does |
|---|---|
| [`get_date_time`](date_time.md#adb_automation_mcp.modules.date_time.tools.get_date_time) | Get the device's current system date/time. |

## Apps

Install and inspect apps, launch components, manage permissions and processes, and run tests.

### [Packages](packages.md)

| Tool | What it does |
|---|---|
| [`list_packages`](packages.md#adb_automation_mcp.modules.packages.tools.list_packages) | List installed Android packages on a device. |
| [`install_apk`](packages.md#adb_automation_mcp.modules.packages.tools.install_apk) | Install an APK on a connected device. |
| [`uninstall_package`](packages.md#adb_automation_mcp.modules.packages.tools.uninstall_package) | Uninstall a package on a connected device. **Destructive** |
| [`install_existing_for_user`](packages.md#adb_automation_mcp.modules.packages.tools.install_existing_for_user) | Make an already-installed package available to another Android user. |
| [`get_package_path`](packages.md#adb_automation_mcp.modules.packages.tools.get_package_path) | Resolve an installed package's on-device APK paths. |
| [`get_package_info`](packages.md#adb_automation_mcp.modules.packages.tools.get_package_info) | Curated snapshot of an installed package. |
| [`set_package_enabled_state`](packages.md#adb_automation_mcp.modules.packages.tools.set_package_enabled_state) | Enable or disable an app, or one of its components. |

### [Activities](activities.md)

| Tool | What it does |
|---|---|
| [`start_activity`](activities.md#adb_automation_mcp.modules.activities.tools.start_activity) | Launch an Android activity on a device. |
| [`resolve_activity`](activities.md#adb_automation_mcp.modules.activities.tools.resolve_activity) | Resolve which Activity would handle an Intent, without launching it. |
| [`get_foreground_activity`](activities.md#adb_automation_mcp.modules.activities.tools.get_foreground_activity) | Report the currently resumed/top Activity. |

### [Services](android_services.md)

| Tool | What it does |
|---|---|
| [`start_service`](android_services.md#adb_automation_mcp.modules.android_services.tools.start_service) | Start an Android service on a device. |
| [`start_foreground_service`](android_services.md#adb_automation_mcp.modules.android_services.tools.start_foreground_service) | Start an Android foreground service. |
| [`stop_service`](android_services.md#adb_automation_mcp.modules.android_services.tools.stop_service) | Stop a started Android service. |
| [`get_service_status`](android_services.md#adb_automation_mcp.modules.android_services.tools.get_service_status) | Status snapshot for one Android Service. |

### [Broadcasts](broadcasts.md)

| Tool | What it does |
|---|---|
| [`send_broadcast`](broadcasts.md#adb_automation_mcp.modules.broadcasts.tools.send_broadcast) | Send an Android intent broadcast to a device. |

### [Permissions](permissions.md)

| Tool | What it does |
|---|---|
| [`grant_permission`](permissions.md#adb_automation_mcp.modules.permissions.tools.grant_permission) | Grant one Android runtime permission to a package. |
| [`revoke_permission`](permissions.md#adb_automation_mcp.modules.permissions.tools.revoke_permission) | Revoke one Android runtime permission from a package. |
| [`get_package_permissions`](permissions.md#adb_automation_mcp.modules.permissions.tools.get_package_permissions) | A package's full permission picture. |

### [App Data](app_data.md)

| Tool | What it does |
|---|---|
| [`clear_app_data`](app_data.md#adb_automation_mcp.modules.app_data.tools.clear_app_data) | Wipe a package's full application data on a device. **Destructive** |
| [`clear_app_cache`](app_data.md#adb_automation_mcp.modules.app_data.tools.clear_app_cache) | Clear only a package's cache, leaving its data intact. |

### [Processes](processes.md)

| Tool | What it does |
|---|---|
| [`force_stop_app`](processes.md#adb_automation_mcp.modules.processes.tools.force_stop_app) | Force-stop an Android package on a device. |
| [`kill_background_processes`](processes.md#adb_automation_mcp.modules.processes.tools.kill_background_processes) | Kill a package's killable background processes. |
| [`list_processes`](processes.md#adb_automation_mcp.modules.processes.tools.list_processes) | List running processes on a device. |
| [`get_process_id`](processes.md#adb_automation_mcp.modules.processes.tools.get_process_id) | Resolve a process/package name to its PIDs. |
| [`get_process_memory`](processes.md#adb_automation_mcp.modules.processes.tools.get_process_memory) | Read a curated memory snapshot for a process. |

### [Content Providers](content.md)

| Tool | What it does |
|---|---|
| [`query_content`](content.md#adb_automation_mcp.modules.content.tools.query_content) | Query a ContentProvider and return its rows. |

### [Instrumentation Tests](instrumentation.md)

| Tool | What it does |
|---|---|
| [`run_instrumentation`](instrumentation.md#adb_automation_mcp.modules.instrumentation.tools.run_instrumentation) | Run an instrumentation test runner. |

## Screen & Interaction

See what's on screen and drive the UI.

### [Screenshots & Recording](screen.md)

| Tool | What it does |
|---|---|
| [`take_screenshot`](screen.md#adb_automation_mcp.modules.screen.tools.take_screenshot) | Capture the device's screen as a PNG, save it to the host, return the path. |
| [`record_screen`](screen.md#adb_automation_mcp.modules.screen.tools.record_screen) | Record the device screen to an MP4, save it to the host, return the path. |

### [Input](input.md)

| Tool | What it does |
|---|---|
| [`tap`](input.md#adb_automation_mcp.modules.input.tools.tap) | Inject a single touch/tap event on a device. |
| [`swipe`](input.md#adb_automation_mcp.modules.input.tools.swipe) | Inject a swipe gesture between two points. |
| [`input_text`](input.md#adb_automation_mcp.modules.input.tools.input_text) | Type literal text into the focused input field. |
| [`press_key`](input.md#adb_automation_mcp.modules.input.tools.press_key) | Inject one Android key event. |

### [UI Inspection](ui.md)

| Tool | What it does |
|---|---|
| [`dump_ui_hierarchy`](ui.md#adb_automation_mcp.modules.ui.tools.dump_ui_hierarchy) | Retrieve the device's current UI hierarchy. |
| [`find_ui_elements`](ui.md#adb_automation_mcp.modules.ui.tools.find_ui_elements) | Search the current UI hierarchy for nodes matching structured criteria. |
| [`wait_for_ui_element`](ui.md#adb_automation_mcp.modules.ui.tools.wait_for_ui_element) | Poll the UI hierarchy until an element appears or disappears. |

### [Displays](displays.md)

| Tool | What it does |
|---|---|
| [`list_displays`](displays.md#adb_automation_mcp.modules.displays.tools.list_displays) | Enumerate a device's logical displays. |
| [`get_display_size`](displays.md#adb_automation_mcp.modules.displays.tools.get_display_size) | Get a display's pixel dimensions. |
| [`get_display_density`](displays.md#adb_automation_mcp.modules.displays.tools.get_display_density) | Get a display's density in dpi. |

## Device Configuration

Read and change device settings, system properties, users, and network state.

### [Settings](settings.md)

| Tool | What it does |
|---|---|
| [`get_setting`](settings.md#adb_automation_mcp.modules.settings.tools.get_setting) | Read one Android Settings-provider value. |
| [`set_setting`](settings.md#adb_automation_mcp.modules.settings.tools.set_setting) | Write one Android Settings-provider value. |

### [System Properties](system_properties.md)

| Tool | What it does |
|---|---|
| [`get_property`](system_properties.md#adb_automation_mcp.modules.system_properties.tools.get_property) | Get the value of one Android system property. |
| [`list_properties`](system_properties.md#adb_automation_mcp.modules.system_properties.tools.list_properties) | List Android system properties as structured data. |
| [`get_property_metadata`](system_properties.md#adb_automation_mcp.modules.system_properties.tools.get_property_metadata) | Get metadata for one Android system property. |
| [`set_property`](system_properties.md#adb_automation_mcp.modules.system_properties.tools.set_property) | Set an ordinary mutable Android system property. |

### [Users](user.md)

| Tool | What it does |
|---|---|
| [`get_current_user`](user.md#adb_automation_mcp.modules.user.tools.get_current_user) | Get the current Android user on a device. |
| [`dump_user`](user.md#adb_automation_mcp.modules.user.tools.dump_user) | Dump detailed Android user info for a device. |
| [`user_info`](user.md#adb_automation_mcp.modules.user.tools.user_info) | Get detailed info for one Android user. |
| [`list_users`](user.md#adb_automation_mcp.modules.user.tools.list_users) | List every Android user on a device. |
| [`switch_user`](user.md#adb_automation_mcp.modules.user.tools.switch_user) | Switch the active Android user on a device. |
| [`create_user`](user.md#adb_automation_mcp.modules.user.tools.create_user) | Create a full secondary Android user on a device. |
| [`remove_user`](user.md#adb_automation_mcp.modules.user.tools.remove_user) | Delete an Android user/profile from a device. **Destructive** |
| [`get_user_capabilities`](user.md#adb_automation_mcp.modules.user.tools.get_user_capabilities) | Get device-wide Android multi-user capabilities: what the platform build supports, not info about any one particular user. |
| [`start_user`](user.md#adb_automation_mcp.modules.user.tools.start_user) | Start a stopped Android user in the background. |
| [`is_user_stopped`](user.md#adb_automation_mcp.modules.user.tools.is_user_stopped) | Check whether an Android user is stopped. |
| [`get_user_state`](user.md#adb_automation_mcp.modules.user.tools.get_user_state) | Get a started user's lifecycle state. |

### [Network](network.md)

| Tool | What it does |
|---|---|
| [`list_network_interfaces`](network.md#adb_automation_mcp.modules.network.tools.list_network_interfaces) | List the device's network interfaces and their addresses. |
| [`get_routes`](network.md#adb_automation_mcp.modules.network.tools.get_routes) | List the device's kernel routing table. |
| [`get_connectivity_state`](network.md#adb_automation_mcp.modules.network.tools.get_connectivity_state) | Curated connectivity snapshot. |

## Files

Move files between the device and your machine.

### [Files](files.md)

| Tool | What it does |
|---|---|
| [`pull_file`](files.md#adb_automation_mcp.modules.files.tools.pull_file) | Copy one file from a device to this server's host. |
| [`push_file`](files.md#adb_automation_mcp.modules.files.tools.push_file) | Copy one file from this server's host to a device. |

## Logs & Debugging

Read logs, investigate crashes and ANRs, and attach debuggers.

### [Logs (logcat)](logger.md)

| Tool | What it does |
|---|---|
| [`read_logs`](logger.md#adb_automation_mcp.modules.logger.tools.read_logs) | Dump recent device logs. |
| [`clear_logs`](logger.md#adb_automation_mcp.modules.logger.tools.clear_logs) | Clear a device's log buffer. |
| [`get_log_buffer_size`](logger.md#adb_automation_mcp.modules.logger.tools.get_log_buffer_size) | Report a log buffer's ring size and usage. |
| [`read_package_logs`](logger.md#adb_automation_mcp.modules.logger.tools.read_package_logs) | Dump recent logs for one package. |
| [`start_log_session`](logger.md#adb_automation_mcp.modules.logger.tools.start_log_session) | Start a log-capture session: anchors on the device's current log position, to be replayed later by stop_log_session. |
| [`stop_log_session`](logger.md#adb_automation_mcp.modules.logger.tools.stop_log_session) | Stop a log-capture session and write everything logged since start_log_session to a file on the host running this server. |

### [ANR Reports](anr.md)

| Tool | What it does |
|---|---|
| [`get_anr_reports`](anr.md#adb_automation_mcp.modules.anr.tools.get_anr_reports) | Get a package's ANR reports from the device's DropBox. |

### [Debugging](debugging.md)

| Tool | What it does |
|---|---|
| [`get_process_exit_history`](debugging.md#adb_automation_mcp.modules.debugging.tools.get_process_exit_history) | Get a package's recent process-exit records. |
| [`set_debug_app`](debugging.md#adb_automation_mcp.modules.debugging.tools.set_debug_app) | Mark an app as ActivityManager's debug app. |
| [`clear_debug_app`](debugging.md#adb_automation_mcp.modules.debugging.tools.clear_debug_app) | Clear ActivityManager's configured debug app. |
| [`list_jdwp_processes`](debugging.md#adb_automation_mcp.modules.debugging.tools.list_jdwp_processes) | List processes exposing a JDWP transport. |
| [`capture_native_backtrace`](debugging.md#adb_automation_mcp.modules.debugging.tools.capture_native_backtrace) | Capture native thread backtraces for a running process. |
| [`capture_native_tombstone`](debugging.md#adb_automation_mcp.modules.debugging.tools.capture_native_tombstone) | Request a full native tombstone for a process and save it to the host. |

## Performance

Measure memory, rendering, CPU, and IPC behavior.

### [Memory](memory.md)

| Tool | What it does |
|---|---|
| [`get_app_memory_summary`](memory.md#adb_automation_mcp.modules.memory.tools.get_app_memory_summary) | Compact memory snapshot for one app/process. |
| [`get_app_memory_details`](memory.md#adb_automation_mcp.modules.memory.tools.get_app_memory_details) | Detailed memory breakdown for one app. |
| [`get_system_memory_summary`](memory.md#adb_automation_mcp.modules.memory.tools.get_system_memory_summary) | System-wide memory totals and top consumers. |
| [`get_memory_history`](memory.md#adb_automation_mcp.modules.memory.tools.get_memory_history) | Historical memory bands for a package. |
| [`capture_heap_dump`](memory.md#adb_automation_mcp.modules.memory.tools.capture_heap_dump) | Capture a heap dump and save it to the host. |
| [`set_heap_watch`](memory.md#adb_automation_mcp.modules.memory.tools.set_heap_watch) | Auto-collect a heap dump when a process gets large. |
| [`clear_heap_watch`](memory.md#adb_automation_mcp.modules.memory.tools.clear_heap_watch) | Clear a previously configured heap watch. |
| [`get_memory_maps`](memory.md#adb_automation_mcp.modules.memory.tools.get_memory_maps) | Get a process's memory-map aggregates. |

### [Graphics & Frame Stats](graphics.md)

| Tool | What it does |
|---|---|
| [`get_frame_stats`](graphics.md#adb_automation_mcp.modules.graphics.tools.get_frame_stats) | Get an app's rendering / jank statistics. |
| [`reset_frame_stats`](graphics.md#adb_automation_mcp.modules.graphics.tools.reset_frame_stats) | Reset an app's graphics frame statistics. |

### [Method Profiling](profiling.md)

| Tool | What it does |
|---|---|
| [`start_method_profile`](profiling.md#adb_automation_mcp.modules.profiling.tools.start_method_profile) | Start Android method profiling for a process. |
| [`stop_method_profile`](profiling.md#adb_automation_mcp.modules.profiling.tools.stop_method_profile) | Stop method profiling and save the trace to the host. |

### [System Tracing](tracing.md)

| Tool | What it does |
|---|---|
| [`capture_system_trace`](tracing.md#adb_automation_mcp.modules.tracing.tools.capture_system_trace) | Capture a bounded Perfetto system trace. |
| [`start_ipc_trace`](tracing.md#adb_automation_mcp.modules.tracing.tools.start_ipc_trace) | Start ActivityManager Binder/IPC transaction tracing. |
| [`stop_ipc_trace`](tracing.md#adb_automation_mcp.modules.tracing.tools.stop_ipc_trace) | Stop IPC tracing, dump it, and save it to the host. |

### [Binder IPC](binder.md)

| Tool | What it does |
|---|---|
| [`get_binder_call_stats`](binder.md#adb_automation_mcp.modules.binder.tools.get_binder_call_stats) | Get Binder IPC call statistics. |
| [`reset_binder_call_stats`](binder.md#adb_automation_mcp.modules.binder.tools.reset_binder_call_stats) | Reset Binder IPC call statistics. |
