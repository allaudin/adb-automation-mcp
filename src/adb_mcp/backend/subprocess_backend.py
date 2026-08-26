"""The real AdbBackend implementation: executes adb as a subprocess.

`list_devices`, `kill_server`, `start_server`, `connect`, `disconnect`, `root`, and
`shell` are exercised by modules built so far (diagnostics, device_info, connection, user);
`install` is used by the packages module's install_apk (uninstall and
install-existing-for-user go through `shell` instead — see packages/service.py for
why). `uninstall` and `push` are implemented to the same standard but not yet used by
any module; `pull` is used by files and screen. None of these have automated
contract-test coverage against the real binary yet — verified manually against a real
device instead.
"""

from __future__ import annotations

import asyncio
import shutil
from asyncio.subprocess import Process

from adb_mcp.backend.protocol import CommandResult, DeviceInfo
from adb_mcp.errors import AdbTimeoutError, AdbUnavailableError

DEFAULT_TIMEOUT_S = 10.0


class SubprocessBackend:
    """AdbBackend implementation that spawns the real `adb` binary per call.

    Owns the one thing every method needs: safely invoking adb as an async
    subprocess, enforcing a timeout, and translating OS/timeout failures into the
    shared transport-level AdbError subclasses. Never interprets a command's stdout —
    callers get the raw CommandResult and decide what it means themselves.
    """

    def __init__(self, adb_path: str | None = None, timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self._adb_path = adb_path or shutil.which("adb") or "adb"
        self._timeout_s = timeout_s

    async def _run(self, *args: str) -> CommandResult:
        loop = asyncio.get_running_loop()
        start = loop.time()

        try:
            proc: Process = await asyncio.create_subprocess_exec(
                self._adb_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise AdbUnavailableError(
                f"Could not find or execute the adb binary at '{self._adb_path}'.",
                details={"adb_path": self._adb_path, "os_error": str(exc)},
                remediation=(
                    "Install Android platform-tools and ensure 'adb' is on PATH, "
                    "or configure an explicit adb path."
                ),
            ) from exc

        try:
            stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=self._timeout_s)
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise AdbTimeoutError(
                f"adb command timed out after {self._timeout_s * 1000:.0f}ms.",
                details={"timeout_ms": self._timeout_s * 1000, "command": " ".join(args)},
                remediation="The device or adb server may be busy or unresponsive. Retrying is reasonable.",
            ) from exc

        duration_ms = (loop.time() - start) * 1000
        return CommandResult(
            stdout=stdout_b.decode("utf-8", errors="replace"),
            stderr=stderr_b.decode("utf-8", errors="replace"),
            exit_code=proc.returncode if proc.returncode is not None else -1,
            duration_ms=duration_ms,
        )

    async def list_devices(self) -> list[DeviceInfo]:
        result = await self._run("devices", "-l")
        return _parse_devices(result.stdout)

    async def shell(self, serial: str, command: str) -> CommandResult:
        return await self._run("-s", serial, "shell", command)

    async def install(self, serial: str, apk_path: str, flags: list[str]) -> CommandResult:
        return await self._run("-s", serial, "install", *flags, apk_path)

    async def uninstall(self, serial: str, package: str, keep_data: bool) -> CommandResult:
        flags = ["-k"] if keep_data else []
        return await self._run("-s", serial, "uninstall", *flags, package)

    async def push(self, serial: str, local_path: str, remote_path: str) -> CommandResult:
        return await self._run("-s", serial, "push", local_path, remote_path)

    async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
        return await self._run("-s", serial, "pull", remote_path, local_path)

    async def kill_server(self) -> CommandResult:
        return await self._run("kill-server")

    async def start_server(self) -> CommandResult:
        return await self._run("start-server")

    async def connect(self, host: str, port: int) -> CommandResult:
        return await self._run("connect", f"{host}:{port}")

    async def disconnect(self, host: str, port: int) -> CommandResult:
        return await self._run("disconnect", f"{host}:{port}")

    async def root(self, serial: str) -> CommandResult:
        return await self._run("-s", serial, "root")


def _parse_devices(stdout: str) -> list[DeviceInfo]:
    devices: list[DeviceInfo] = []
    for raw_line in stdout.splitlines()[1:]:  # skip "List of devices attached" header
        line = raw_line.strip()
        if not line:
            continue
        serial, state, *rest = line.split()
        model: str | None = None
        product: str | None = None
        for token in rest:
            if token.startswith("model:"):
                model = token.split(":", 1)[1]
            elif token.startswith("product:"):
                product = token.split(":", 1)[1]
        devices.append(DeviceInfo(serial=serial, state=state, model=model, product=product))
    return devices
