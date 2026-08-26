"""A deterministic, in-memory AdbBackend implementation for tests.

Fixture values passed in must be realistic once methods beyond list_devices are
implemented — a test is only a trustworthy predictor of real behavior if it's
exercised against real-shaped data. For now the unimplemented methods raise
NotImplementedError loudly rather than returning silently-wrong fake data.
"""

from __future__ import annotations

from adb_mcp.backend.protocol import CommandResult, DeviceInfo
from adb_mcp.errors import AdbUnavailableError


class FakeBackend:
    """AdbBackend implementation backed by in-memory fixtures instead of a real
    device or adb install — deterministic, fast, and usable in any environment.
    """

    def __init__(
        self,
        devices: list[DeviceInfo] | None = None,
        unavailable: bool = False,
        kill_server_result: CommandResult | None = None,
        start_server_result: CommandResult | None = None,
        connect_result: CommandResult | None = None,
        disconnect_result: CommandResult | None = None,
        shell_result: CommandResult | None = None,
        dumpsys_user_result: CommandResult | None = None,
        user_info_result: CommandResult | None = None,
        list_users_result: CommandResult | None = None,
        switch_user_result: CommandResult | None = None,
        create_user_result: CommandResult | None = None,
        remove_user_result: CommandResult | None = None,
    ) -> None:
        self._devices = devices or []
        self._unavailable = unavailable
        self._kill_server_result = kill_server_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=5.0
        )
        # Real `adb start-server` output when a server needs starting, captured
        # from an actual run — fixtures should be real-shaped, not hand-invented.
        self._start_server_result = start_server_result or CommandResult(
            stdout="",
            stderr="* daemon not running; starting now at tcp:5037\n* daemon started successfully\n",
            exit_code=0,
            duration_ms=180.0,
        )
        # None (the default) means "build a realistic success message from
        # whatever host:port connect() is actually called with" — see connect()
        # below. A fixed override here is for simulating a specific failure.
        self._connect_result = connect_result
        self._disconnect_result = disconnect_result
        # Real `adb shell am get-current-user` output for the common case (a
        # single-user device, primary/owner user), captured from an actual run.
        self._shell_result = shell_result or CommandResult(
            stdout="0\n", stderr="", exit_code=0, duration_ms=45.0
        )
        # Real `adb shell dumpsys user` output, trimmed to one UserInfo block
        # (the real dump was ~1000 lines covering every user on the device).
        self._dumpsys_user_result = dumpsys_user_result or CommandResult(
            stdout=(
                "Current user: 10\n"
                "\n"
                "Users:\n"
                "  UserInfo{10:Driver:412} serialNo=10 isPrimary=false\n"
                "    Type: android.os.usertype.full.SECONDARY\n"
                "    Flags: 1042 (ADMIN|FULL|INITIALIZED)\n"
                "    State: RUNNING_UNLOCKED\n"
                "    Created: +3d9h55m0s649ms ago\n"
                "    Last logged in: +3d9h54m53s394ms ago\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=90.0,
        )
        # None (the default) means "build a realistic single-user block for
        # whatever user_id user_info() is actually called with" — see shell()
        # below. A fixed override here is for simulating "User N not found".
        self._user_info_result = user_info_result
        # Real `adb shell cmd user list -v` output, captured from an actual run.
        self._list_users_result = list_users_result or CommandResult(
            stdout=(
                "2 users:\n"
                "\n"
                "0: id=0, name=System User, type=system.HEADLESS, "
                "flags=INITIALIZED|PRIMARY|SYSTEM (running)\n"
                "1: id=10, name=Driver, type=full.SECONDARY, "
                "flags=ADMIN|FULL|INITIALIZED (running) (current) (visible)\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=55.0,
        )
        # Real `adb shell am switch-user N` success output: empty stdout, exit 0.
        self._switch_user_result = switch_user_result or CommandResult(
            stdout="", stderr="", exit_code=0, duration_ms=100.0
        )
        # Real `adb shell pm create-user NAME` success output, captured from an actual run.
        self._create_user_result = create_user_result or CommandResult(
            stdout="Success: created user id 12\n", stderr="", exit_code=0, duration_ms=400.0
        )
        # Real `adb shell pm remove-user ID` success output, captured from an actual run.
        self._remove_user_result = remove_user_result or CommandResult(
            stdout="Success: removed user\n", stderr="", exit_code=0, duration_ms=350.0
        )

    def _raise_if_unavailable(self) -> None:
        if self._unavailable:
            raise AdbUnavailableError(
                "Could not find or execute the adb binary (simulated).",
                details={"adb_path": "adb"},
                remediation="Install Android platform-tools and ensure 'adb' is on PATH.",
            )

    async def list_devices(self) -> list[DeviceInfo]:
        self._raise_if_unavailable()
        return list(self._devices)

    async def shell(self, serial: str, command: str) -> CommandResult:
        self._raise_if_unavailable()
        if command.startswith("dumpsys user --user "):
            if self._user_info_result is not None:
                return self._user_info_result
            user_id = command.rsplit(" ", 1)[-1]
            # Real adb wording/shape for a single filtered user block.
            return CommandResult(
                stdout=(
                    f"  UserInfo{{{user_id}:Driver:412}} serialNo={user_id} isPrimary=false\n"
                    "    Type: android.os.usertype.full.SECONDARY\n"
                    "    Flags: 1042 (ADMIN|FULL|INITIALIZED)\n"
                    "    State: RUNNING_UNLOCKED\n"
                ),
                stderr="",
                exit_code=0,
                duration_ms=60.0,
            )
        if command == "dumpsys user":
            return self._dumpsys_user_result
        if command == "cmd user list -v":
            return self._list_users_result
        if command.startswith("am switch-user "):
            return self._switch_user_result
        if command.startswith("pm create-user "):
            return self._create_user_result
        if command.startswith("pm remove-user "):
            return self._remove_user_result
        return self._shell_result

    async def install(self, serial: str, apk_path: str, flags: list[str]) -> CommandResult:
        raise NotImplementedError("FakeBackend.install: no module needs this yet")

    async def uninstall(self, serial: str, package: str, keep_data: bool) -> CommandResult:
        raise NotImplementedError("FakeBackend.uninstall: no module needs this yet")

    async def push(self, serial: str, local_path: str, remote_path: str) -> CommandResult:
        raise NotImplementedError("FakeBackend.push: no module needs this yet")

    async def pull(self, serial: str, remote_path: str, local_path: str) -> CommandResult:
        raise NotImplementedError("FakeBackend.pull: no module needs this yet")

    async def kill_server(self) -> CommandResult:
        self._raise_if_unavailable()
        return self._kill_server_result

    async def start_server(self) -> CommandResult:
        self._raise_if_unavailable()
        return self._start_server_result

    async def connect(self, host: str, port: int) -> CommandResult:
        self._raise_if_unavailable()
        if self._connect_result is not None:
            return self._connect_result
        # Real adb wording (AOSP adb_client.cpp) for a fresh successful connect.
        return CommandResult(
            stdout=f"connected to {host}:{port}\n", stderr="", exit_code=0, duration_ms=220.0
        )

    async def disconnect(self, host: str, port: int) -> CommandResult:
        self._raise_if_unavailable()
        if self._disconnect_result is not None:
            return self._disconnect_result
        return CommandResult(
            stdout=f"disconnected {host}:{port}\n", stderr="", exit_code=0, duration_ms=15.0
        )
