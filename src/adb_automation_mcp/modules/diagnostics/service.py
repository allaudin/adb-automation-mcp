"""Domain logic for the diagnostics module.

check_adb_available is a deliberate exception to the usual "let AdbError propagate"
pattern used elsewhere in this codebase: adb being unreachable is the expected "false"
answer for a health check, not a tool failure, so it's caught here and turned into
data instead of an error.
"""

from __future__ import annotations

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend
from adb_automation_mcp.errors import AdbTimeoutError, AdbUnavailableError


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
