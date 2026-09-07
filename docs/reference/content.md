# content

Reading rows from an exported or shell-accessible ContentProvider on a
connected device (`adb shell content query`). `query_content` takes a typed
`content://` URI plus optional projection, `where` selection, `sort` order,
and `--user` scope — never a raw argument string — and parses `content`'s
`Row: N col=val, …` output into structured column→value maps (a value the
provider rendered as `NULL` comes back as null). An empty result set is a
valid response; a missing/unexported authority raises
`CONTENT_PROVIDER_NOT_FOUND`. Inserting, updating and deleting rows aren't
implemented yet.

::: adb_automation_mcp.modules.content.tools
