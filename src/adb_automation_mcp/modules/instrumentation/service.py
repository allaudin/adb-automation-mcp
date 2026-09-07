"""Domain logic for the instrumentation module: running an Android
instrumentation test runner on a connected device
(`adb shell am instrument -w -r`).

The command is always run with `-w` (wait for completion — required for test
runners) and `-r` (raw output) so the machine-readable
`INSTRUMENTATION_STATUS` / `INSTRUMENTATION_STATUS_CODE` / `..._RESULT` /
`..._CODE` marker stream can be parsed in Python. Parsing is deliberately
conservative: pass/fail/error counts come from the per-test status codes, and
anything unrecognized is left out rather than guessed. Typed `-e key value`
runner arguments are supported; a free-form argument string is not.
"""

from __future__ import annotations

import re
import shlex

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InstrumentationFailedError,
    InvalidArgumentError,
    PermissionDeniedError,
)

_MIN_TIMEOUT_S = 1.0
_MAX_TIMEOUT_S = 600.0
_RAW_CAP = 20_000

# `am instrument -r` marker lines.
_STATUS_CODE_RE = re.compile(r"^INSTRUMENTATION_STATUS_CODE:\s*(-?\d+)\s*$", re.MULTILINE)
_CODE_RE = re.compile(r"^INSTRUMENTATION_CODE:\s*(-?\d+)\s*$", re.MULTILINE)
_NUMTESTS_RE = re.compile(r"^INSTRUMENTATION_STATUS:\s*numtests=(\d+)\s*$", re.MULTILINE)
_RESULT_STREAM_RE = re.compile(
    r"INSTRUMENTATION_RESULT:\s*stream=(?P<stream>.*?)(?:\nINSTRUMENTATION_CODE:|\Z)",
    re.DOTALL,
)

# Per-test INSTRUMENTATION_STATUS_CODE values (AndroidJUnitRunner / JUnit):
# 1 = test started, 0 = passed, -1 = error, -2 = assertion failure.
_CODE_PASSED = 0
_CODE_ERROR = -1
_CODE_FAILURE = -2


class InstrumentationRun(BaseModel):
    """Structured outcome of `adb shell am instrument -w -r COMPONENT`.

    completed is True only if a final `INSTRUMENTATION_CODE` line was seen —
    False means the run was cut short (device crash, timeout mid-run) and the
    counts below are partial. result_code is that final code as the runner
    reported it (-1 is the usual "session finished" value; a runner may use
    other values). tests_passed/tests_failed/tests_errored are counts of
    per-test status codes (0 / -2 / -1); tests_total is the runner's declared
    `numtests` when present. result_stream is the human-readable summary the
    runner emitted in its `INSTRUMENTATION_RESULT: stream=` block, if any.
    raw is the unparsed marker output (capped), for anything this model
    doesn't break out.
    """

    serial: str
    component: str
    completed: bool
    result_code: int | None
    tests_total: int | None
    tests_passed: int
    tests_failed: int
    tests_errored: int
    result_stream: str | None
    raw: str

    def summary(self) -> str:
        if not self.completed:
            return (
                f"instrumentation {self.component} on {self.serial} did not "
                f"complete ({self.tests_passed} passed so far)."
            )
        return (
            f"instrumentation {self.component} on {self.serial}: "
            f"{self.tests_passed} passed, {self.tests_failed} failed, "
            f"{self.tests_errored} errored (code {self.result_code})."
        )


class InstrumentationService:
    """Runs instrumentation test runners on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def run_instrumentation(
        self,
        serial: str,
        component: str,
        *,
        args: dict[str, str] | None = None,
        user_id: int | None = None,
        no_window_animation: bool = False,
        timeout_s: float = 120.0,
    ) -> InstrumentationRun:
        if not component.strip():
            raise InvalidArgumentError(
                "component must be '<test_package>/<runner_class>' or '<test_package>'.",
                details={"serial": serial},
            )
        if user_id is not None and user_id < 0:
            raise InvalidArgumentError(
                "user_id must be a non-negative Android user id.",
                details={"serial": serial, "user_id": user_id},
            )
        if not _MIN_TIMEOUT_S <= timeout_s <= _MAX_TIMEOUT_S:
            raise InvalidArgumentError(
                f"timeout_s must be between {_MIN_TIMEOUT_S} and {_MAX_TIMEOUT_S} seconds.",
                details={"serial": serial, "timeout_s": timeout_s},
            )
        args = args or {}
        if any(not key.strip() for key in args):
            raise InvalidArgumentError(
                "instrumentation arg names must be non-blank.",
                details={"serial": serial},
            )

        parts = ["am", "instrument", "-w", "-r"]
        if no_window_animation:
            parts.append("--no-window-animation")
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        for key, value in args.items():
            parts.extend(["-e", shlex.quote(key), shlex.quote(value)])
        parts.append(shlex.quote(component))

        result = await self._backend.shell(serial, " ".join(parts), timeout_s=timeout_s)
        _raise_for_instrument_failure(serial, component, result)
        return _parse_instrumentation(serial, component, result.stdout)


def _raise_for_instrument_failure(serial: str, component: str, result: CommandResult) -> None:
    combined = f"{result.stdout}\n{result.stderr}"
    # `am instrument` exits 0 even when it can't start the runner.
    if "INSTRUMENTATION_FAILED:" in combined or "Unable to find instrumentation" in combined:
        detail = next(
            (
                ln.strip()
                for ln in combined.splitlines()
                if "INSTRUMENTATION_STATUS: Error=" in ln
            ),
            "",
        )
        raise InstrumentationFailedError(
            detail or f"Could not start instrumentation {component}.",
            details={"serial": serial, "component": component},
        )
    if "Permission Denial" in combined:
        raise PermissionDeniedError(
            f"Permission denied running instrumentation {component}.",
            details={"serial": serial, "component": component},
        )
    if result.exit_code != 0:
        message = (result.stderr or result.stdout).strip() or "am instrument exited non-zero."
        if message.startswith("adb:") and "not found" in message:
            raise DeviceNotFoundError(message, details={"serial": serial})
        raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})
    if "INSTRUMENTATION_STATUS_CODE:" not in combined and "INSTRUMENTATION_CODE:" not in combined:
        raise InstrumentationFailedError(
            "am instrument produced no INSTRUMENTATION_* markers.",
            details={"serial": serial, "component": component, "output_head": result.stdout[:400]},
        )


def _parse_instrumentation(serial: str, component: str, text: str) -> InstrumentationRun:
    codes = [int(m.group(1)) for m in _STATUS_CODE_RE.finditer(text)]
    numtests = [int(m.group(1)) for m in _NUMTESTS_RE.finditer(text)]
    final_codes = _CODE_RE.findall(text)
    stream_match = _RESULT_STREAM_RE.search(text)
    stream = stream_match.group("stream").strip() if stream_match else ""

    return InstrumentationRun(
        serial=serial,
        component=component,
        completed=bool(final_codes),
        result_code=int(final_codes[-1]) if final_codes else None,
        tests_total=max(numtests) if numtests else None,
        tests_passed=sum(1 for c in codes if c == _CODE_PASSED),
        tests_failed=sum(1 for c in codes if c == _CODE_FAILURE),
        tests_errored=sum(1 for c in codes if c == _CODE_ERROR),
        result_stream=stream or None,
        raw=text if len(text) <= _RAW_CAP else text[:_RAW_CAP] + "\n...[truncated]",
    )
