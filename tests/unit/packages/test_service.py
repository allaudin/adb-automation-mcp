"""Layer 1 unit tests: PackagesService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import AdbUnavailableError, BackendError, DeviceNotFoundError
from adb_mcp.modules.packages.service import PackageList, PackagesService


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
