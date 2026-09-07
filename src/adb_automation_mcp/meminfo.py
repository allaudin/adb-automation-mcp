"""Shared, model-free parsers for `adb shell dumpsys meminfo` output.

`processes/get_process_memory` and the whole `memory` module read the same
`dumpsys meminfo` families (`-s <p>` summary, `-a <p>` detail, and the bare
system-wide dump), so the block-finding and table parsing live here rather
than drifting across modules. Everything returns plain primitives (int / str
/ dict / list) — each caller wraps them in its own pydantic model.

`dumpsys meminfo` always exits 0; a target with no running process is
reported in words (`NOT_RUNNING_MARKER`). Callers check for that before
trusting a parse.
"""

from __future__ import annotations

import re

# `dumpsys meminfo -s|-a <target>` prints this (still exit 0) when nothing is
# running for the given package/pid.
NOT_RUNNING_MARKER = "No process found for:"

# "** MEMINFO in pid 1224 [com.android.systemui] **"
_PID_HEADER_RE = re.compile(r"\*\*\s*MEMINFO in pid\s+(?P<pid>\d+)\s+\[(?P<name>[^\]]+)\]")

# The "App Summary" table's TOTAL line (Android 8+):
# "  TOTAL PSS:  104328   TOTAL RSS:  264948   TOTAL SWAP (KB):  8"
_TOTAL_RE = re.compile(
    r"TOTAL PSS:\s*(?P<pss>\d+)\s+TOTAL RSS:\s*(?P<rss>\d+)"
    r"\s+TOTAL SWAP(?:\s*\(KB\))?:\s*(?P<swap>\d+)"
)

# "App Summary" per-category rows whose first integer column is the Pss value.
# "Unknown" is excluded on purpose — its Pss column is blank there, so its
# first integer is actually the Rss value.
_SUMMARY_LABELS: tuple[tuple[str, str], ...] = (
    ("Java Heap", "java_heap_pss_kb"),
    ("Native Heap", "native_heap_pss_kb"),
    ("Code", "code_pss_kb"),
    ("Stack", "stack_pss_kb"),
    ("Graphics", "graphics_pss_kb"),
    ("Private Other", "private_other_pss_kb"),
    ("System", "system_pss_kb"),
)

# One detail-table row from `-a`: a text label (may contain a space or a
# leading dot: "Native Heap", "Dalvik Other", ".so mmap") then 2+ spaces then
# space-separated integers. Labels never contain digits.
_DETAIL_ROW_RE = re.compile(r"^\s*(?P<label>[A-Za-z.][\w .-]*?)\s{2,}(?P<nums>\d[\d\s]*)$")
_DETAIL_COLUMNS: tuple[str, ...] = (
    "pss_total_kb",
    "pss_clean_kb",
    "shared_dirty_kb",
    "private_dirty_kb",
    "shared_clean_kb",
    "private_clean_kb",
    "swap_dirty_kb",
    "rss_total_kb",
    "heap_size_kb",
    "heap_alloc_kb",
    "heap_free_kb",
)

_KV_INT_RE = re.compile(r"([A-Za-z][\w ]*?):\s*(\d+)")

# System-wide `dumpsys meminfo` RAM lines (values are KB with thousands commas).
_TOTAL_RAM_RE = re.compile(r"^\s*Total RAM:\s*([\d,]+)K(?:\s*\((?P<status>[^)]*)\))?", re.MULTILINE)
_FREE_RAM_RE = re.compile(r"^\s*Free RAM:\s*([\d,]+)K", re.MULTILINE)
_USED_RAM_RE = re.compile(r"^\s*Used RAM:\s*([\d,]+)K", re.MULTILINE)
_LOST_RAM_RE = re.compile(r"^\s*Lost RAM:\s*([\d,]+)K", re.MULTILINE)
_ZRAM_RE = re.compile(
    r"^\s*ZRAM:\s*([\d,]+)K physical used for\s*([\d,]+)K in swap\s*\(([\d,]+)K total swap\)",
    re.MULTILINE,
)
# "   103,176K: com.android.systemui (pid 1224) (user 10)"
_TOP_PROC_RE = re.compile(
    r"^\s*([\d,]+)K:\s+(?P<name>.+?)\s+\(pid (?P<pid>\d+)(?:[^)]*)\)(?:\s+\(user (?P<user>\d+)\))?\s*$"
)


def _int(text: str) -> int:
    return int(text.replace(",", ""))


def parse_pid_header(text: str) -> tuple[int | None, str | None]:
    match = _PID_HEADER_RE.search(text)
    if match is None:
        return None, None
    return int(match.group("pid")), match.group("name")


