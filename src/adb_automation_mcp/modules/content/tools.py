"""Module-level, statically-introspectable tool functions for the content module.

Kept as plain top-level functions, never closures, so that documentation tooling and
the registry meta-test can both introspect them directly.
"""

from __future__ import annotations

from typing import cast

from fastmcp import Context

from adb_automation_mcp.modules.content.service import ContentQueryResult, ContentService
from adb_automation_mcp.registry import category


@category("read")
async def query_content(
    ctx: Context,
    serial: str,
    uri: str,
    projection: list[str] | None = None,
    where: str | None = None,
    sort: str | None = None,
    user_id: int | None = None,
) -> ContentQueryResult:
    """Query a ContentProvider and return its rows: `adb shell content query`.

    Reads from any provider exported to the shell (settings, media store, a
    test app's own provider, ...) and parses `content`'s row output into
    structured column→value maps. Every knob is a typed field — there is no
    raw-argument passthrough. Reading is the only operation here; inserting,
    updating and deleting rows aren't implemented.

    Args:
        serial: The target device's adb serial (see list_connected_devices).
        uri: The provider URI to read, e.g.
            "content://settings/system". Must start with "content://".
        projection: Column names to return (`--projection`). Omit for all
            columns.
        where: A SQL selection clause (`--where`), e.g. "name='volume_music'".
            Omit for no filter.
        sort: A SQL sort order (`--sort`), e.g. "name ASC". Omit for the
            provider's default order.
        user_id: Query the provider as this Android user (`--user`). Omit for
            the current user.

    Returns:
        The serial, the uri and user_id that were queried, row_count, and
        rows — a list of column→value maps in provider order. A value
        `content` printed as the literal "NULL" comes back as null. An empty
        rows list means the query matched nothing (a valid result).

    Error handling:
        A uri that doesn't start with "content://", a negative user_id, or a
        blank/empty projection entry raises INVALID_ARGUMENT before anything
        runs. An unknown serial or unresponsive adb binary raises
        DEVICE_NOT_FOUND/ADB_UNAVAILABLE. `content` exits 0 even when the
        authority is missing or unexported — that raises
        CONTENT_PROVIDER_NOT_FOUND. A provider that rejects the read raises
        PERMISSION_DENIED; any other non-zero exit raises BACKEND_ERROR.

    Example:
        Called with serial="emulator-5554",
        uri="content://settings/system", where="name='volume_music'". A
        typical response:

        ```json
        {
          "status": "success",
          "message": "1 row from content://settings/system on emulator-5554.",
          "data": {
            "serial": "emulator-5554",
            "uri": "content://settings/system",
            "user_id": null,
            "row_count": 1,
            "rows": [{"_id": "0", "name": "volume_music", "value": "5"}]
          },
          "error": null
        }
        ```
    """
    services = cast("dict[str, object]", ctx.lifespan_context["services"])
    content = cast(ContentService, services["content"])
    return await content.query_content(
        serial, uri, projection=projection, where=where, sort=sort, user_id=user_id
    )
