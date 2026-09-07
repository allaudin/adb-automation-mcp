"""Module-level, statically-introspectable tool functions for the instrumentation module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.instrumentation.service import (
    InstrumentationRun,
    InstrumentationService,
)
from adb_automation_mcp.registry import category


@category("write")
async def run_instrumentation(
    ctx: Context,
    serial: str,
    component: str,
    args: dict[str, str] | None = None,
    user_id: int | None = None,
    no_window_animation: bool = False,
    timeout_s: float = 120.0,
) -> InstrumentationRun:
    """Run an instrumentation test runner: `adb shell am instrument -w -r`.

    Always runs with `-w` (wait for completion — required for test runners)
    and `-r` (raw output), then parses the
    INSTRUMENTATION_STATUS/RESULT/CODE marker stream into pass/fail/error
    counts and the runner's summary. Categorized `write` because a test run
    executes arbitrary app code on the device. Test failures are a normal
    result returned as data — only a failure to *start* the runner is an
    error.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        component: The instrumentation to run, as
            "<test_package>/<runner_class>" (e.g.
            "com.example.test/androidx.test.runner.AndroidJUnitRunner"), or
            just "<test_package>" when it declares only one.
        args: Runner arguments passed as `-e <name> <value>` pairs, e.g.
            {"class": "com.example.FooTest#testBar"} or {"package":
            "com.example.feature"}. Omit for none.
        user_id: Run the instrumentation as this Android user (`--user`).
            Omit for the current user.
        no_window_animation: Pass `--no-window-animation` to disable window
            animations during the run.
        timeout_s: How long to wait for the run to finish, 1-600 seconds
            (default 120). A run exceeding this raises TIMEOUT.

    Returns:
        The serial and component; completed (false if the run was cut
        short); result_code (the final INSTRUMENTATION_CODE); tests_total
        (declared numtests when reported); tests_passed / tests_failed /
        tests_errored counts; result_stream (the runner's human-readable
        summary); and raw (the capped marker output).

    Error handling:
        A blank component, negative user_id, or out-of-range timeout_s
        raises INVALID_ARGUMENT before anything runs. An unknown serial or
        unresponsive adb binary raises DEVICE_NOT_FOUND/ADB_UNAVAILABLE. A
        component whose test package/runner isn't installed raises
        INSTRUMENTATION_FAILED (`am` exits 0 for this, so it's detected from
        the output). A permission rejection raises PERMISSION_DENIED; any
        other non-zero exit raises BACKEND_ERROR; a run that exceeds
        timeout_s raises TIMEOUT.

    Example:
        Called with serial="emulator-5554",
        component="com.example.test/androidx.test.runner.AndroidJUnitRunner",
        args={"class": "com.example.FooTest"}. A typical response:

        ```json
        {
          "status": "success",
          "message": "instrumentation com.example.test/androidx.test.runner.AndroidJUnitRunner on emulator-5554: 2 passed, 0 failed, 0 errored (code -1).",
          "data": {
            "serial": "emulator-5554",
            "component": "com.example.test/androidx.test.runner.AndroidJUnitRunner",
            "completed": true,
            "result_code": -1,
            "tests_total": 2,
            "tests_passed": 2,
            "tests_failed": 0,
            "tests_errored": 0,
            "result_stream": "OK (2 tests)",
            "raw": "INSTRUMENTATION_STATUS: numtests=2\\n..."
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    instrumentation = cast(InstrumentationService, services["instrumentation"])
    return await instrumentation.run_instrumentation(
        serial,
        component,
        args=args,
        user_id=user_id,
        no_window_animation=no_window_animation,
        timeout_s=timeout_s,
    )
