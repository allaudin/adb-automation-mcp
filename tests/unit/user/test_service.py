"""Layer 1 unit tests: UserService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    UserNotFoundError,
)
from adb_mcp.modules.user.service import (
    CreateUserResult,
    CurrentUser,
    RemoveUserResult,
    SwitchUserResult,
    UserCapabilities,
    UserDump,
    UserInfo,
    UserList,
    UserListEntry,
    UserService,
)


@pytest.mark.asyncio
async def test_get_current_user__single_user_device_reports_user_0() -> None:
    service = UserService(FakeBackend())

    result = await service.get_current_user("emulator-5554")

    assert result.serial == "emulator-5554"
    assert result.user_id == 0


@pytest.mark.asyncio
async def test_get_current_user__multi_user_device_reports_actual_user_id() -> None:
    backend = FakeBackend(
        shell_result=CommandResult(stdout="10\n", stderr="", exit_code=0, duration_ms=45.0)
    )
    service = UserService(backend)

    result = await service.get_current_user("emulator-5554")

    assert result.user_id == 10


@pytest.mark.asyncio
async def test_get_current_user__unknown_serial_raises_device_not_found() -> None:
    # Real adb behavior, verified live: unknown serial fails at the
    # adb-client level with "adb: device '<serial>' not found", exit 1.
    backend = FakeBackend(
        shell_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = UserService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.get_current_user("bogus")


@pytest.mark.asyncio
async def test_get_current_user__other_nonzero_exit_raises_backend_error() -> None:
    backend = FakeBackend(
        shell_result=CommandResult(
            stdout="", stderr="some other adb shell failure", exit_code=1, duration_ms=10.0
        )
    )
    service = UserService(backend)

    with pytest.raises(BackendError):
        await service.get_current_user("emulator-5554")


@pytest.mark.asyncio
async def test_get_current_user__adb_unavailable_propagates_as_error() -> None:
    service = UserService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.get_current_user("emulator-5554")


def test_current_user_summary_mentions_serial_and_user_id() -> None:
    summary = CurrentUser(serial="emulator-5554", user_id=10).summary()
    assert "emulator-5554" in summary
    assert "10" in summary


@pytest.mark.asyncio
async def test_dump_user__returns_raw_dumpsys_output() -> None:
    service = UserService(FakeBackend())

    result = await service.dump_user("emulator-5554")

    assert result.serial == "emulator-5554"
    assert "UserInfo{10:Driver:412}" in result.output


@pytest.mark.asyncio
async def test_dump_user__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        dumpsys_user_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = UserService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.dump_user("bogus")


@pytest.mark.asyncio
async def test_dump_user__other_nonzero_exit_raises_backend_error() -> None:
    backend = FakeBackend(
        dumpsys_user_result=CommandResult(
            stdout="", stderr="some other adb shell failure", exit_code=1, duration_ms=10.0
        )
    )
    service = UserService(backend)

    with pytest.raises(BackendError):
        await service.dump_user("emulator-5554")


@pytest.mark.asyncio
async def test_dump_user__adb_unavailable_propagates_as_error() -> None:
    service = UserService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.dump_user("emulator-5554")


def test_user_dump_summary_mentions_char_count() -> None:
    summary = UserDump(serial="emulator-5554", output="x" * 50).summary()
    assert "emulator-5554" in summary
    assert "50" in summary


@pytest.mark.asyncio
async def test_user_info__returns_single_user_block() -> None:
    service = UserService(FakeBackend())

    result = await service.user_info("emulator-5554", 10)

    assert result.serial == "emulator-5554"
    assert result.user_id == 10
    assert "UserInfo{10:Driver:412}" in result.output


@pytest.mark.asyncio
async def test_user_info__different_user_ids_produce_different_output() -> None:
    service = UserService(FakeBackend())

    result0 = await service.user_info("emulator-5554", 0)
    result10 = await service.user_info("emulator-5554", 10)

    assert result0.output != result10.output
    assert "UserInfo{0:" in result0.output
    assert "UserInfo{10:" in result10.output


@pytest.mark.asyncio
async def test_user_info__nonexistent_user_raises_user_not_found() -> None:
    # Real adb behavior, verified live: adb exits 0 and prints
    # "User <id> not found" as ordinary stdout for a nonexistent user.
    backend = FakeBackend(
        user_info_result=CommandResult(
            stdout="User 9999 not found\n", stderr="", exit_code=0, duration_ms=40.0
        )
    )
    service = UserService(backend)

    with pytest.raises(UserNotFoundError):
        await service.user_info("emulator-5554", 9999)


@pytest.mark.asyncio
async def test_user_info__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        user_info_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = UserService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.user_info("bogus", 10)


@pytest.mark.asyncio
async def test_user_info__adb_unavailable_propagates_as_error() -> None:
    service = UserService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.user_info("emulator-5554", 10)


def test_user_info_summary_mentions_user_id_and_char_count() -> None:
    summary = UserInfo(serial="emulator-5554", user_id=10, output="x" * 50).summary()
    assert "10" in summary
    assert "emulator-5554" in summary
    assert "50" in summary


@pytest.mark.asyncio
async def test_list_users__parses_real_cmd_user_list_output() -> None:
    service = UserService(FakeBackend())

    result = await service.list_users("emulator-5554")

    assert result.serial == "emulator-5554"
    assert len(result.users) == 2
    system_user, driver = result.users
    assert system_user == UserListEntry(
        user_id=0,
        name="System User",
        type="system.HEADLESS",
        flags=["INITIALIZED", "PRIMARY", "SYSTEM"],
        states=["running"],
    )
    assert driver == UserListEntry(
        user_id=10,
        name="Driver",
        type="full.SECONDARY",
        flags=["ADMIN", "FULL", "INITIALIZED"],
        states=["running", "current", "visible"],
    )


@pytest.mark.asyncio
async def test_list_users__single_user_device() -> None:
    backend = FakeBackend(
        list_users_result=CommandResult(
            stdout=(
                "1 users:\n\n"
                "0: id=0, name=Owner, type=full.SYSTEM, flags=INITIALIZED|PRIMARY|ADMIN"
                "|SYSTEM (running) (current) (visible)\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=40.0,
        )
    )
    service = UserService(backend)

    result = await service.list_users("emulator-5554")

    assert len(result.users) == 1
    assert result.users[0].user_id == 0
    assert result.users[0].name == "Owner"


@pytest.mark.asyncio
async def test_list_users__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        list_users_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = UserService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.list_users("bogus")


@pytest.mark.asyncio
async def test_list_users__adb_unavailable_propagates_as_error() -> None:
    service = UserService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.list_users("emulator-5554")


def test_user_list_summary_pluralizes_correctly() -> None:
    assert "1 user " in UserList(serial="s", users=[_entry(0)]).summary() + " "
    assert "2 users" in UserList(serial="s", users=[_entry(0), _entry(1)]).summary()
    assert "0 users" in UserList(serial="s", users=[]).summary()


def _entry(user_id: int) -> UserListEntry:
    return UserListEntry(user_id=user_id, name="x", type="t", flags=[], states=[])


@pytest.mark.asyncio
async def test_switch_user__success_returns_serial_and_user_id() -> None:
    service = UserService(FakeBackend())

    result = await service.switch_user("emulator-5554", 0)

    assert result.serial == "emulator-5554"
    assert result.user_id == 0


@pytest.mark.asyncio
async def test_switch_user__invalid_user_raises_backend_error() -> None:
    # Real adb behavior, verified live: exit 1, "Error: Failed to switch to
    # user <id>" — unlike connect/dumpsys quirks, this exit code IS reliable.
    backend = FakeBackend(
        switch_user_result=CommandResult(
            stdout="", stderr="Error: Failed to switch to user 9999", exit_code=1, duration_ms=50.0
        )
    )
    service = UserService(backend)

    with pytest.raises(BackendError):
        await service.switch_user("emulator-5554", 9999)


@pytest.mark.asyncio
async def test_switch_user__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        switch_user_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = UserService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.switch_user("bogus", 0)


@pytest.mark.asyncio
async def test_switch_user__adb_unavailable_propagates_as_error() -> None:
    service = UserService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.switch_user("emulator-5554", 0)


def test_switch_user_result_summary_mentions_user_id() -> None:
    summary = SwitchUserResult(serial="emulator-5554", user_id=0).summary()
    assert "0" in summary
    assert "emulator-5554" in summary


@pytest.mark.asyncio
async def test_create_user__success_parses_new_user_id() -> None:
    service = UserService(FakeBackend())

    result = await service.create_user("emulator-5554", "Guest")

    assert result.serial == "emulator-5554"
    assert result.user_id == 12
    assert result.name == "Guest"


@pytest.mark.asyncio
async def test_create_user__shell_quotes_name_with_metacharacters() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = UserService(RecordingBackend())

    await service.create_user("emulator-5554", "; echo pwned; #")

    assert "command" in captured
    assert captured["command"] == "pm create-user '; echo pwned; #'"


@pytest.mark.asyncio
async def test_create_user__unexpected_output_raises_backend_error() -> None:
    backend = FakeBackend(
        create_user_result=CommandResult(
            stdout="Error: could not create user\n", stderr="", exit_code=0, duration_ms=100.0
        )
    )
    service = UserService(backend)

    with pytest.raises(BackendError):
        await service.create_user("emulator-5554", "Guest")


@pytest.mark.asyncio
async def test_create_user__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        create_user_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = UserService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.create_user("bogus", "Guest")


@pytest.mark.asyncio
async def test_create_user__adb_unavailable_propagates_as_error() -> None:
    service = UserService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.create_user("emulator-5554", "Guest")


def test_create_user_result_summary_mentions_id_and_name() -> None:
    summary = CreateUserResult(serial="emulator-5554", user_id=12, name="Guest").summary()
    assert "12" in summary
    assert "Guest" in summary
    assert "emulator-5554" in summary


@pytest.mark.asyncio
async def test_remove_user__success_returns_serial_and_user_id() -> None:
    service = UserService(FakeBackend())

    result = await service.remove_user("emulator-5554", 12)

    assert result.serial == "emulator-5554"
    assert result.user_id == 12


@pytest.mark.asyncio
async def test_remove_user__nonexistent_or_active_user_raises_backend_error() -> None:
    # Real adb behavior, verified live: exit 1, "Error: couldn't remove user
    # id <id>" — identical whether the user doesn't exist or is currently active.
    backend = FakeBackend(
        remove_user_result=CommandResult(
            stdout="", stderr="Error: couldn't remove user id 9999", exit_code=1, duration_ms=80.0
        )
    )
    service = UserService(backend)

    with pytest.raises(BackendError):
        await service.remove_user("emulator-5554", 9999)


@pytest.mark.asyncio
async def test_remove_user__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        remove_user_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = UserService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.remove_user("bogus", 12)


@pytest.mark.asyncio
async def test_remove_user__adb_unavailable_propagates_as_error() -> None:
    service = UserService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.remove_user("emulator-5554", 12)


def test_remove_user_result_summary_mentions_user_id() -> None:
    summary = RemoveUserResult(serial="emulator-5554", user_id=12).summary()
    assert "12" in summary
    assert "emulator-5554" in summary


@pytest.mark.asyncio
async def test_get_user_capabilities__multi_user_capable_device_populates_everything() -> None:
    service = UserService(FakeBackend())

    result = await service.get_user_capabilities("emulator-5554")

    assert result == UserCapabilities(
        serial="emulator-5554",
        supports_multiple_users=True,
        max_users=4,
        max_running_users=4,
        headless_system_user_mode=False,
        visible_background_users_supported=False,
        visible_background_users_on_default_display_supported=False,
    )


@pytest.mark.asyncio
async def test_get_user_capabilities__single_user_device_reports_false() -> None:
    backend = FakeBackend(
        supports_multiple_users_result=CommandResult(
            stdout="Supports multiple users: false\n", stderr="", exit_code=0, duration_ms=20.0
        )
    )
    service = UserService(backend)

    result = await service.get_user_capabilities("emulator-5554")

    assert result.supports_multiple_users is False


@pytest.mark.asyncio
async def test_get_user_capabilities__max_users_parses_labeled_text_variant() -> None:
    backend = FakeBackend(
        max_users_result=CommandResult(
            stdout="Maximum supported users: 4\n", stderr="", exit_code=0, duration_ms=20.0
        )
    )
    service = UserService(backend)

    result = await service.get_user_capabilities("emulator-5554")

    assert result.max_users == 4


@pytest.mark.asyncio
async def test_get_user_capabilities__max_running_users_parses_bare_int() -> None:
    backend = FakeBackend(
        max_running_users_result=CommandResult(stdout="2\n", stderr="", exit_code=0, duration_ms=20.0)
    )
    service = UserService(backend)

    result = await service.get_user_capabilities("emulator-5554")

    assert result.max_running_users == 2


@pytest.mark.asyncio
async def test_get_user_capabilities__headless_system_user_mode_true() -> None:
    backend = FakeBackend(
        headless_system_user_mode_result=CommandResult(
            stdout="true\n", stderr="", exit_code=0, duration_ms=20.0
        )
    )
    service = UserService(backend)

    result = await service.get_user_capabilities("emulator-5554")

    assert result.headless_system_user_mode is True


@pytest.mark.asyncio
async def test_get_user_capabilities__headless_system_user_mode_false() -> None:
    service = UserService(FakeBackend())

    result = await service.get_user_capabilities("emulator-5554")

    assert result.headless_system_user_mode is False


@pytest.mark.asyncio
async def test_get_user_capabilities__visible_background_users_supported_true() -> None:
    backend = FakeBackend(
        visible_background_users_supported_result=CommandResult(
            stdout="true\n", stderr="", exit_code=0, duration_ms=20.0
        )
    )
    service = UserService(backend)

    result = await service.get_user_capabilities("emulator-5554")

    assert result.visible_background_users_supported is True


@pytest.mark.asyncio
async def test_get_user_capabilities__one_tier2_capability_unrecognized_degrades_to_none() -> None:
    # An older Android build that doesn't recognize this cmd user subcommand:
    # non-zero exit, no "not found" — should degrade to None, not fail the call.
    backend = FakeBackend(
        headless_system_user_mode_result=CommandResult(
            stdout="", stderr="Unknown command: is-headless-system-user-mode", exit_code=1, duration_ms=20.0
        )
    )
    service = UserService(backend)

    result = await service.get_user_capabilities("emulator-5554")

    assert result.headless_system_user_mode is None
    # The rest of the call still succeeds and is populated normally.
    assert result.supports_multiple_users is True
    assert result.max_users == 4


@pytest.mark.asyncio
async def test_get_user_capabilities__on_device_shell_not_found_degrades_to_none_not_device_not_found() -> None:
    # A pre-Android-7 build lacking the `cmd` binary entirely fails at the
    # on-device shell level ("cmd: not found"), NOT the adb-client level
    # ("adb: device '<serial>' not found") — this must still degrade to None
    # like any other unrecognized Tier 2 subcommand, not be misclassified as
    # a transport failure just because its message also contains "not found".
    backend = FakeBackend(
        headless_system_user_mode_result=CommandResult(
            stdout="", stderr="/system/bin/sh: cmd: not found", exit_code=127, duration_ms=15.0
        )
    )
    service = UserService(backend)

    result = await service.get_user_capabilities("emulator-5554")

    assert result.headless_system_user_mode is None
    assert result.supports_multiple_users is True


@pytest.mark.asyncio
async def test_get_user_capabilities__unparseable_tier1_boolean_raises_backend_error() -> None:
    backend = FakeBackend(
        supports_multiple_users_result=CommandResult(
            stdout="unexpected garbage\n", stderr="", exit_code=0, duration_ms=20.0
        )
    )
    service = UserService(backend)

    with pytest.raises(BackendError):
        await service.get_user_capabilities("emulator-5554")


@pytest.mark.asyncio
async def test_get_user_capabilities__unparseable_tier1_integer_raises_backend_error() -> None:
    backend = FakeBackend(
        max_users_result=CommandResult(stdout="unexpected garbage\n", stderr="", exit_code=0, duration_ms=20.0)
    )
    service = UserService(backend)

    with pytest.raises(BackendError):
        await service.get_user_capabilities("emulator-5554")


@pytest.mark.asyncio
async def test_get_user_capabilities__tier1_command_unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        supports_multiple_users_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = UserService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.get_user_capabilities("bogus")


@pytest.mark.asyncio
async def test_get_user_capabilities__tier2_command_not_found_still_fails_whole_call() -> None:
    # A genuine transport failure on a Tier 2 command must not be swallowed
    # just because that command is "optional".
    backend = FakeBackend(
        visible_background_users_on_default_display_supported_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = UserService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.get_user_capabilities("bogus")


@pytest.mark.asyncio
async def test_get_user_capabilities__adb_unavailable_propagates_as_error() -> None:
    service = UserService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.get_user_capabilities("emulator-5554")


def test_user_capabilities_summary_mentions_support_and_limits() -> None:
    summary = UserCapabilities(
        serial="emulator-5554",
        supports_multiple_users=True,
        max_users=4,
        max_running_users=4,
        headless_system_user_mode=False,
        visible_background_users_supported=False,
        visible_background_users_on_default_display_supported=False,
    ).summary()
    assert "emulator-5554" in summary
    assert "supports multiple users" in summary
    assert "4" in summary


def test_user_capabilities_summary_mentions_lack_of_support() -> None:
    summary = UserCapabilities(
        serial="emulator-5554",
        supports_multiple_users=False,
        max_users=1,
        max_running_users=1,
        headless_system_user_mode=None,
        visible_background_users_supported=None,
        visible_background_users_on_default_display_supported=None,
    ).summary()
    assert "does not support multiple users" in summary
