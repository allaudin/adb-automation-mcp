"""Domain logic for the displays module: enumerating a device's logical
displays from `adb shell dumpsys display`, plus reading one display's size
and density from `adb shell wm size` / `adb shell wm density`.

`dumpsys display` is hundreds of lines of unstable internal state; this
module reads only two curated, long-stable markers and parses them in
Python (no shell `grep`/`awk`):

- the ``mViewports=[DisplayViewport{...}, ...]`` line — one entry per
  active viewport, carrying ``displayId``, ``type``, ``densityDpi``,
  ``deviceWidth``/``deviceHeight`` and ``orientation``;
- the ``Display States:`` section — a ``Display Id=N`` / ``Display
  State=ON`` pair per display, which is the authoritative list of *every*
  display (a powered-off display may have no viewport).

The display-state list is the row source; viewport data enriches each row
with dimensions/density/type when present. `wm size` / `wm density` print
a ``Physical ...`` line and, only when an override is in effect, an
``Override ...`` line. Changing display state (setting size/density/
rotation) isn't implemented here.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    DeviceNotFoundError,
    DisplayInfoUnavailableError,
    InvalidArgumentError,
    PermissionDeniedError,
)

_VIEWPORT_RE = re.compile(r"DisplayViewport\{(?P<body>[^}]*)\}")
_DISPLAY_ID_RE = re.compile(r"^\s*Display Id=(?P<id>\d+)\s*$")
_DISPLAY_STATE_RE = re.compile(r"^\s*Display State=(?P<state>\S+)\s*$")

# `wm size` / `wm density` output lines. `wm` does not error on a
# non-existent display id — it prints "Physical size: 0x0" / "Physical
# density: -1" and exits 0 (verified live on a car AVD), which this module
# treats as "no such display" and raises DISPLAY_INFO_UNAVAILABLE for.
_PHYSICAL_SIZE_RE = re.compile(r"^\s*Physical size:\s*(?P<w>\d+)x(?P<h>\d+)\s*$", re.MULTILINE)
_OVERRIDE_SIZE_RE = re.compile(r"^\s*Override size:\s*(?P<w>\d+)x(?P<h>\d+)\s*$", re.MULTILINE)
_PHYSICAL_DENSITY_RE = re.compile(r"^\s*Physical density:\s*(?P<d>-?\d+)\s*$", re.MULTILINE)
_OVERRIDE_DENSITY_RE = re.compile(r"^\s*Override density:\s*(?P<d>-?\d+)\s*$", re.MULTILINE)


class DisplayInfo(BaseModel):
    """One logical display on the device.

    display_id is the logical display ID used everywhere else in this
    server (`-d` on input/screenshot tools, `--display` on activity
    launches). state is the power state from `dumpsys display`'s "Display
    States:" section ("ON", "OFF", "DOZE", ...) — None only if that section
    was missing. type ("INTERNAL", "EXTERNAL", "VIRTUAL", "OVERLAY"),
    width/height (in pixels), density_dpi and rotation (0-3, quarter-turns)
    come from the display's viewport entry and are None when it has no
    active viewport (e.g. a powered-off display) or the field wasn't
    present. unique_id is the stable per-display identifier string when
    available.
    """

    display_id: int
    state: str | None
    type: str | None
    width: int | None
    height: int | None
    density_dpi: int | None
    rotation: int | None
    unique_id: str | None


class DisplayList(BaseModel):
    """The device's logical display inventory (`adb shell dumpsys display`).

    displays is ordered by display_id ascending and always contains at
    least one entry (display 0, the built-in screen) — an empty list is
    never returned; unparseable output raises DISPLAY_INFO_UNAVAILABLE
    instead.
    """

    serial: str
    displays: list[DisplayInfo]

    def summary(self) -> str:
        n = len(self.displays)
        ids = ", ".join(str(d.display_id) for d in self.displays)
        return f"{n} display{'s' if n != 1 else ''} on {self.serial}: {ids}."


class DisplaySize(BaseModel):
    """One display's pixel dimensions (`adb shell wm size`).

    physical_* is the panel's native resolution; override_* is set only
    when a `wm size WxH` override is currently in effect (None otherwise).
    effective_* is the resolution apps actually see — the override when one
    is set, else the physical size.
    """

    serial: str
    display_id: int | None
    physical_width: int
    physical_height: int
    override_width: int | None
    override_height: int | None
    effective_width: int
    effective_height: int

    def summary(self) -> str:
        where = "default display" if self.display_id is None else f"display {self.display_id}"
        base = f"{where} on {self.serial}: {self.effective_width}x{self.effective_height}"
        if self.override_width is not None:
            return f"{base} (override; physical {self.physical_width}x{self.physical_height})."
        return f"{base}."


class DisplayDensity(BaseModel):
    """One display's density in dpi (`adb shell wm density`).

    physical_density is the panel's native density; override_density is set
    only when a `wm density N` override is in effect (None otherwise).
    effective_density is what apps see — the override when set, else physical.
    """

    serial: str
    display_id: int | None
    physical_density: int
    override_density: int | None
    effective_density: int

    def summary(self) -> str:
        where = "default display" if self.display_id is None else f"display {self.display_id}"
        base = f"{where} on {self.serial}: {self.effective_density}dpi"
        if self.override_density is not None:
            return f"{base} (override; physical {self.physical_density}dpi)."
        return f"{base}."


class DisplaysService:
    """Enumerates a connected device's logical displays and reads one
    display's size/density.
    """

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def list_displays(self, serial: str) -> DisplayList:
        result = await self._backend.shell(serial, "dumpsys display")
        _raise_for_dumpsys_failure(serial, result)

        displays = _parse_displays(result.stdout)
        if not displays:
            raise DisplayInfoUnavailableError(
                "dumpsys display produced no recognizable display records.",
                details={"serial": serial, "output_head": result.stdout[:400]},
            )
        return DisplayList(serial=serial, displays=displays)

    async def get_display_size(self, serial: str, display_id: int | None = None) -> DisplaySize:
        _validate_display_id(display_id)
        command = "wm size" if display_id is None else f"wm size -d {display_id}"
        result = await self._backend.shell(serial, command)
        _raise_for_dumpsys_failure(serial, result)

        physical = _PHYSICAL_SIZE_RE.search(result.stdout)
        if physical is None:
            raise DisplayInfoUnavailableError(
                "wm size produced no recognizable 'Physical size:' line.",
                details={"serial": serial, "display_id": display_id, "output": result.stdout[:200]},
            )
        pw, ph = int(physical.group("w")), int(physical.group("h"))
        if pw == 0 or ph == 0:
            raise DisplayInfoUnavailableError(
                f"wm size reported {pw}x{ph} — display id {display_id} does not exist.",
                details={"serial": serial, "display_id": display_id},
            )
        override = _OVERRIDE_SIZE_RE.search(result.stdout)
        ow = int(override.group("w")) if override else None
        oh = int(override.group("h")) if override else None
        return DisplaySize(
            serial=serial,
            display_id=display_id,
            physical_width=pw,
            physical_height=ph,
            override_width=ow,
            override_height=oh,
            effective_width=ow if ow is not None else pw,
            effective_height=oh if oh is not None else ph,
        )

    async def get_display_density(
        self, serial: str, display_id: int | None = None
    ) -> DisplayDensity:
        _validate_display_id(display_id)
        command = "wm density" if display_id is None else f"wm density -d {display_id}"
        result = await self._backend.shell(serial, command)
        _raise_for_dumpsys_failure(serial, result)

        physical = _PHYSICAL_DENSITY_RE.search(result.stdout)
        if physical is None:
            raise DisplayInfoUnavailableError(
                "wm density produced no recognizable 'Physical density:' line.",
                details={"serial": serial, "display_id": display_id, "output": result.stdout[:200]},
            )
        pd = int(physical.group("d"))
        if pd < 0:
            raise DisplayInfoUnavailableError(
                f"wm density reported {pd} — display id {display_id} does not exist.",
                details={"serial": serial, "display_id": display_id},
            )
        override = _OVERRIDE_DENSITY_RE.search(result.stdout)
        od = int(override.group("d")) if override else None
        return DisplayDensity(
            serial=serial,
            display_id=display_id,
            physical_density=pd,
            override_density=od,
            effective_density=od if od is not None else pd,
        )


def _validate_display_id(display_id: int | None) -> None:
    if display_id is not None and display_id < 0:
        raise InvalidArgumentError(
            "display_id must be a non-negative logical display id (see list_displays).",
            details={"display_id": display_id},
        )


def _raise_for_dumpsys_failure(serial: str, result: CommandResult) -> None:
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell command exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    if "Permission Denial" in message or "Permission denied" in message:
        raise PermissionDeniedError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})


def _parse_viewport_fields(body: str) -> dict[str, str]:
    """Split one `DisplayViewport{...}` body into a flat key→value dict.

    Fields are comma-separated `key=value`; a few values themselves contain
    commas inside `Rect(...)` / quotes, but every field this module reads
    (displayId, type, densityDpi, deviceWidth, deviceHeight, orientation,
    uniqueId) is a comma-free scalar, so a simple split is safe for them.
    """
    fields: dict[str, str] = {}
    for chunk in body.split(", "):
        key, sep, value = chunk.partition("=")
        if sep:
            fields[key.strip()] = value.strip().strip("'\"")
    return fields


def _int_or_none(fields: dict[str, str], key: str) -> int | None:
    raw = fields.get(key)
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _parse_displays(text: str) -> list[DisplayInfo]:
    viewports: dict[int, dict[str, str]] = {}
    mviewports_line = next(
        (line for line in text.splitlines() if "mViewports=[" in line), ""
    )
    for match in _VIEWPORT_RE.finditer(mviewports_line):
        fields = _parse_viewport_fields(match.group("body"))
        display_id = _int_or_none(fields, "displayId")
        if display_id is not None:
            viewports[display_id] = fields

    states = _parse_display_states(text)

    # Row source: every display that has a state, unioned with every display
    # that has a viewport (covers format drift where one section is absent).
    display_ids = sorted(set(states) | set(viewports))
    displays: list[DisplayInfo] = []
    for display_id in display_ids:
        fields = viewports.get(display_id, {})
        displays.append(
            DisplayInfo(
                display_id=display_id,
                state=states.get(display_id),
                type=fields.get("type"),
                width=_int_or_none(fields, "deviceWidth"),
                height=_int_or_none(fields, "deviceHeight"),
                density_dpi=_int_or_none(fields, "densityDpi"),
                rotation=_int_or_none(fields, "orientation"),
                unique_id=fields.get("uniqueId"),
            )
        )
    return displays


def _parse_display_states(text: str) -> dict[int, str]:
    """Parse the "Display States:" section into {display_id: state}.

    Each display is a `Display Id=N` line followed (not necessarily
    immediately) by a `Display State=X` line before the next `Display Id=`.
    """
    states: dict[int, str] = {}
    current_id: int | None = None
    for line in text.splitlines():
        id_match = _DISPLAY_ID_RE.match(line)
        if id_match:
            current_id = int(id_match.group("id"))
            continue
        if current_id is not None:
            state_match = _DISPLAY_STATE_RE.match(line)
            if state_match:
                states[current_id] = state_match.group("state")
                current_id = None
    return states
