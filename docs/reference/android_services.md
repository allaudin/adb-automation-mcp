# android_services

Starting Android services (`adb shell am start-service`) on a connected device.
Named `android_services`, not `services`, to avoid colliding with this
project's own "services" concept (the per-module domain service instances the
registry builds). Foreground-service starts and stopping/querying a service's
status aren't implemented yet.

::: adb_mcp.modules.android_services.tools
