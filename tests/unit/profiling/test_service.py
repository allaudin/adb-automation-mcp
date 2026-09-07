"""Layer 1 unit tests: ProfilingService against FakeBackend directly."""

from __future__ import annotations

from pathlib import Path

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
    PolicyViolationError,
    RemoteFileNotFoundError,
)
from adb_automation_mcp.modules.profiling.service import ProfilingService


class RecordingBackend(FakeBackend):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.commands: list[str] = []

    async def shell(
        self, serial: str, command: str, timeout_s: float | None = None
    ) -> CommandResult:
        self.commands.append(command)
        return await super().shell(serial, command, timeout_s)


def _cr(stdout: str = "", stderr: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(stdout=stdout, stderr=stderr, exit_code=exit_code, duration_ms=20.0)


_REMOTE = "/data/local/tmp/adb_automation_mcp_methodprofile_com.example.app.trace"


@pytest.mark.asyncio
async def test_start_method_profile__default_command() -> None:
    backend = RecordingBackend()

    result = await ProfilingService(backend).start_method_profile(
        "emulator-5554", "com.example.app"
    )

    assert backend.commands == [f"am profile start com.example.app {_REMOTE}"]
    assert result.device_trace_path == _REMOTE
    assert result.sampling_interval_us is None
    assert result.started is True


@pytest.mark.asyncio
async def test_start_method_profile__sampling_and_user() -> None:
    backend = RecordingBackend()

    await ProfilingService(backend).start_method_profile(
        "emulator-5554", "com.example.app", sampling_interval_us=1000, user_id=10
    )

    assert backend.commands == [
        f"am profile start --user 10 --sampling 1000 com.example.app {_REMOTE}"
    ]


@pytest.mark.asyncio
async def test_start_method_profile__streaming_flag() -> None:
    backend = RecordingBackend()

    await ProfilingService(backend).start_method_profile(
        "emulator-5554", "com.example.app", streaming=True
    )

    assert backend.commands == [f"am profile start --streaming com.example.app {_REMOTE}"]


@pytest.mark.asyncio
async def test_start_method_profile__sampling_and_streaming_conflict_rejected() -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await ProfilingService(Exploding()).start_method_profile(
            "emulator-5554", "com.x", sampling_interval_us=1000, streaming=True
        )


@pytest.mark.asyncio
async def test_start_method_profile__invalid_interval_rejected() -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await ProfilingService(Exploding()).start_method_profile(
            "emulator-5554", "com.x", sampling_interval_us=0
        )
    with pytest.raises(InvalidArgumentError):
        await ProfilingService(Exploding()).start_method_profile(
            "emulator-5554", "com.x", sampling_interval_us=99_999_999
        )


@pytest.mark.asyncio
async def test_start_method_profile__blank_package_rejected() -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await ProfilingService(Exploding()).start_method_profile("emulator-5554", "  ")


@pytest.mark.asyncio
async def test_start_method_profile__not_profileable_raises_permission_denied() -> None:
    backend = FakeBackend(
        am_profile_start_result=_cr(
            stdout="java.lang.SecurityException: Process not debuggable\n", exit_code=255
        )
    )
    with pytest.raises(PermissionDeniedError):
        await ProfilingService(backend).start_method_profile("emulator-5554", "com.x")


@pytest.mark.asyncio
async def test_start_method_profile__error_output_raises_backend_error() -> None:
    backend = FakeBackend(am_profile_start_result=_cr(stdout="Error: Unknown process: com.x\n"))
    with pytest.raises(BackendError):
        await ProfilingService(backend).start_method_profile("emulator-5554", "com.x")


@pytest.mark.asyncio
async def test_stop_method_profile__normal_stop_pull_cleanup(tmp_path: Path) -> None:
    backend = RecordingBackend()

    result = await ProfilingService(backend, local_root=tmp_path).stop_method_profile(
        "emulator-5554", "com.example.app", "app.trace"
    )

    assert "am profile stop com.example.app" in backend.commands
    assert any(c == f"rm -f {_REMOTE}" for c in backend.commands)
    assert result.local_path == str(tmp_path / "profiles" / "app.trace")
    assert result.success is True


@pytest.mark.asyncio
async def test_stop_method_profile__no_local_root_raises_policy() -> None:
    with pytest.raises(PolicyViolationError):
        await ProfilingService(FakeBackend(), local_root=None).stop_method_profile(
            "emulator-5554", "com.x", "x.trace"
        )


@pytest.mark.asyncio
async def test_stop_method_profile__path_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(PolicyViolationError):
        await ProfilingService(FakeBackend(), local_root=tmp_path).stop_method_profile(
            "emulator-5554", "com.x", "../../escape.trace"
        )


@pytest.mark.asyncio
async def test_stop_method_profile__no_active_profile_raises_remote_file_not_found(
    tmp_path: Path,
) -> None:
    class FailingPull(FakeBackend):
        async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
            return _cr(stderr="adb: error: remote object does not exist\n", exit_code=1)

    with pytest.raises(RemoteFileNotFoundError):
        await ProfilingService(FailingPull(), local_root=tmp_path).stop_method_profile(
            "emulator-5554", "com.x", "x.trace"
        )


@pytest.mark.asyncio
async def test_stop_method_profile__pull_failure_cleans_up(tmp_path: Path) -> None:
    class FailingPull(RecordingBackend):
        async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
            return _cr(stderr="adb: error: connection reset\n", exit_code=1)

    backend = FailingPull()
    with pytest.raises(BackendError):
        await ProfilingService(backend, local_root=tmp_path).stop_method_profile(
            "emulator-5554", "com.x", "x.trace"
        )
    assert any(c.startswith("rm -f /data/local/tmp/") for c in backend.commands)


@pytest.mark.asyncio
async def test_stop_method_profile__unknown_serial(tmp_path: Path) -> None:
    backend = FakeBackend(
        am_profile_stop_result=_cr(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )
    with pytest.raises(DeviceNotFoundError):
        await ProfilingService(backend, local_root=tmp_path).stop_method_profile(
            "bogus", "com.x", "x.trace"
        )


@pytest.mark.asyncio
async def test_profiling_service__backend_unavailable() -> None:
    with pytest.raises(AdbUnavailableError):
        await ProfilingService(FakeBackend(unavailable=True)).start_method_profile(
            "emulator-5554", "com.x"
        )