def parse_app_summary(text: str) -> dict[str, int | None]:
    """The "App Summary" block → {<field>_kb: int | None}. Absent rows are None."""
    summary: dict[str, int | None] = {}
    for label, field in _SUMMARY_LABELS:
        m = re.search(rf"^\s*{re.escape(label)}:\s*(\d+)", text, re.MULTILINE)
        summary[field] = int(m.group(1)) if m else None
    totals = _TOTAL_RE.search(text)
    summary["total_pss_kb"] = int(totals.group("pss")) if totals else None
    summary["total_rss_kb"] = int(totals.group("rss")) if totals else None
    summary["total_swap_kb"] = int(totals.group("swap")) if totals else None
    return summary


def parse_detail_table(text: str) -> list[dict[str, int | str]]:
    """The `-a` per-mapping table (Native Heap … Unknown … TOTAL).

    Only the region between the `------` separator and the following blank
    line is read, so the later "Dalvik Details" sub-table is not included.
    """
    lines = text.splitlines()
    start: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        # The rule line under the column headers — a run of "------" groups,
        # possibly space-separated ("------   ------   ------").
        if stripped and "-" in stripped and set(stripped) <= {"-", " "} and len(stripped) >= 6:
            start = i + 1
            break
    if start is None:
        return []

    rows: list[dict[str, int | str]] = []
    for line in lines[start:]:
        if not line.strip():
            break
        m = _DETAIL_ROW_RE.match(line.rstrip())
        if m is None:
            continue
        nums = [int(tok) for tok in m.group("nums").split()]
        row: dict[str, int | str] = {"name": m.group("label").strip()}
        for column, value in zip(_DETAIL_COLUMNS, nums, strict=False):
            row[column] = value
        rows.append(row)
    return rows


def _parse_labelled_block(text: str, heading: str) -> dict[str, int]:
    lines = text.splitlines()
    out: dict[str, int] = {}
    capturing = False
    for line in lines:
        if line.strip() == heading:
            capturing = True
            continue
        if capturing:
            if not line.strip():
                break
            for key, value in _KV_INT_RE.findall(line):
                out[key.strip().lower().replace(" ", "_")] = int(value)
    return out


def parse_objects(text: str) -> dict[str, int]:
    """The `-a` "Objects" section → {views: int, view_root_impl: int, ...}."""
    return _parse_labelled_block(text, "Objects")


def parse_sql(text: str) -> dict[str, int]:
    """The `-a` "SQL" section → {memory_used: int, pagecache_overflow: int, ...}."""
    return _parse_labelled_block(text, "SQL")


def parse_system_ram(text: str) -> dict[str, int | str | None]:
    """The bare `dumpsys meminfo` RAM totals (all *_kb values, plus `status`)."""
    out: dict[str, int | str | None] = {
        "total_ram_kb": None,
        "free_ram_kb": None,
        "used_ram_kb": None,
        "lost_ram_kb": None,
        "zram_physical_used_kb": None,
        "zram_in_swap_kb": None,
        "zram_total_swap_kb": None,
        "status": None,
    }
    total = _TOTAL_RAM_RE.search(text)
    if total:
        out["total_ram_kb"] = _int(total.group(1))
        out["status"] = (total.group("status") or "").strip() or None
    for key, regex in (
        ("free_ram_kb", _FREE_RAM_RE),
        ("used_ram_kb", _USED_RAM_RE),
        ("lost_ram_kb", _LOST_RAM_RE),
    ):
        m = regex.search(text)
        if m:
            out[key] = _int(m.group(1))
    zram = _ZRAM_RE.search(text)
    if zram:
        out["zram_physical_used_kb"] = _int(zram.group(1))
        out["zram_in_swap_kb"] = _int(zram.group(2))
        out["zram_total_swap_kb"] = _int(zram.group(3))
    return out


def parse_top_processes(
    text: str, section: str = "Total PSS by process", limit: int = 15
) -> list[dict[str, int | str | None]]:
    """The bare `dumpsys meminfo` "Total PSS by process:" (or RSS) list."""
    lines = text.splitlines()
    out: list[dict[str, int | str | None]] = []
    capturing = False
    for line in lines:
        if line.strip().rstrip(":") == section:
            capturing = True
            continue
        if capturing:
            m = _TOP_PROC_RE.match(line)
            if m is None:
                if not line.strip():
                    continue
                break
            out.append(
                {
                    "pss_kb": _int(m.group(1)),
                    "name": m.group("name").strip(),
                    "pid": int(m.group("pid")),
                    "user": int(m.group("user")) if m.group("user") else None,
                }
            )
            if len(out) >= limit:
                break
    return out
