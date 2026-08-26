"""Domain logic for the user module: the current Android user on a connected
device (`adb shell am get-current-user`) — relevant on multi-user devices
(work profiles, guest users, Android Automotive), where more than one user
account can exist on the same device.
"""

from __future__ import annotations

from pydantic import BaseModel

from adb_mcp.backend.protocol import AdbBackend
from adb_mcp.errors import BackendError, DeviceNotFoundError


class CurrentUser(BaseModel):
    """The current Android user on a device, as reported by
    `adb shell am get-current-user`.
    """

    serial: str
    user_id: int

    def summary(self) -> str:
        return f"Current user on {self.serial} is {self.user_id}."


class UserService:
    """Reads the current Android user from a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def get_current_user(self, serial: str) -> CurrentUser:
        result = await self._backend.shell(serial, "am get-current-user")
        if result.exit_code != 0:
            # Verified live against a real device: an unknown serial fails at
            # the adb-client level (before reaching any device) with
            # "adb: device '<serial>' not found", exit 1.
            message = (result.stderr or result.stdout).strip() or "am get-current-user exited non-zero."
            if "not found" in message:
                raise DeviceNotFoundError(message, details={"serial": serial})
            raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})
        return CurrentUser(serial=serial, user_id=int(result.stdout.strip()))
