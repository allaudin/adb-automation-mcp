"""Layer 1 unit tests: AnrService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.anr.service import AnrService

_NO_ENTRIES = (
    "Drop box contents: 1000 entries\n"
    "Max entries: 1000\n"
    "Searching for: data_app_anr system_app_anr\n"
    "\n"
    "(No entries found.)\n"
)


class RecordingBackend(FakeBackend):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.commands: list[str] = []

    async def shell(
        self, serial: str, command: str, timeout_s: float | None = None
    ) -> CommandResult:
        self.commands.append(command)
        return await super().shell(serial, command, timeout_s)


def _cr(stdout: str = "", stderr: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(stdout=stdout, stderr=stderr, exit_code=exit_code, duration_ms=20.0)


@pytest.mark.asyncio
async def test_get_anr_reports__command_and_package_filter_newest_first() -> None:
    backend = RecordingBackend()

    result = await AnrService(backend).get_anr_reports("emulator-5554", "com.example.app")

    assert backend.commands == [
        "dumpsys dropbox --print data_app_anr",
        "dumpsys dropbox --print system_app_anr",
    ]
    assert result.serial == "emulator-5554"
    assert result.package_name == "com.example.app"
    # the com.other.app entry is filtered out; the two com.example.app ones remain
    assert result.count == 2
    # newest first (16:52:25 before 16:50:01)
    assert [r.timestamp for r in result.reports] == [
        "2026-09-06 16:52:25",
        "2026-09-06 16:50:01",
    ]

    first = result.reports[0]
    assert first.tag == "data_app_anr"
    assert first.process == "com.example.app"
    assert first.package == "com.example.app"
    assert first.pid == 12777
    assert first.uid == 10234
    assert first.flags == "0x30c8be45"
    assert first.subject == "ANR in com.example.app (com.example.app/.DetailActivity)"
    assert first.size_bytes == 1042
    assert first.trace is not None
    assert '"main" prio=5 tid=1 Native' in first.trace


@pytest.mark.asyncio
async def test_get_anr_reports__limit_caps_results() -> None:
    result = await AnrService(FakeBackend()).get_anr_reports(
        "emulator-5554", "com.example.app", limit=1
    )

    assert result.count == 1
    assert result.reports[0].timestamp == "2026-09-06 16:52:25"


@pytest.mark.asyncio
async def test_get_anr_reports__include_traces_false_drops_body_keeps_headers() -> None:
    result = await AnrService(FakeBackend()).get_anr_reports(
        "emulator-5554", "com.example.app", include_traces=False
    )

    assert result.count == 2
    for report in result.reports:
        assert report.trace is None
        assert report.subject is not None
        assert report.pid is not None


@pytest.mark.asyncio
async def test_get_anr_reports__no_entries_is_valid_empty() -> None:
    backend = FakeBackend(dropbox_print_result=_cr(stdout=_NO_ENTRIES))

    result = await AnrService(backend).get_anr_reports("emulator-5554", "com.example.app")

    assert result.count == 0
    assert result.reports == []
    assert "No ANR reports" in result.summary()


@pytest.mark.asyncio
async def test_get_anr_reports__package_with_no_matching_entries_is_empty() -> None:
    result = await AnrService(FakeBackend()).get_anr_reports(
        "emulator-5554", "com.nomatch.here"
    )

    assert result.count == 0


@pytest.mark.asyncio
async def test_get_anr_reports__blank_package_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await AnrService(ExplodingBackend()).get_anr_reports("emulator-5554", "   ")


@pytest.mark.asyncio
async def test_get_anr_reports__out_of_range_limit_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await AnrService(ExplodingBackend()).get_anr_reports("emulator-5554", "com.x", limit=0)
    with pytest.raises(InvalidArgumentError):
        await AnrService(ExplodingBackend()).get_anr_reports("emulator-5554", "com.x", limit=999)


@pytest.mark.asyncio
async def test_get_anr_reports__system_app_anr_tag_is_included() -> None:
    backend = FakeBackend(
        dropbox_print_result=_cr(stdout=_NO_ENTRIES),
        dropbox_system_anr_result=_cr(
            stdout=(
                "Searching for: system_app_anr\n"
                "\n"
                "========================================\n"
                "2026-09-06 10:00:00 system_app_anr (text, 300 bytes)\n"
                "Process: com.android.systemui\n"
                "PID: 1224\n"
                "Package: com.android.systemui v37 (Baklava)\n"
                "\n"
                "Subject: ANR in com.android.systemui\n"
                '"main" prio=5 tid=1 Blocked\n'
            )
        ),
    )

    result = await AnrService(backend).get_anr_reports("emulator-5554", "com.android.systemui")

    assert result.count == 1
    assert result.reports[0].tag == "system_app_anr"


@pytest.mark.asyncio
async def test_get_anr_reports__garbage_output_does_not_crash() -> None:
    backend = FakeBackend(
        dropbox_print_result=_cr(stdout="\x00 not dropbox output }}} === garbage ===\n")
    )

    result = await AnrService(backend).get_anr_reports("emulator-5554", "com.example.app")

    assert result.count == 0


@pytest.mark.asyncio
async def test_get_anr_reports__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        dropbox_print_result=_cr(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )

    with pytest.raises(DeviceNotFoundError):
        await AnrService(backend).get_anr_reports("bogus", "com.example.app")


@pytest.mark.asyncio
async def test_get_anr_reports__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        dropbox_print_result=_cr(stderr="Permission Denial: can't dump dropbox\n", exit_code=1)
    )

    with pytest.raises(PermissionDeniedError):
        await AnrService(backend).get_anr_reports("emulator-5554", "com.example.app")


@pytest.mark.asyncio
async def test_get_anr_reports__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(dropbox_print_result=_cr(stderr="something odd\n", exit_code=2))

    with pytest.raises(BackendError):
        await AnrService(backend).get_anr_reports("emulator-5554", "com.example.app")


@pytest.mark.asyncio
async def test_get_anr_reports__backend_unavailable_raises_adb_unavailable() -> None:
    with pytest.raises(AdbUnavailableError):
        await AnrService(FakeBackend(unavailable=True)).get_anr_reports(
            "emulator-5554", "com.example.app"
        )
