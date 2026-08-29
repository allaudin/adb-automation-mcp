"""Layer 0: the per-module tool listing in README.md (and the tool-count summary in
README.md + docs/index.md) must match the live registry. Same source of truth as
test_tool_contract.py — discover_modules() — so a tool added or moved without updating
the docs fails CI here, printing the corrected table to paste in.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from adb_automation_mcp.registry import discover_modules

_REPO_ROOT = Path(__file__).resolve().parents[2]
_README = _REPO_ROOT / "README.md"
_DOCS_INDEX = _REPO_ROOT / "docs" / "index.md"


def _module_rows() -> list[tuple[str, list[str]]]:
    """[(module, [tool names, destructive ones suffixed with †]), ...] — modules with
    tools only, sorted by module name, tools in manifest order.
    """
    rows: list[tuple[str, list[str]]] = []
    for manifest in sorted(discover_modules(), key=lambda m: m.name):
        if not manifest.tools:
            continue
        names = [
            fn.__name__ + ("†" if getattr(fn, "__adb_category__", "read") == "destructive" else "")
            for fn in manifest.tools
        ]
        rows.append((manifest.name, names))
    return rows


def _totals() -> tuple[int, int]:
    rows = _module_rows()
    return sum(len(tools) for _, tools in rows), len(rows)


def _render_table() -> str:
    lines = ["| Module | Tools |", "|---|---|"]
    for module, names in _module_rows():
        rendered = ", ".join(f"`{n[:-1]}`†" if n.endswith("†") else f"`{n}`" for n in names)
        lines.append(f"| `{module}` ({len(names)}) | {rendered} |")
    return "\n".join(lines)


def _fenced(text: str, tag: str) -> str:
    m = re.search(rf"<!-- {tag} -->(.*?)<!-- /{tag} -->", text, re.DOTALL)
    assert m, f"marker <!-- {tag} --> not found"
    return m.group(1).strip()


def test_readme_module_tool_table_matches_registry() -> None:
    got = _fenced(_README.read_text(), "stats:tools-table")
    want = _render_table()
    if got != want:
        pytest.fail(
            "README.md per-module tool table is stale. Replace the "
            "<!-- stats:tools-table --> block with:\n\n" + want
        )


def test_tools_count_matches_registry_in_readme_and_docs() -> None:
    total, _ = _totals()
    problems = []
    for label, path in (("README.md", _README), ("docs/index.md", _DOCS_INDEX)):
        m = re.search(r"\*\*(\d+) tools\.\*\*", path.read_text())
        if m is None:
            problems.append(f"{label}: no '**N tools.**' line found")
        elif int(m.group(1)) != total:
            problems.append(f"{label}: says '**{m.group(1)} tools.**', registry has {total}")
    if problems:
        pytest.fail("tool count is stale:\n  - " + "\n  - ".join(problems))
