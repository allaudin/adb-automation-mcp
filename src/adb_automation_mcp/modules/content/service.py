"""Domain logic for the content module: reading rows from an exported or
otherwise accessible ContentProvider on a connected device
(`adb shell content query`).

Only a typed, constrained slice of the `content` command is exposed — a
`content://` URI plus optional projection / selection / sort / user — never a
raw argument passthrough. `content query` prints one `Row: N col=val, col=val`
line per row; that format is parsed in Python (no shell `grep`/`awk`).
Inserting, updating, and deleting rows aren't implemented here.
"""

from __future__ import annotations

import re
import shlex

from pydantic import BaseModel

from adb_automation_mcp.backend.protocol import AdbBackend, CommandResult
from adb_automation_mcp.errors import (
    BackendError,
    ContentProviderNotFoundError,
    DeviceNotFoundError,
    InvalidArgumentError,
    PermissionDeniedError,
)

# Strips the "Row: <n> " prefix `content` puts on each row line.
_ROW_PREFIX_RE = re.compile(r"^Row:\s+\d+\s+")

# Locates each "col=" field start within a row body: either at the start of
# the body or after a ", " separator. Values may themselves contain "=" (URIs
# with query strings) — those are not preceded by ", " so they don't match.
_FIELD_START_RE = re.compile(r"(?:^|,\s+)([A-Za-z_][A-Za-z0-9_]*)=")

# `content query`'s wording for an empty result set (still exit 0).
_NO_RESULT = "No result found."


class ContentQueryResult(BaseModel):
    """Rows returned by `adb shell content query --uri ...`.

    rows is a list of column→value maps, one per row, in the order the
    provider returned them. Values are the raw text `content` printed; a
    column whose value `content` rendered as the literal `NULL` is mapped to
    null. An empty rows list is a valid result (the query matched nothing),
    not an error. user_id echoes the `--user` scope when one was given.
    """

    serial: str
    uri: str
    user_id: int | None
    row_count: int
    rows: list[dict[str, str | None]]

    def summary(self) -> str:
        scope = "" if self.user_id is None else f" (user {self.user_id})"
        noun = "row" if self.row_count == 1 else "rows"
        return f"{self.row_count} {noun} from {self.uri}{scope} on {self.serial}."


class ContentService:
    """Queries ContentProviders on a connected device."""

    def __init__(self, backend: AdbBackend) -> None:
        self._backend = backend

    async def query_content(
        self,
        serial: str,
        uri: str,
        *,
        projection: list[str] | None = None,
        where: str | None = None,
        sort: str | None = None,
        user_id: int | None = None,
    ) -> ContentQueryResult:
        if not uri.startswith("content://"):
            raise InvalidArgumentError(
                "uri must be a content:// URI, e.g. content://settings/system.",
                details={"serial": serial, "uri": uri},
            )
        if user_id is not None and user_id < 0:
            raise InvalidArgumentError(
                "user_id must be a non-negative Android user id.",
                details={"serial": serial, "user_id": user_id},
            )
        if projection is not None and (not projection or any(not c.strip() for c in projection)):
            raise InvalidArgumentError(
                "projection must be a non-empty list of non-blank column names.",
                details={"serial": serial, "projection": projection},
            )

        parts = ["content", "query", "--uri", shlex.quote(uri)]
        if user_id is not None:
            parts.extend(["--user", str(user_id)])
        if projection is not None:
            parts.extend(["--projection", shlex.quote(":".join(projection))])
        if where is not None:
            parts.extend(["--where", shlex.quote(where)])
        if sort is not None:
            parts.extend(["--sort", shlex.quote(sort)])

        result = await self._backend.shell(serial, " ".join(parts))
        _raise_for_content_failure(serial, uri, result)

        rows = _parse_content_rows(result.stdout)
        return ContentQueryResult(
            serial=serial, uri=uri, user_id=user_id, row_count=len(rows), rows=rows
        )


def _raise_for_content_failure(serial: str, uri: str, result: CommandResult) -> None:
    combined = f"{result.stdout}\n{result.stderr}"
    first_line = next((ln for ln in combined.splitlines() if ln.strip()), "").strip()
    # `content` reports a bad/unexported authority on stdout and still exits 0.
    if "Could not find provider" in combined or "Error while accessing provider" in combined:
        raise ContentProviderNotFoundError(
            first_line or f"No content provider for {uri}.",
            details={"serial": serial, "uri": uri},
        )
    if "Permission Denial" in combined:
        raise PermissionDeniedError(
            first_line or f"Permission denied reading {uri}.",
            details={"serial": serial, "uri": uri},
        )
    if result.exit_code == 0:
        return
    message = (result.stderr or result.stdout).strip() or "adb shell content query exited non-zero."
    if message.startswith("adb:") and "not found" in message:
        raise DeviceNotFoundError(message, details={"serial": serial})
    raise BackendError(message, details={"serial": serial, "exit_code": result.exit_code})


def _parse_content_rows(output: str) -> list[dict[str, str | None]]:
    if output.strip() in ("", _NO_RESULT):
        return []
    rows: list[dict[str, str | None]] = []
    for line in output.splitlines():
        if not line.startswith("Row:"):
            continue
        rows.append(_parse_row_body(_ROW_PREFIX_RE.sub("", line, count=1)))
    return rows


def _parse_row_body(body: str) -> dict[str, str | None]:
    starts = list(_FIELD_START_RE.finditer(body))
    row: dict[str, str | None] = {}
    for i, match in enumerate(starts):
        value_start = match.end()
        value_end = starts[i + 1].start() if i + 1 < len(starts) else len(body)
        raw = body[value_start:value_end].strip()
        row[match.group(1)] = None if raw == "NULL" else raw
    return row
