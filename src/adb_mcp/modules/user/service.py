"""Domain logic for the user module: Android user info and lifecycle on a
connected device (`adb shell am get-current-user`, `adb shell dumpsys user`,
`adb shell dumpsys user --user ID`, `adb shell cmd user list -v`, `adb shell am
switch-user ID`, `adb shell pm create-user NAME`, `adb shell pm remove-user
ID`) — relevant on multi-user devices (work profiles, guest users, Android
Automotive), where more than one user account can exist on the same device.
"""

from __future__ import annotations

import re
import shlex

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


class UserListEntry(BaseModel):
    """One user from `adb shell cmd user list -v`, e.g. the real line
    `1: id=10, name=Driver, type=full.SECONDARY, flags=ADMIN|FULL|INITIALIZED
    (running) (current) (visible)` parses into user_id=10, name="Driver",
    type="full.SECONDARY", flags=["ADMIN", "FULL", "INITIALIZED"],
    states=["running", "current", "visible"].
    """

    user_id: int
    name: str
    type: str
    flags: list[str]
    states: list[str]


class UserList(BaseModel):
    """Every user on a device, as reported by `adb shell cmd user list -v`."""

    serial: str
    users: list[UserListEntry]

    def summary(self) -> str:
        n = len(self.users)
        plural = "" if n == 1 else "s"
        return f"{n} user{plural} on {self.serial}."


class SwitchUserResult(BaseModel):
    """Outcome of switching the active Android user
    (`adb shell am switch-user USERID`).

    Unlike connect_device/disconnect_device's adb-level exit-code quirks,
    `am switch-user`'s exit code was verified live to be reliable: 0 on
    success (empty stdout), 1 with "Error: Failed to switch to user <id>" for
    an invalid one. A failed switch therefore raises rather than being
    returned as data — there's no meaningful "success" field on this model,
    since reaching it at all means the switch worked.
    """

    serial: str
    user_id: int

    def summary(self) -> str:
        return f"Switched to user {self.user_id} on {self.serial}."


class CreateUserResult(BaseModel):
    """Outcome of creating a new Android user (`adb shell pm create-user NAME`).

    Verified live, including that a name containing spaces or shell
    metacharacters (`; echo ... `) is passed through as a literal user name,
    not interpreted by the device's shell — the service shell-quotes it
    before sending the command.
    """

    serial: str
    user_id: int
    name: str

    def summary(self) -> str:
        return f"Created user {self.user_id} ({self.name}) on {self.serial}."


class RemoveUserResult(BaseModel):
    """Outcome of removing an Android user (`adb shell pm remove-user USERID`).

    Verified live that this fails the same way ("Error: couldn't remove user
    id <id>", exit 1) whether the user doesn't exist or is currently the
    active/foreground user — the message alone can't distinguish the two.
    Switch away from a user (switch_user) before trying to remove it.
    """

    serial: str
    user_id: int

    def summary(self) -> str:
        return f"Removed user {self.user_id} on {self.serial}."


class UserService:
    """Reads and changes Android user state on a connected device."""

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

    async def list_users(self, serial: str) -> UserList:
        result = await self._backend.shell(serial, "cmd user list -v")
        self._raise_for_shell_failure(serial, result)
        return UserList(serial=serial, users=_parse_user_list(result.stdout))

    async def switch_user(self, serial: str, user_id: int) -> SwitchUserResult:
        result = await self._backend.shell(serial, f"am switch-user {user_id}")
        self._raise_for_shell_failure(serial, result)
        return SwitchUserResult(serial=serial, user_id=user_id)

    async def create_user(self, serial: str, name: str) -> CreateUserResult:
        # name is free-form and reaches the device's own shell via `adb shell`
        # (unlike every other command here, which only ever interpolates an
        # int) — shlex.quote it, verified live to correctly neutralize shell
        # metacharacters rather than just happening to work for plain names.
        result = await self._backend.shell(serial, f"pm create-user {shlex.quote(name)}")
        self._raise_for_shell_failure(serial, result)
        match = re.search(r"Success: created user id (\d+)", result.stdout)
        if match is None:
            raise BackendError(
                result.stdout.strip() or "pm create-user succeeded but returned unexpected output.",
                details={"serial": serial, "name": name},
            )
        return CreateUserResult(serial=serial, user_id=int(match.group(1)), name=name)

    async def remove_user(self, serial: str, user_id: int) -> RemoveUserResult:
        result = await self._backend.shell(serial, f"pm remove-user {user_id}")
        self._raise_for_shell_failure(serial, result)
        return RemoveUserResult(serial=serial, user_id=user_id)


# One line of `adb shell cmd user list -v`, e.g.:
# "1: id=10, name=Driver, type=full.SECONDARY, flags=ADMIN|FULL|INITIALIZED (running) (current) (visible)"
_USER_LIST_LINE_RE = re.compile(
    r"^\d+:\s*id=(?P<id>\d+),\s*name=(?P<name>[^,]*),\s*type=(?P<type>[^,]+),\s*"
    r"flags=(?P<flags>\S+)(?P<states>(?:\s+\([^)]*\))*)\s*$"
)


def _parse_user_list(output: str) -> list[UserListEntry]:
    entries: list[UserListEntry] = []
    for line in output.splitlines():
        match = _USER_LIST_LINE_RE.match(line.strip())
        if match is None:
            continue  # the "N users:" header line and blank lines don't match
        entries.append(
            UserListEntry(
                user_id=int(match.group("id")),
                name=match.group("name"),
                type=match.group("type"),
                flags=match.group("flags").split("|"),
                states=re.findall(r"\(([^)]*)\)", match.group("states")),
            )
        )
    return entries
