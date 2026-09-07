"""Layer 1 unit tests: DiagnosticsService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from adb_automation_mcp.backend.protocol import CommandResult, DeviceInfo
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PolicyViolationError,
)
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


# --- generate_bugreport ------------------------------------------------

_ONLINE = [DeviceInfo(serial="emulator-5554", state="device")]


@pytest.mark.asyncio
async def test_generate_bugreport__zip_success(tmp_path: Path) -> None:
    service = DiagnosticsService(FakeBackend(devices=_ONLINE), local_root=tmp_path)

    result = await service.generate_bugreport("emulator-5554", "device.zip")

    assert result.success is True
    assert result.is_zip is True
    assert result.local_path == str(tmp_path / "bugreports" / "device.zip")
    assert result.size_bytes is not None and result.size_bytes > 0


@pytest.mark.asyncio
async def test_generate_bugreport__no_extension_gets_zip(tmp_path: Path) -> None:
    service = DiagnosticsService(FakeBackend(devices=_ONLINE), local_root=tmp_path)

    result = await service.generate_bugreport("emulator-5554", "device")

    assert result.local_path == str(tmp_path / "bugreports" / "device.zip")
    assert result.is_zip is True


@pytest.mark.asyncio
async def test_generate_bugreport__unknown_serial_fails_fast(tmp_path: Path) -> None:
    # no wait-for-device block: the preflight rejects it before backend.bugreport
    backend = FakeBackend(devices=[DeviceInfo(serial="emulator-5556", state="device")])
    with pytest.raises(DeviceNotFoundError):
        await DiagnosticsService(backend, local_root=tmp_path).generate_bugreport(
            "emulator-5554", "device.zip"
        )


@pytest.mark.asyncio
async def test_generate_bugreport__offline_serial_fails_fast(tmp_path: Path) -> None:
    backend = FakeBackend(devices=[DeviceInfo(serial="emulator-5554", state="offline")])
    with pytest.raises(DeviceNotFoundError):
        await DiagnosticsService(backend, local_root=tmp_path).generate_bugreport(
            "emulator-5554", "device.zip"
        )


@pytest.mark.asyncio
async def test_generate_bugreport__no_local_root_raises_policy() -> None:
    with pytest.raises(PolicyViolationError):
        await DiagnosticsService(FakeBackend(), local_root=None).generate_bugreport(
            "emulator-5554", "device.zip"
        )


@pytest.mark.asyncio
async def test_generate_bugreport__path_traversal_rejected(tmp_path: Path) -> None:
    with pytest.raises(PolicyViolationError):
        await DiagnosticsService(FakeBackend(), local_root=tmp_path).generate_bugreport(
            "emulator-5554", "../../escape.zip"
        )


@pytest.mark.asyncio
async def test_generate_bugreport__blank_path_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidArgumentError):
        await DiagnosticsService(FakeBackend(), local_root=tmp_path).generate_bugreport(
            "emulator-5554", "  "
        )


@pytest.mark.asyncio
async def test_generate_bugreport__bad_timeout_rejected(tmp_path: Path) -> None:
    with pytest.raises(InvalidArgumentError):
        await DiagnosticsService(FakeBackend(), local_root=tmp_path).generate_bugreport(
            "emulator-5554", "device.zip", timeout_s=5
        )


@pytest.mark.asyncio
async def test_generate_bugreport__adb_failure_disconnect_raises_device_not_found(
    tmp_path: Path,
) -> None:
    backend = FakeBackend(
        devices=_ONLINE,
        bugreport_result=CommandResult(
            stdout="", stderr="error: no devices/emulators found\n", exit_code=1, duration_ms=10.0
        ),
    )
    with pytest.raises(DeviceNotFoundError):
        await DiagnosticsService(backend, local_root=tmp_path).generate_bugreport(
            "emulator-5554", "device.zip"
        )


@pytest.mark.asyncio
async def test_generate_bugreport__adb_failure_other_raises_backend_error(tmp_path: Path) -> None:
    backend = FakeBackend(
        devices=_ONLINE,
        bugreport_result=CommandResult(
            stdout="", stderr="something broke\n", exit_code=1, duration_ms=10.0
        ),
    )
    with pytest.raises(BackendError):
        await DiagnosticsService(backend, local_root=tmp_path).generate_bugreport(
            "emulator-5554", "device.zip"
        )


@pytest.mark.asyncio
async def test_generate_bugreport__backend_unavailable(tmp_path: Path) -> None:
    with pytest.raises(AdbUnavailableError):
        await DiagnosticsService(FakeBackend(unavailable=True), local_root=tmp_path).generate_bugreport(
            "emulator-5554", "device.zip"
        )
