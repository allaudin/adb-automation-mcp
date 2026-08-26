"""Layer 3 protocol-level E2E tests for get_user_capabilities — a real
fastmcp.Client speaking actual MCP protocol to a running FastMCP server
instance, backed by FakeBackend. Kept in its own file (not
test_protocol_e2e.py) to avoid concurrent edits to a shared test file.
"""

from __future__ import annotations

import pytest
from fastmcp import Client

from adb_mcp.backend.protocol import CommandResult
from adb_mcp.backend.testing import FakeBackend
from tests.e2e.test_protocol_e2e import _build_test_server


@pytest.mark.asyncio
async def test_get_user_capabilities_tool_round_trips_over_mcp_protocol() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("get_user_capabilities", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.supports_multiple_users is True
    assert result.data.data.max_users == 4
    assert result.data.data.max_running_users == 4
    assert result.data.data.headless_system_user_mode is False
    assert result.data.data.visible_background_users_supported is False
    assert result.data.data.visible_background_users_on_default_display_supported is False


@pytest.mark.asyncio
async def test_get_user_capabilities_tool_degrades_unsupported_tier2_capability_to_none() -> None:
    backend = FakeBackend(
        headless_system_user_mode_result=CommandResult(
            stdout="", stderr="Unknown command: is-headless-system-user-mode", exit_code=1, duration_ms=20.0
        )
    )
    mcp = _build_test_server(backend)

    async with Client(mcp) as client:
        result = await client.call_tool("get_user_capabilities", {"serial": "emulator-5554"})

    assert result.data.status == "success"
    assert result.data.data.headless_system_user_mode is None
    # The rest of the payload is still populated normally.
    assert result.data.data.supports_multiple_users is True


@pytest.mark.asyncio
async def test_get_user_capabilities_tool_unknown_serial_returns_device_not_found_error() -> None:
    mcp = _build_test_server(
        FakeBackend(
            supports_multiple_users_result=CommandResult(
                stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
            )
        )
    )

    async with Client(mcp) as client:
        result = await client.call_tool("get_user_capabilities", {"serial": "bogus"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"
