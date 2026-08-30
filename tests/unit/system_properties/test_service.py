"""Layer 1 unit tests: SystemPropertiesService against FakeBackend directly —
no MCP registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PolicyViolationError,
    PropertyWriteRejectedError,
)
from adb_automation_mcp.modules.system_properties.service import (
    Property,
    PropertyList,
    PropertyMetadata,
    SetPropertyResult,
    SystemPropertiesService,
)


@pytest.mark.asyncio
async def test_get_property__returns_normal_value() -> None:
    service = SystemPropertiesService(FakeBackend())

    result = await service.get_property("emulator-5554", "ro.build.version.release")

    assert result.serial == "emulator-5554"
    assert result.name == "ro.build.version.release"
    assert result.value == "14"


@pytest.mark.asyncio
async def test_get_property__empty_value_is_not_an_error() -> None:
    backend = FakeBackend(
        getprop_result=CommandResult(stdout="\n", stderr="", exit_code=0, duration_ms=10.0)
    )
    service = SystemPropertiesService(backend)

    result = await service.get_property("emulator-5554", "this.prop.does.not.exist")

    assert result.value == ""


@pytest.mark.asyncio
async def test_get_property__shell_quotes_name() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = SystemPropertiesService(RecordingBackend())

    await service.get_property("emulator-5554", "ro.build.version.release")

    assert captured["command"] == "getprop ro.build.version.release"


@pytest.mark.asyncio
async def test_get_property__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        getprop_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = SystemPropertiesService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.get_property("bogus", "ro.build.version.release")


@pytest.mark.asyncio
async def test_get_property__other_nonzero_exit_raises_backend_error() -> None:
    backend = FakeBackend(
        getprop_result=CommandResult(
            stdout="", stderr="some other adb shell failure", exit_code=1, duration_ms=10.0
        )
    )
    service = SystemPropertiesService(backend)

    with pytest.raises(BackendError):
        await service.get_property("emulator-5554", "ro.build.version.release")


@pytest.mark.asyncio
async def test_get_property__adb_unavailable_propagates_as_error() -> None:
    service = SystemPropertiesService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.get_property("emulator-5554", "ro.build.version.release")


def test_property_summary_mentions_name_value_and_serial() -> None:
    summary = Property(serial="emulator-5554", name="ro.debuggable", value="1").summary()
    assert "ro.debuggable" in summary
    assert "1" in summary
    assert "emulator-5554" in summary


@pytest.mark.asyncio
async def test_list_properties__parses_real_getprop_output() -> None:
    service = SystemPropertiesService(FakeBackend())

    result = await service.list_properties("emulator-5554")

    assert result.serial == "emulator-5554"
    assert result.prefix is None
    names = {p.name for p in result.properties}
    assert "ro.build.version.release" in names
    assert "dalvik.vm.heapsize" in names
    heapsize = next(p for p in result.properties if p.name == "dalvik.vm.heapsize")
    assert heapsize.value == ""
    release = next(p for p in result.properties if p.name == "ro.build.version.release")
    assert release.value == "14"


@pytest.mark.asyncio
async def test_list_properties__prefix_filter_applied_after_parsing() -> None:
    service = SystemPropertiesService(FakeBackend())

    result = await service.list_properties("emulator-5554", prefix="ro.build.")

    assert result.prefix == "ro.build."
    assert len(result.properties) == 2
    assert all(p.name.startswith("ro.build.") for p in result.properties)


@pytest.mark.asyncio
async def test_list_properties__prefix_matching_nothing_returns_empty_list() -> None:
    service = SystemPropertiesService(FakeBackend())

    result = await service.list_properties("emulator-5554", prefix="does.not.match.")

    assert result.properties == []


@pytest.mark.asyncio
async def test_list_properties__malformed_lines_are_skipped() -> None:
    backend = FakeBackend(
        list_properties_result=CommandResult(
            stdout=(
                "not a property line\n"
                "\n"
                "[ro.debuggable]: [0]\n"
                "also garbage: no brackets here\n"
            ),
            stderr="",
            exit_code=0,
            duration_ms=10.0,
        )
    )
    service = SystemPropertiesService(backend)

    result = await service.list_properties("emulator-5554")

    assert len(result.properties) == 1
    assert result.properties[0] == Property(serial="emulator-5554", name="ro.debuggable", value="0")


@pytest.mark.asyncio
async def test_list_properties__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        list_properties_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = SystemPropertiesService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.list_properties("bogus")


@pytest.mark.asyncio
async def test_list_properties__adb_unavailable_propagates_as_error() -> None:
    service = SystemPropertiesService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.list_properties("emulator-5554")


def test_property_list_summary_pluralizes_and_mentions_prefix() -> None:
    single = PropertyList(
        serial="s", prefix=None, properties=[Property(serial="s", name="a", value="1")]
    ).summary()
    assert "1 property" in single

    multi = PropertyList(
        serial="s",
        prefix="ro.",
        properties=[
            Property(serial="s", name="ro.a", value="1"),
            Property(serial="s", name="ro.b", value="2"),
        ],
    ).summary()
    assert "2 properties" in multi
    assert "ro." in multi


@pytest.mark.asyncio
async def test_get_property_metadata__returns_value_context_and_type() -> None:
    service = SystemPropertiesService(FakeBackend())

    result = await service.get_property_metadata("emulator-5554", "ro.build.version.release")

    assert result.serial == "emulator-5554"
    assert result.name == "ro.build.version.release"
    assert result.value == "14"
    assert result.selinux_context == "u:object_r:build_prop:s0"
    assert result.declared_type == "build_prop"


@pytest.mark.asyncio
async def test_get_property_metadata__unsupported_context_lookup_degrades_gracefully() -> None:
    backend = FakeBackend(
        getprop_context_result=CommandResult(
            stdout="", stderr="getprop: unrecognized option '-Z'\n", exit_code=1, duration_ms=5.0
        )
    )
    service = SystemPropertiesService(backend)

    result = await service.get_property_metadata("emulator-5554", "ro.build.version.release")

    assert result.value == "14"
    assert result.selinux_context is None
    assert result.declared_type is None


@pytest.mark.asyncio
async def test_get_property_metadata__unparseable_context_output_degrades_gracefully() -> None:
    backend = FakeBackend(
        getprop_context_result=CommandResult(
            stdout="not-a-context-string\n", stderr="", exit_code=0, duration_ms=5.0
        )
    )
    service = SystemPropertiesService(backend)

    result = await service.get_property_metadata("emulator-5554", "ro.build.version.release")

    assert result.selinux_context is None
    assert result.declared_type is None


@pytest.mark.asyncio
async def test_get_property_metadata__unknown_serial_on_value_lookup_raises_device_not_found() -> None:
    backend = FakeBackend(
        getprop_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = SystemPropertiesService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.get_property_metadata("bogus", "ro.build.version.release")


@pytest.mark.asyncio
async def test_get_property_metadata__unknown_serial_on_context_lookup_raises_device_not_found() -> None:
    backend = FakeBackend(
        getprop_context_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = SystemPropertiesService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.get_property_metadata("bogus", "ro.build.version.release")


@pytest.mark.asyncio
async def test_get_property_metadata__adb_unavailable_propagates_as_error() -> None:
    service = SystemPropertiesService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.get_property_metadata("emulator-5554", "ro.build.version.release")


def test_property_metadata_summary_reflects_missing_type() -> None:
    summary = PropertyMetadata(
        serial="s", name="ro.x", value="1", selinux_context=None, declared_type=None
    ).summary()
    assert "no SELinux metadata" in summary


@pytest.mark.asyncio
async def test_set_property__success_returns_name_and_value() -> None:
    service = SystemPropertiesService(FakeBackend())

    result = await service.set_property("emulator-5554", "debug.myapp.loglevel", "verbose")

    assert result == SetPropertyResult(
        serial="emulator-5554", name="debug.myapp.loglevel", value="verbose"
    )


@pytest.mark.asyncio
async def test_set_property__shell_quotes_name_and_value() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = SystemPropertiesService(RecordingBackend())

    await service.set_property("emulator-5554", "debug.myapp.name", "; echo pwned; #")

    assert captured["command"] == "setprop debug.myapp.name '; echo pwned; #'"


@pytest.mark.asyncio
async def test_set_property__android_rejects_write_raises_property_write_rejected() -> None:
    backend = FakeBackend(
        setprop_result=CommandResult(
            stdout="",
            stderr="could not set property 'ro.debuggable' to '1'",
            exit_code=1,
            duration_ms=20.0,
        )
    )
    service = SystemPropertiesService(backend)

    with pytest.raises(PropertyWriteRejectedError):
        await service.set_property("emulator-5554", "ro.debuggable", "1")


@pytest.mark.asyncio
async def test_set_property__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        setprop_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = SystemPropertiesService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.set_property("bogus", "debug.myapp.loglevel", "verbose")


@pytest.mark.asyncio
async def test_set_property__adb_unavailable_propagates_as_error() -> None:
    service = SystemPropertiesService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.set_property("emulator-5554", "debug.myapp.loglevel", "verbose")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "name",
    ["ctl.start", "ctl.stop", "ctl.restart", "sys.powerctl"],
)
async def test_set_property__rejects_prohibited_control_properties(name: str) -> None:
    calls: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            calls.append(command)
            return await super().shell(serial, command)

    service = SystemPropertiesService(RecordingBackend())

    with pytest.raises(PolicyViolationError):
        await service.set_property("emulator-5554", name, "some-value")

    assert calls == []  # rejected before any backend call


def test_set_property_result_summary_mentions_name_value_and_serial() -> None:
    summary = SetPropertyResult(serial="emulator-5554", name="debug.x", value="y").summary()
    assert "debug.x" in summary
    assert "y" in summary
    assert "emulator-5554" in summary


@pytest.mark.asyncio
async def test_get_property__empty_name_raises_invalid_argument() -> None:
    calls: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            calls.append(command)
            return await super().shell(serial, command)

    service = SystemPropertiesService(RecordingBackend())

    with pytest.raises(InvalidArgumentError):
        await service.get_property("emulator-5554", "   ")
    assert calls == []  # rejected before any getprop


@pytest.mark.asyncio
async def test_get_property_metadata__empty_name_raises_invalid_argument() -> None:
    service = SystemPropertiesService(FakeBackend())

    with pytest.raises(InvalidArgumentError):
        await service.get_property_metadata("emulator-5554", "")
