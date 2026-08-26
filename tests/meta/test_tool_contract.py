"""Layer 0 registry contract: every tool declared in any module's manifest must be
fully typed and fully documented — checked against the manifests directly, not
against what policy happens to register at runtime, since the typing/docs bar should
hold regardless of whether a given deployment's policy config allows the tool.
"""

from __future__ import annotations

import inspect
from typing import Any, get_type_hints

import pytest
from docstring_parser import parse

from adb_mcp.registry import discover_modules


def _collect_all_tools() -> list[tuple[str, Any]]:
    return [
        (f"{manifest.name}.{fn.__name__}", fn)
        for manifest in discover_modules()
        for fn in manifest.tools
    ]


_TOOLS = _collect_all_tools()
_IDS = [name for name, _ in _TOOLS]


def _real_params(fn: Any) -> list[str]:
    return [name for name in inspect.signature(fn).parameters if name != "ctx"]


@pytest.mark.parametrize("name,fn", _TOOLS, ids=_IDS)
def test_tool_signature_is_fully_typed(name: str, fn: Any) -> None:
    hints = get_type_hints(fn, include_extras=True)
    for param_name in _real_params(fn):
        assert param_name in hints, f"{name}: '{param_name}' is untyped"
        assert hints[param_name] is not Any, f"{name}: '{param_name}' is typed Any"
    assert "return" in hints, f"{name}: missing return type"


@pytest.mark.parametrize("name,fn", _TOOLS, ids=_IDS)
def test_tool_docstring_is_complete(name: str, fn: Any) -> None:
    doc = parse(fn.__doc__ or "")
    assert doc.short_description, f"{name}: missing summary line"

    documented = {p.arg_name for p in doc.params}
    for param_name in _real_params(fn):
        assert param_name in documented, f"{name}: '{param_name}' undocumented in Args"

    assert "Example:" in (fn.__doc__ or ""), f"{name}: missing an Example section"


def test_at_least_one_tool_was_actually_collected() -> None:
    # Guards against the parametrized tests above silently passing on zero cases if
    # entry_points discovery breaks (e.g. package not installed in editable mode).
    assert _TOOLS, "no tools discovered via entry_points — is the package installed?"
