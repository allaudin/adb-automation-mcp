"""Validates the registry's envelope-wrapping mechanism directly: success uses a data
model's summary() as the message, AdbError becomes a structured error, and an
unexpected exception becomes a generic INTERNAL_ERROR without leaking internals.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from adb_mcp.errors import AdbUnavailableError
from adb_mcp.registry import wrap_with_envelope


class _Data(BaseModel):
    value: int

    def summary(self) -> str:
        return f"value is {self.value}"


async def _ok(x: int) -> _Data:
    return _Data(value=x)


async def _fails(x: int) -> _Data:
    raise AdbUnavailableError("adb missing", details={"x": x}, remediation="install adb")


async def _crashes(x: int) -> _Data:
    raise RuntimeError("boom, internal file path /etc/secret")


@pytest.mark.asyncio
async def test_wrap_with_envelope__success_uses_data_summary_as_message() -> None:
    wrapped = wrap_with_envelope(_ok)

    result: Any = await wrapped(5)

    assert result.status == "success"
    assert result.data.value == 5
    assert result.message == "value is 5"
    assert result.error is None


@pytest.mark.asyncio
async def test_wrap_with_envelope__adb_error_becomes_structured_error() -> None:
    wrapped = wrap_with_envelope(_fails)

    result: Any = await wrapped(1)

    assert result.status == "error"
    assert result.data is None
    assert result.error.code == "ADB_UNAVAILABLE"
    assert result.error.remediation == "install adb"
    assert result.error.details == {"x": 1}
    assert result.error.retryable is False


@pytest.mark.asyncio
async def test_wrap_with_envelope__unexpected_exception_becomes_internal_error_without_leaking() -> None:
    wrapped = wrap_with_envelope(_crashes)

    result: Any = await wrapped(1)

    assert result.status == "error"
    assert result.error.code == "INTERNAL_ERROR"
    assert "secret" not in result.message
    assert "boom" not in result.message
