"""Validates the registry's envelope-wrapping mechanism directly: success uses a data
model's summary() as the message, AdbError becomes a structured error, and an
unexpected exception becomes a generic INTERNAL_ERROR without leaking internals.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastmcp import FastMCP
from fastmcp.exceptions import ResourceError
from pydantic import BaseModel

from adb_automation_mcp.errors import AdbUnavailableError
from adb_automation_mcp.policy import PolicyConfig, PolicyEngine
from adb_automation_mcp.registry import ModuleManifest, Registry, wrap_resource, wrap_with_envelope


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


@pytest.mark.asyncio
async def test_wrap_resource__success_returns_data_directly_with_no_envelope() -> None:
    wrapped = wrap_resource(_ok)

    result: Any = await wrapped(5)

    assert result.value == 5


@pytest.mark.asyncio
async def test_wrap_resource__adb_error_becomes_resource_error_with_remediation() -> None:
    wrapped = wrap_resource(_fails)

    with pytest.raises(ResourceError) as exc_info:
        await wrapped(1)

    assert "adb missing" in str(exc_info.value)
    assert "install adb" in str(exc_info.value)


@pytest.mark.asyncio
async def test_wrap_resource__unexpected_exception_becomes_generic_resource_error_without_leaking() -> None:
    wrapped = wrap_resource(_crashes)

    with pytest.raises(ResourceError) as exc_info:
        await wrapped(1)

    assert "secret" not in str(exc_info.value)
    assert "boom" not in str(exc_info.value)


async def _device_data() -> _Data:
    return _Data(value=1)


def _manifest_with_one_resource() -> ModuleManifest:
    return ModuleManifest(
        name="mymodule",
        service_factory=lambda backend: object(),
        resources=[("mymodule://thing", _device_data)],
    )


@pytest.mark.asyncio
async def test_register_resources__allowed_resource_is_registered_with_fastmcp() -> None:
    registry = Registry(policy=PolicyEngine(PolicyConfig()))
    mcp = FastMCP("test-server")

    registry.register_resources(mcp, [_manifest_with_one_resource()])

    resource = await mcp.get_resource("mymodule://thing")
    assert resource is not None


@pytest.mark.asyncio
async def test_register_resources__denied_resource_is_not_registered() -> None:
    registry = Registry(policy=PolicyEngine(PolicyConfig(deny=frozenset({"mymodule._device_data"}))))
    mcp = FastMCP("test-server")

    registry.register_resources(mcp, [_manifest_with_one_resource()])

    resource = await mcp.get_resource("mymodule://thing")
    assert resource is None
