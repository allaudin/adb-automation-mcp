"""Layer 1 unit tests: ScreenService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adb_automation_mcp.backend.protocol import CommandResult, ExecOutResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbTimeoutError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
    PolicyViolationError,
)
from adb_automation_mcp.modules.screen.service import ScreenService

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_take_screenshot__saves_png_and_returns_path_and_metadata(tmp_path: Path) -> None:
    service = ScreenService(FakeBackend(), local_root=tmp_path)

    result = await service.take_screenshot("emulator-5554")

    assert result.serial == "emulator-5554"
    assert result.display_id is None
    assert result.success is True

    saved = Path(result.local_path)
    assert saved.is_absolute()
    assert saved.parent == tmp_path / "screenshots"  # auto-created
    assert saved.name.startswith("screenshot-emulator-5554-")
    assert saved.suffix == ".png"
    assert saved.read_bytes().startswith(_PNG_SIGNATURE)
    # The FakeBackend fixture is a real 2x2 PNG (77 bytes).
    assert (result.width, result.height) == (2, 2)
    assert result.size_bytes == saved.stat().st_size


@pytest.mark.asyncio
async def test_take_screenshot__no_display_id_sends_bare_screencap(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def exec_out(self, serial: str, command: str) -> ExecOutResult:
            captured["command"] = command
            return await super().exec_out(serial, command)

    await ScreenService(RecordingBackend(), local_root=tmp_path).take_screenshot("emulator-5554")

    assert captured["command"] == "screencap -p"


@pytest.mark.asyncio
async def test_take_screenshot__display_id_sends_dash_d_flag(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def exec_out(self, serial: str, command: str) -> ExecOutResult:
            captured["command"] = command
            return await super().exec_out(serial, command)

    result = await ScreenService(RecordingBackend(), local_root=tmp_path).take_screenshot(
        "emulator-5554", display_id=2
    )

    assert result.display_id == 2
    assert captured["command"] == "screencap -p -d 2"


@pytest.mark.asyncio
async def test_take_screenshot__explicit_filename(tmp_path: Path) -> None:
    service = ScreenService(FakeBackend(), local_root=tmp_path)

    result = await service.take_screenshot("emulator-5554", filename="shot")

    assert result.local_path == str(tmp_path / "screenshots" / "shot.png")
    assert (tmp_path / "screenshots" / "shot.png").read_bytes().startswith(_PNG_SIGNATURE)


@pytest.mark.asyncio
async def test_take_screenshot__filename_keeps_existing_png_suffix(tmp_path: Path) -> None:
    service = ScreenService(FakeBackend(), local_root=tmp_path)

    result = await service.take_screenshot("emulator-5554", filename="run1.png")

    assert result.local_path == str(tmp_path / "screenshots" / "run1.png")


@pytest.mark.asyncio
async def test_take_screenshot__no_local_root_raises_policy_violation() -> None:
    service = ScreenService(FakeBackend())  # no local_root

    with pytest.raises(PolicyViolationError):
        await service.take_screenshot("emulator-5554")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["../escape.png", "a/b.png", "sub\\shot.png", "..", "  "])
async def test_take_screenshot__filename_with_separator_raises_invalid_argument(
    tmp_path: Path, bad: str
) -> None:
    service = ScreenService(FakeBackend(), local_root=tmp_path)

    with pytest.raises(InvalidArgumentError):
        await service.take_screenshot("emulator-5554", filename=bad)
    assert not (tmp_path / "screenshots").exists()


@pytest.mark.asyncio
async def test_take_screenshot__screencap_failure_raises_backend_error(tmp_path: Path) -> None:
    backend = FakeBackend(
        exec_out_result=ExecOutResult(
            stdout=b"", stderr="Error: unable to open display\n", exit_code=1, duration_ms=20.0
        )
    )

    with pytest.raises(BackendError):
        await ScreenService(backend, local_root=tmp_path).take_screenshot("emulator-5554")


@pytest.mark.asyncio
async def test_take_screenshot__unknown_serial_raises_device_not_found(tmp_path: Path) -> None:
    # `adb exec-out` wording (differs from `adb shell`): captured live from
    # a real emulator — "error: device '<serial>' not found", exit 255.
    backend = FakeBackend(
        exec_out_result=ExecOutResult(
            stdout=b"", stderr="error: device 'bogus' not found\n", exit_code=255, duration_ms=10.0
        )
    )

    with pytest.raises(DeviceNotFoundError):
        await ScreenService(backend, local_root=tmp_path).take_screenshot("bogus")


@pytest.mark.asyncio
async def test_take_screenshot__permission_denied_raises_permission_denied(tmp_path: Path) -> None:
    backend = FakeBackend(
        exec_out_result=ExecOutResult(
            stdout=b"", stderr="screencap: Permission denied\n", exit_code=1, duration_ms=10.0
        )
    )

    with pytest.raises(PermissionDeniedError):
        await ScreenService(backend, local_root=tmp_path).take_screenshot("emulator-5554")


@pytest.mark.asyncio
async def test_take_screenshot__screencap_error_on_stdout_with_exit_0_raises_backend_error(
    tmp_path: Path,
) -> None:
    # Captured live: an invalid display_id makes screencap print an error to
    # stdout and still exit 0. The PNG-signature guard must catch this and
    # surface the message, and nothing is written to disk.
    backend = FakeBackend(
        exec_out_result=ExecOutResult(
            stdout=b"Failed to take screenshot. Status: -2\nCapturing failed.\n",
            stderr="",
            exit_code=0,
            duration_ms=10.0,
        )
    )

    with pytest.raises(BackendError, match="Failed to take screenshot"):
        await ScreenService(backend, local_root=tmp_path).take_screenshot("emulator-5554", display_id=999)
    assert not (tmp_path / "screenshots").exists()


# --- record_screen -----------------------------------------------------------


class _RecordingBackend(FakeBackend):
    """Captures every shell command and the pull args; writes real bytes to
    the pull destination so size_bytes is exercised.
    """

    def __init__(self, screenrecord_result: CommandResult | None = None) -> None:
        super().__init__(screenrecord_result=screenrecord_result)
        self.commands: list[str] = []
        self.shell_timeouts: list[float | None] = []
        self.pulled: tuple[str, str, str] | None = None

    async def shell(
        self, serial: str, command: str, timeout_s: float | None = None
    ) -> CommandResult:
        self.commands.append(command)
        self.shell_timeouts.append(timeout_s)
        return await super().shell(serial, command, timeout_s)

    async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
        self.pulled = (serial, remote_path, local_path)
        Path(local_path).write_bytes(b"\x00\x00\x00\x18ftypmp42fake-mp4-body")
        return await super().pull(serial, remote_path, local_path)


@pytest.mark.asyncio
async def test_record_screen__default_command_pull_and_cleanup(tmp_path: Path) -> None:
    backend = _RecordingBackend()

    result = await ScreenService(backend, local_root=tmp_path).record_screen(
        "emulator-5554", duration_s=5, filename="run1"
    )

    record_cmd = backend.commands[0]
    assert record_cmd.startswith("screenrecord --time-limit 5 ")
    assert "--size" not in record_cmd
    assert "--bit-rate" not in record_cmd
    assert "/data/local/tmp/adb_automation_mcp_screenrecord_" in record_cmd
    # shell timeout must exceed the requested duration.
    assert backend.shell_timeouts[0] is not None and backend.shell_timeouts[0] > 5

    saved = tmp_path / "recordings" / "run1.mp4"
    assert result.local_path == str(saved)
    assert result.duration_s == 5
    assert result.success is True
    assert result.size_bytes == saved.stat().st_size
    assert saved.exists()

    # temp file removed on the way out
    assert backend.commands[-1].startswith("rm -f /data/local/tmp/adb_automation_mcp_screenrecord_")


@pytest.mark.asyncio
async def test_record_screen__maps_size_bitrate_bugreport_verbose(tmp_path: Path) -> None:
    backend = _RecordingBackend()

    await ScreenService(backend, local_root=tmp_path).record_screen(
        "emulator-5554",
        duration_s=3,
        size="1280x720",
        bit_rate_mbps=4,
        bugreport=True,
        verbose=True,
    )

    cmd = backend.commands[0]
    assert "--size 1280x720" in cmd
    assert "--bit-rate 4000000" in cmd
    assert "--bugreport" in cmd
    assert "--verbose" in cmd


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_duration", [0, -1, 181, 600])
async def test_record_screen__duration_out_of_range_rejected(tmp_path: Path, bad_duration: int) -> None:
    backend = _RecordingBackend()

    with pytest.raises(InvalidArgumentError):
        await ScreenService(backend, local_root=tmp_path).record_screen(
            "emulator-5554", duration_s=bad_duration
        )
    assert backend.commands == []


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_size", ["1280", "1280*720", "widexhigh", "x720"])
async def test_record_screen__malformed_size_rejected(tmp_path: Path, bad_size: str) -> None:
    backend = _RecordingBackend()

    with pytest.raises(InvalidArgumentError):
        await ScreenService(backend, local_root=tmp_path).record_screen(
            "emulator-5554", duration_s=5, size=bad_size
        )
    assert backend.commands == []


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_rate", [0, -2, 250])
async def test_record_screen__bad_bit_rate_rejected(tmp_path: Path, bad_rate: float) -> None:
    backend = _RecordingBackend()

    with pytest.raises(InvalidArgumentError):
        await ScreenService(backend, local_root=tmp_path).record_screen(
            "emulator-5554", duration_s=5, bit_rate_mbps=bad_rate
        )
    assert backend.commands == []


@pytest.mark.asyncio
async def test_record_screen__no_local_root_raises_policy_violation() -> None:
    with pytest.raises(PolicyViolationError):
        await ScreenService(FakeBackend()).record_screen("emulator-5554", duration_s=5)


@pytest.mark.asyncio
async def test_record_screen__filename_with_separator_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidArgumentError):
        await ScreenService(FakeBackend(), local_root=tmp_path).record_screen(
            "emulator-5554", duration_s=5, filename="../escape.mp4"
        )


@pytest.mark.asyncio
async def test_record_screen__screenrecord_failure_raises_backend_error_and_cleans_up(
    tmp_path: Path,
) -> None:
    backend = _RecordingBackend(
        screenrecord_result=CommandResult(
            stdout="",
            stderr="Unable to get IGraphicBufferProducer\n",
            exit_code=1,
            duration_ms=20.0,
        )
    )

    with pytest.raises(BackendError):
        await ScreenService(backend, local_root=tmp_path).record_screen("emulator-5554", duration_s=5)

    assert backend.pulled is None  # never tried to pull a file that wasn't made
    assert backend.commands[-1].startswith("rm -f /data/local/tmp/adb_automation_mcp_screenrecord_")


@pytest.mark.asyncio
async def test_record_screen__unknown_serial_raises_device_not_found(tmp_path: Path) -> None:
    backend = _RecordingBackend(
        screenrecord_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )

    with pytest.raises(DeviceNotFoundError):
        await ScreenService(backend, local_root=tmp_path).record_screen("bogus", duration_s=5)


@pytest.mark.asyncio
async def test_record_screen__timeout_propagates_as_adb_timeout(tmp_path: Path) -> None:
    class TimingOutBackend(_RecordingBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            self.commands.append(command)
            if command.startswith("screenrecord "):
                raise AdbTimeoutError("adb command timed out.", details={"command": command})
            return await FakeBackend.shell(self, serial, command, timeout_s)

    backend = TimingOutBackend()

    with pytest.raises(AdbTimeoutError):
        await ScreenService(backend, local_root=tmp_path).record_screen("emulator-5554", duration_s=5)

    # cleanup still runs
    assert backend.commands[-1].startswith("rm -f /data/local/tmp/adb_automation_mcp_screenrecord_")
