# displays

Enumerating a device's logical displays from `adb shell dumpsys display`.
`dumpsys display` is hundreds of lines of unstable internal state; this
module reads only two curated markers — the `mViewports=[...]` line and the
`Display States:` section — and parses them in Python. The `display_id`
values it returns are the ones `-d` / `--display` on the screenshot, input,
and activity-launch tools expect. Changing display state (size, density,
rotation) isn't implemented yet.

::: adb_automation_mcp.modules.displays.tools
