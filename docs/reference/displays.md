# displays

Reading a device's displays: `list_displays` enumerates every logical
display from `adb shell dumpsys display` (parsing only two curated markers —
the `mViewports=[...]` line and the `Display States:` section), and
`get_display_size` / `get_display_density` read one display's pixel
dimensions and dpi from `adb shell wm size` / `adb shell wm density`,
including a currently-set override where present. The `display_id` values
`list_displays` returns are the ones `-d` / `--display` on the screenshot,
input, and activity-launch tools expect. Changing display state (setting
size, density, or rotation) isn't implemented yet.

::: adb_automation_mcp.modules.displays.tools
