"""Layer 1 unit tests: PackagesService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    AndroidRejectionError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PackageNotFoundError,
    UserNotFoundError,
)
from adb_automation_mcp.modules.packages.service import PackageList, PackagesService


def test_service_constructs_with_backend() -> None:
    service = PackagesService(FakeBackend())

    assert service is not None


@pytest.mark.asyncio
async def test_list_packages__parses_real_pm_list_packages_output() -> None:
    service = PackagesService(FakeBackend())

    result = await service.list_packages("emulator-5554")

    assert result.serial == "emulator-5554"
    assert result.packages == [
        "com.android.chrome",
        "com.example.thirdparty",
        "com.android.systemui",
    ]


@pytest.mark.asyncio
async def test_list_packages__no_packages_returns_empty_list() -> None:
    backend = FakeBackend(
        list_packages_result=CommandResult(stdout="", stderr="", exit_code=0, duration_ms=50.0)
    )
    service = PackagesService(backend)

    result = await service.list_packages("emulator-5554")

    assert result.packages == []


@pytest.mark.asyncio
async def test_list_packages__user_id_included_in_command() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PackagesService(RecordingBackend())

    await service.list_packages("emulator-5554", user_id=10)

    assert captured["command"] == "pm list packages --user 10"


@pytest.mark.asyncio
async def test_list_packages__system_filter_adds_dash_s_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PackagesService(RecordingBackend())

    await service.list_packages("emulator-5554", package_filter="system")

    assert captured["command"] == "pm list packages -s"


@pytest.mark.asyncio
async def test_list_packages__third_party_filter_adds_dash_3_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PackagesService(RecordingBackend())

    await service.list_packages("emulator-5554", package_filter="third_party")

    assert captured["command"] == "pm list packages -3"


@pytest.mark.asyncio
async def test_list_packages__filter_and_user_id_combine_in_command() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PackagesService(RecordingBackend())

    await service.list_packages("emulator-5554", user_id=0, package_filter="third_party")

    assert captured["command"] == "pm list packages -3 --user 0"


@pytest.mark.asyncio
async def test_list_packages__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        list_packages_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = PackagesService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.list_packages("bogus")


@pytest.mark.asyncio
async def test_list_packages__other_nonzero_exit_raises_backend_error() -> None:
    backend = FakeBackend(
        list_packages_result=CommandResult(
            stdout="", stderr="some other pm failure", exit_code=1, duration_ms=10.0
        )
    )
    service = PackagesService(backend)

    with pytest.raises(BackendError):
        await service.list_packages("emulator-5554")


@pytest.mark.asyncio
async def test_list_packages__adb_unavailable_propagates_as_error() -> None:
    service = PackagesService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.list_packages("emulator-5554")


def test_package_list_summary_pluralizes_correctly() -> None:
    assert "1 package " in PackageList(serial="s", packages=["a"]).summary() + " "
    assert "2 packages" in PackageList(serial="s", packages=["a", "b"]).summary()
    assert "0 packages" in PackageList(serial="s", packages=[]).summary()


# --- install_apk -------------------------------------------------------


class _RecordingInstallBackend(FakeBackend):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[tuple[str, str, list[str]]] = []

    async def install(self, serial: str, apk_path: str, flags: list[str]) -> CommandResult:
        self.calls.append((serial, apk_path, flags))
        return await super().install(serial, apk_path, flags)


@pytest.mark.asyncio
async def test_install_apk__ordinary_install_sends_no_flags() -> None:
    backend = _RecordingInstallBackend()
    service = PackagesService(backend)

    result = await service.install_apk("emulator-5554", "/tmp/app.apk")

    assert result.success is True
    assert result.apk_path == "/tmp/app.apk"
    assert result.user_id is None
    assert backend.calls == [("emulator-5554", "/tmp/app.apk", [])]


@pytest.mark.asyncio
async def test_install_apk__user_specific_install() -> None:
    backend = _RecordingInstallBackend()
    service = PackagesService(backend)

    result = await service.install_apk("emulator-5554", "/tmp/app.apk", user_id=10)

    assert result.user_id == 10
    assert backend.calls[0][2] == ["--user", "10"]


@pytest.mark.asyncio
async def test_install_apk__replace_existing_sends_dash_r() -> None:
    backend = _RecordingInstallBackend()
    service = PackagesService(backend)

    result = await service.install_apk("emulator-5554", "/tmp/app.apk", replace_existing=True)

    assert result.replace_existing is True
    assert backend.calls[0][2] == ["-r"]


@pytest.mark.asyncio
async def test_install_apk__allow_downgrade_sends_dash_d() -> None:
    backend = _RecordingInstallBackend()
    service = PackagesService(backend)

    result = await service.install_apk("emulator-5554", "/tmp/app.apk", allow_downgrade=True)

    assert result.allow_downgrade is True
    assert backend.calls[0][2] == ["-d"]


@pytest.mark.asyncio
async def test_install_apk__grant_runtime_permissions_sends_dash_g() -> None:
    backend = _RecordingInstallBackend()
    service = PackagesService(backend)

    result = await service.install_apk("emulator-5554", "/tmp/app.apk", grant_runtime_permissions=True)

    assert result.grant_runtime_permissions is True
    assert backend.calls[0][2] == ["-g"]


@pytest.mark.asyncio
async def test_install_apk__allow_test_packages_sends_dash_t() -> None:
    backend = _RecordingInstallBackend()
    service = PackagesService(backend)

    result = await service.install_apk("emulator-5554", "/tmp/app.apk", allow_test_packages=True)

    assert result.allow_test_packages is True
    assert backend.calls[0][2] == ["-t"]


@pytest.mark.asyncio
async def test_install_apk__force_sdk_sends_force_sdk_flag() -> None:
    backend = _RecordingInstallBackend()
    service = PackagesService(backend)

    result = await service.install_apk("emulator-5554", "/tmp/app.apk", force_sdk=True)

    assert result.force_sdk is True
    assert backend.calls[0][2] == ["--force-sdk"]


@pytest.mark.asyncio
async def test_install_apk__multiple_options_combine_in_order() -> None:
    backend = _RecordingInstallBackend()
    service = PackagesService(backend)

    result = await service.install_apk(
        "emulator-5554",
        "/tmp/app.apk",
        user_id=10,
        replace_existing=True,
        allow_downgrade=True,
        grant_runtime_permissions=True,
        allow_test_packages=True,
        force_sdk=True,
    )

    assert result.success is True
    assert backend.calls[0][2] == ["--user", "10", "-r", "-d", "-g", "-t", "--force-sdk"]


@pytest.mark.asyncio
async def test_install_apk__pm_rejection_raises_android_rejection_error() -> None:
    backend = FakeBackend(
        install_result=CommandResult(
            stdout="Performing Streamed Install\nFailure [INSTALL_FAILED_ALREADY_EXISTS: ...]\n",
            stderr="",
            exit_code=1,
            duration_ms=100.0,
        )
    )
    service = PackagesService(backend)

    with pytest.raises(AndroidRejectionError) as exc_info:
        await service.install_apk("emulator-5554", "/tmp/app.apk")

    assert exc_info.value.details["reason"] == "INSTALL_FAILED_ALREADY_EXISTS: ..."


@pytest.mark.asyncio
async def test_install_apk__empty_apk_path_raises_invalid_argument() -> None:
    service = PackagesService(FakeBackend())

    with pytest.raises(InvalidArgumentError):
        await service.install_apk("emulator-5554", "   ")


@pytest.mark.asyncio
async def test_install_apk__negative_user_id_raises_invalid_argument() -> None:
    service = PackagesService(FakeBackend())

    with pytest.raises(InvalidArgumentError):
        await service.install_apk("emulator-5554", "/tmp/app.apk", user_id=-1)


@pytest.mark.asyncio
async def test_install_apk__backend_unavailable_propagates() -> None:
    service = PackagesService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.install_apk("emulator-5554", "/tmp/app.apk")


@pytest.mark.asyncio
async def test_install_apk__generic_nonzero_exit_raises_backend_error() -> None:
    backend = FakeBackend(
        install_result=CommandResult(stdout="", stderr="unexpected adb failure", exit_code=1, duration_ms=10.0)
    )
    service = PackagesService(backend)

    with pytest.raises(BackendError):
        await service.install_apk("emulator-5554", "/tmp/app.apk")


# --- uninstall_package ---------------------------------------------------


@pytest.mark.asyncio
async def test_uninstall_package__normal_uninstall() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PackagesService(RecordingBackend())

    result = await service.uninstall_package("emulator-5554", "com.example.app")

    assert result.success is True
    assert result.user_id is None
    assert captured["command"] == "pm uninstall com.example.app"


@pytest.mark.asyncio
async def test_uninstall_package__user_specific_uninstall_does_not_become_all_users() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PackagesService(RecordingBackend())

    result = await service.uninstall_package("emulator-5554", "com.example.app", user_id=10)

    assert result.user_id == 10
    assert captured["command"] == "pm uninstall --user 10 com.example.app"
    assert "--user all" not in captured["command"]


@pytest.mark.asyncio
async def test_uninstall_package__keep_data_sends_dash_k() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PackagesService(RecordingBackend())

    result = await service.uninstall_package("emulator-5554", "com.example.app", keep_data=True)

    assert result.keep_data is True
    assert captured["command"] == "pm uninstall -k com.example.app"


@pytest.mark.asyncio
async def test_uninstall_package__version_specific_uninstall() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PackagesService(RecordingBackend())

    result = await service.uninstall_package("emulator-5554", "com.example.app", version_code=5)

    assert result.version_code == 5
    assert captured["command"] == "pm uninstall --versionCode 5 com.example.app"


@pytest.mark.asyncio
async def test_uninstall_package__package_missing_raises_package_not_found() -> None:
    backend = FakeBackend(
        pm_uninstall_result=CommandResult(
            stdout="Failure [DELETE_FAILED_INTERNAL_ERROR]\n", stderr="", exit_code=1, duration_ms=50.0
        )
    )
    service = PackagesService(backend)

    with pytest.raises(PackageNotFoundError):
        await service.uninstall_package("emulator-5554", "com.doesnt.exist")


@pytest.mark.asyncio
async def test_uninstall_package__not_installed_for_target_user_raises_package_not_found() -> None:
    backend = FakeBackend(
        pm_uninstall_result=CommandResult(
            stdout="Failure [not installed for 0]\n", stderr="", exit_code=1, duration_ms=50.0
        )
    )
    service = PackagesService(backend)

    with pytest.raises(PackageNotFoundError):
        await service.uninstall_package("emulator-5554", "com.example.app", user_id=0)


@pytest.mark.asyncio
async def test_uninstall_package__nonexistent_user_raises_user_not_found() -> None:
    backend = FakeBackend(
        pm_uninstall_result=CommandResult(
            stdout=(
                "Exception occurred while executing 'uninstall':\n"
                "java.lang.IllegalArgumentException: User 999 does not exist or has been removed\n"
            ),
            stderr="",
            exit_code=1,
            duration_ms=50.0,
        )
    )
    service = PackagesService(backend)

    with pytest.raises(UserNotFoundError):
        await service.uninstall_package("emulator-5554", "com.example.app", user_id=999)


@pytest.mark.asyncio
async def test_uninstall_package__version_mismatch_raises_android_rejection() -> None:
    # Captured live: a --versionCode that doesn't match the installed package
    # produces a bare "Failure [DELETE_FAILED_INTERNAL_ERROR]", exit 1. With a
    # version_code in play that is an on-device rejection, not "not found".
    backend = FakeBackend(
        pm_uninstall_result=CommandResult(
            stdout="Failure [DELETE_FAILED_INTERNAL_ERROR]\n", stderr="", exit_code=1, duration_ms=50.0
        )
    )
    service = PackagesService(backend)

    with pytest.raises(AndroidRejectionError):
        await service.uninstall_package("emulator-5554", "com.example.app", version_code=99)


@pytest.mark.asyncio
async def test_uninstall_package__internal_error_without_version_code_is_package_not_found() -> None:
    # Same bare internal-error reason, but no version_code: nothing matched to
    # remove -> PACKAGE_NOT_FOUND (unchanged behaviour).
    backend = FakeBackend(
        pm_uninstall_result=CommandResult(
            stdout="Failure [DELETE_FAILED_INTERNAL_ERROR]\n", stderr="", exit_code=1, duration_ms=50.0
        )
    )
    service = PackagesService(backend)

    with pytest.raises(PackageNotFoundError):
        await service.uninstall_package("emulator-5554", "com.example.app")


@pytest.mark.asyncio
async def test_uninstall_package__empty_package_name_raises_invalid_argument() -> None:
    service = PackagesService(FakeBackend())

    with pytest.raises(InvalidArgumentError):
        await service.uninstall_package("emulator-5554", "  ")


@pytest.mark.asyncio
async def test_uninstall_package__non_positive_version_code_raises_invalid_argument() -> None:
    service = PackagesService(FakeBackend())

    with pytest.raises(InvalidArgumentError):
        await service.uninstall_package("emulator-5554", "com.example.app", version_code=0)


@pytest.mark.asyncio
async def test_uninstall_package__backend_unavailable_propagates() -> None:
    service = PackagesService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.uninstall_package("emulator-5554", "com.example.app")


# --- install_existing_for_user -------------------------------------------


@pytest.mark.asyncio
async def test_install_existing_for_user__successful_install_existing() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = PackagesService(RecordingBackend())

    result = await service.install_existing_for_user("emulator-5554", "com.example.app", 10)

    assert result.success is True
    assert result.user_id == 10
    assert captured["command"] == "pm install-existing --user 10 com.example.app"
    assert "10" in result.output


@pytest.mark.asyncio
async def test_install_existing_for_user__unknown_package_raises_package_not_found() -> None:
    backend = FakeBackend(
        pm_install_existing_result=CommandResult(
            stdout="", stderr="Unknown package: com.doesnt.exist\n", exit_code=1, duration_ms=50.0
        )
    )
    service = PackagesService(backend)

    with pytest.raises(PackageNotFoundError):
        await service.install_existing_for_user("emulator-5554", "com.doesnt.exist", 10)


@pytest.mark.asyncio
async def test_install_existing_for_user__nonexistent_user_raises_user_not_found() -> None:
    backend = FakeBackend(
        pm_install_existing_result=CommandResult(
            stdout=(
                "Exception occurred while executing:\n"
                "java.lang.IllegalArgumentException: User 999 does not exist or has been removed\n"
            ),
            stderr="",
            exit_code=1,
            duration_ms=50.0,
        )
    )
    service = PackagesService(backend)

    with pytest.raises(UserNotFoundError):
        await service.install_existing_for_user("emulator-5554", "com.example.app", 999)


@pytest.mark.asyncio
async def test_install_existing_for_user__pm_rejection_raises_android_rejection_error() -> None:
    backend = FakeBackend(
        pm_install_existing_result=CommandResult(
            stdout="Failure [INSTALL_FAILED_INTERNAL_ERROR]\n", stderr="", exit_code=1, duration_ms=50.0
        )
    )
    service = PackagesService(backend)

    with pytest.raises(AndroidRejectionError):
        await service.install_existing_for_user("emulator-5554", "com.example.app", 10)


@pytest.mark.asyncio
async def test_install_existing_for_user__empty_package_name_raises_invalid_argument() -> None:
    service = PackagesService(FakeBackend())

    with pytest.raises(InvalidArgumentError):
        await service.install_existing_for_user("emulator-5554", "   ", 10)


@pytest.mark.asyncio
async def test_install_existing_for_user__negative_user_id_raises_invalid_argument() -> None:
    service = PackagesService(FakeBackend())

    with pytest.raises(InvalidArgumentError):
        await service.install_existing_for_user("emulator-5554", "com.example.app", -1)


@pytest.mark.asyncio
async def test_install_existing_for_user__backend_unavailable_propagates() -> None:
    service = PackagesService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.install_existing_for_user("emulator-5554", "com.example.app", 10)
