"""Builds the FastMCP app: tool registration happens once at import time (it's
static — policy + manifests, no backend needed); the backend and per-module services
are constructed per-process in the lifespan, since which backend to use is a runtime
decision.

Env vars read at startup:
    ADB_AUTOMATION_BACKEND=fake       use the deterministic FakeBackend instead of a real adb
    ADB_AUTOMATION_ADB_PATH           explicit path to the adb binary (falls back to PATH lookup)
    ADB_AUTOMATION_TIMEOUT_S          per-command timeout in seconds (default: 10)
    ADB_AUTOMATION_ALLOW_DESTRUCTIVE=1  flip the default policy posture to also allow destructive
                                 tools (e.g. remove_user); denied by default
    ADB_AUTOMATION_LOCAL_ROOT         the folder on this machine where file-saving tools
                                 (pull_file, take_screenshot, stop_log_session) are
                                 allowed to write; unset means those tools refuse to
                                 write anywhere

The legacy ADB_MCP_* names (from before the project was renamed) are still read as a
fallback, with a deprecation warning; prefer the ADB_AUTOMATION_* names.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastmcp import FastMCP

from adb_automation_mcp import __version__
from adb_automation_mcp.backend.protocol import AdbBackend
from adb_automation_mcp.backend.subprocess_backend import SubprocessBackend
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.policy import PolicyConfig, PolicyEngine
from adb_automation_mcp.registry import Registry, discover_modules

logger = logging.getLogger(__name__)

_ENV_PREFIX = "ADB_AUTOMATION_"
_LEGACY_ENV_PREFIX = "ADB_MCP_"


def _env(suffix: str) -> str | None:
    """Read an ADB_AUTOMATION_<suffix> setting, falling back to the legacy
    ADB_MCP_<suffix> name (from before the project was renamed) with a
    deprecation warning."""
    value = os.environ.get(_ENV_PREFIX + suffix)
    if value is not None:
        return value
    legacy = os.environ.get(_LEGACY_ENV_PREFIX + suffix)
    if legacy is not None:
        logger.warning(
            "%s%s is deprecated; use %s%s", _LEGACY_ENV_PREFIX, suffix, _ENV_PREFIX, suffix
        )
    return legacy


_manifests = discover_modules()
_policy = PolicyEngine(PolicyConfig(allow_destructive=_env("ALLOW_DESTRUCTIVE") == "1"))
_registry = Registry(policy=_policy)


def _build_backend() -> AdbBackend:
    if _env("BACKEND") == "fake":
        return FakeBackend()

    adb_path = _env("ADB_PATH")  # explicit path; falls back to PATH lookup if unset
    timeout_s = float(_env("TIMEOUT_S") or "10")
    return SubprocessBackend(adb_path=adb_path, timeout_s=timeout_s)


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    backend = _build_backend()
    services = _registry.build_services(backend, _manifests)
    yield {"backend": backend, "services": services}


mcp = FastMCP(name="adb-automation-mcp", version=__version__, lifespan=app_lifespan)
_registry.register_tools(mcp, _manifests)
_registry.register_resources(mcp, _manifests)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.run()


if __name__ == "__main__":
    main()
