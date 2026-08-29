"""adb-automation-mcp: an MCP server exposing ADB capabilities as tools and resources."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("adb-automation-mcp")
except PackageNotFoundError:  # pragma: no cover - only when running from a source tree with no metadata
    __version__ = "0.0.0"

__all__ = ["__version__"]
