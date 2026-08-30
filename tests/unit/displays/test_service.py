"""Layer 1 skeleton test: the displays module has no domain logic yet — this
only confirms DisplaysService constructs against the shared backend
abstraction, the same construction pattern every other module uses.
"""

from __future__ import annotations

from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.modules.displays.service import DisplaysService


def test_service_constructs_with_backend() -> None:
    service = DisplaysService(FakeBackend())

    assert service is not None
