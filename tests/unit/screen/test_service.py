"""Layer 1 unit tests: ScreenService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adb_automation_mcp.backend.protocol import ExecOutResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
    PolicyViolationError,
)
from adb_automation_mcp.modules.screen.service import ScreenService

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@pytest.mark.asyncio
async def test_take_screenshot__returns_png_bytes_and_metadata() -> None:
    service = ScreenService(FakeBackend())

    result = await service.take_screenshot("emulator-5554", display_id=None)

    assert result.serial == "emulator-5554"
    assert result.display_id is None
    assert result.mime_type == "image/png"
    assert result.success is True
    assert result.image_bytes.startswith(_PNG_SIGNATURE)
    # The FakeBackend fixture is a real 2x2 PNG (77 bytes).
    assert (result.width, result.height) == (2, 2)
    assert result.size_bytes == len(result.image_bytes)


@pytest.mark.asyncio
async def test_take_screenshot__no_display_id_sends_bare_screencap() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def exec_out(self, serial: str, command: str) -> ExecOutResult:
            captured["command"] = command
            return await super().exec_out(serial, command)

    await ScreenService(RecordingBackend()).take_screenshot("emulator-5554")

    assert captured["command"] == "screencap -p"


@pytest.mark.asyncio
async def test_take_screenshot__display_id_sends_dash_d_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def exec_out(self, serial: str, command: str) -> ExecOutResult:
            captured["command"] = command
            return await super().exec_out(serial, command)

    result = await ScreenService(RecordingBackend()).take_screenshot("emulator-5554", display_id=2)

    assert result.display_id == 2
    assert captured["command"] == "screencap -p -d 2"


@pytest.mark.asyncio
async def test_take_screenshot__screencap_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        exec_out_result=ExecOutResult(
            stdout=b"", stderr="Error: unable to open display\n", exit_code=1, duration_ms=20.0
        )
    )

    with pytest.raises(BackendError):
        await ScreenService(backend).take_screenshot("emulator-5554")


@pytest.mark.asyncio
async def test_take_screenshot__unknown_serial_raises_device_not_found() -> None:
    # `adb exec-out` wording (differs from `adb shell`): captured live from
    # a real emulator — "error: device '<serial>' not found", exit 255.
    backend = FakeBackend(
        exec_out_result=ExecOutResult(
            stdout=b"", stderr="error: device 'bogus' not found\n", exit_code=255, duration_ms=10.0
        )
    )

    with pytest.raises(DeviceNotFoundError):
        await ScreenService(backend).take_screenshot("bogus")


@pytest.mark.asyncio
async def test_take_screenshot__permission_denied_raises_permission_denied() -> None:
    backend = FakeBackend(
        exec_out_result=ExecOutResult(
            stdout=b"", stderr="screencap: Permission denied\n", exit_code=1, duration_ms=10.0
        )
    )

    with pytest.raises(PermissionDeniedError):
        await ScreenService(backend).take_screenshot("emulator-5554")


@pytest.mark.asyncio
async def test_take_screenshot__screencap_error_on_stdout_with_exit_0_raises_backend_error() -> None:
    # Captured live: an invalid display_id makes screencap print an error to
    # stdout and still exit 0. The PNG-signature guard must catch this and
    # surface the message.
    backend = FakeBackend(
        exec_out_result=ExecOutResult(
            stdout=b"Failed to take screenshot. Status: -2\nCapturing failed.\n",
            stderr="",
            exit_code=0,
            duration_ms=10.0,
        )
    )

    with pytest.raises(BackendError, match="Failed to take screenshot"):
        await ScreenService(backend).take_screenshot("emulator-5554", display_id=999)


# --- save= ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_take_screenshot__save_false_writes_nothing(tmp_path: Path) -> None:
    service = ScreenService(FakeBackend(), local_root=tmp_path)

    result = await service.take_screenshot("emulator-5554")

    assert result.local_path is None
    assert result.image_bytes.startswith(_PNG_SIGNATURE)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_take_screenshot__save_writes_png_under_screenshots_dir(tmp_path: Path) -> None:
    service = ScreenService(FakeBackend(), local_root=tmp_path)

    result = await service.take_screenshot("emulator-5554", save=True)

    assert result.local_path is not None
    saved = Path(result.local_path)
    assert saved.parent == tmp_path / "screenshots"  # auto-created
    assert saved.name.startswith("screenshot-emulator-5554-")
    assert saved.suffix == ".png"
    assert saved.read_bytes() == result.image_bytes
    assert saved.read_bytes().startswith(_PNG_SIGNATURE)


@pytest.mark.asyncio
async def test_take_screenshot__save_with_explicit_filename(tmp_path: Path) -> None:
    service = ScreenService(FakeBackend(), local_root=tmp_path)

    result = await service.take_screenshot("emulator-5554", save=True, filename="shot")

    assert result.local_path == str(tmp_path / "screenshots" / "shot.png")
    assert (tmp_path / "screenshots" / "shot.png").read_bytes().startswith(_PNG_SIGNATURE)


@pytest.mark.asyncio
async def test_take_screenshot__save_filename_keeps_existing_png_suffix(tmp_path: Path) -> None:
    service = ScreenService(FakeBackend(), local_root=tmp_path)

    result = await service.take_screenshot("emulator-5554", save=True, filename="run1.png")

    assert result.local_path == str(tmp_path / "screenshots" / "run1.png")


@pytest.mark.asyncio
async def test_take_screenshot__save_without_local_root_raises_policy_violation() -> None:
    service = ScreenService(FakeBackend())  # no local_root

    with pytest.raises(PolicyViolationError):
        await service.take_screenshot("emulator-5554", save=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["../escape.png", "a/b.png", "sub\\shot.png", "..", "  "])
async def test_take_screenshot__save_filename_with_separator_raises_invalid_argument(
    tmp_path: Path, bad: str
) -> None:
    service = ScreenService(FakeBackend(), local_root=tmp_path)

    with pytest.raises(InvalidArgumentError):
        await service.take_screenshot("emulator-5554", save=True, filename=bad)
    assert not (tmp_path / "screenshots").exists()
