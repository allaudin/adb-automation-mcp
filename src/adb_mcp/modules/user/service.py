"""Domain logic for the user module: Android user info on a connected device
(`adb shell am get-current-user`, `adb shell dumpsys user`, `adb shell dumpsys
user --user ID`) — relevant on multi-user devices (work profiles, guest users,
Android Automotive), where more than one user account can exist on the same
device.
"""

from __future__ import annotations

from pydantic import BaseModel

from adb_mcp.backend.protocol import AdbBackend, CommandResult
from adb_mcp.errors import BackendError, DeviceNotFoundError, UserNotFoundError


class CurrentUser(BaseModel):
    """The current Android user on a device, as reported by
    `adb shell am get-current-user`.
    """

    serial: str
    user_id: int

    def summary(self) -> str:
        return f"Current user on {self.serial} is {self.user_id}."


class UserDump(BaseModel):
    """Raw `adb shell dumpsys user` output: every user on the device.

    No per-user filtering: verified live (Android 14 automotive build) that
    `dumpsys user`'s optional userId argument has no effect whatsoever —
    `dumpsys user 0`, `dumpsys user 10`, and `dumpsys user 9999` all produced
    byte-for-byte identical output (modulo timing noise). UserManagerService's
    dump handler always dumps every user; there's no way to scope it to one.
    """

    serial: str
    output: str

    def summary(self) -> str:
        return f"Dumped users on {self.serial} ({len(self.output)} chars)."


class UserInfo(BaseModel):
    """Detailed info for one Android user, as reported by
    `adb shell dumpsys user --user USERID`.

    Unlike the bare `dumpsys user` argument, `--user` genuinely filters:
    verified live that `--user 0` and `--user 10` returned different,
    single-user blocks. Also verified live that a nonexistent user ID doesn't
    fail the adb command at all — it returns "User <id> not found" as
    ordinary stdout with exit code 0, which this service turns into
    UserNotFoundError rather than treating as successful data.
    """

    serial: str
    user_id: int
    output: str

    def summary(self) -> str:
        return f"User {self.user_id} info on {self.serial} ({len(self.output)} chars)."


class UserService:
    """Reads Android user info from a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    @staticmethod
    def _raise_for_shell_failure(serial: str, result: CommandResult) -> None:
        if result.exit_code == 0:
            return
        # Verified live against a real device: an unknown serial fails at the
        # adb-client level (before reaching any device) with
        # "adb: device '<serial>' not found", exit 1.
        message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
        if "not found" in message:
            raise DeviceNotFoundError(message, details={"serial": serial})
        raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})

    async def get_current_user(self, serial: str) -> CurrentUser:
        result = await self._backend.shell(serial, "am get-current-user")
        self._raise_for_shell_failure(serial, result)
        return CurrentUser(serial=serial, user_id=int(result.stdout.strip()))

    async def dump_user(self, serial: str) -> UserDump:
        result = await self._backend.shell(serial, "dumpsys user")
        self._raise_for_shell_failure(serial, result)
        return UserDump(serial=serial, output=result.stdout)

    async def user_info(self, serial: str, user_id: int) -> UserInfo:
        result = await self._backend.shell(serial, f"dumpsys user --user {user_id}")
        self._raise_for_shell_failure(serial, result)
        output = result.stdout.strip()
        if output == f"User {user_id} not found":
            raise UserNotFoundError(output, details={"serial": serial, "user_id": user_id})
        return UserInfo(serial=serial, user_id=user_id, output=output)
