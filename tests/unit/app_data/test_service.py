"""Layer 1 unit tests: AppDataService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AndroidRejectionError,
    BackendError,
    DeviceNotFoundError,
    PackageNotFoundError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.app_data.service import AppDataService


@pytest.mark.asyncio
async def test_clear_app_data__success() -> None:
    service = AppDataService(FakeBackend())

    result = await service.clear_app_data("emulator-5554", "com.example.app")

    assert result.serial == "emulator-5554"
    assert result.package_name == "com.example.app"
    assert result.user_id is None
    assert result.success is True


@pytest.mark.asyncio
async def test_clear_app_data__sends_bare_pm_clear_and_user_id_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = AppDataService(RecordingBackend())

    result = await service.clear_app_data("emulator-5554", "com.example.app", user_id=10)

    assert captured["command"] == "pm clear --user 10 com.example.app"
    assert result.user_id == 10


@pytest.mark.asyncio
async def test_clear_app_data__no_user_id_omits_user_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = AppDataService(RecordingBackend())

    await service.clear_app_data("emulator-5554", "com.example.app")

    assert captured["command"] == "pm clear com.example.app"


@pytest.mark.asyncio
async def test_clear_app_data__package_not_found_raises_package_not_found() -> None:
    backend = FakeBackend(
        clear_app_data_result=CommandResult(
            stdout="", stderr="Error: Package not found: com.example.bogus\n", exit_code=1, duration_ms=15.0
        )
    )
    service = AppDataService(backend)

    with pytest.raises(PackageNotFoundError):
        await service.clear_app_data("emulator-5554", "com.example.bogus")


@pytest.mark.asyncio
async def test_clear_app_data__android_rejection_raises_android_rejection() -> None:
    backend = FakeBackend(
        clear_app_data_result=CommandResult(stdout="Failed\n", stderr="", exit_code=0, duration_ms=40.0)
    )
    service = AppDataService(backend)

    with pytest.raises(AndroidRejectionError):
        await service.clear_app_data("emulator-5554", "com.example.app")


@pytest.mark.asyncio
async def test_clear_app_data__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        clear_app_data_result=CommandResult(
            stdout="",
            stderr="java.lang.SecurityException: Permission Denial: clearApplicationUserData\n",
            exit_code=1,
            duration_ms=12.0,
        )
    )
    service = AppDataService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.clear_app_data("emulator-5554", "com.example.app")


@pytest.mark.asyncio
async def test_clear_app_data__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        clear_app_data_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = AppDataService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.clear_app_data("bogus", "com.example.app")


@pytest.mark.asyncio
async def test_clear_app_data__unclassified_backend_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        clear_app_data_result=CommandResult(
            stdout="", stderr="Error: Package manager has died\n", exit_code=1, duration_ms=5.0
        )
    )
    service = AppDataService(backend)

    with pytest.raises(BackendError):
        await service.clear_app_data("emulator-5554", "com.example.app")


# --- clear_app_cache ---------------------------------------------------------


from adb_automation_mcp.errors import CacheOnlyUnsupportedError
from adb_automation_mcp.modules.app_data.service import ClearAppCacheResult


class _ShellRec(FakeBackend):
    def __init__(self, **kw: object) -> None:
        super().__init__(**kw)  # type: ignore[arg-type]
        self.cmds: list[str] = []

    async def shell(self, serial: str, command: str) -> CommandResult:
        self.cmds.append(command)
        return await super().shell(serial, command)


@pytest.mark.asyncio
async def test_clear_app_cache__pm_path_constructs_command_and_resolves_current_user() -> None:
    b = _ShellRec()
    r = await AppDataService(b).clear_app_cache("emulator-5554", "com.example.app")
    assert "pm clear --cache-only com.example.app" in b.cmds
    assert "am get-current-user" in b.cmds  # resolved because user_id omitted
    assert isinstance(r, ClearAppCacheResult)
    assert r.method == "pm_clear_cache_only"
    assert r.user_id == 0
    assert r.success is True


@pytest.mark.asyncio
async def test_clear_app_cache__explicit_user_scope_flag_after_cache_only() -> None:
    b = _ShellRec()
    r = await AppDataService(b).clear_app_cache("emulator-5554", "com.example.app", user_id=10)
    assert b.cmds == ["pm clear --cache-only --user 10 com.example.app"]
    assert r.user_id == 10


@pytest.mark.asyncio
async def test_clear_app_cache__unsupported_flag_falls_back_to_rm() -> None:
    b = _ShellRec(
        pm_clear_cache_result=CommandResult(
            stdout="", stderr="Error: Unknown option: --cache-only\n", exit_code=1, duration_ms=5.0
        )
    )
    r = await AppDataService(b).clear_app_cache("emulator-5554", "com.example.app", user_id=10)
    assert r.method == "rm_cache_dirs"
    assert r.success is True
    rm_cmd = next(c for c in b.cmds if c.startswith("rm -rf "))
    assert "/data/user/10/com.example.app/cache" in rm_cmd
    assert "/data/user/10/com.example.app/code_cache" in rm_cmd
    assert "/data/user_de/10/com.example.app/cache" in rm_cmd
    # never an unscoped pm clear
    assert not any(c == "pm clear com.example.app" for c in b.cmds)


@pytest.mark.asyncio
async def test_clear_app_cache__hang_times_out_then_falls_back_to_rm() -> None:
    b = _ShellRec(pm_clear_cache_timeout=True)
    r = await AppDataService(b).clear_app_cache("emulator-5554", "com.example.app", user_id=0)
    assert r.method == "rm_cache_dirs"
    assert any(c.startswith("rm -rf ") for c in b.cmds)


@pytest.mark.asyncio
async def test_clear_app_cache__rm_fallback_permission_denied_raises_cache_only_unsupported() -> None:
    b = FakeBackend(
        pm_clear_cache_timeout=True,
        rm_cache_result=CommandResult(
            stdout="", stderr="rm: /data/user/0/com.example.app/cache: Permission denied\n",
            exit_code=1, duration_ms=5.0,
        ),
    )
    with pytest.raises(CacheOnlyUnsupportedError):
        await AppDataService(b).clear_app_cache("emulator-5554", "com.example.app", user_id=0)


@pytest.mark.asyncio
async def test_clear_app_cache__failed_outcome_raises_android_rejected() -> None:
    b = FakeBackend(
        pm_clear_cache_result=CommandResult(stdout="Failed\n", stderr="", exit_code=0, duration_ms=5.0)
    )
    with pytest.raises(AndroidRejectionError):
        await AppDataService(b).clear_app_cache("emulator-5554", "com.example.app", user_id=0)


@pytest.mark.asyncio
async def test_clear_app_cache__unknown_package_raises_package_not_found() -> None:
    b = FakeBackend(
        pm_clear_cache_result=CommandResult(
            stdout="", stderr="Error: Package com.zzz.nope not found\n", exit_code=1, duration_ms=5.0
        )
    )
    with pytest.raises(PackageNotFoundError):
        await AppDataService(b).clear_app_cache("emulator-5554", "com.zzz.nope", user_id=0)


@pytest.mark.asyncio
async def test_clear_app_cache__unknown_serial_raises_device_not_found() -> None:
    b = FakeBackend(
        pm_clear_cache_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    with pytest.raises(DeviceNotFoundError):
        await AppDataService(b).clear_app_cache("bogus", "com.example.app", user_id=0)


def test_clear_app_cache_result_summary() -> None:
    assert ClearAppCacheResult(
        serial="emulator-5554", package_name="com.x", user_id=0,
        method="pm_clear_cache_only", success=True, output="Success\n",
    ).summary() == "Cleared cache for com.x (user 0) on emulator-5554."
    assert "(via rm)" in ClearAppCacheResult(
        serial="emulator-5554", package_name="com.x", user_id=10,
        method="rm_cache_dirs", success=True, output="removed: ...",
    ).summary()
