"""Layer 1 unit tests: DiagnosticsService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult, DeviceInfo
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import AdbUnavailableError, BackendError
from adb_automation_mcp.modules.diagnostics.service import AdbVersionInfo, DiagnosticsService


@pytest.mark.asyncio
async def test_check_adb_available__adb_reachable_with_devices_reports_available_true() -> None:
    backend = FakeBackend(devices=[DeviceInfo(serial="emulator-5554", state="device")])
    service = DiagnosticsService(backend)

    result = await service.check_adb_available()

    assert result.available is True
    assert result.device_count == 1
    assert result.reason is None


@pytest.mark.asyncio
async def test_check_adb_available__adb_reachable_with_no_devices_still_available_true() -> None:
    backend = FakeBackend(devices=[])
    service = DiagnosticsService(backend)

    result = await service.check_adb_available()

    assert result.available is True
    assert result.device_count == 0


@pytest.mark.asyncio
async def test_check_adb_available__adb_missing_reports_available_false_not_an_error() -> None:
    backend = FakeBackend(unavailable=True)
    service = DiagnosticsService(backend)

    result = await service.check_adb_available()

    assert result.available is False
    assert result.reason is not None
    assert result.device_count is None


def test_summary_mentions_device_count_when_available() -> None:
    from adb_automation_mcp.modules.diagnostics.service import AdbAvailability

    assert "2 devices" in AdbAvailability(available=True, device_count=2).summary()
    assert "1 device " in AdbAvailability(available=True, device_count=1).summary() + " "


def test_summary_explains_reason_when_unavailable() -> None:
    from adb_automation_mcp.modules.diagnostics.service import AdbAvailability

    summary = AdbAvailability(available=False, reason="adb not on PATH").summary()
    assert "not available" in summary
    assert "adb not on PATH" in summary


# --- get_adb_version ---------------------------------------------------------


def _version_backend(stdout: str, *, exit_code: int = 0, stderr: str = "") -> FakeBackend:
    return FakeBackend(
        version_result=CommandResult(
            stdout=stdout, stderr=stderr, exit_code=exit_code, duration_ms=8.0
        )
    )


@pytest.mark.asyncio
async def test_get_adb_version__modern_output_parses_every_line() -> None:
    # Real captured `adb version` output (this repo's build host).
    service = DiagnosticsService(
        _version_backend(
            "Android Debug Bridge version 1.0.41\n"
            "Version 37.0.0-eng.allaud\n"
            "Installed as /media/allaudin/extusb/out/host/linux-x86/bin/adb\n"
            "Running on Linux 6.8.0-138-generic (x86_64)\n"
        )
    )

    result = await service.get_adb_version()

    assert result.bridge_version == "1.0.41"
    assert result.platform_tools_version == "37.0.0-eng.allaud"
    assert result.installed_path == "/media/allaudin/extusb/out/host/linux-x86/bin/adb"
    assert result.running_on == "Linux 6.8.0-138-generic (x86_64)"
    assert result.revision is None
    assert result.raw.startswith("Android Debug Bridge version 1.0.41")


@pytest.mark.asyncio
async def test_get_adb_version__default_fake_backend_fixture_parses() -> None:
    result = await DiagnosticsService(FakeBackend()).get_adb_version()

    assert result.bridge_version == "1.0.41"
    assert result.platform_tools_version == "37.0.0-eng.allaud"


@pytest.mark.asyncio
async def test_get_adb_version__older_output_with_revision_and_no_version_line() -> None:
    # Pre-2017 platform-tools printed only the bridge line plus a Revision line.
    service = DiagnosticsService(
        _version_backend(
            "Android Debug Bridge version 1.0.36\nRevision 0e9850346394-android\n"
        )
    )

    result = await service.get_adb_version()

    assert result.bridge_version == "1.0.36"
    assert result.revision == "0e9850346394-android"
    assert result.platform_tools_version is None
    assert result.running_on is None


@pytest.mark.asyncio
async def test_get_adb_version__malformed_output_does_not_crash_and_keeps_raw() -> None:
    service = DiagnosticsService(_version_backend("totally unrecognizable garbage\n"))

    result = await service.get_adb_version()

    assert result.bridge_version is None
    assert result.platform_tools_version is None
    assert result.raw == "totally unrecognizable garbage"


@pytest.mark.asyncio
async def test_get_adb_version__non_zero_exit_is_translated_to_backend_error() -> None:
    service = DiagnosticsService(
        _version_backend("", exit_code=1, stderr="adb: unknown command version\n")
    )

    with pytest.raises(BackendError) as excinfo:
        await service.get_adb_version()

    assert "unknown command version" in str(excinfo.value)
    assert excinfo.value.details["exit_code"] == 1


@pytest.mark.asyncio
async def test_get_adb_version__adb_missing_propagates_unavailable_error() -> None:
    service = DiagnosticsService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.get_adb_version()


def test_adb_version_info_summary_prefers_platform_tools_then_bridge() -> None:
    assert "platform-tools 35.0.2" in AdbVersionInfo(
        raw="", bridge_version="1.0.41", platform_tools_version="35.0.2"
    ).summary()
    assert "bridge version 1.0.41" in AdbVersionInfo(raw="", bridge_version="1.0.41").summary()
    assert "no recognizable version line" in AdbVersionInfo(raw="junk").summary()
