"""The AdbBackend Protocol: the one interface every module is allowed to depend on
for talking to a device. Mechanical execution only — implementations raise AdbError
subclasses solely for transport-level failures (device not found, timeout, adb
unavailable), never for domain-specific interpretation of adb's output. Interpreting
what a command's output *means* is a module's service class's job, not the backend's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CommandResult:
    """The uniform result of running one adb (or adb-shell) command."""

    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float


@dataclass(frozen=True)
class DeviceInfo:
    """One entry from `adb devices -l`: a connected device's identity and state."""

    serial: str
    state: str
    model: str | None = None
    product: str | None = None


class AdbBackend(Protocol):
    """Structural interface for executing adb operations.

    A `typing.Protocol`, not an ABC, so a third-party backend or test double only
    needs to satisfy these method signatures — no inheritance from this package
    required. Every implementation must raise the same transport-level AdbError
    subclasses for the same scenarios (see backend/testing.py's FakeBackend and
    backend/subprocess_backend.py's SubprocessBackend).
    """

    async def list_devices(self) -> list[DeviceInfo]: ...

    async def shell(self, serial: str, command: str) -> CommandResult: ...

    async def install(self, serial: str, apk_path: str, flags: list[str]) -> CommandResult: ...

    async def uninstall(self, serial: str, package: str, keep_data: bool) -> CommandResult: ...

    async def push(self, serial: str, local_path: str, remote_path: str) -> CommandResult: ...

    async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult: ...

    async def kill_server(self) -> CommandResult: ...

    async def start_server(self) -> CommandResult: ...

    async def connect(self, host: str, port: int) -> CommandResult: ...

    async def disconnect(self, host: str, port: int) -> CommandResult: ...

    async def root(self, serial: str) -> CommandResult: ...
