"""Layer 1 unit tests: TracingService against FakeBackend directly."""

from __future__ import annotations

import shlex
from pathlib import Path

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PolicyViolationError,
    RemoteFileNotFoundError,
    TracingUnavailableError,
)
from adb_automation_mcp.modules.tracing.service import PRESETS, TracingService


class RecordingBackend(FakeBackend):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.commands: list[str] = []
        self.timeouts: list[float | None] = []

    async def shell(
        self, serial: str, command: str, timeout_s: float | None = None
    ) -> CommandResult:
        self.commands.append(command)
        self.timeouts.append(timeout_s)
        return await super().shell(serial, command, timeout_s)


def _cr(stdout: str = "", stderr: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(stdout=stdout, stderr=stderr, exit_code=exit_code, duration_ms=20.0)


@pytest.mark.asyncio
async def test_capture_system_trace__command_shape_and_cleanup(tmp_path: Path) -> None:
    backend = RecordingBackend()

    result = await TracingService(backend, local_root=tmp_path).capture_system_trace(
        "emulator-5554", "cpu", "cpu.perfetto-trace", duration_seconds=5
    )

    perfetto_cmd = next(c for c in backend.commands if c.startswith("perfetto "))
    tokens = shlex.split(perfetto_cmd)
    assert tokens[:2] == ["perfetto", "-o"]
    assert tokens[tokens.index("-t") + 1] == "5s"
    assert tokens[tokens.index("-b") + 1] == "32mb"
    assert tokens[-3:] == ["sched", "freq", "idle"]  # cpu preset
    assert "-a" not in tokens
    assert any(c.startswith("rm -f /data/misc/perfetto-traces/") for c in backend.commands)
    assert result.success is True
    assert result.preset == "cpu"
    assert result.device_bytes == 84260
    assert result.local_path == str(tmp_path / "traces" / "cpu.perfetto-trace")


@pytest.mark.asyncio
async def test_capture_system_trace__package_scope_adds_dash_a(tmp_path: Path) -> None:
    backend = RecordingBackend()

    await TracingService(backend, local_root=tmp_path).capture_system_trace(
        "emulator-5554", "app_startup", "s.perfetto-trace", package="com.example.app"
    )

    perfetto_cmd = next(c for c in backend.commands if c.startswith("perfetto "))
    tokens = shlex.split(perfetto_cmd)
    assert tokens[tokens.index("-a") + 1] == "com.example.app"


@pytest.mark.asyncio
async def test_capture_system_trace__timeout_covers_duration(tmp_path: Path) -> None:
    backend = RecordingBackend()

    await TracingService(backend, local_root=tmp_path).capture_system_trace(
        "emulator-5554", "cpu", "c.perfetto-trace", duration_seconds=30
    )

    perfetto_idx = next(i for i, c in enumerate(backend.commands) if c.startswith("perfetto "))
    assert backend.timeouts[perfetto_idx] is not None
    assert backend.timeouts[perfetto_idx] >= 30


@pytest.mark.parametrize("preset", PRESETS)
@pytest.mark.asyncio
async def test_capture_system_trace__every_preset_runs(preset: str, tmp_path: Path) -> None:
    result = await TracingService(FakeBackend(), local_root=tmp_path).capture_system_trace(
        "emulator-5554", preset, f"{preset}.perfetto-trace", duration_seconds=2
    )
    assert result.preset == preset
    assert result.success is True


@pytest.mark.asyncio
async def test_capture_system_trace__unknown_preset_rejected(tmp_path: Path) -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await TracingService(Exploding(), local_root=tmp_path).capture_system_trace(
            "emulator-5554", "nonsense", "x.perfetto-trace"
        )


@pytest.mark.asyncio
async def test_capture_system_trace__duration_out_of_range_rejected(tmp_path: Path) -> None:
    class Exploding(FakeBackend):
        async def shell(self, serial: str, command: str, timeout_s: float | None = None) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await TracingService(Exploding(), local_root=tmp_path).capture_system_trace(
            "emulator-5554", "cpu", "x.perfetto-trace", duration_seconds=0
        )
    with pytest.raises(InvalidArgumentError):
        await TracingService(Exploding(), local_root=tmp_path).capture_system_trace(
            "emulator-5554", "cpu", "x.perfetto-trace", duration_seconds=999
        )


@pytest.mark.asyncio
async def test_capture_system_trace__no_local_root_raises_policy() -> None:
    with pytest.raises(PolicyViolationError):
        await TracingService(FakeBackend(), local_root=None).capture_system_trace(
            "emulator-5554", "cpu", "x.perfetto-trace"
        )


@pytest.mark.asyncio
async def test_capture_system_trace__path_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(PolicyViolationError):
        await TracingService(FakeBackend(), local_root=tmp_path).capture_system_trace(
            "emulator-5554", "cpu", "../../escape.perfetto-trace"
        )


@pytest.mark.asyncio
async def test_capture_system_trace__perfetto_unavailable(tmp_path: Path) -> None:
    backend = FakeBackend(
        perfetto_result=_cr(stderr="/system/bin/sh: perfetto: not found\n", exit_code=127)
    )
    with pytest.raises(TracingUnavailableError):
        await TracingService(backend, local_root=tmp_path).capture_system_trace(
            "emulator-5554", "cpu", "x.perfetto-trace"
        )


@pytest.mark.asyncio
async def test_capture_system_trace__perfetto_failure_and_cleanup(tmp_path: Path) -> None:
    backend = RecordingBackend(
        perfetto_result=_cr(stderr="Failed to open output file\n", exit_code=1)
    )
    with pytest.raises(BackendError):
        await TracingService(backend, local_root=tmp_path).capture_system_trace(
            "emulator-5554", "cpu", "x.perfetto-trace"
        )
    assert any(c.startswith("rm -f /data/misc/perfetto-traces/") for c in backend.commands)


@pytest.mark.asyncio
async def test_capture_system_trace__pull_failure(tmp_path: Path) -> None:
    class FailingPull(FakeBackend):
        async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
            return _cr(stderr="adb: error: remote object does not exist\n", exit_code=1)

    with pytest.raises(RemoteFileNotFoundError):
        await TracingService(FailingPull(), local_root=tmp_path).capture_system_trace(
            "emulator-5554", "cpu", "x.perfetto-trace"
        )


@pytest.mark.asyncio
async def test_capture_system_trace__unknown_serial(tmp_path: Path) -> None:
    backend = FakeBackend(
        perfetto_result=_cr(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )
    with pytest.raises(DeviceNotFoundError):
        await TracingService(backend, local_root=tmp_path).capture_system_trace(
            "bogus", "cpu", "x.perfetto-trace"
        )


@pytest.mark.asyncio
async def test_capture_system_trace__backend_unavailable(tmp_path: Path) -> None:
    with pytest.raises(AdbUnavailableError):
        await TracingService(FakeBackend(unavailable=True), local_root=tmp_path).capture_system_trace(
            "emulator-5554", "cpu", "x.perfetto-trace"
        )
