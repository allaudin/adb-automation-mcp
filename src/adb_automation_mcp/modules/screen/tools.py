"""Module-level, statically-introspectable tool functions for the screen module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.screen.service import (
    ScreenRecordingResult,
    ScreenService,
    TakeScreenshotResult,
)
from adb_automation_mcp.registry import category


@category("read")
async def take_screenshot(
    ctx: Context,
    serial: str,
    display_id: int | None = None,
    filename: str | None = None,
) -> TakeScreenshotResult:
    """Capture the device's screen as a PNG, save it to the host, return the path.

    Runs `adb exec-out screencap -p`, writes the PNG to
    `<ADB_AUTOMATION_LOCAL_ROOT>/screenshots/`, and returns the absolute path
    it was saved to (plus width/height/size). The caller reads the image from
    that path — no image bytes are returned inline.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        display_id: Capture one specific display (`-d`, see list_displays)
            on a multi-display device. Omit to capture the default display.
        filename: Bare filename for the saved file (no path separators);
            `.png` is appended if missing. Omit for an auto name like
            `screenshot-<serial>-<UTC timestamp>.png`.

    Returns:
        The serial, display_id, the absolute local_path the PNG was saved to,
        best-effort width/height read from the PNG header, and size_bytes.

    Error handling:
        No `ADB_AUTOMATION_LOCAL_ROOT` configured (or a `filename` that
        resolves outside it) raises POLICY_DENIED. A `filename` containing a
        path separator raises INVALID_ARGUMENT. An unknown serial or
        unresponsive adb binary raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A
        permission rejection raises PERMISSION_DENIED. If screencap runs but
        returns no PNG data (e.g. an invalid display_id on some builds), or
        any other non-zero exit, this raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554". A typical response:

        ```json
        {
          "status": "success",
          "message": "Saved 1080x2400 screenshot from emulator-5554 to /srv/adb/screenshots/screenshot-emulator-5554-20260830-101500.png.",
          "data": {
            "serial": "emulator-5554",
            "display_id": null,
            "local_path": "/srv/adb/screenshots/screenshot-emulator-5554-20260830-101500.png",
            "width": 1080,
            "height": 2400,
            "size_bytes": 843221,
            "success": true
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    screen = cast(ScreenService, services["screen"])
    return await screen.take_screenshot(serial, display_id=display_id, filename=filename)


@category("read")
async def record_screen(
    ctx: Context,
    serial: str,
    duration_s: int = 10,
    size: str | None = None,
    bit_rate_mbps: float | None = None,
    bugreport: bool = False,
    verbose: bool = False,
    filename: str | None = None,
) -> ScreenRecordingResult:
    """Record the device screen to an MP4, save it to the host, return the path.

    Runs `adb shell screenrecord --time-limit <duration_s>` against a
    device-side temp file, `adb pull`s the result into
    `<ADB_AUTOMATION_LOCAL_ROOT>/recordings/`, and always removes the
    device-side temp file afterward. screenrecord stops itself at the
    duration limit, so this call blocks for roughly `duration_s` seconds.
    Only the primary display is recorded.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        duration_s: How long to record, in seconds. Must be between 1 and
            180 (screenrecord's own maximum); there is no unlimited option.
            Defaults to 10.
        size: Video frame size as "<width>x<height>", e.g. "1280x720". Omit
            to use the display's native resolution. Must match the AVC
            encoder's constraints or screenrecord fails.
        bit_rate_mbps: Target video bit rate in megabits per second (e.g.
            4 or 8). Must be > 0 and <= 100. Omit for screenrecord's
            default (20 Mbps).
        bugreport: Overlay a timestamp and device-info frame, as
            screenrecord's `--bugreport` does — useful when the recording
            documents a bug.
        verbose: Pass screenrecord's `--verbose`, surfacing its progress
            lines in the result's `output` field.
        filename: Bare filename for the saved file (no path separators);
            `.mp4` is appended if missing. Omit for an auto name like
            `recording-<serial>-<UTC timestamp>.mp4`.

    Returns:
        The serial, the absolute local_path the .mp4 was saved to, the
        duration_s / size / bit_rate_mbps / bugreport / verbose used,
        size_bytes (the saved file's size, or None if it couldn't be
        stat'd), and output (screenrecord's stdout — progress lines when
        verbose, otherwise empty).

    Error handling:
        duration_s out of range, a malformed size, or a bit_rate_mbps
        outside (0, 100] is rejected before any device round-trip
        (INVALID_ARGUMENT). No `ADB_AUTOMATION_LOCAL_ROOT` configured, or a
        filename that resolves outside it / contains a path separator,
        raises POLICY_DENIED / INVALID_ARGUMENT. An unknown serial or
        unresponsive adb binary raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE; a
        recording that runs past its expected duration without returning
        raises TIMEOUT. A permission rejection raises PERMISSION_DENIED;
        screenrecord failing to initialize the encoder or write its file,
        or any other failure, raises BACKEND_ERROR. The device-side temp
        file is removed on every path.

    Example:
        Called with serial="emulator-5554", duration_s=5, filename="run1".
        A typical response:

        ```json
        {
          "status": "success",
          "message": "Recorded 5s of emulator-5554 to /srv/adb/recordings/run1.mp4.",
          "data": {
            "serial": "emulator-5554",
            "local_path": "/srv/adb/recordings/run1.mp4",
            "duration_s": 5,
            "size": null,
            "bit_rate_mbps": null,
            "bugreport": false,
            "verbose": false,
            "size_bytes": 481234,
            "success": true,
            "output": ""
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    screen = cast(ScreenService, services["screen"])
    return await screen.record_screen(
        serial,
        duration_s=duration_s,
        size=size,
        bit_rate_mbps=bit_rate_mbps,
        bugreport=bugreport,
        verbose=verbose,
        filename=filename,
    )
