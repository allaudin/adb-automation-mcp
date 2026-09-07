"""Layer 1 unit tests: GraphicsService against FakeBackend directly."""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PackageNotRunningError,
)
from adb_automation_mcp.modules.graphics.service import GraphicsService


class RecordingBackend(FakeBackend):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.command: str | None = None

    async def shell(
        self, serial: str, command: str, timeout_s: float | None = None
    ) -> CommandResult:
        self.command = command
        return await super().shell(serial, command, timeout_s)


def _cr(stdout: str = "", stderr: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(stdout=stdout, stderr=stderr, exit_code=exit_code, duration_ms=20.0)


@pytest.mark.asyncio
async def test_get_frame_stats__command_and_parse() -> None:
    backend = RecordingBackend()

    result = await GraphicsService(backend).get_frame_stats("emulator-5554", "com.example.app")

    assert backend.command == "dumpsys gfxinfo com.example.app framestats"
    assert result.pid == 1224
    assert result.total_frames_rendered == 728
    assert result.janky_frames == 164
    assert result.janky_percent == 22.53
    assert result.janky_frames_legacy == 116
    assert result.p50_ms == 7
    assert result.p99_ms == 400
    assert result.counters["missed_vsync"] == 14
    assert result.counters["high_input_latency"] == 211
    assert result.counters["frame_deadline_missed_legacy"] == 59
    assert result.histogram is None


@pytest.mark.asyncio
async def test_get_frame_stats__include_histogram() -> None:
    result = await GraphicsService(FakeBackend()).get_frame_stats(
        "emulator-5554", "com.example.app", include_histogram=True
    )

    assert result.histogram is not None
    assert result.histogram["5ms"] == 291
    assert result.histogram["16ms"] == 107


@pytest.mark.asyncio
async def test_get_frame_stats__no_rendered_frames() -> None:
    backend = FakeBackend(
        gfxinfo_framestats_result=_cr(
            stdout=(
                "** Graphics info for pid 55 [com.x] **\n"
                "\n"
                "Stats since: 100ns\n"
                "Total frames rendered: 0\n"
            )
        )
    )

    result = await GraphicsService(backend).get_frame_stats("emulator-5554", "com.x")

    assert result.total_frames_rendered == 0
    assert result.p50_ms is None
    assert result.janky_frames is None


@pytest.mark.asyncio
async def test_get_frame_stats__package_not_running() -> None:
    backend = FakeBackend(gfxinfo_framestats_result=_cr(stdout="No process found for: com.x\n"))
    with pytest.raises(PackageNotRunningError):
        await GraphicsService(backend).get_frame_stats("emulator-5554", "com.x")


@pytest.mark.asyncio
async def test_get_frame_stats__blank_package_rejected_before_backend() -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await GraphicsService(Exploding()).get_frame_stats("emulator-5554", "  ")


@pytest.mark.asyncio
async def test_get_frame_stats__malformed_output_does_not_crash() -> None:
    backend = FakeBackend(gfxinfo_framestats_result=_cr(stdout="\x00 not gfxinfo }}}\n"))

    result = await GraphicsService(backend).get_frame_stats("emulator-5554", "com.x")

    assert result.total_frames_rendered is None
    assert result.counters == {}


@pytest.mark.asyncio
async def test_get_frame_stats__unknown_serial() -> None:
    backend = FakeBackend(
        gfxinfo_framestats_result=_cr(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )
    with pytest.raises(DeviceNotFoundError):
        await GraphicsService(backend).get_frame_stats("bogus", "com.x")


@pytest.mark.asyncio
async def test_reset_frame_stats__command_and_confirm() -> None:
    backend = RecordingBackend()

    result = await GraphicsService(backend).reset_frame_stats("emulator-5554", "com.example.app")

    assert backend.command == "dumpsys gfxinfo com.example.app reset"
    assert result.reset is True
    assert result.package == "com.example.app"


@pytest.mark.asyncio
async def test_reset_frame_stats__package_not_running() -> None:
    backend = FakeBackend(gfxinfo_reset_result=_cr(stdout="No process found for: com.x\n"))
    with pytest.raises(PackageNotRunningError):
        await GraphicsService(backend).reset_frame_stats("emulator-5554", "com.x")


@pytest.mark.asyncio
async def test_reset_frame_stats__unclassified_backend_error() -> None:
    backend = FakeBackend(gfxinfo_reset_result=_cr(stderr="broken\n", exit_code=2))
    with pytest.raises(BackendError):
        await GraphicsService(backend).reset_frame_stats("emulator-5554", "com.x")


@pytest.mark.asyncio
async def test_graphics_service__backend_unavailable() -> None:
    with pytest.raises(AdbUnavailableError):
        await GraphicsService(FakeBackend(unavailable=True)).get_frame_stats(
            "emulator-5554", "com.x"
        )
