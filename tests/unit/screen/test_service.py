"""Layer 1 unit tests: ScreenService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    PolicyViolationError,
    RemoteFileNotFoundError,
)
from adb_automation_mcp.modules.screen.service import ScreenService

_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    + struct.pack(">I", 13)
    + b"IHDR"
    + struct.pack(">II", 1080, 2400)
    + b"\x08\x06\x00\x00\x00"  # bit depth, color type, compression, filter, interlace
    + b"\x00\x00\x00\x00"  # fake CRC, not validated by our reader
)


class _WritingBackend(FakeBackend):
    """Simulates a real backend's pull() actually writing bytes to
    local_path — plain FakeBackend doesn't touch the filesystem, but
    take_screenshot's width/height/size_bytes metadata can only be
    exercised against a real file on disk.
    """

    async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
        result = await super().pull(serial, remote_path, local_path)
        if result.exit_code == 0:
            Path(local_path).write_bytes(_MINIMAL_PNG)
        return result


@pytest.mark.asyncio
async def test_take_screenshot__success_reports_local_path(tmp_path: Path) -> None:
    service = ScreenService(FakeBackend(), local_root=tmp_path)

    result = await service.take_screenshot("emulator-5554", "screen.png")

    assert result.serial == "emulator-5554"
    assert result.local_path == str(tmp_path / "screen.png")
    assert result.display_id is None
    assert result.success is True


@pytest.mark.asyncio
async def test_take_screenshot__reads_width_height_size_from_pulled_png(tmp_path: Path) -> None:
    service = ScreenService(_WritingBackend(), local_root=tmp_path)

    result = await service.take_screenshot("emulator-5554", "screen.png")

    assert result.width == 1080
    assert result.height == 2400
    assert result.size_bytes == len(_MINIMAL_PNG)


@pytest.mark.asyncio
async def test_take_screenshot__metadata_is_none_when_file_was_not_actually_written(tmp_path: Path) -> None:
    # Plain FakeBackend doesn't write real bytes — metadata must degrade to
    # None rather than fabricate values, since it's genuinely undeterminable.
    service = ScreenService(FakeBackend(), local_root=tmp_path)

    result = await service.take_screenshot("emulator-5554", "screen.png")

    assert result.width is None
    assert result.height is None
    assert result.size_bytes is None


@pytest.mark.asyncio
async def test_take_screenshot__sends_screencap_and_pull_with_matching_temp_path(tmp_path: Path) -> None:
    captured: list[tuple[str, ...]] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured.append(("shell", command))
            return await super().shell(serial, command)

        async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
            captured.append(("pull", remote_path, local_path))
            return await super().pull(serial, remote_path, local_path)

    service = ScreenService(RecordingBackend(), local_root=tmp_path)

    await service.take_screenshot("emulator-5554", "screen.png")

    screencap_calls = [c for c in captured if c[0] == "shell" and c[1].startswith("screencap -p ")]
    pull_calls = [c for c in captured if c[0] == "pull"]
    assert len(screencap_calls) == 1
    assert len(pull_calls) == 1
    remote_tmp_path = screencap_calls[0][1].removeprefix("screencap -p ")
    assert pull_calls[0][1] == remote_tmp_path
    assert remote_tmp_path.startswith("/data/local/tmp/adb_automation_mcp_screenshot_")
    assert pull_calls[0][2] == str(tmp_path / "screen.png")


@pytest.mark.asyncio
async def test_take_screenshot__display_id_sends_dash_d_flag(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            if command.startswith("screencap -p "):
                captured["command"] = command
            return await super().shell(serial, command)

    service = ScreenService(RecordingBackend(), local_root=tmp_path)

    result = await service.take_screenshot("emulator-5554", "screen.png", display_id=2)

    assert result.display_id == 2
    assert " -d 2 " in captured["command"]


@pytest.mark.asyncio
async def test_take_screenshot__no_local_root_configured_raises_policy_violation() -> None:
    service = ScreenService(FakeBackend())  # local_root omitted

    with pytest.raises(PolicyViolationError):
        await service.take_screenshot("emulator-5554", "screen.png")


@pytest.mark.asyncio
async def test_take_screenshot__path_escaping_local_root_raises_policy_violation(tmp_path: Path) -> None:
    service = ScreenService(FakeBackend(), local_root=tmp_path)

    with pytest.raises(PolicyViolationError):
        await service.take_screenshot("emulator-5554", "../outside.png")


@pytest.mark.asyncio
async def test_take_screenshot__screencap_failure_raises_backend_error_and_skips_pull(tmp_path: Path) -> None:
    pull_calls: list[str] = []

    class RecordingBackend(FakeBackend):
        async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
            pull_calls.append(remote_path)
            return await super().pull(serial, remote_path, local_path)

    backend = RecordingBackend(
        screencap_result=CommandResult(
            stdout="", stderr="Error: unable to open display\n", exit_code=1, duration_ms=20.0
        )
    )
    service = ScreenService(backend, local_root=tmp_path)

    with pytest.raises(BackendError):
        await service.take_screenshot("emulator-5554", "screen.png")

    assert pull_calls == []


@pytest.mark.asyncio
async def test_take_screenshot__screencap_unknown_serial_raises_device_not_found(tmp_path: Path) -> None:
    backend = FakeBackend(
        screencap_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = ScreenService(backend, local_root=tmp_path)

    with pytest.raises(DeviceNotFoundError):
        await service.take_screenshot("bogus", "screen.png")


@pytest.mark.asyncio
async def test_take_screenshot__pull_failure_raises_remote_file_not_found(tmp_path: Path) -> None:
    backend = FakeBackend(
        pull_result=CommandResult(
            stdout="",
            stderr="adb: error: remote object '/data/local/tmp/adb_automation_mcp_screenshot_x.png' does not exist\n",
            exit_code=1,
            duration_ms=15.0,
        )
    )
    service = ScreenService(backend, local_root=tmp_path)

    with pytest.raises(RemoteFileNotFoundError):
        await service.take_screenshot("emulator-5554", "screen.png")


@pytest.mark.asyncio
async def test_take_screenshot__cleanup_runs_after_successful_capture(tmp_path: Path) -> None:
    shell_commands: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            shell_commands.append(command)
            return await super().shell(serial, command)

    service = ScreenService(RecordingBackend(), local_root=tmp_path)

    await service.take_screenshot("emulator-5554", "screen.png")

    rm_commands = [c for c in shell_commands if c.startswith("rm -f /data/local/tmp/adb_automation_mcp_screenshot_")]
    assert len(rm_commands) == 1


@pytest.mark.asyncio
async def test_take_screenshot__cleanup_runs_even_when_pull_fails(tmp_path: Path) -> None:
    shell_commands: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            shell_commands.append(command)
            return await super().shell(serial, command)

    backend = RecordingBackend(
        pull_result=CommandResult(
            stdout="", stderr="adb: error: remote object 'x' does not exist\n", exit_code=1, duration_ms=15.0
        )
    )
    service = ScreenService(backend, local_root=tmp_path)

    with pytest.raises(RemoteFileNotFoundError):
        await service.take_screenshot("emulator-5554", "screen.png")

    rm_commands = [c for c in shell_commands if c.startswith("rm -f /data/local/tmp/adb_automation_mcp_screenshot_")]
    assert len(rm_commands) == 1


@pytest.mark.asyncio
async def test_take_screenshot__cleanup_runs_even_when_screencap_fails(tmp_path: Path) -> None:
    shell_commands: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            shell_commands.append(command)
            return await super().shell(serial, command)

    backend = RecordingBackend(
        screencap_result=CommandResult(stdout="", stderr="Error: boom\n", exit_code=1, duration_ms=20.0)
    )
    service = ScreenService(backend, local_root=tmp_path)

    with pytest.raises(BackendError):
        await service.take_screenshot("emulator-5554", "screen.png")

    rm_commands = [c for c in shell_commands if c.startswith("rm -f /data/local/tmp/adb_automation_mcp_screenshot_")]
    assert len(rm_commands) == 1


@pytest.mark.asyncio
async def test_take_screenshot__cleanup_failure_does_not_mask_original_success(tmp_path: Path) -> None:
    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            if command.startswith("rm -f "):
                raise RuntimeError("simulated cleanup transport error")
            return await super().shell(serial, command)

    service = ScreenService(RecordingBackend(), local_root=tmp_path)

    result = await service.take_screenshot("emulator-5554", "screen.png")

    assert result.success is True
