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
    InvalidArgumentError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.displays.service import DisplaysService


def _size(stdout: str) -> FakeBackend:
    return FakeBackend(
        wm_size_result=CommandResult(stdout=stdout, stderr="", exit_code=0, duration_ms=30.0)
    )


def _density(stdout: str) -> FakeBackend:
    return FakeBackend(
        wm_density_result=CommandResult(stdout=stdout, stderr="", exit_code=0, duration_ms=30.0)
    )


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


# --- get_display_size -------------------------------------------------------


@pytest.mark.asyncio
async def test_get_display_size__default_display_sends_wm_size_and_parses_physical() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command, timeout_s)

    result = await DisplaysService(RecordingBackend()).get_display_size("emulator-5554")

    assert captured["command"] == "wm size"
    assert result.serial == "emulator-5554"
    assert result.display_id is None
    assert (result.physical_width, result.physical_height) == (1408, 792)
    assert result.override_width is None and result.override_height is None
    assert (result.effective_width, result.effective_height) == (1408, 792)


@pytest.mark.asyncio
async def test_get_display_size__display_id_maps_to_dash_d_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command, timeout_s)

    result = await DisplaysService(RecordingBackend()).get_display_size("emulator-5554", 2)

    assert captured["command"] == "wm size -d 2"
    assert result.display_id == 2


@pytest.mark.asyncio
async def test_get_display_size__override_line_is_parsed_and_wins_effective() -> None:
    result = await DisplaysService(
        _size("Physical size: 1408x792\nOverride size: 1080x720\n")
    ).get_display_size("emulator-5554")

    assert (result.physical_width, result.physical_height) == (1408, 792)
    assert (result.override_width, result.override_height) == (1080, 720)
    assert (result.effective_width, result.effective_height) == (1080, 720)


@pytest.mark.asyncio
async def test_get_display_size__negative_display_id_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await DisplaysService(ExplodingBackend()).get_display_size("emulator-5554", -1)


@pytest.mark.asyncio
async def test_get_display_size__nonexistent_display_reports_zero_raises_unavailable() -> None:
    with pytest.raises(DisplayInfoUnavailableError):
        await DisplaysService(_size("Physical size: 0x0\n")).get_display_size("emulator-5554", 99)


@pytest.mark.asyncio
async def test_get_display_size__unrecognized_output_raises_unavailable() -> None:
    with pytest.raises(DisplayInfoUnavailableError):
        await DisplaysService(_size("wm: command not understood\n")).get_display_size(
            "emulator-5554"
        )


@pytest.mark.asyncio
async def test_get_display_size__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        wm_size_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    with pytest.raises(DeviceNotFoundError):
        await DisplaysService(backend).get_display_size("bogus")


@pytest.mark.asyncio
async def test_get_display_size__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        wm_size_result=CommandResult(
            stdout="", stderr="something unexpected\n", exit_code=2, duration_ms=5.0
        )
    )
    with pytest.raises(BackendError):
        await DisplaysService(backend).get_display_size("emulator-5554")


# --- get_display_density --------------------------------------------------


@pytest.mark.asyncio
async def test_get_display_density__default_display_sends_wm_density_and_parses() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command, timeout_s)

    result = await DisplaysService(RecordingBackend()).get_display_density("emulator-5554")

    assert captured["command"] == "wm density"
    assert result.physical_density == 160
    assert result.override_density is None
    assert result.effective_density == 160


@pytest.mark.asyncio
async def test_get_display_density__display_id_maps_to_dash_d_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command, timeout_s)

    await DisplaysService(RecordingBackend()).get_display_density("emulator-5554", 0)

    assert captured["command"] == "wm density -d 0"


@pytest.mark.asyncio
async def test_get_display_density__override_line_parsed_and_wins_effective() -> None:
    result = await DisplaysService(
        _density("Physical density: 160\nOverride density: 240\n")
    ).get_display_density("emulator-5554")

    assert result.physical_density == 160
    assert result.override_density == 240
    assert result.effective_density == 240


@pytest.mark.asyncio
async def test_get_display_density__negative_display_id_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await DisplaysService(ExplodingBackend()).get_display_density("emulator-5554", -5)


@pytest.mark.asyncio
async def test_get_display_density__nonexistent_display_reports_minus_one_raises_unavailable() -> (
    None
):
    with pytest.raises(DisplayInfoUnavailableError):
        await DisplaysService(_density("Physical density: -1\n")).get_display_density(
            "emulator-5554", 99
        )


@pytest.mark.asyncio
async def test_get_display_density__unrecognized_output_raises_unavailable() -> None:
    with pytest.raises(DisplayInfoUnavailableError):
        await DisplaysService(_density("nothing useful here\n")).get_display_density("emulator-5554")


@pytest.mark.asyncio
async def test_get_display_density__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        wm_density_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    with pytest.raises(DeviceNotFoundError):
        await DisplaysService(backend).get_display_density("bogus")
