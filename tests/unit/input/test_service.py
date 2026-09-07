"""Layer 1 unit tests: InputService against FakeBackend directly — no MCP
registration, no event-loop server startup, just the service.
"""

from __future__ import annotations

import pytest

from adb_automation_mcp.backend.protocol import CommandResult
from adb_automation_mcp.backend.testing import FakeBackend
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)
from adb_automation_mcp.modules.input.service import InputService


@pytest.mark.asyncio
async def test_tap__valid_coordinates_succeeds() -> None:
    service = InputService(FakeBackend())

    result = await service.tap("emulator-5554", 500, 800)

    assert result.serial == "emulator-5554"
    assert result.x == 500
    assert result.y == 800
    assert result.display_id is None
    assert result.success is True


@pytest.mark.asyncio
async def test_tap__zero_coordinates_succeeds() -> None:
    service = InputService(FakeBackend())

    result = await service.tap("emulator-5554", 0, 0)

    assert result.x == 0
    assert result.y == 0
    assert result.success is True


@pytest.mark.asyncio
async def test_tap__sends_display_id_flag() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = InputService(RecordingBackend())

    result = await service.tap("emulator-5554", 500, 800, display_id=1)

    assert captured["command"] == "input -d 1 tap 500 800"
    assert result.display_id == 1


@pytest.mark.asyncio
async def test_tap__omits_display_flag_when_not_given() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = InputService(RecordingBackend())

    await service.tap("emulator-5554", 500, 800)

    assert captured["command"] == "input tap 500 800"


@pytest.mark.asyncio
async def test_tap__negative_x_rejected_before_backend_call() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = InputService(RecordingBackend())

    with pytest.raises(InvalidArgumentError):
        await service.tap("emulator-5554", -1, 800)

    assert "command" not in captured


@pytest.mark.asyncio
async def test_tap__negative_y_rejected_before_backend_call() -> None:
    captured: dict[str, str] = {}

    class RecordingBackend(FakeBackend):
        async def shell(self, serial: str, command: str) -> CommandResult:
            captured["command"] = command
            return await super().shell(serial, command)

    service = InputService(RecordingBackend())

    with pytest.raises(InvalidArgumentError):
        await service.tap("emulator-5554", 500, -1)

    assert "command" not in captured


@pytest.mark.asyncio
async def test_tap__unknown_serial_raises_device_not_found() -> None:
    backend = FakeBackend(
        input_tap_result=CommandResult(
            stdout="", stderr="adb: device 'bogus' not found\n", exit_code=1, duration_ms=10.0
        )
    )
    service = InputService(backend)

    with pytest.raises(DeviceNotFoundError):
        await service.tap("bogus", 500, 800)


@pytest.mark.asyncio
async def test_tap__permission_denial_raises_permission_denied() -> None:
    backend = FakeBackend(
        input_tap_result=CommandResult(
            stdout="",
            stderr="Permission Denial: injecting input events\n",
            exit_code=1,
            duration_ms=10.0,
        )
    )
    service = InputService(backend)

    with pytest.raises(PermissionDeniedError):
        await service.tap("emulator-5554", 500, 800)


@pytest.mark.asyncio
async def test_tap__unclassified_failure_raises_backend_error() -> None:
    backend = FakeBackend(
        input_tap_result=CommandResult(
            stdout="", stderr="Error: Injecting to display 5 was ignored.\n", exit_code=1, duration_ms=5.0
        )
    )
    service = InputService(backend)

    with pytest.raises(BackendError):
        await service.tap("emulator-5554", 500, 800)


# --- swipe / input_text / press_key -----------------------------------------


from adb_automation_mcp.modules.input.service import (
    PressKeyResult,
    SwipeResult,
    TextInputResult,
)


class _Rec(FakeBackend):
    def __init__(self, **kw: object) -> None:
        super().__init__(**kw)  # type: ignore[arg-type]
        self.cmd: str | None = None

    async def shell(self, serial: str, command: str) -> CommandResult:
        self.cmd = command
        return await super().shell(serial, command)


@pytest.mark.asyncio
async def test_swipe__constructs_command_without_duration() -> None:
    b = _Rec()
    r = await InputService(b).swipe("emulator-5554", 100, 800, 100, 200)
    assert b.cmd == "input swipe 100 800 100 200"
    assert isinstance(r, SwipeResult)
    assert r.duration_ms is None


