"""Shared, model-free parsers for `adb shell dumpsys package <pkg>` output.

Both packages/get_package_info and permissions/get_package_permissions read the
same dump; the block-finding and permission-sub-block parsing live here so the
two modules share one implementation instead of drifting. Everything returns
plain primitives (str / bool / list / dict / tuple) — each caller wraps them in
its own pydantic model.

dumpsys always exits 0; an unknown package is reported in words. Callers detect
that with `package_present` before trusting a parse.
"""

from __future__ import annotations

import re

_PKG_BLOCK_RE = re.compile(r"^  Package \[(?P<name>[^\]]+)\] \(")
_KV_RE = re.compile(r"(\w+)=((?:\[[^\]]*\])|(?:\S+))")
_GRANTED_RE = re.compile(r"^\s+(?P<perm>[\w.]+): granted=(?P<granted>true|false)\b")
_GRANTED_TRUE_RE = re.compile(r"^\s+(?P<perm>[\w.]+): granted=true\b")
_USER_HEADER_RE = re.compile(r"^\s+User (?P<uid>\d+):")
_PROT_RE = re.compile(r"^(?P<name>[\w.]+):\s*prot=(?P<prot>\S+)")


def package_present(text: str, package_name: str) -> bool:
    """Whether the dump actually describes `package_name` — i.e. it has a
    `Package [<name>]` block and no "Unable to find package" line for it.
    """
    if f"Unable to find package: {package_name}" in text:
        return False
    return f"Package [{package_name}]" in text


def find_package_block(text: str, package_name: str) -> list[str] | None:
    """The lines of the `Package [<name>] (...)` setting block (header through
    the line before the next column-0 section or next Package block). None if
    that header isn't present.
    """
    lines = text.splitlines()
    start: int | None = None
    for i, ln in enumerate(lines):
        m = _PKG_BLOCK_RE.match(ln)
        if m is not None and m.group("name") == package_name:
            start = i
            break
    if start is None:
        return None

    end = len(lines)
    for i in range(start + 1, len(lines)):
        ln = lines[i]
        if ln and not ln.startswith(" "):
            end = i
            break
        if _PKG_BLOCK_RE.match(ln):
            end = i
            break
    return lines[start:end]


def parse_kv(line: str) -> dict[str, str]:
    """`key=value` / `key=[a b c]` tokens on one line, as a dict (last wins)."""
    return dict(_KV_RE.findall(line))


def first_value(block: list[str], key: str) -> str | None:
    """The first `key=<rest of line>` value in the block, or None. Keeps the
    whole remainder (so values with spaces, like a timestamp, survive).
    """
    prefix = f"{key}="
    for raw in block:
        stripped = raw.strip()
        if stripped.startswith(prefix):
            value = stripped[len(prefix) :].strip()
            return value or None
    return None


def parse_bracket_list(block: list[str], key: str) -> list[str]:
    """`key=[ A B C ]` → ["A", "B", "C"]. Used for flags=/pkgFlags=."""
    for raw in block:
        stripped = raw.strip()
        if stripped.startswith(f"{key}=[") and "]" in stripped:
            inner = stripped[stripped.index("[") + 1 : stripped.rindex("]")]
            return inner.split()
    return []


def parse_requested_permissions(block: list[str]) -> list[str]:
    """The bare permission names under a `requested permissions:` header."""
    perms: list[str] = []
    collecting = False
    for raw in block:
        stripped = raw.strip()
        if stripped == "requested permissions:":
            collecting = True
            continue
        if collecting:
            if not stripped or stripped.endswith(":") or "=" in stripped:
                break
            perms.append(stripped)
    return perms


def parse_declared_permissions(block: list[str]) -> list[tuple[str, str | None]]:
    """(name, protection) for each `NAME: prot=<level>` under a
    `declared permissions:` header.
    """
    out: list[tuple[str, str | None]] = []
    collecting = False
    for raw in block:
        stripped = raw.strip()
        if stripped == "declared permissions:":
            collecting = True
            continue
        if collecting:
            m = _PROT_RE.match(stripped)
            if m is None:
                break
            out.append((m.group("name"), m.group("prot")))
    return out


def parse_install_permissions(block: list[str]) -> list[tuple[str, bool]]:
    """(name, granted) for each `NAME: granted=BOOL` under an
    `install permissions:` header (package-wide, no per-user scope).
    """
    out: list[tuple[str, bool]] = []
    collecting = False
    for raw in block:
        stripped = raw.strip()
        if stripped == "install permissions:":
            collecting = True
            continue
        if collecting:
            m = _GRANTED_RE.match(raw)
            if m is None:
                break
            out.append((m.group("perm"), m.group("granted") == "true"))
    return out


def parse_runtime_permissions_by_user(
    text: str,
) -> dict[int, list[tuple[str, bool, list[str]]]]:
    """{user_id: [(name, granted, [flags...]), ...]} from every
    `runtime permissions:` sub-block in the dump.

    Scans the whole text, not just the setting block: a shared-uid package's
    runtime grants are dumped under a later `Shared users:` section. Entries are
    bucketed under the nearest preceding `User N:` header.
    """
    by_user: dict[int, list[tuple[str, bool, list[str]]]] = {}
    current_user: int | None = None
    in_runtime = False
    for raw in text.splitlines():
        header = _USER_HEADER_RE.match(raw)
        if header is not None:
            current_user = int(header.group("uid"))
            in_runtime = False
            continue
        if raw.strip() == "runtime permissions:":
            in_runtime = True
            continue
        if not in_runtime:
            continue
        m = _GRANTED_RE.match(raw)
        if m is None:
            in_runtime = False
            continue
        flags: list[str] = []
        if "flags=[" in raw:
            inner = raw[raw.index("flags=[") + len("flags=[") : raw.rindex("]")]
            flags = [f for f in inner.replace(" ", "").split("|") if f]
        if current_user is not None:
            by_user.setdefault(current_user, []).append(
                (m.group("perm"), m.group("granted") == "true", flags)
            )
    return by_user


def granted_permission_names(text: str) -> list[str]:
    """Every distinct permission with `granted=true` anywhere in the dump, in
    first-seen order (covers install + runtime, all users; dumpsys package
    <pkg> is filtered to the one package so every such line belongs to it).
    """
    seen: dict[str, None] = {}
    for line in text.splitlines():
        m = _GRANTED_TRUE_RE.match(line)
        if m is not None:
            seen.setdefault(m.group("perm"), None)
    return list(seen)
