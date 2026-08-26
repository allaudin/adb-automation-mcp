"""Module-level, statically-introspectable tool functions for the device_info
module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_mcp.modules.device_info.service import ConnectedDevice, DeviceInfoService
from adb_mcp.registry import category


@category("read")
async def list_connected_devices(ctx: Context) -> list[ConnectedDevice]:
    """List currently connected adb devices, as reported by `adb devices -l`.

    Returns:
        One entry per connected device, in whatever state adb currently reports
        (including unauthorized or offline devices). Empty list if none are
        connected.

    Example:
        Called with no arguments. A typical response:

        ```json
        {
          "status": "success",
          "message": "list_connected_devices completed successfully.",
          "data": [
            {"serial": "emulator-5554", "state": "device", "model": "Pixel", "product": "redfin"}
          ],
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    device_info = cast(DeviceInfoService, services["device_info"])
    return await device_info.list_devices()
