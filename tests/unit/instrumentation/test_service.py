"""Layer 1 unit tests: InstrumentationService against FakeBackend directly — no
MCP registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import shlex

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InstrumentationFailedError,
    InvalidArgumentError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.instrumentation.service import InstrumentationService

_COMPONENT = "com.example.test/androidx.test.runner.AndroidJUnitRunner"


class RecordingBackend(FakeBackend):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self.command: str | None = None
        self.timeout_s: float | None = None

    async def shell(
        self, serial: str, command: str, timeout_s: float | None = None
    ) -> CommandResult:
        self.command = command
        self.timeout_s = timeout_s
        return await super().shell(serial, command, timeout_s)


def _cr(stdout: str = "", stderr: str = "", exit_code: int = 0) -> CommandResult:
    return CommandResult(stdout=stdout, stderr=stderr, exit_code=exit_code, duration_ms=50.0)


_FAILED_OUTPUT = (
    "android.util.AndroidException: INSTRUMENTATION_FAILED: bogus/bogus.Runner\n"
    "\tat com.android.commands.am.Instrument.run(Instrument.java:549)\n"
    "INSTRUMENTATION_STATUS: Error=Unable to find instrumentation info for: "
    "ComponentInfo{bogus/bogus.Runner}\n"
    "INSTRUMENTATION_STATUS: id=ActivityManagerService\n"
    "INSTRUMENTATION_STATUS_CODE: -1\n"
)

_FAILURE_RUN = (
    "INSTRUMENTATION_STATUS: numtests=2\n"
    "INSTRUMENTATION_STATUS: test=testAlpha\n"
    "INSTRUMENTATION_STATUS_CODE: 1\n"
    "INSTRUMENTATION_STATUS: numtests=2\n"
    "INSTRUMENTATION_STATUS: stream=\nException...\n"
    "INSTRUMENTATION_STATUS: test=testAlpha\n"
    "INSTRUMENTATION_STATUS_CODE: -2\n"
    "INSTRUMENTATION_STATUS: numtests=2\n"
    "INSTRUMENTATION_STATUS: test=testBeta\n"
    "INSTRUMENTATION_STATUS_CODE: 1\n"
    "INSTRUMENTATION_STATUS_CODE: 0\n"
    "INSTRUMENTATION_RESULT: stream=\n\nFAILURES!!!\nTests run: 2,  Failures: 1\n\n"
    "INSTRUMENTATION_CODE: -1\n"
)


@pytest.mark.asyncio
async def test_run_instrumentation__default_command_and_all_pass_parse() -> None:
    backend = RecordingBackend()

    result = await InstrumentationService(backend).run_instrumentation("emulator-5554", _COMPONENT)

    assert backend.command == f"am instrument -w -r {_COMPONENT}"
    assert backend.timeout_s == 120.0
    assert result.completed is True
    assert result.result_code == -1
    assert result.tests_total == 2
    assert result.tests_passed == 2
    assert result.tests_failed == 0
    assert result.tests_errored == 0
    assert "OK (2 tests)" in (result.result_stream or "")


@pytest.mark.asyncio
async def test_run_instrumentation__options_map_to_flags_and_e_args() -> None:
    backend = RecordingBackend()

    await InstrumentationService(backend).run_instrumentation(
        "emulator-5554",
        _COMPONENT,
        args={"class": "com.example.FooTest", "size": "small"},
        user_id=10,
        no_window_animation=True,
        timeout_s=30.0,
    )

    assert backend.timeout_s == 30.0
    tokens = shlex.split(backend.command or "")
    assert tokens[:4] == ["am", "instrument", "-w", "-r"]
    assert "--no-window-animation" in tokens
    assert tokens[tokens.index("--user") + 1] == "10"
    # -e key value pairs, in insertion order, before the component (last token)
    assert tokens[-1] == _COMPONENT
    e_idx = [i for i, t in enumerate(tokens) if t == "-e"]
    assert [tokens[i + 1 : i + 3] for i in e_idx] == [
        ["class", "com.example.FooTest"],
        ["size", "small"],
    ]


@pytest.mark.asyncio
async def test_run_instrumentation__assertion_failure_is_returned_as_data() -> None:
    backend = FakeBackend(instrument_result=_cr(stdout=_FAILURE_RUN))

    result = await InstrumentationService(backend).run_instrumentation("emulator-5554", _COMPONENT)

    assert result.completed is True
    assert result.tests_passed == 1
    assert result.tests_failed == 1
    assert result.tests_errored == 0
    assert "FAILURES" in (result.result_stream or "")


@pytest.mark.asyncio
async def test_run_instrumentation__cut_short_run_is_incomplete_not_error() -> None:
    backend = FakeBackend(
        instrument_result=_cr(
            stdout=(
                "INSTRUMENTATION_STATUS: numtests=5\n"
                "INSTRUMENTATION_STATUS: test=testAlpha\n"
                "INSTRUMENTATION_STATUS_CODE: 1\n"
                "INSTRUMENTATION_STATUS_CODE: 0\n"
            )
        )
    )

    result = await InstrumentationService(backend).run_instrumentation("emulator-5554", _COMPONENT)

    assert result.completed is False
    assert result.result_code is None
    assert result.tests_passed == 1
    assert result.tests_total == 5


@pytest.mark.asyncio
async def test_run_instrumentation__blank_component_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await InstrumentationService(ExplodingBackend()).run_instrumentation("emulator-5554", "  ")


@pytest.mark.asyncio
async def test_run_instrumentation__out_of_range_timeout_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await InstrumentationService(ExplodingBackend()).run_instrumentation(
            "emulator-5554", _COMPONENT, timeout_s=9999.0
        )


@pytest.mark.asyncio
async def test_run_instrumentation__negative_user_id_rejected_before_backend() -> None:
    class ExplodingBackend(FakeBackend):
        async def shell(
            self, serial: str, command: str, timeout_s: float | None = None
        ) -> CommandResult:
            raise AssertionError("backend should not be reached")

    with pytest.raises(InvalidArgumentError):
        await InstrumentationService(ExplodingBackend()).run_instrumentation(
            "emulator-5554", _COMPONENT, user_id=-1
        )


@pytest.mark.asyncio
async def test_run_instrumentation__unable_to_start_raises_instrumentation_failed() -> None:
    # `am instrument` exits 0 even here.
    backend = FakeBackend(instrument_result=_cr(stdout=_FAILED_OUTPUT))

    with pytest.raises(InstrumentationFailedError):
        await InstrumentationService(backend).run_instrumentation("emulator-5554", "bogus/bogus.Runner")


@pytest.mark.asyncio
async def test_run_instrumentation__no_markers_at_all_raises_instrumentation_failed() -> None:
    backend = FakeBackend(instrument_result=_cr(stdout="totally unrelated output\n"))

    with pytest.raises(InstrumentationFailedError):
        await InstrumentationService(backend).run_instrumentation("emulator-5554", _COMPONENT)


@pytest.mark.asyncio
async def test_run_instrumentation__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        instrument_result=_cr(
            stdout="java.lang.SecurityException: Permission Denial: starting instrumentation\n"
        )
    )

    with pytest.raises(PermissionDeniedError):
        await InstrumentationService(backend).run_instrumentation("emulator-5554", _COMPONENT)


@pytest.mark.asyncio
async def test_run_instrumentation__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        instrument_result=_cr(stderr="adb: device 'bogus' not found\n", exit_code=1)
    )

    with pytest.raises(DeviceNotFoundError):
        await InstrumentationService(backend).run_instrumentation("bogus", _COMPONENT)


@pytest.mark.asyncio
async def test_run_instrumentation__unclassified_nonzero_exit_raises_backend_error() -> None:
    backend = FakeBackend(instrument_result=_cr(stderr="am: something broke\n", exit_code=1))

    with pytest.raises(BackendError):
        await InstrumentationService(backend).run_instrumentation("emulator-5554", _COMPONENT)


@pytest.mark.asyncio
async def test_run_instrumentation__backend_unavailable_raises_adb_unavailable() -> None:
    with pytest.raises(AdbUnavailableError):
        await InstrumentationService(FakeBackend(unavailable=True)).run_instrumentation(
            "emulator-5554", _COMPONENT
        )
