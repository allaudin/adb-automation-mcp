"""Layer 1 unit tests: UiService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    AdbTimeoutError,
    AdbUnavailableError,
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
    RemoteFileNotFoundError,
    UiAutomatorFailedError,
    UiHierarchyUnavailableError,
)
from adb_automation_mcp.modules.ui.service import UiService

# Two-node hierarchy with a matchable, clickable "Phone" TextView — same shape
# as FakeBackend's default cat fixture, restated here for the find/wait tests.
_TWO_NODE_XML = (
    "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
    '<hierarchy rotation="0">'
    '<node index="0" text="" resource-id="" class="android.widget.FrameLayout" '
    'package="com.android.launcher3" content-desc="" clickable="false" enabled="true" '
    'focused="false" bounds="[0,0][1080,2400]">'
    '<node index="0" text="Phone" resource-id="com.android.launcher3:id/icon" '
    'class="android.widget.TextView" package="com.android.launcher3" content-desc="Phone" '
    'clickable="true" enabled="true" focused="false" long-clickable="true" '
    'bounds="[100,200][300,400]" />'
    "</node>"
    "</hierarchy>"
)
_EMPTY_XML = (
    "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?><hierarchy rotation=\"0\" />"
)


class _ScriptedHierarchyBackend(FakeBackend):
    """Returns a scripted sequence of `cat` (hierarchy) payloads, one per
    capture, holding on the last once exhausted.
    """

    def __init__(self, xml_sequence: list[str]) -> None:
        super().__init__()
        self._xml_sequence = xml_sequence
        self.cat_calls = 0

    async def shell(
        self, serial: str, command: str, timeout_s: float | None = None
    ) -> CommandResult:
        if command.startswith("cat ") and "adb_automation_mcp_ui_dump_" in command:
            idx = min(self.cat_calls, len(self._xml_sequence) - 1)
            self.cat_calls += 1
            return CommandResult(
                stdout=self._xml_sequence[idx], stderr="", exit_code=0, duration_ms=10.0
            )
        return await super().shell(serial, command, timeout_s)


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__successful_dump_returns_parsed_xml() -> None:
    service = UiService(FakeBackend())

    result = await service.dump_ui_hierarchy("emulator-5554")

    assert result.serial == "emulator-5554"
    assert result.success is True
    assert "<hierarchy" in result.xml
    assert result.node_count == 2
    assert "UI hierarchy dumped to:" in result.output


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__cleans_up_temp_file_on_success() -> None:
    commands: list[str] = []

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            commands.append(command)
            return await super().shell(serial, command)

    service = UiService(RecordingBackend())

    await service.dump_ui_hierarchy("emulator-5554")

    assert commands[0].startswith("uiautomator dump /data/local/tmp/adb_automation_mcp_ui_dump_")
    assert commands[1].startswith("cat /data/local/tmp/adb_automation_mcp_ui_dump_")
    assert commands[2].startswith("rm -f /data/local/tmp/adb_automation_mcp_ui_dump_")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__empty_hierarchy_returns_zero_nodes() -> None:
    backend = FakeBackend(
        ui_hierarchy_cat_result=CommandResult(stdout="", stderr="", exit_code=0, duration_ms=5.0)
    )
    service = UiService(backend)

    result = await service.dump_ui_hierarchy("emulator-5554")

    assert result.success is True
    assert result.xml == ""
    assert result.node_count == 0


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__uiautomator_command_not_found_raises_uiautomator_failed() -> None:
    backend = FakeBackend(
        uiautomator_dump_result=CommandResult(
            stdout="", stderr="/system/bin/sh: uiautomator: not found\n", exit_code=127, duration_ms=5.0
        )
    )
    service = UiService(backend)

    with pytest.raises(UiAutomatorFailedError):
        await service.dump_ui_hierarchy("emulator-5554")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__null_root_node_raises_ui_hierarchy_unavailable() -> None:
    backend = FakeBackend(
        uiautomator_dump_result=CommandResult(
            stdout="",
            stderr="ERROR: null root node returned by UiTestAutomationBridge.\n",
            exit_code=0,
            duration_ms=800.0,
        )
    )
    service = UiService(backend)

    with pytest.raises(UiHierarchyUnavailableError):
        await service.dump_ui_hierarchy("emulator-5554")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        uiautomator_dump_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )
    service = UiService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.dump_ui_hierarchy("bogus")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        uiautomator_dump_result=CommandResult(
            stdout="", stderr="Permission Denial: dumping UI hierarchy\n", exit_code=1, duration_ms=5.0
        )
    )
    service = UiService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.dump_ui_hierarchy("emulator-5554")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__temp_file_missing_raises_remote_file_not_found() -> None:
    backend = FakeBackend(
        ui_hierarchy_cat_result=CommandResult(
            stdout="",
            stderr="cat: /data/local/tmp/adb_automation_mcp_ui_dump_xyz.xml: No such file or directory\n",
            exit_code=1,
            duration_ms=5.0,
        )
    )
    service = UiService(backend)

    with pytest.raises(RemoteFileNotFoundError):
        await service.dump_ui_hierarchy("emulator-5554")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__unclassified_dump_failure_raises_uiautomator_failed() -> None:
    backend = FakeBackend(
        uiautomator_dump_result=CommandResult(
            stdout="", stderr="java.lang.RuntimeException: crashed\n", exit_code=1, duration_ms=5.0
        )
    )
    service = UiService(backend)

    with pytest.raises(UiAutomatorFailedError):
        await service.dump_ui_hierarchy("emulator-5554")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__unclassified_cat_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        ui_hierarchy_cat_result=CommandResult(
            stdout="", stderr="some other unclassified failure\n", exit_code=1, duration_ms=5.0
        )
    )
    service = UiService(backend)

    with pytest.raises(BackendError):
        await service.dump_ui_hierarchy("emulator-5554")


@pytest.mark.asyncio
async def test_dump_ui_hierarchy__backend_unavailable_raises_adb_unavailable() -> None:
    service = UiService(FakeBackend(unavailable=True))

    with pytest.raises(AdbUnavailableError):
        await service.dump_ui_hierarchy("emulator-5554")


# --- find_ui_elements ------------------------------------------------------


@pytest.mark.asyncio
async def test_find_ui_elements__by_exact_text_returns_one_match_with_bounds() -> None:
    service = UiService(_ScriptedHierarchyBackend([_TWO_NODE_XML]))

    result = await service.find_ui_elements("emulator-5554", text="Phone")

    assert result.match_count == 1
    assert result.returned_count == 1
    assert result.truncated is False
    el = result.elements[0]
    assert el.text == "Phone"
    assert el.resource_id == "com.android.launcher3:id/icon"
    assert el.class_name == "android.widget.TextView"
    assert el.clickable is True
    assert el.long_clickable is True
    assert el.bounds is not None
    assert (el.bounds.center_x, el.bounds.center_y) == (200, 300)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "criteria",
    [
        {"text_contains": "hon"},
        {"resource_id": "icon"},
        {"resource_id": "com.android.launcher3:id/icon"},
        {"class_name": "TextView"},
        {"class_name": "android.widget.TextView"},
        {"content_desc": "Phone"},
        {"clickable": True},
        {"text": "Phone", "clickable": True, "enabled": True},
    ],
)
async def test_find_ui_elements__criteria_variants_match_the_textview(
    criteria: dict[str, object],
) -> None:
    service = UiService(_ScriptedHierarchyBackend([_TWO_NODE_XML]))

    result = await service.find_ui_elements("emulator-5554", **criteria)  # type: ignore[arg-type]

    assert result.match_count == 1
    assert result.elements[0].text == "Phone"


@pytest.mark.asyncio
async def test_find_ui_elements__package_matches_both_nodes() -> None:
    service = UiService(_ScriptedHierarchyBackend([_TWO_NODE_XML]))

    result = await service.find_ui_elements("emulator-5554", package="com.android.launcher3")

    assert result.match_count == 2


@pytest.mark.asyncio
async def test_find_ui_elements__limit_truncates_but_reports_true_total() -> None:
    service = UiService(_ScriptedHierarchyBackend([_TWO_NODE_XML]))

    result = await service.find_ui_elements(
        "emulator-5554", package="com.android.launcher3", limit=1
    )

    assert result.match_count == 2
    assert result.returned_count == 1
    assert result.truncated is True


@pytest.mark.asyncio
async def test_find_ui_elements__no_match_is_ordinary_success() -> None:
    service = UiService(_ScriptedHierarchyBackend([_TWO_NODE_XML]))

    result = await service.find_ui_elements("emulator-5554", text="Nonexistent")

    assert result.match_count == 0
    assert result.elements == []


@pytest.mark.asyncio
async def test_find_ui_elements__no_criteria_raises_invalid_argument() -> None:
    service = UiService(_ScriptedHierarchyBackend([_TWO_NODE_XML]))

    with pytest.raises(InvalidArgumentError):
        await service.find_ui_elements("emulator-5554")


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_limit", [0, -1, 501, 10_000])
async def test_find_ui_elements__bad_limit_raises_invalid_argument(bad_limit: int) -> None:
    service = UiService(_ScriptedHierarchyBackend([_TWO_NODE_XML]))

    with pytest.raises(InvalidArgumentError):
        await service.find_ui_elements("emulator-5554", text="Phone", limit=bad_limit)


@pytest.mark.asyncio
async def test_find_ui_elements__malformed_hierarchy_is_zero_matches_not_crash() -> None:
    service = UiService(_ScriptedHierarchyBackend(["<hierarchy><node text='Phone' "]))

    result = await service.find_ui_elements("emulator-5554", text="Phone")

    assert result.match_count == 0


@pytest.mark.asyncio
async def test_find_ui_elements__empty_hierarchy_is_zero_matches() -> None:
    service = UiService(_ScriptedHierarchyBackend([""]))

    result = await service.find_ui_elements("emulator-5554", text="Phone")

    assert result.match_count == 0


@pytest.mark.asyncio
async def test_find_ui_elements__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        uiautomator_dump_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=5.0
        )
    )

    with pytest.raises(DeviceNotFoundError):
        await UiService(backend).find_ui_elements("bogus", text="Phone")


# --- wait_for_ui_element --------------------------------------------------


@pytest.mark.asyncio
async def test_wait_for_ui_element__present_immediately() -> None:
    backend = _ScriptedHierarchyBackend([_TWO_NODE_XML])
    service = UiService(backend)

    result = await service.wait_for_ui_element(
        "emulator-5554", text="Phone", timeout_s=1.0, poll_interval_s=0.1
    )

    assert result.satisfied is True
    assert result.condition == "present"
    assert result.match_count == 1
    assert result.poll_count == 1
    assert backend.cat_calls == 1


@pytest.mark.asyncio
async def test_wait_for_ui_element__present_after_a_delay() -> None:
    backend = _ScriptedHierarchyBackend([_EMPTY_XML, _EMPTY_XML, _TWO_NODE_XML])
    service = UiService(backend)

    result = await service.wait_for_ui_element(
        "emulator-5554", text="Phone", timeout_s=2.0, poll_interval_s=0.1
    )

    assert result.satisfied is True
    assert result.poll_count == 3


@pytest.mark.asyncio
async def test_wait_for_ui_element__present_times_out() -> None:
    service = UiService(_ScriptedHierarchyBackend([_EMPTY_XML]))

    with pytest.raises(AdbTimeoutError):
        await service.wait_for_ui_element(
            "emulator-5554", text="Phone", timeout_s=0.3, poll_interval_s=0.1
        )


@pytest.mark.asyncio
async def test_wait_for_ui_element__absent_immediately() -> None:
    service = UiService(_ScriptedHierarchyBackend([_TWO_NODE_XML]))

    result = await service.wait_for_ui_element(
        "emulator-5554", text="Nonexistent", condition="absent", timeout_s=1.0, poll_interval_s=0.1
    )

    assert result.satisfied is True
    assert result.condition == "absent"
    assert result.match_count == 0


@pytest.mark.asyncio
async def test_wait_for_ui_element__absent_times_out_while_element_stays() -> None:
    service = UiService(_ScriptedHierarchyBackend([_TWO_NODE_XML]))

    with pytest.raises(AdbTimeoutError):
        await service.wait_for_ui_element(
            "emulator-5554",
            text="Phone",
            condition="absent",
            timeout_s=0.3,
            poll_interval_s=0.1,
        )


@pytest.mark.asyncio
async def test_wait_for_ui_element__no_criteria_raises_invalid_argument() -> None:
    service = UiService(_ScriptedHierarchyBackend([_TWO_NODE_XML]))

    with pytest.raises(InvalidArgumentError):
        await service.wait_for_ui_element("emulator-5554")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_s": 0.0},
        {"timeout_s": -1.0},
        {"timeout_s": 999.0},
        {"poll_interval_s": 0.0},
        {"poll_interval_s": 60.0},
        {"condition": "bogus"},
    ],
)
async def test_wait_for_ui_element__out_of_range_params_raise_invalid_argument(
    kwargs: dict[str, object],
) -> None:
    service = UiService(_ScriptedHierarchyBackend([_TWO_NODE_XML]))

    with pytest.raises(InvalidArgumentError):
        await service.wait_for_ui_element("emulator-5554", text="Phone", **kwargs)  # type: ignore[arg-type]
