# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An MCP server exposing Android Debug Bridge (ADB) capabilities as typed, documented
tools (stdio transport). Full design docs live in-repo — read them before making
non-trivial changes:

- `../docs/ARCHITECTURE.md` — current-state description: component diagram, boot
  sequence, core concepts (Backend/Service/Tool/Registry/Policy/Envelope), module
  layering, repo layout, testing layers, CI/CD. **Read this first.**
- `../docs/ADR.md` — decision log (18 ADRs). Explains *why* things are shaped this way,
  including several non-obvious findings (fastmcp docstring-parsing quirks,
  `docstring_parser` crashing on prose `Raises:` sections, `adb connect`'s exit code
  being useless, etc.) that are easy to accidentally re-break.

Both are living docs updated in place, not changelogs — treat them as authoritative
over any summary here.

## Commands

```bash
uv sync                        # install deps (dev group for testing)
uv run adb-automation-mcp          # run the server (stdio)

uv run pytest                  # meta (Layer 0) + unit (Layer 1) + e2e (Layer 3) tests
uv run pytest tests/unit/user   # run one module's tests
uv run pytest -k test_name      # run a single test by name

uv run mypy src                # strict type checking — must pass, no bare Any
uv run ruff check .            # lint
uv run mkdocs build --strict   # docs site (fails on broken nav/links)
```

CI (`../.github/workflows/ci.yml`) runs `ruff check` → `mypy --strict` → `pytest` on
every push/PR to `main`, plus a strict `mkdocs build` (and `gh-deploy` on merge to
`main`).

Useful env vars (see `server.py` header and ADR-010):

- `ADB_AUTOMATION_BACKEND=fake` — use the deterministic `FakeBackend` instead of a real `adb`
- `ADB_AUTOMATION_ADB_PATH` — explicit path to the `adb` binary
- `ADB_AUTOMATION_TIMEOUT_S` — per-command timeout (default 10s)
- `ADB_AUTOMATION_ALLOW_DESTRUCTIVE=1` — flip default policy posture to also allow
  `destructive`-category tools
- `ADB_AUTOMATION_LOCAL_ROOT` — the folder on this machine where file-saving tools
  (`pull_file`, `stop_log_session`, `take_screenshot`) are allowed to write; no
  default, those tools refuse to run until this is set

## Architecture (essentials — see `../docs/ARCHITECTURE.md` for the full picture)

- **Layering per module**: `tools.py` (thin, typed, module-level async function,
  `@category("read"|"write"|"destructive")`) → `service.py` (domain logic: command
  construction, output parsing, domain exceptions) → `AdbBackend` Protocol
  (mechanical execution only). Tool functions are never closures — they're
  module-level so `mkdocstrings` can statically introspect them (ADR-014).
- **Backend seam**: `AdbBackend` is a `typing.Protocol`. `SubprocessBackend` (real,
  via `asyncio.create_subprocess_exec`) and `FakeBackend` (deterministic, in-memory,
  test-only) are the two implementations. Nothing above this line knows which one
  it's talking to.
- **Modules are plugins**: discovered via `entry_points` (group `adb_automation_mcp.modules`),
  declared in `../pyproject.toml` — the file's `[project.entry-points."adb_automation_mcp.modules"]`
  table is the authoritative list (~20+ built-in modules, e.g. `diagnostics`,
  `device_info`, `connection`, `user`, `logger`, `packages`, `files`, `screen`,
  `input`, `ui`). Built-ins use the exact same mechanism a third-party package would —
  no special-cased "core module" path.
- **Registry** (`registry.py`) wires it all together at import time: discovers
  manifests, asks `PolicyEngine` whether each tool is allowed *before* registering it
  with `FastMCP` (a denied tool is never exposed to the client at all), wraps allowed
  tools with the response envelope.
- **Response envelope**: every tool returns `ToolResponse[T]`
  (`status`/`message`/`data`/`error`) — always `isError: false` at the MCP level; a
  domain failure is `status: "error"` in the payload, not a protocol-level error.
  Module/service code raises typed `AdbError` subclasses; only the registry wrapper
  builds the envelope. No exceptions — every tool returns a bare `ToolResponse`
  (ADR-022 reverted the one `@image_content` carve-out that briefly existed).
- **Policy**: category default posture (`destructive` denied unless
  `ADB_AUTOMATION_ALLOW_DESTRUCTIVE=1`) plus explicit allow/deny lists by tool name,
  evaluated once at registration time. `local_root` (host filesystem writes) is a
  separate *call-time* check inside the service, not the policy engine, since it
  depends on the actual argument value.
- **No generic shell tool** (ADR-009, deliberate): every operation is a specific,
  named, parameterized tool. Don't add an `adb_shell(serial, command: str)`-shaped
  tool.

## Adding a new tool/module

Follow `../docs/ARCHITECTURE.md` §6 and ADR-014 exactly: module-level function in
`tools.py` (never a closure), service method in `service.py`, `AdbBackend` primitive
in `backend/protocol.py` only if the operation needs genuinely new mechanical
execution. Every tool must be fully typed (`mypy --strict`, no bare `Any`) and carry
a Google-style docstring with Summary/Args/Returns/Example — enforced by
`../tests/meta/test_tool_contract.py` against the live registry, not a fixed list. Use
`Error handling:` instead of `Raises:` for prose-style failure descriptions
(`docstring_parser`/`griffe` both mishandle a non-`ExceptionType: description`
`Raises:` section — ADR-017). Add fixture `CommandResult`s to `FakeBackend` using
real, captured `adb`/`pm`/`am`/`dumpsys` output, not hand-invented strings.

## Testing layers

Layer 0 (`../tests/meta`) — registry contract: every registered tool fully typed +
documented. Layer 1 (`../tests/unit`, per module) — service class against
`FakeBackend`, no MCP machinery. Layer 3 (`../tests/e2e`) — real `fastmcp.Client`
against a `Registry`-wired server backed by `FakeBackend`, catching
registration/schema/serialization bugs the lower layers can't see. Layers 2
(dual-backend contract tests) and 4 (CI emulator integration) are not yet
implemented — see `../docs/ARCHITECTURE.md` §9.
