"""Layer 1 unit tests: FilesService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    PermissionDeniedError,
    PolicyViolationError,
    RemoteFileNotFoundError,
)
from adb_automation_mcp.modules.files.service import FilesService


@pytest.mark.asyncio
async def test_pull_file__success_reports_source_destination_and_success(tmp_path: Path) -> None:
    service = FilesService(FakeBackend(), local_root=tmp_path)

    result = await service.pull_file("emulator-5554", "/sdcard/test.txt", "test.txt")

    assert result.serial == "emulator-5554"
    assert result.remote_path == "/sdcard/test.txt"
    assert result.local_path == str(tmp_path / "test.txt")
    assert result.success is True


@pytest.mark.asyncio
async def test_pull_file__passes_resolved_local_path_to_backend(tmp_path: Path) -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
            captured["serial"] = serial
            captured["remote_path"] = remote_path
            captured["local_path"] = local_path
            return await super().pull(serial, remote_path, local_path)

    service = FilesService(RecordingBackend(), local_root=tmp_path)

    await service.pull_file("emulator-5554", "/sdcard/test.txt", "test.txt")

    assert captured["serial"] == "emulator-5554"
    assert captured["remote_path"] == "/sdcard/test.txt"
    assert captured["local_path"] == str(tmp_path / "test.txt")


@pytest.mark.asyncio
async def test_pull_file__no_local_root_configured_raises_policy_violation() -> None:
    service = FilesService(FakeBackend())  # local_root omitted

    with pytest.raises(PolicyViolationError):
        await service.pull_file("emulator-5554", "/sdcard/test.txt", "test.txt")


@pytest.mark.asyncio
async def test_pull_file__path_escaping_local_root_raises_policy_violation(tmp_path: Path) -> None:
    service = FilesService(FakeBackend(), local_root=tmp_path)

    with pytest.raises(PolicyViolationError):
        await service.pull_file("emulator-5554", "/sdcard/test.txt", "../outside.txt")


@pytest.mark.asyncio
async def test_pull_file__absolute_local_path_outside_local_root_raises_policy_violation(
    tmp_path: Path,
) -> None:
    service = FilesService(FakeBackend(), local_root=tmp_path)

    with pytest.raises(PolicyViolationError):
        await service.pull_file("emulator-5554", "/sdcard/test.txt", "/etc/passwd")


@pytest.mark.asyncio
async def test_pull_file__source_missing_raises_remote_file_not_found(tmp_path: Path) -> None:
    backend = FakeBackend(
        pull_result=CommandResult(
            stdout="",
            stderr="adb: error: remote object '/sdcard/missing.txt' does not exist\n",
            exit_code=1,
            duration_ms=15.0,
        )
    )
    service = FilesService(backend, local_root=tmp_path)

    with pytest.raises(RemoteFileNotFoundError):
        await service.pull_file("emulator-5554", "/sdcard/missing.txt", "test.txt")


@pytest.mark.asyncio
async def test_pull_file__permission_denied_raises_permission_denied(tmp_path: Path) -> None:
    backend = FakeBackend(
        pull_result=CommandResult(
            stdout="",
            stderr=(
                "adb: error: failed to stat remote object "
                "'/data/data/com.other.app/files/secret.txt': Permission denied\n"
            ),
            exit_code=1,
            duration_ms=15.0,
        )
    )
    service = FilesService(backend, local_root=tmp_path)

    with pytest.raises(PermissionDeniedError):
        await service.pull_file(
            "emulator-5554", "/data/data/com.other.app/files/secret.txt", "secret.txt"
        )


@pytest.mark.asyncio
async def test_pull_file__unknown_serial_raises_device_not_found(tmp_path: Path) -> None:
    backend = FakeBackend(
        pull_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = FilesService(backend, local_root=tmp_path)

    with pytest.raises(DeviceNotFoundError):
        await service.pull_file("bogus", "/sdcard/test.txt", "test.txt")


@pytest.mark.asyncio
async def test_pull_file__unclassified_failure_raises_backend_error(tmp_path: Path) -> None:
    backend = FakeBackend(
        pull_result=CommandResult(
            stdout="", stderr="adb: error: failed to copy; I/O error\n", exit_code=1, duration_ms=25.0
        )
    )
    service = FilesService(backend, local_root=tmp_path)

    with pytest.raises(BackendError):
        await service.pull_file("emulator-5554", "/sdcard/test.txt", "test.txt")


# --- push_file -------------------------------------------------------------


from adb_automation_mcp.errors import InvalidArgumentError
from adb_automation_mcp.modules.files.service import PushFileResult


class _PushRec(FakeBackend):
    def __init__(self, **kw: object) -> None:
        super().__init__(**kw)  # type: ignore[arg-type]
        self.call: tuple[str, str, str] | None = None

    async def push(self, serial: str, local_path: str, remote_path: str) -> CommandResult:
        self.call = (serial, local_path, remote_path)
        return await super().push(serial, local_path, remote_path)


@pytest.mark.asyncio
async def test_push_file__resolves_local_within_root_and_pushes(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("hi")
    backend = _PushRec()
    service = FilesService(backend, local_root=tmp_path)

    result = await service.push_file("emulator-5554", "f.txt", "/data/local/tmp/f.txt")

    assert backend.call == ("emulator-5554", str(tmp_path / "f.txt"), "/data/local/tmp/f.txt")
    assert isinstance(result, PushFileResult)
    assert result.remote_path == "/data/local/tmp/f.txt"
    assert result.success is True


@pytest.mark.asyncio
async def test_push_file__missing_local_file_rejected_before_backend(tmp_path: Path) -> None:
    backend = _PushRec()
    service = FilesService(backend, local_root=tmp_path)

    with pytest.raises(InvalidArgumentError):
        await service.push_file("emulator-5554", "nope.txt", "/data/local/tmp/x")

    assert backend.call is None


@pytest.mark.asyncio
async def test_push_file__no_local_root_raises_policy_violation(tmp_path: Path) -> None:
    service = FilesService(FakeBackend())
    with pytest.raises(PolicyViolationError):
        await service.push_file("emulator-5554", "f.txt", "/data/local/tmp/x")


@pytest.mark.asyncio
async def test_push_file__path_escaping_local_root_raises_policy_violation(tmp_path: Path) -> None:
    service = FilesService(FakeBackend(), local_root=tmp_path)
    with pytest.raises(PolicyViolationError):
        await service.push_file("emulator-5554", "../etc/passwd", "/data/local/tmp/x")


@pytest.mark.asyncio
async def test_push_file__unknown_serial_raises_device_not_found(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("hi")
    backend = FakeBackend(
        push_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    service = FilesService(backend, local_root=tmp_path)
    with pytest.raises(DeviceNotFoundError):
        await service.push_file("bogus", "f.txt", "/data/local/tmp/f.txt")


@pytest.mark.asyncio
async def test_push_file__read_only_remote_raises_permission_denied(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("hi")
    backend = FakeBackend(
        push_result=CommandResult(
            stdout="",
            stderr=(
                "adb: error: failed to copy '...' to '/system/x': "
                "remote couldn't create file: Read-only file system\n"
            ),
            exit_code=1,
            duration_ms=5.0,
        )
    )
    service = FilesService(backend, local_root=tmp_path)
    with pytest.raises(PermissionDeniedError):
        await service.push_file("emulator-5554", "f.txt", "/system/x")


@pytest.mark.asyncio
async def test_push_file__missing_remote_dir_raises_remote_file_not_found(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("hi")
    backend = FakeBackend(
        push_result=CommandResult(
            stdout="",
            stderr="adb: error: failed to copy '...' to '/nope/x': remote No such file or directory\n",
            exit_code=1,
            duration_ms=5.0,
        )
    )
    service = FilesService(backend, local_root=tmp_path)
    with pytest.raises(RemoteFileNotFoundError):
        await service.push_file("emulator-5554", "f.txt", "/nope/x")


@pytest.mark.asyncio
async def test_push_file__other_failure_raises_backend_error(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("hi")
    backend = FakeBackend(
        push_result=CommandResult(
            stdout="", stderr="adb: error: something odd\n", exit_code=1, duration_ms=5.0
        )
    )
    service = FilesService(backend, local_root=tmp_path)
    with pytest.raises(BackendError):
        await service.push_file("emulator-5554", "f.txt", "/data/local/tmp/x")


def test_push_file_result_summary(tmp_path: Path) -> None:
    s = PushFileResult(
        serial="emulator-5554",
        local_path="/root/f.txt",
        remote_path="/data/local/tmp/f.txt",
        success=True,
        output="",
    ).summary()
    assert "Pushed /root/f.txt to /data/local/tmp/f.txt" in s
