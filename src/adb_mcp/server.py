"""Builds the FastMCP app: tool registration happens once at import time (it's
static — policy + manifests, no backend needed); the backend and per-module services
are constructed per-process in the lifespan, since which backend to use is a runtime
decision.

Env vars read at startup:
    ADB_MCP_BACKEND=fake       use the deterministic FakeBackend instead of a real adb
    ADB_MCP_ADB_PATH           explicit path to the adb binary (falls back to PATH lookup)
    ADB_MCP_TIMEOUT_S          per-command timeout in seconds (default: 10)
    ADB_MCP_ALLOW_DESTRUCTIVE=1  flip the default policy posture to also allow destructive
                                 tools (e.g. remove_user); denied by default
    ADB_MCP_LOCAL_ROOT         host directory stop_log_session's local_path must resolve
                                 inside; unset means that tool refuses to write anywhere
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP

from adb_mcp.backend.protocol import AdbBackend
from adb_mcp.backend.subprocess_backend import SubprocessBackend
from adb_mcp.backend.testing import FakeBackend
from adb_mcp.policy import PolicyConfig, PolicyEngine
from adb_mcp.registry import Registry, discover_modules

logger = logging.getLogger(__name__)

_manifests = discover_modules()
_policy = PolicyEngine(
    PolicyConfig(allow_destructive=os.environ.get("ADB_MCP_ALLOW_DESTRUCTIVE") == "1")
)
_registry = Registry(policy=_policy)


def _build_backend() -> AdbBackend:
    if os.environ.get("ADB_MCP_BACKEND") == "fake":
        return FakeBackend()

    adb_path = os.environ.get("ADB_MCP_ADB_PATH")  # explicit path; falls back to PATH lookup if unset
    timeout_s = float(os.environ.get("ADB_MCP_TIMEOUT_S", "10"))
    return SubprocessBackend(adb_path=adb_path, timeout_s=timeout_s)


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    backend = _build_backend()
    services = _registry.build_services(backend, _manifests)
    yield {"backend": backend, "services": services}


mcp = FastMCP(name="adb-mcp-server", lifespan=app_lifespan)
_registry.register_tools(mcp, _manifests)
_registry.register_resources(mcp, _manifests)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
