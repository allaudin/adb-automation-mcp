"""Domain logic for the diagnostics module.

check_adb_available is a deliberate exception to the usual "let AdbError propagate"
pattern used elsewhere in this codebase: adb being unreachable is the expected "false"
answer for a health check, not a tool failure, so it's caught here and turned into
data instead of an error.
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    AdbTimeoutError,
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PolicyViolationError,
)

_BUGREPORT_SUBDIR = "bugreports"
_MIN_BUGREPORT_TIMEOUT_S = 60.0
_MAX_BUGREPORT_TIMEOUT_S = 600.0
_COPIED_RE = re.compile(r"Bug report copied to (?P<path>.+?)\s*$", re.MULTILINE)


class AdbVersionInfo(BaseModel):
    """The host's adb client version, parsed from `adb version`.

    `adb version` output has grown over time; every field below is optional so a
    missing or reworded line degrades to null rather than a parse failure.
    Fields, by the line they come from:

    - `bridge_version` — "Android Debug Bridge version 1.0.41": the wire-protocol
      version, essentially frozen for years and rarely useful on its own.
    - `platform_tools_version` — "Version 37.0.0-eng.allaud": the platform-tools
      release, the number that actually tracks feature support (wireless pairing,
      `--fastdeploy`, etc.). None on very old adb builds that printed no such line.
    - `revision` — "Revision <hash>": present on some older/vendor builds instead
      of, or alongside, the Version line.
    - `installed_path` — "Installed as /usr/lib/android-sdk/platform-tools/adb".
    - `running_on` — "Running on Linux 6.8.0 (x86_64)": added ~2023; None before.
    """

    bridge_version: str | None = None
    platform_tools_version: str | None = None
    revision: str | None = None
    installed_path: str | None = None
    running_on: str | None = None
    raw: str

    def summary(self) -> str:
        if self.platform_tools_version:
            return f"adb platform-tools {self.platform_tools_version} (bridge {self.bridge_version or 'unknown'})."
        if self.bridge_version:
            return f"adb bridge version {self.bridge_version} (platform-tools version not reported)."
        return "adb version reported, but no recognizable version line was found."


def _parse_adb_version(stdout: str) -> AdbVersionInfo:
    """Parse `adb version` stdout line-by-line by known prefix. Any unrecognized
    or missing line simply leaves its field None — never raises.
    """
    prefixes: dict[str, str] = {
        "Android Debug Bridge version ": "bridge_version",
        "Version ": "platform_tools_version",
        "Revision ": "revision",
        "Installed as ": "installed_path",
        "Running on ": "running_on",
    }
    fields: dict[str, str] = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        for prefix, field_name in prefixes.items():
            if line.startswith(prefix) and field_name not in fields:
                fields[field_name] = line[len(prefix) :].strip()
                break
    return AdbVersionInfo(raw=stdout.strip(), **fields)


class AdbAvailability(BaseModel):
    """Whether adb is currently reachable, and how many devices it sees if so."""

    available: bool
    device_count: int | None = None
    reason: str | None = None

    def summary(self) -> str:
        if self.available:
            n = self.device_count or 0
            plural = "" if n == 1 else "s"
            return f"adb is available ({n} device{plural} connected)."
        return f"adb is not available: {self.reason or 'unknown reason'}"


class BugreportResult(BaseModel):
    """Outcome of `adb -s <serial> bugreport <local_path>`.

    local_path is the absolute path the bugreport was written to on this
    server's host. is_zip is True for the modern zipped form (the common
    case); a legacy text bugreport comes back is_zip=False. size_bytes is
    the saved file size, or null if it couldn't be stat'd. Only ever
    returned on success.
    """

    serial: str
    local_path: str
    is_zip: bool
    size_bytes: int | None
    success: bool

    def summary(self) -> str:
        kind = "zip" if self.is_zip else "text"
        return f"Saved {kind} bugreport from {self.serial} to {self.local_path}."


class DiagnosticsService:
    """Health-check and introspection logic for the adb connection itself, as
    opposed to any particular device — the thing to call first when something
    else on this server is failing or behaving unexpectedly.
    """

    def __init__(self, backend: AdbBackend, local_root: Path | None = None) -> None:
        self._backend = backend
        self._local_root = local_root.resolve() if local_root is not None else None

    def _resolve_local_path(self, rel: str) -> Path:
        if self._local_root is None:
            raise PolicyViolationError(
                "No local_root configured for this server — generate_bugreport "
                "cannot write to the host. Set ADB_AUTOMATION_LOCAL_ROOT.",
                details={"local_path": rel},
            )
        resolved = (self._local_root / rel).resolve()
        if not resolved.is_relative_to(self._local_root):
            raise PolicyViolationError(
                f"local_path '{rel}' resolves outside the configured local_root.",
                details={"local_path": rel, "local_root": str(self._local_root)},
            )
        return resolved

    async def generate_bugreport(
        self, serial: str, local_path: str, timeout_s: float = 300.0
    ) -> BugreportResult:
        if not local_path.strip():
            raise InvalidArgumentError(
                "local_path must be a non-empty path.", details={"local_path": local_path}
            )
        if not _MIN_BUGREPORT_TIMEOUT_S <= timeout_s <= _MAX_BUGREPORT_TIMEOUT_S:
            raise InvalidArgumentError(
                f"timeout_s must be between {_MIN_BUGREPORT_TIMEOUT_S} and "
                f"{_MAX_BUGREPORT_TIMEOUT_S} seconds.",
                details={"serial": serial, "timeout_s": timeout_s},
            )
        target = self._resolve_local_path(f"{_BUGREPORT_SUBDIR}/{local_path}")
        target.parent.mkdir(parents=True, exist_ok=True)

        # `adb -s <serial> bugreport` does an implicit wait-for-device, so an
        # unknown or offline serial makes it block for the whole (deliberately
        # long) timeout_s instead of failing. Preflight with a cheap device
        # list so a bad serial fails immediately, like every other tool.
        await self._require_online_device(serial)

        result = await self._backend.bugreport(serial, str(target), timeout_s=timeout_s)
        _raise_for_bugreport_failure(serial, result)

        copied = _COPIED_RE.search(f"{result.stdout}\n{result.stderr}")
        written = Path(copied.group("path")) if copied else target
        if not written.is_file() and target.with_suffix(".zip").is_file():
            written = target.with_suffix(".zip")
        return BugreportResult(
            serial=serial,
            local_path=str(written),
            is_zip=written.suffix == ".zip",
            size_bytes=written.stat().st_size if written.is_file() else None,
            success=True,
        )

    async def _require_online_device(self, serial: str) -> None:
        """Fail fast if serial isn't a currently-usable device.

        Cheap `adb devices` lookup used to guard the long-blocking bugreport
        call. An unreachable adb binary raises AdbUnavailableError from the
        backend, which is the correct surface for that case.
        """
        devices = await self._backend.list_devices()
        match = next((d for d in devices if d.serial == serial), None)
        if match is None:
            raise DeviceNotFoundError(
                f"device '{serial}' not found",
                details={"serial": serial, "known": [d.serial for d in devices]},
            )
        if match.state != "device":
            raise DeviceNotFoundError(
                f"device '{serial}' is {match.state}, not ready for a bugreport",
                details={"serial": serial, "state": match.state},
            )

    async def check_adb_available(self) -> AdbAvailability:
        try:
            devices = await self._backend.list_devices()
        except (AdbUnavailableError, AdbTimeoutError) as exc:
            return AdbAvailability(available=False, reason=str(exc))
        return AdbAvailability(available=True, device_count=len(devices))

    async def get_adb_version(self) -> AdbVersionInfo:
        """Report the host adb client version via `adb version`.

        The adb binary being unreachable raises AdbUnavailableError from the
        backend (a transport-level failure); a non-zero exit from adb itself —
        rare for `version`, but possible on a broken install — is surfaced as
        BackendError. Recognizable-but-reworded output is not a failure: it
        parses to whatever fields are present, see _parse_adb_version.
        """
        result = await self._backend.version()
        if result.exit_code != 0:
            message = (result.stderr or result.stdout).strip() or "adb version exited non-zero."
            raise BackendError(message, details={"exit_code": result.exit_code})
        return _parse_adb_version(result.stdout)


def _raise_for_bugreport_failure(serial: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb bugreport exited non-zero."
    if "not found" in message or "no devices/emulators found" in message or "offline" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})