@pytest.mark.asyncio
async def test_swipe__includes_duration_and_display() -> None:
    b = _Rec()
    await InputService(b).swipe("emulator-5554", 1, 2, 3, 4, duration_ms=250, display_id=2)
    assert b.cmd == "input -d 2 swipe 1 2 3 4 250"


@pytest.mark.asyncio
@pytest.mark.parametrize("coords", [(-1, 0, 0, 0), (0, 0, 5, -2)])
async def test_swipe__negative_coord_rejected_before_backend(coords: tuple[int, int, int, int]) -> None:
    b = _Rec()
    with pytest.raises(InvalidArgumentError):
        await InputService(b).swipe("emulator-5554", *coords)
    assert b.cmd is None


@pytest.mark.asyncio
async def test_swipe__negative_duration_rejected_before_backend() -> None:
    b = _Rec()
    with pytest.raises(InvalidArgumentError):
        await InputService(b).swipe("emulator-5554", 1, 2, 3, 4, duration_ms=-1)
    assert b.cmd is None


@pytest.mark.asyncio
async def test_input_text__spaces_become_percent_s_and_quoted() -> None:
    b = _Rec()
    r = await InputService(b).input_text("emulator-5554", "hello world")
    assert b.cmd == "input text hello%sworld"
    assert isinstance(r, TextInputResult)
    assert r.text == "hello world"


@pytest.mark.asyncio
async def test_input_text__special_chars_are_shell_quoted() -> None:
    b = _Rec()
    await InputService(b).input_text("emulator-5554", "a$b`c;d")
    assert b.cmd == "input text 'a$b`c;d'"


@pytest.mark.asyncio
async def test_input_text__empty_rejected_before_backend() -> None:
    b = _Rec()
    with pytest.raises(InvalidArgumentError):
        await InputService(b).input_text("emulator-5554", "")
    assert b.cmd is None


@pytest.mark.asyncio
async def test_press_key__maps_name_to_keycode() -> None:
    b = _Rec()
    r = await InputService(b).press_key("emulator-5554", "BACK")
    assert b.cmd == "input keyevent KEYCODE_BACK"
    assert isinstance(r, PressKeyResult)
    assert r.key == "BACK"
    assert r.keycode == "KEYCODE_BACK"


@pytest.mark.asyncio
async def test_press_key__display_flag_precedes_keyevent() -> None:
    b = _Rec()
    await InputService(b).press_key("emulator-5554", "DPAD_DOWN", display_id=1)
    assert b.cmd == "input -d 1 keyevent KEYCODE_DPAD_DOWN"


@pytest.mark.asyncio
async def test_press_key__unknown_key_rejected_before_backend() -> None:
    b = _Rec()
    with pytest.raises(InvalidArgumentError):
        await InputService(b).press_key("emulator-5554", "BOGUS")  # type: ignore[arg-type]
    assert b.cmd is None


@pytest.mark.asyncio
@pytest.mark.parametrize("verb,call", [
    ("swipe", lambda s: s.swipe("emulator-5554", 1, 2, 3, 4)),
    ("text", lambda s: s.input_text("emulator-5554", "x")),
    ("key", lambda s: s.press_key("emulator-5554", "HOME")),
])
async def test_input_variants__unknown_serial_raises_device_not_found(verb, call) -> None:
    fixtures = {
        "swipe": {"input_swipe_result": CommandResult(stdout="", stderr="adb: device 'b' not found\n", exit_code=1, duration_ms=1)},
        "text": {"input_text_result": CommandResult(stdout="", stderr="adb: device 'b' not found\n", exit_code=1, duration_ms=1)},
        "key": {"input_keyevent_result": CommandResult(stdout="", stderr="adb: device 'b' not found\n", exit_code=1, duration_ms=1)},
    }[verb]
    with pytest.raises(DeviceNotFoundError):
        await call(InputService(FakeBackend(**fixtures)))


def test_new_input_result_summaries() -> None:
    assert "over 250ms" in SwipeResult(
        serial="s", x1=0, y1=0, x2=1, y2=1, duration_ms=250, display_id=None, success=True, output=""
    ).summary()
    assert "Typed 'hi'" in TextInputResult(
        serial="s", text="hi", display_id=None, success=True, output=""
    ).summary()
    assert "Pressed HOME" in PressKeyResult(
        serial="s", key="HOME", keycode="KEYCODE_HOME", display_id=None, success=True, output=""
    ).summary()
