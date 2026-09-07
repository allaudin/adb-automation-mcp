"""Layer 3 protocol-level E2E tests for capture_system_trace."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.modules.tracing.service import TracingService
from adb_automation_mcp.policy import PolicyConfig, PolicyEngine
from adb_automation_mcp.registry import Registry, discover_modules
from tests.e2e.test_protocol_e2e import _build_test_server


def _server_with_local_root(backend: FakeBackend, local_root: Path | None) -> FastMCP:
    manifests = discover_modules()
    registry = Registry(policy=PolicyEngine(PolicyConfig()))

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        services = registry.build_services(backend, manifests)
        services["tracing"] = TracingService(backend, local_root=local_root)
        yield {"backend": backend, "services": services}

    mcp = FastMCP("test-server", lifespan=lifespan)
    registry.register_tools(mcp, manifests)
    registry.register_resources(mcp, manifests)
    return mcp


@pytest.mark.asyncio
async def test_capture_system_trace_tool_registered_without_destructive_gate() -> None:
    mcp = _build_test_server(FakeBackend(), allow_destructive=False)

    async with Client(mcp) as client:
        tools = {t.name for t in await client.list_tools()}

    assert "capture_system_trace" in tools


@pytest.mark.asyncio
async def test_capture_system_trace_tool_round_trips_with_local_root(tmp_path: Path) -> None:
    mcp = _server_with_local_root(FakeBackend(), tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "capture_system_trace",
            {
                "serial": "emulator-5554",
                "preset": "cpu",
                "local_path": "cpu.perfetto-trace",
                "duration_seconds": 3,
            },
        )

    assert result.data.status == "success"
    assert result.data.data.preset == "cpu"
    assert result.data.data.local_path == str(tmp_path / "traces" / "cpu.perfetto-trace")
    assert result.data.data.device_bytes == 84260


@pytest.mark.asyncio
async def test_capture_system_trace_tool_unknown_preset_rejected_by_schema(
    tmp_path: Path,
) -> None:
    # preset is a typed Literal enum, so an invalid value is a schema violation
    # (raised) rather than a domain error in the envelope.
    mcp = _server_with_local_root(FakeBackend(), tmp_path)

    async with Client(mcp) as client:
        with pytest.raises(Exception, match="preset"):
            await client.call_tool(
                "capture_system_trace",
                {
                    "serial": "emulator-5554",
                    "preset": "nonsense",
                    "local_path": "x.perfetto-trace",
                },
            )


@pytest.mark.asyncio
async def test_capture_system_trace_tool_bad_duration_returns_invalid_argument(
    tmp_path: Path,
) -> None:
    mcp = _server_with_local_root(FakeBackend(), tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "capture_system_trace",
            {
                "serial": "emulator-5554",
                "preset": "cpu",
                "local_path": "x.perfetto-trace",
                "duration_seconds": 999,
            },
        )

    assert result.data.status == "error"
    assert result.data.error.code == "INVALID_ARGUMENT"


@pytest.mark.asyncio
async def test_capture_system_trace_tool_no_local_root_returns_policy_denied(tmp_path: Path) -> None:
    mcp = _server_with_local_root(FakeBackend(), None)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "capture_system_trace",
            {"serial": "emulator-5554", "preset": "cpu", "local_path": "x.perfetto-trace"},
        )

    assert result.data.status == "error"
    assert result.data.error.code == "POLICY_DENIED"


@pytest.mark.asyncio
async def test_capture_system_trace_tool_perfetto_unavailable_is_structured_error(
    tmp_path: Path,
) -> None:
    mcp = _server_with_local_root(
        FakeBackend(
            perfetto_result=CommandResult(
                stdout="", stderr="perfetto: not found\n", exit_code=127, duration_ms=5.0
            )
        ),
        tmp_path,
    )

    async with Client(mcp) as client:
        result = await client.call_tool(
            "capture_system_trace",
            {"serial": "emulator-5554", "preset": "cpu", "local_path": "x.perfetto-trace"},
        )

    assert result.data.status == "error"
    assert result.data.error.code == "TRACING_UNAVAILABLE"
