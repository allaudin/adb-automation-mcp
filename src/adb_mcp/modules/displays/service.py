"""Domain logic for the displays module: querying and manipulating device
display state (size, density, orientation, multi-display) — not yet
implemented, this is the module skeleton only.
"""

from __future__ import annotations

from adb_mcp.backend.protocol import AdbBackend


class DisplaysService:
    """Display query/manipulation logic — no domain methods yet."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend
