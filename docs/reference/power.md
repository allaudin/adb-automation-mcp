# power

`get_power_state` reads the device's current high-level power state (`adb
shell dumpsys power`), deliberately minimal — wakefulness and, when
reported, interactive state only. `wake_device` turns a sleeping screen
back on by injecting the WAKEUP key (`adb shell input keyevent WAKEUP`);
it's idempotent and does not dismiss keyguard. `reboot_device` requests a
reboot into the normal system image (`adb reboot`); it's `destructive`
(denied unless `ADB_AUTOMATION_ALLOW_DESTRUCTIVE=1`) and returns as soon as
the request is accepted, so pair it with `wait_for_device_state`. Shutdown,
sleep, and reboot-to-bootloader/recovery aren't implemented yet.

::: adb_automation_mcp.modules.power.tools
