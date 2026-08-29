"""Layer 3 protocol-level E2E tests for take_screenshot — a real fastmcp.Client
speaking actual MCP protocol to a running FastMCP server instance, backed by
FakeBackend. Kept in its own file (not test_protocol_e2e.py) to avoid
concurrent edits to a shared test file.
"""

from __future__ import annotations

import base64
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from adb_automation_mcp.backend.protocol import ExecOutResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.modules.screen.service import ScreenService
from adb_automation_mcp.policy import PolicyConfig, PolicyEngine
from adb_automation_mcp.registry import Registry, discover_modules
from tests.e2e.test_protocol_e2e import _build_test_server

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _build_test_server_with_local_root(backend: FakeBackend, local_root: Path | None) -> FastMCP:
    # take_screenshot's save= needs a configured local_root, which the shared
    # _build_test_server helper doesn't parameterize — build the server the same
    # way but construct the screen service directly with local_root instead of
    # reading ADB_AUTOMATION_LOCAL_ROOT from the environment.
    manifests = discover_modules()
    registry = Registry(policy=PolicyEngine(PolicyConfig()))

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        services = registry.build_services(backend, manifests)
        services["screen"] = ScreenService(backend, local_root=local_root)
        yield {"backend": backend, "services": services}

    mcp = FastMCP("test-server", lifespan=lifespan)
    registry.register_tools(mcp, manifests)
    registry.register_resources(mcp, manifests)
    return mcp


@pytest.mark.asyncio
async def test_take_screenshot_tool_returns_image_content_block() -> None:
    mcp = _build_test_server(FakeBackend())

    async with Client(mcp) as client:
        result = await client.call_tool("take_screenshot", {"serial": "emulator-5554"})

    # The screenshot comes back as a real MCP image content block.
    image_blocks = [c for c in result.content if getattr(c, "type", None) == "image"]
    assert len(image_blocks) == 1
    assert image_blocks[0].mimeType == "image/png"
    assert base64.b64decode(image_blocks[0].data).startswith(_PNG_SIGNATURE)

    # Structured metadata rides along in the envelope; raw bytes are not duplicated there.
    assert result.data.status == "success"
    assert result.data.data.serial == "emulator-5554"
    assert result.data.data.mime_type == "image/png"
    assert result.data.data.width == 2
    assert result.data.data.height == 2
    assert result.data.data.size_bytes > 0
    assert result.data.data.success is True


@pytest.mark.asyncio
async def test_take_screenshot_tool_accepts_display_id() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def exec_out(self, serial: str, command: str) -> ExecOutResult:
            captured["command"] = command
            return await super().exec_out(serial, command)

    mcp = _build_test_server(RecordingBackend())

    async with Client(mcp) as client:
        result = await client.call_tool(
            "take_screenshot", {"serial": "emulator-5554", "display_id": 2}
        )

    assert result.data.status == "success"
    assert result.data.data.display_id == 2
    assert captured["command"] == "screencap -p -d 2"


@pytest.mark.asyncio
async def test_take_screenshot_tool_screencap_failure_returns_backend_error() -> None:
    backend = FakeBackend(
        exec_out_result=ExecOutResult(
            stdout=b"", stderr="Error: unable to open display\n", exit_code=1, duration_ms=20.0
        )
    )
    mcp = _build_test_server(backend)

    async with Client(mcp) as client:
        result = await client.call_tool("take_screenshot", {"serial": "emulator-5554"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "BACKEND_ERROR"
    assert not any(getattr(c, "type", None) == "image" for c in result.content)


@pytest.mark.asyncio
async def test_take_screenshot_tool_unknown_serial_returns_device_not_found_error() -> None:
    # `adb exec-out` wording, captured live from a real emulator.
    backend = FakeBackend(
        exec_out_result=ExecOutResult(
            stdout=b"", stderr="error: device 'bogus' not found\n", exit_code=255, duration_ms=10.0
        )
    )
    mcp = _build_test_server(backend)

    async with Client(mcp) as client:
        result = await client.call_tool("take_screenshot", {"serial": "bogus"})

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "DEVICE_NOT_FOUND"


@pytest.mark.asyncio
async def test_take_screenshot_tool_save_writes_file_and_returns_image_block(tmp_path: Path) -> None:
    mcp = _build_test_server_with_local_root(FakeBackend(), tmp_path)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "take_screenshot", {"serial": "emulator-5554", "save": True, "filename": "e2e"}
        )

    image_blocks = [c for c in result.content if getattr(c, "type", None) == "image"]
    assert len(image_blocks) == 1

    saved = tmp_path / "screenshots" / "e2e.png"
    assert result.data.status == "success"
    assert result.data.data.local_path == str(saved)
    assert saved.read_bytes() == base64.b64decode(image_blocks[0].data)
    assert saved.read_bytes().startswith(_PNG_SIGNATURE)


@pytest.mark.asyncio
async def test_take_screenshot_tool_save_without_local_root_returns_policy_denied(tmp_path: Path) -> None:
    mcp = _build_test_server_with_local_root(FakeBackend(), None)

    async with Client(mcp) as client:
        result = await client.call_tool(
            "take_screenshot", {"serial": "emulator-5554", "save": True}
        )

    assert result.data.status == "error"
    assert result.data.error is not None
    assert result.data.error.code == "POLICY_DENIED"
    assert not any(getattr(c, "type", None) == "image" for c in result.content)
