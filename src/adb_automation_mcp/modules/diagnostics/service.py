"""Domain logic for the diagnostics module.

check_adb_available is a deliberate exception to the usual "let AdbError propagate"
pattern used elsewhere in this codebase: adb being unreachable is the expected "false"
answer for a health check, not a tool failure, so it's caught here and turned into
data instead of an error.
"""

from __future__ import annotations

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend
from adb_automation_mcp.errors import AdbTimeoutError, AdbUnavailableError, BackendError


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


class DiagnosticsService:
    """Health-check and introspection logic for the adb connection itself, as
    opposed to any particular device — the thing to call first when something
    else on this server is failing or behaving unexpectedly.
    """

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

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
