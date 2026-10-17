---
title: "Instrumentation: Run Android Tests"
description: "MCP tool to run Android instrumentation tests via adb shell am instrument and get structured pass/fail results."
---

# Instrumentation Tests

Running an Android instrumentation test runner on a connected device
(`adb shell am instrument -w -r`). `run_instrumentation` always waits for the
run to finish and requests raw output, then parses the
`INSTRUMENTATION_STATUS` / `INSTRUMENTATION_STATUS_CODE` / `..._RESULT` /
`..._CODE` markers into pass/fail/error counts, the final result code, and the
runner's summary stream. Typed `-e name value` runner arguments, `--user`
scope, `--no-window-animation`, and a bounded `timeout_s` are supported; a
free-form argument string is not. Test failures are returned as data — only a
failure to *start* the runner raises (`INSTRUMENTATION_FAILED`).

::: adb_automation_mcp.modules.instrumentation.tools
