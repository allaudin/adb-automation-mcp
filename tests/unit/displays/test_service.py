"""Layer 1 unit tests: DisplaysService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    DisplayInfoUnavailableError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.displays.service import DisplaysService


def test_service_constructs_with_backend() -> None:
    assert DisplaysService(FakeBackend()) is not None


@pytest.mark.asyncio
async def test_list_displays__sends_dumpsys_display() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command, timeout_s)

    await DisplaysService(RecordingBackend()).list_displays("emulator-5554")

    assert captured["command"] == "dumpsys display"


@pytest.mark.asyncio
async def test_list_displays__parses_default_fixture_two_displays() -> None:
    result = await DisplaysService(FakeBackend()).list_displays("emulator-5554")

    assert result.serial == "emulator-5554"
    assert [d.display_id for d in result.displays] == [0, 2]

    primary = result.displays[0]
    assert primary.state == "ON"
    assert primary.type == "INTERNAL"
    assert (primary.width, primary.height) == (1408, 792)
    assert primary.density_dpi == 160
    assert primary.rotation == 0
    assert primary.unique_id == "local:4619827259835644672"

    secondary = result.displays[1]
    assert secondary.state == "OFF"
    assert secondary.type == "EXTERNAL"
    assert (secondary.width, secondary.height) == (1920, 1080)
    assert secondary.density_dpi == 213


@pytest.mark.asyncio
async def test_list_displays__single_internal_display() -> None:
    backend = FakeBackend(
        dumpsys_display_result=CommandResult(
            stdout=(
                "DISPLAY MANAGER (dumpsys display)\n"
                "  mViewports=[DisplayViewport{type=INTERNAL, valid=true, isActive=true, "
                "displayId=0, uniqueId='local:123', orientation=1, densityDpi=320, "
                "deviceWidth=1080, deviceHeight=2400}]\n"
                "Display States: size=1\n"
                "  Display Id=0\n"
                "  Display State=ON\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=120.0,
        )
    )

    result = await DisplaysService(backend).list_displays("emulator-5554")

    assert len(result.displays) == 1
    only = result.displays[0]
    assert only.display_id == 0
    assert only.rotation == 1
    assert only.density_dpi == 320
    assert (only.width, only.height) == (1080, 2400)


@pytest.mark.asyncio
async def test_list_displays__powered_off_display_has_no_viewport_fields() -> None:
    # A display present in "Display States:" but absent from mViewports (it's
    # off) still appears as a row, with dimension/density fields None.
    backend = FakeBackend(
        dumpsys_display_result=CommandResult(
            stdout=(
                "DISPLAY MANAGER (dumpsys display)\n"
                "  mViewports=[DisplayViewport{type=INTERNAL, valid=true, isActive=true, "
                "displayId=0, uniqueId='local:1', orientation=0, densityDpi=160, "
                "deviceWidth=1408, deviceHeight=792}]\n"
                "Display States: size=2\n"
                "  Display Id=0\n"
                "  Display State=ON\n"
                "  Display Id=4\n"
                "  Display State=OFF\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=120.0,
        )
    )

    result = await DisplaysService(backend).list_displays("emulator-5554")

    assert [d.display_id for d in result.displays] == [0, 4]
    off = result.displays[1]
    assert off.state == "OFF"
    assert off.type is None
    assert off.width is None
    assert off.density_dpi is None


@pytest.mark.asyncio
async def test_list_displays__unparseable_output_raises_display_info_unavailable() -> None:
    backend = FakeBackend(
        dumpsys_display_result=CommandResult(
            stdout="DISPLAY MANAGER (dumpsys display)\n  mSafeMode=false\n",
            stderr="",
            exit_code=0,
            duration_ms=30.0,
        )
    )

    with pytest.raises(DisplayInfoUnavailableError):
        await DisplaysService(backend).list_displays("emulator-5554")


@pytest.mark.asyncio
async def test_list_displays__garbage_output_does_not_crash_parser() -> None:
    backend = FakeBackend(
        dumpsys_display_result=CommandResult(
            stdout="\x00 not remotely dumpsys output ]]]}}} mViewports=[oops",
            stderr="",
            exit_code=0,
            duration_ms=30.0,
        )
    )

    with pytest.raises(DisplayInfoUnavailableError):
        await DisplaysService(backend).list_displays("emulator-5554")


@pytest.mark.asyncio
async def test_list_displays__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        dumpsys_display_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )

    with pytest.raises(DeviceNotFoundError):
        await DisplaysService(backend).list_displays("bogus")


@pytest.mark.asyncio
async def test_list_displays__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        dumpsys_display_result=CommandResult(
            stdout="", stderr="Permission Denial: can't dump display\n", exit_code=1, duration_ms=5.0
        )
    )

    with pytest.raises(PermissionDeniedError):
        await DisplaysService(backend).list_displays("emulator-5554")


@pytest.mark.asyncio
async def test_list_displays__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        dumpsys_display_result=CommandResult(
            stdout="", stderr="something unexpected\n", exit_code=2, duration_ms=5.0
        )
    )

    with pytest.raises(BackendError):
        await DisplaysService(backend).list_displays("emulator-5554")


@pytest.mark.asyncio
async def test_list_displays__backend_unavailable_raises_adb_unavailable() -> None:
    with pytest.raises(AdbUnavailableError):
        await DisplaysService(FakeBackend(unavailable=True)).list_displays("emulator-5554")
