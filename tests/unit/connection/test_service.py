"""Layer 1 unit tests: ConnectionService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.errors import AdbUnavailableError
from adb_mcp.modules.connection.service import AdbServerRestartResult, ConnectionService


@pytest.mark.asyncio
async def test_restart_adb_server__start_server_succeeds_reports_success_true() -> None:
    service = ConnectionService(FakeBackend())

    result = await service.restart_adb_server()

    assert result.success is True
    assert "daemon started successfully" in result.output


@pytest.mark.asyncio
async def test_restart_adb_server__start_server_fails_reports_success_false_with_output() -> None:
    backend = FakeBackend(
        start_server_result=CommandResult(
            stdout="", stderr="cannot bind to 127.0.0.1:5037", exit_code=1, duration_ms=10.0
        )
    )
    service = ConnectionService(backend)

    result = await service.restart_adb_server()

    assert result.success is False
    assert "cannot bind to 127.0.0.1:5037" in result.output


@pytest.mark.asyncio
async def test_restart_adb_server__adb_unavailable_propagates_as_error() -> None:
    service = ConnectionService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.restart_adb_server()


def test_restart_result_summary_mentions_success() -> None:
    assert "restarted successfully" in AdbServerRestartResult(success=True, output="").summary()


def test_restart_result_summary_includes_output_on_failure() -> None:
    summary = AdbServerRestartResult(success=False, output="cannot bind").summary()
    assert "failed" in summary
    assert "cannot bind" in summary
