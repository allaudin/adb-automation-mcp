# Architecture Decision Records

This is the decision log for `adb-automation-mcp`: what was decided, why, and what was
rejected instead. For a description of the *current* system — components, boot
sequence, how things fit together — see `ARCHITECTURE.md`. This file is a historical
record; entries are not rewritten as the system evolves; a superseded decision gets a
new entry that says so, the old one stays.

Started: 2026-08-25

---

## ADR-001: Backend Abstraction

**Status:** Accepted

**Context:** Every module needs to execute adb operations, but modules must be testable
without a real device or `adb` installed, and the execution mechanism should be
swappable (e.g. a future pure-Python driver) without touching module code.

**Decision:** Define `AdbBackend` as a `typing.Protocol` (structural typing, not an
ABC) with six primitive methods: `list_devices`, `shell`, `install`, `uninstall`,
`push`, `pull`. Ship two implementations: `SubprocessBackend` (real, via
`asyncio.create_subprocess_exec`) and `FakeBackend` (deterministic, in-memory,
test-only). Backend methods raise only *transport-level* exceptions
(`DeviceNotFoundError`, `DeviceUnauthorizedError`, `DeviceOfflineError`,
`AdbTimeoutError`, `AdbUnavailableError`) — anything requiring knowledge of *which*
command was run or what its output means is explicitly not the backend's job (see
ADR-014).

**Consequences:** A Protocol keeps third-party backends and test doubles decoupled
from the core package's inheritance hierarchy — a plugin author only needs to satisfy
the method signatures. A third implementation is purely additive: everything above
`AdbBackend` depends only on the six-method Protocol. A pure-Python backend is
deferred — no concrete deployment driver requires it yet, and the Protocol removes
*integration* friction, not *implementation* friction (wire-protocol/auth code is
still real engineering work; prefer wrapping an existing library like `adb-shell`
over writing it from scratch when the need arises). `CommandResult` (`stdout`,
`stderr`, `exit_code`, `duration_ms`) is returned uniformly by both backends.

---

## ADR-002: Device Targeting

**Status:** Accepted

**Context:** An MCP server is a shared, potentially long-lived process; a device farm
or multi-emulator dev box may have several devices attached at once. Implicit
"current device" session state is a classic source of "which device did that just run
on?" bugs.

**Decision:** Every device-scoped tool/resource takes an explicit `serial: str`
parameter — no hidden current-device state on the server. An `adb://devices` resource
exposes what's connected.

**Consequences:** Costs one extra parameter per call, removes an entire class of
ambiguity. A `resolve_serial` helper allows omitting `serial` when exactly one device
is connected, otherwise raising `AmbiguousDeviceError` (multiple candidates) or
`DeviceNotFoundError` (zero) — both carrying the list of currently-connected serials
so the caller doesn't need a round trip to `adb://devices` just to see its options.

*Superseded in part by ADR-015: the `adb://devices` resource shipped as the
`list_connected_devices` tool instead.*

---

## ADR-003: Plugin Architecture for Command Modules

**Status:** Accepted

**Context:** Outside contributors should be able to add new command domains via PR
without understanding or touching registry/server internals, and niche
vendor-specific modules should eventually be able to ship as independent PyPI
packages without forking core.

**Decision:** Command modules are discovered via Python `entry_points` (group
`adb_automation_mcp.modules`), not a hardcoded import list. Each module exposes a static
`ModuleManifest` (name, `service_factory`, `tools`, `resources`) — data, not a
side-effecting registration call. Built-in modules use the exact same mechanism a
third-party plugin would.

**Consequences:** No "core modules are special" second code path to maintain.
Trade-off accepted: slightly more indirection at startup — you check
`pyproject.toml`'s `[project.entry-points."adb_automation_mcp.modules"]` table rather than
grepping for where a module is registered.

---

## ADR-004: Testing Strategy

**Status:** Accepted

**Context:** Every behavior needs to be verifiable without a physical device or
emulator, while still catching backend-specific and integration bugs before release.

**Decision:** A five-layer pyramid: Layer 0 registry meta-tests (typing + docs
contract, see ADR-012), Layer 1 unit/behavior tests against `FakeBackend`, Layer 2
contract tests parametrized over both backends, Layer 3 protocol-level E2E against a
running server, Layer 4 CI emulator integration.

**Consequences:** See `ARCHITECTURE.md`'s testing section for what each layer actually
checks day to day. Layer 4's cadence: a smoke subset runs on every PR; the full
integration suite runs nightly and before a release cut, not on every merge — gating
every merge on the slowest thing in the pipeline trades iteration speed for a
confidence level nightly-plus-pre-release already delivers. Revisit toward per-merge
gating once merge frequency is low enough for the cost to be trivial.

---

## ADR-005: MCP SDK & Framework

**Status:** Accepted

**Context:** Two same-named "FastMCP" projects exist: the standalone PyPI package
(`fastmcp`, PrefectHQ) and the bundled `mcp.server.fastmcp.FastMCP` in the official
`modelcontextprotocol/python-sdk`. Picking wrong means building an entire
tool/resource/policy/envelope layer on a foundation that ages badly.

**Decision:** Build on the standalone `fastmcp` package, not the official SDK's
bundled class.

**Consequences:** The official SDK's own v2.0 beta renames its bundled class to
`MCPServer`, specifically to stop it being confused with the actively-developed
standalone project — which by public estimate powers roughly 70% of MCP servers
across languages at this point. Verified against the actually-installed package
source (`fastmcp` 3.4.7), not just docs, since this ecosystem moves fast enough that
published docs can lag: per-parameter descriptions come from `Args:` parsing unless
overridden by an explicit `Annotated[..., Field(description=...)]`; structured output
(`outputSchema`) is auto-generated from the return type annotation; and a docstring's
`description` field is only the pre-`Args:` summary when the docstring has at least
one documented parameter — with an undocumented fallback where a *zero-parameter*
tool's entire docstring (including `Returns`/`Raises`/`Example`) becomes the
description instead. This distinction drives part of ADR-012's docstring convention.
Re-verify this finding if the pinned `fastmcp` version changes materially — it was
confirmed empirically against one specific version, not guaranteed by any spec.

---

## ADR-006: Concurrency Model

**Status:** Accepted

**Decision:** `asyncio` throughout. `FastMCP` handlers are async; `SubprocessBackend`
uses `asyncio.create_subprocess_exec` (never blocking `subprocess.run`); `FakeBackend`
methods are `async def` too even though nothing needs awaiting, so module code and
tests never branch on backend type and exercise the real calling convention.

---

## ADR-007: Build Tooling

**Status:** Accepted

**Decision:** `uv`, `pyproject.toml`, `src/` layout, Python ≥ 3.10.

---

## ADR-008: Release Automation

**Status:** Accepted

**Decision:** Conventional Commits + `python-semantic-release` in GitHub Actions,
computing the next SemVer version from commit history automatically. PyPI trusted
publishing (OIDC from GitHub Actions) — no long-lived API tokens stored as secrets.
Ships a console-script entry point so end users run it as `uvx adb-automation-mcp`.

**Consequences:** See `ARCHITECTURE.md`'s CI/CD section for the actual pipeline shape
and what's currently implemented versus still planned.

---

## ADR-009: Safety — No Unrestricted Shell Tool

**Status:** Accepted

**Context:** ADB access is effectively root-adjacent control of a device: arbitrary
file read/write, app install/uninstall, broadcast injection. A generic
`adb_shell(serial, command: str)` tool would make every other module redundant and
turn this server into generic remote-code-execution-as-a-tool for whatever it's
plugged into.

**Decision:** Core does not ship a generic shell-passthrough tool. Each module exposes
specific, named, parameterized operations (`install_package`, not
`shell("pm install ...")`). A future raw-shell capability, if one is ever genuinely
needed, must be an explicit, separately-named tool with its own PR and review — not a
default capability contributors can casually add.

---

## ADR-010: Policy / Authorization Layer

**Status:** Accepted

**Context:** Need per-server-instance control over *which tools exist at all* (not
per-caller RBAC — that's explicitly out of scope), with destructive operations
opt-in rather than opt-out, plus a way to constrain host-filesystem access for
`push_file`/`pull_file`, whose `local_path` argument points at the host machine, not
the device.

**Decision:** A flat config: a category default posture (`destructive` denied by
default) plus explicit tool-name `allow`/`deny` lists, evaluated once at
*registration* time — a denied tool is never exposed to the client at all, not
refused after the fact. No rule-selector DSL. Separately, a *call-time* `local_root`
constraint on `push_file`/`pull_file`'s host path, enforced inside the `FileManager`
service class (not the `PolicyEngine`) since it depends on the actual argument value
of a specific call, not just the tool's name — this is the one policy check that
can't be decided at registration time.

**Consequences:** An ordered rule-matching engine with `module:`/`tool:`/`category:`
selectors and first-match-wins precedence was the original design; rejected as
speculative generality for a v1 with roughly twenty tools — a parser and a
footgun-prone ordering convention, built before there's evidence anyone needs
composable rules. The flat model's precedence is three lines: a tool name in `deny` is
always denied; otherwise a name in `allow` is always allowed; otherwise the category
default applies. `local_root` has no default that's safe to ship silently —
`push_file`/`pull_file` refuse to run at all until an operator sets one explicitly,
because unconstrained host-path access lets an agent read or write far outside
anything "device management" implies (credentials, SSH keys, arbitrary host
locations). Every `destructive`-category invocation and every policy denial
(registration-time or call-time) emits a structured audit log line — bundled into
this decision rather than deferred, since the enforcement point already exists and
it's the first thing an operator wants if state changes unexpectedly.

---

## ADR-011: Standard Tool Response Envelope

**Status:** Accepted

**Context:** An agent calling a tool needs a predictable response shape whether the
call succeeded or failed. Most tool failures here are *domain outcomes* ("no device
with that serial," "package isn't installed," "adb timed out") that the agent should
reason about and often recover from — not crashes.

**Decision:** Every tool returns exactly one JSON shape — `status`, `message`, `data`,
`error` — via `ToolResponse[T]`/`ToolError` Pydantic models. Domain failures return a
completely normal, `isError: false` MCP result whose *payload* says
`status: "error"`; MCP-level `isError` is reserved for something the server itself
couldn't classify. Backend and module code never construct the envelope directly —
they raise typed `AdbError` subclasses, and a single wrapper at the registry boundary
converts them.

**Consequences:** The wrapper derives the concrete `ToolResponse[data_type]` from the
tool function's own *raw* return-type annotation (via `get_type_hints`), rather than
requiring a hand-declared alias per tool. The first version of this design required
each tool to declare e.g. `InstallPackageResponse = ToolResponse[PackageInstallResult]`
and annotate the function `-> InstallPackageResponse` — but the function body actually
returns the raw data (the wrapper builds the envelope), so that annotation was
incorrect, and `mypy --strict` caught it the moment real code existed to check against.
The corrected design needs no per-tool alias: the wrapper resolves the raw return
type and builds `ToolResponse[data_type]` itself, then explicitly fixes up the
wrapper's own `__annotations__` afterward (since `functools.wraps` would otherwise
overwrite it with the raw type, which would make `fastmcp` generate the wrong
`outputSchema`). `INTERNAL_ERROR` responses are deliberately generic (no stack trace,
no internal paths) even though the full exception is logged server-side. Resources use
a lighter-weight version — plain-text `message`/`remediation` on failure, no `data`
envelope — since a read either returns content or doesn't.

---

## ADR-012: Mandatory Typing & Self-Documentation Contract

**Status:** Accepted

**Context:** An MCP tool's only interface to the calling agent is its generated schema
plus its description text — there's no human present to explain a parameter or what a
successful call looks like.

**Decision:** Every tool is fully typed (`mypy --strict`, no bare `Any`), preferring
self-documenting types over prose (`Literal`/`Enum` for closed choices,
`Annotated[..., Field(description=...)]` on every parameter). Every tool carries a
Google-style docstring with Summary, Args, Returns, and Example sections (Raises
whenever the tool can fail beyond the generic set — almost always). Both requirements
are enforced by a meta-test that introspects the *live registry*, not a fixed list or
a review-time habit.

**Consequences:** The Example block is written as "Called with `<args>`. A typical
response: `<json>`", not `>>> await tool(...)` doctest/REPL syntax — the actual reader
(an agent doing a doc-lookup, or a human skimming generated docs) never writes Python
to invoke an MCP tool, so REPL syntax addresses the wrong audience. Per ADR-005's
verified findings: for any tool with a documented `Args:` parameter (effectively every
device-scoped tool, since ADR-002 requires `serial`), only the pre-`Args:` summary
paragraph reaches the agent at tool-listing time — `Returns`/`Raises`/`Example` are
excluded, so anything the agent genuinely needs to know *before* calling has to be
said in that first paragraph, in prose. The documented exception: a tool with zero
parameters gets its entire docstring sent as the description instead (rare enough in
this project's tool set not to change the general guidance).

---

## ADR-013: Documentation Site

**Status:** Accepted

**Decision:** `mkdocs-material` + `mkdocstrings[python]`, generating the published API
reference directly from the ADR-012 docstrings, so the same docstring serves both the
agent-facing schema and the human-facing docs — they can't drift apart the way
hand-maintained docs and code inevitably do. Built `--strict` on every PR (fails on
broken internal links/nav, not just missing pages), deployed to GitHub Pages on merge
to `main`. Single "latest" site for v1, no multi-version (`mike`).

**Consequences:** Depends directly on ADR-014's module-level-function requirement —
`mkdocstrings` performs static introspection on importable modules, so a
closure-based `register()` function would give it nothing to point at.

---

## ADR-014: Module Internal Layering

**Status:** Accepted

**Context:** "Add a tool" shouldn't mean writing one handler that does argument
parsing, command construction, adb invocation, output parsing, and error translation
all in one function — that's untestable without the full MCP/registry stack running,
and it duplicates cross-cutting concerns (envelope wrapping, policy checks) per
module.

**Decision:** Three layers per module, each with exactly one reason to change: a thin,
typed, documented module-level tool/resource function → a domain service class (e.g.
`PackageManager`: command construction, output parsing, domain exceptions) →
`AdbBackend` (mechanical execution, transport-level errors only, ADR-001). Tool
functions are plain **module-level** functions — not closures nested inside a
registration call — retrieving their per-request service instance via `fastmcp`'s
`Context.lifespan_context` rather than closure capture.

**Consequences:** `mkdocstrings` (ADR-013) can only see top-level, importable
functions and classes via static introspection — a closure-based tool defined inside
a `register()` call is invisible to it, which is why "module-level" is load-bearing,
not a style preference. An earlier sketch that nested tool functions inside
`register(ctx)`, closing over a locally-constructed service instance, was corrected
for exactly this reason. The service class is independently unit-testable with zero
MCP/registry machinery involved:
`PackageManager(FakeBackend(...)).install(...)` in a plain `pytest` test.
`@category(...)` is a *transparent* marker decorator — it sets `fn.__adb_category__`
and returns the identical function object; `functools.wraps`'s default
`__dict__`-merging behavior means the marker (and the original signature, via
`inspect.signature(..., follow_wrapped=True)`) survive onto the registry's
envelope-wrapping wrapper automatically, with no extra plumbing needed. `FakeBackend`'s
fixture `CommandResult`s for domain scenarios must be realistic — captured or
accurately transcribed from real `adb`/`pm`/`am`/`dumpsys` output, not hand-invented
strings — since a service class's parsing logic is only a trustworthy predictor of
real behavior if it was exercised against real-shaped text.

---

## ADR-015: Device Listing Shipped as a Tool, Not a Resource

**Status:** Accepted — supersedes part of ADR-002

**Context:** ADR-002 planned device listing as an `adb://devices` resource.
Implementing it surfaced two problems, only discoverable once real MCP clients
were in the loop (see ARCHITECTURE.md §9's Layer 3): fastmcp's resource-read path
doesn't serialize pydantic models the way its tool path does, so the resource
function crashed every real read; and, once that was fixed, resource support
itself turned out to be inconsistent across clients — reading `adb://devices`
worked from Claude Code but Claude Desktop couldn't read it at all.

**Decision:** Device listing ships as the `list_connected_devices` tool (in a new
`device_info` module, kept out of `diagnostics`) instead of the `adb://devices`
resource. The resource was removed entirely rather than kept alongside the tool.

**Consequences:** Tools work uniformly across MCP clients; resources currently
don't, at least not to the same degree. `Registry.register_resources` and
`wrap_resource` (ADR-011) stay in `registry.py`, exercised by
`tests/unit/test_registry.py` and `tests/e2e/`'s `register_resources` call, for a
future read where cache/re-read semantics are worth a client-compatibility
tradeoff — but the default for new module data is now a tool, not a resource,
until MCP client resource support is more consistent in practice.

---

## ADR-016: adb Server Lifecycle Backend Primitives, and a `connection` Module

**Status:** Accepted — extends ADR-001

**Context:** A `restart_adb_server` tool — kill the local adb server daemon and
start it again — was needed for cases `check_adb_available` can't fix or even
diagnose (a wedged server process, stale device state). It was first added to
`diagnostics`, then moved out: `diagnostics` only *reports* on the health of an
existing connection and never mutates anything, while restarting the server (and
a planned future tool to connect to a device over TCP, `adb connect host:port`)
*changes* the connection itself — a different concern, and one that shouldn't
gate on `diagnostics`'s read-only framing. Unlike every existing backend method,
neither of these is device-scoped: no `serial`, since they act on the adb server
itself, not any particular device.

**Decision:** New `connection` module, starting with `restart_adb_server`
(`ConnectionService`). Add two primitives to `AdbBackend` (ADR-001),
`kill_server` and `start_server`, one per real `adb` subcommand (`adb
kill-server`, `adb start-server`) at the same mechanical-execution granularity as
every other backend method — composing them into one domain action is the
service layer's job (ADR-014), not the backend's. This grows ADR-001's Protocol
past the "six primitive methods" it named at the time.

**Consequences:** `ConnectionService.restart_adb_server` calls both in sequence
and judges success on `start_server`'s exit code alone — `kill_server` is
idempotent and effectively always reports success even when nothing was running,
so surfacing its result would add noise, not signal. Verified against a real
device: `SubprocessBackend.kill_server`/`start_server` produced the exact
`FakeBackend` fixture output captured for the unit tests (`* daemon not running;
starting now at tcp:5037` / `* daemon started successfully`) — but also
demonstrated a real side effect worth documenting here rather than learning it
again later: restarting the adb server drops any TCP-connected device (`adb
connect host:port`) without reconnecting it automatically, unlike a USB device or
a standard local emulator. `restart_adb_server`'s docstring warns that it's a
global, non-device-scoped operation for this reason.

---

## ADR-017: `connect_device` — a `connect` Primitive, and a Docstring/Tooling Fix

**Status:** Accepted — extends ADR-001/ADR-016

**Context:** `connection` needed a way to reach a device over TCP/IP
(`adb connect host:port`) — devices switched into TCP/IP mode off USB, or a
remote/cloud emulator (this repo's own real device, disconnected earlier by a
live `restart_adb_server` test, is exactly such a case — ADR-016). Live testing
against a real `adb` binary (no reachable device required — refused/unreachable
targets are enough) showed `adb connect` exits `0` unconditionally: `failed to
connect to '127.0.0.1:1': Connection refused` and `failed to connect to
127.0.0.1:9001` (a bare-TCP listener that doesn't speak the adb protocol — no
quotes, no reason given) both came back with `exit_code == 0`, same as a real
success would. Exit code is therefore useless here, unlike `kill_server`/
`start_server` (ADR-016), where it's reliable.

**Decision:** Add a third primitive to `AdbBackend`, `connect(host, port)`, at
the same mechanical-execution granularity as `kill_server`/`start_server`.
`ConnectionService.connect` judges success on adb's message text instead of
exit code: `"connected to"` is present in adb's own success wordings
(`"connected to <addr>"` for a fresh connection, `"already connected to <addr>"`
for the idempotent case — both AOSP's stable, documented format, not
independently captured live since no TCP-reachable device was available this
session) and absent from every failure wording observed.

Separately, adding `connect_device` — the first tool in this codebase with real
parameters — surfaced a second, unrelated bug: `docstring_parser` (the library
`tests/meta/test_tool_contract.py` uses to check every param is documented)
hard-crashes (`ParseError`) on a Google-style `Raises:` section written as
narrative prose rather than `ExceptionType: description` pairs, e.g.
`restart_adb_server`'s "Raises: Propagates the same way most tools do...". Its
`AUTO`-style `parse()` silently swallows that crash and falls back to a
different parser that doesn't understand `Args:` sections at all — so
`doc.params` comes back empty, and the per-param `Args:` check would have
silently never worked for *any* tool with real parameters. This is the same
underlying incompatibility ADR-013's `mkdocstrings`/`griffe` setup already hit
and worked around (a warning there, not a crash) — same root cause,
independently rediscovered via a different tool.

**Decision (docstring convention):** Renamed `Raises:` → `Error handling:` in
every tool docstring that used it (`check_adb_available`, `restart_adb_server`,
`connect_device`) — not a `docstring_parser`/`griffe`-recognized section
keyword, so it's parsed as ordinary prose rather than triggering either tool's
structured-parsing attempt. Chosen over reshaping the prose into fake
`ExceptionType: description` entries, which would misrepresent tools whose
actual point is an *absence* of raises (`check_adb_available` deliberately
doesn't raise for adb being unreachable).

**Consequences:** `test_tool_docstring_is_complete` now actually validates
`Args:` completeness for every tool — previously untested in practice, since no
tool had real parameters before `connect_device`. Any future prose-style
section risks the same `docstring_parser`/`griffe` incompatibility; `Error
handling:` (or any heading outside both tools' recognized section lists) is the
established workaround, not a per-tool judgment call.

---

## ADR-018: `restart_adbd_as_root` — a `root` Primitive, Judged Text-First

**Status:** Accepted — extends ADR-001/ADR-016/ADR-017

**Context:** `connection` needed a way to restart the *device-side* `adbd` daemon as
root (`adb -s <serial> root`) — distinct from `restart_adb_server`'s host-side
`kill-server`/`start-server`, and distinct from every shell-routed module's
`shell(serial, command)` calls, since `root` is a top-level, per-device adb-client
subcommand, not something `adb shell` can express. No adb/rootable device was
available in this environment, unlike ADR-016/ADR-017's live verification against a
real device — the design below is based on `adb root`'s documented behavior, not
independently confirmed here, and is flagged as such in code (`ARCHITECTURE.md` §1,
`RestartAdbdAsRootResult`'s docstring, and the `FakeBackend` fixture comment).

**Decision:** Add a fourth device-scoped primitive to `AdbBackend`, `root(serial)`, at
the same mechanical-execution granularity as `connect`/`disconnect` (ADR-016/017).
`ConnectionService.restart_adbd_as_root` checks for three known `adb root` stdout
wordings *before* looking at the exit code at all — `"restarting adbd as root"`,
`"adbd is already running as root"`, and `"adbd cannot run as root in production
builds"` (the last a normal, expected non-debuggable-build answer, returned as
`success: false` domain data, not raised) — and only falls back to exit-code-based
transport-failure classification (`DeviceNotFoundError`/`BackendError`) when none of
those wordings appear. This differs deliberately from `connect_device`'s ADR-017
design, which trusts that `adb connect` always exits 0 (verified live) and so never
needs to look at exit code at all for its success/failure judgment: here, since the
exit-code behavior is unverified, wording is checked first so an unexpected non-zero
exit on a real device doesn't misclassify a legitimate "reached adbd, got a known
answer" outcome as a transport error.

Categorized `@category("destructive")` — the only deny-by-default/opt-in category
`PolicyEngine` (ADR-010) has — since restarting adbd as root is a genuine privilege
escalation on the device, not a data-mutating write, and no more specific category
exists (see the new Deferred/Open Questions entry on this below).

**Consequences:** Restarting adbd also briefly drops the device off the adb
transport (documented in the tool's docstring, following ADR-016's precedent of
noting `restart_adb_server`'s TCP-disconnect side effect) — an immediately-following
call against the same serial can transiently see a device-not-found failure. Because
the exit-code assumption is unverified, a real-device pass is still owed before
trusting the three-wording classification in production, same caveat as
`system_properties`' `getprop -Z`-based metadata (see that module's own ADR-worthy
note in `ARCHITECTURE.md` §1, though it predates a dedicated ADR entry).

---

## ADR-019: `app_data` Clears Full Data, Not Cache-Only

**Status:** Accepted — supersedes the original cache-only scope of the `app_data`
module

**Context:** The `app_data` module originally exposed a single tool, `clear_app_cache`,
running `adb shell pm clear --cache-only` and deliberately refusing to fall back to
an unscoped `pm clear` (a dedicated `CacheOnlyUnsupportedError` was raised instead).
Device testing showed `--cache-only` is unsupported on a large share of real devices —
it is an Android 11+ (API 30) `PackageManagerShellCommand` addition — so the tool
failed outright there. There is no reliable cross-version ADB substitute for a
per-package cache-only clear: `pm trim-caches <size>` is device-wide and needs a
system permission, and deleting `/data/data/<pkg>/cache` directly needs root. The
only `pm clear` variant supported on effectively every Android version is the
unscoped one, which wipes the package's databases, shared preferences, files *and*
cache.

**Decision:** Repurpose the module to run the unscoped `adb shell pm clear <pkg>`
(plus optional `--user`). Rename `clear_app_cache` → `clear_app_data`, the service
method and result model to match (`ClearAppDataResult`), and recategorize the tool
`@category("read"|"write"|"destructive")` → `destructive` — a full data wipe is
squarely destructive, consistent with `uninstall_package`/`remove_user`, so it is
deny-by-default and only registered when the server opts in
(`ADB_AUTOMATION_ALLOW_DESTRUCTIVE=1`). The `--cache-only` option-parsing failure
branch and its "never silently fall back to a full clear" guard are dropped, since a
full clear is now the intended behavior. `CacheOnlyUnsupportedError` is left in
`errors.py` unused rather than removed, to keep this change scoped to the one module.
Not verified live (no device was available in this environment) — the success/failure
text classification is unchanged from the cache-only implementation, which was
itself shaped on documented `runClear()` behavior.

**Consequences:** Callers of `clear_app_cache` must migrate to `clear_app_data` and
understand it now resets the app to a fresh-install state, not just frees cached
files. Servers that do not set `ADB_AUTOMATION_ALLOW_DESTRUCTIVE=1` no longer see
this tool at all. A cache-only tool could be reintroduced later, gated on the
device's API level, if a real need appears.

---

## ADR-020: Binary `exec_out` Primitive; `take_screenshot` Returns Image Content

**Status:** Accepted — extends ADR-001 / ADR-011 / ADR-014

**Context:** `take_screenshot` originally wrote the PNG to a device-side temp file,
`adb pull`-ed it to a host file under `ADB_AUTOMATION_LOCAL_ROOT`, and returned only
the host path. ADR-001's six primitives all carry `stdout` as `str`, so binary
command output had no seam — the file+pull dance was the documented workaround.
For an MCP server this is the wrong shape: the point of a screenshot tool is that the
model/host can *see* the image, and MCP has a first-class image content block for
exactly that. The bytes never reaching the client defeated the purpose.

**Decision:** Add a seventh `AdbBackend` primitive, `exec_out(serial, command) ->
ExecOutResult`, mapping to `adb exec-out <command>`. `ExecOutResult` mirrors
`CommandResult` but `stdout` is raw `bytes`. `adb exec-out` is chosen over `adb
shell` (which can apply PTY CRLF translation that corrupts a raw PNG) and over
`screencap`+`pull` (no device temp file, no `adb pull`, no host write, one
round-trip). `SubprocessBackend` grows a `_run_bytes` helper that skips the stdout
decode; `_run` now decodes its result. `FakeBackend` returns a real 77-byte 2×2 PNG
fixture.

`ScreenService.take_screenshot(serial, display_id=None)` now runs `screencap -p` via
`exec_out`, validates the PNG signature (empty/garbage output → `BackendError`
rather than an empty image), and returns `TakeScreenshotResult` carrying the raw
bytes in an `image_bytes` field that is `Field(exclude=True)` — excluded from the
structured envelope. A new transparent marker decorator `@image_content` (sibling of
`@category`) flags the tool; on success `wrap_with_envelope` *additionally* emits an
MCP image content block (`fastmcp` `Image` → `ImageContent`) built from
`image_bytes`/`mime_type`, returning a `ToolResult(content=[block],
structured_content=<the usual ToolResponse envelope>)`. Errors are enveloped exactly
as before. This is the **one documented exception** to ADR-011's "every tool returns
a bare `ToolResponse`".

`take_screenshot` loses its `local_path` parameter and no longer consults
`ADB_AUTOMATION_LOCAL_ROOT`; `pull_file` and `stop_log_session` still do. This
supersedes the host-file half of the screen module's original design and follows
ADR-016's precedent for growing the Protocol with its own ADR.

**Consequences:** Breaking change — clients calling `take_screenshot` with
`local_path` must drop it and read the image content block instead. Verified live
against a real emulator (`emulator-5554`): a normal capture round-trips a valid
1080×2400 PNG through the full MCP path; an unknown serial surfaces as
`DEVICE_NOT_FOUND` — note `adb exec-out` reports this differently from `adb shell`
("`error: device '<serial>' not found`", exit 255, vs "`adb: device ...`", exit 1),
so the classifier matches both wordings; and an invalid `display_id` makes `screencap`
print an error to **stdout while still exiting 0**, which the PNG-signature guard
catches as `BACKEND_ERROR` (with screencap's message attached). `exec_out` still has
no Layer 2 contract-test coverage (that layer is unimplemented). The generic
`ExecOutResult` seam is reusable for any future binary-output tool (`screenrecord`
pull, `bugreportz`, etc.).

---

## ADR-021: `take_screenshot` Optional `save`

**Status:** Accepted — extends ADR-020

**Context:** ADR-020 removed `take_screenshot`'s host-file write so the tool became a
pure "return the PNG bytes" call. But some callers legitimately want a file on the
host too — to diff screenshots across a run, attach one to a bug, or keep a capture
log — and the only workaround was a separate `pull_file` against a path the tool
doesn't even leave on the device any more.

**Decision:** Add two optional parameters, `save: bool = False` and
`filename: str | None = None`. With `save=True` the PNG is *also* written to
`<ADB_AUTOMATION_LOCAL_ROOT>/screenshots/` — reusing the shared `local_root` seam
(and its `PolicyViolationError` → `POLICY_DENIED` semantics) that `pull_file` and
`stop_log_session` already use, not a screen-specific mechanism. The `screen`
module's `service_factory` reads `ADB_AUTOMATION_LOCAL_ROOT` the same way
`logger`/`files` do. Files land in a fixed `screenshots/` subdirectory (not the root
directly) so a caller can't scatter PNGs across the whole allow-listed tree; the
`filename` is validated as a bare name (no path separators → `INVALID_ARGUMENT`) and
`.png` is enforced, then still funnelled through `_resolve_local_path` as
defence-in-depth. `save=False` (the default) is byte-for-byte the ADR-020 behaviour,
and the inline MCP image content block is returned unconditionally either way — so
`save` is purely additive, not a mode switch.

**Consequences:** `screen` regains a `local_root` dependency, but only exercised on
the opt-in path — a server with no `ADB_AUTOMATION_LOCAL_ROOT` set is unchanged
unless a caller passes `save=true`, which then fails loudly with `POLICY_DENIED`
rather than silently not saving. This is a minor, backward-compatible addition (new
optional params) — no version-major implications, unlike ADR-020 itself.

---

## ADR-022: `take_screenshot` Saves a File and Returns Its Path

**Status:** Accepted — supersedes ADR-020's "returns image content" decision and
folds in ADR-021; ADR-020's `exec_out` primitive decision stands

**Context:** ADR-020 made `take_screenshot` return the PNG inline as an MCP image
content block, via the one `@image_content` carve-out in `wrap_with_envelope`
(ADR-011's only documented exception). In practice this is the wrong shape for how
the tool is used: a multi-megabyte base64 blob in the tool result bloats the model's
context on every call, most MCP hosts don't render it usefully anyway, and what
callers actually want is a file on disk they can reference by path (to attach to a
bug, diff across a run, hand to another tool). ADR-021 then bolted an opt-in `save=`
onto the side of that, leaving two ways to get the same bytes.

**Decision:** `take_screenshot` now *only* saves. It captures with `exec_out`
(unchanged — ADR-020's primitive is genuinely better than the old
screencap-to-tmpfile + `adb pull` dance and stays), writes the PNG to
`<ADB_AUTOMATION_LOCAL_ROOT>/screenshots/` unconditionally, and returns an ordinary
`ToolResponse[TakeScreenshotResult]` whose `data.local_path` is the absolute path it
wrote (plus `width`/`height`/`size_bytes`). The `save` parameter, the `image_bytes`
and `mime_type` result fields, the `@image_content` marker decorator, and the
`returns_image` branch in `wrap_with_envelope` are all removed — so **every** tool is
a bare `ToolResponse` again, with no ADR-011 exception. `filename` (optional bare
name, `.png` enforced, path separators rejected as `INVALID_ARGUMENT`) is kept.
`ADB_AUTOMATION_LOCAL_ROOT` is now *required* for `take_screenshot` (was opt-in under
ADR-021): unset → `POLICY_DENIED`, same as `pull_file`.

**Consequences:** Breaking — a caller reading the image content block must switch to
reading `data.local_path` and loading the file itself; a server that never set
`ADB_AUTOMATION_LOCAL_ROOT` now gets `POLICY_DENIED` from this tool where ADR-020's
version would have returned bytes. This ships as a major version bump. Verified live
against a connected emulator (`emulator-5554`): a normal call writes a valid
1080×2400 PNG under `screenshots/` and returns its absolute path; `filename=`,
`INVALID_ARGUMENT` on a path-separator name, `DEVICE_NOT_FOUND` on an unknown serial,
and `POLICY_DENIED` with no `local_root` all behave as documented.

---

## Deferred / Open Questions

Decisions deliberately not made yet, with the condition that would trigger revisiting
them:

- **Pure-Python ADB backend** (ADR-001) — revisit if there's a concrete driver (e.g.
  running without platform-tools installed, or wanting lower per-call latency than a
  spawned process). Prefer wrapping an existing library (`adb-shell`) over writing
  wire-protocol/auth code from scratch.
- **Versioned docs (`mike`)** (ADR-013) — revisit once multiple major versions need
  concurrently-published docs.
- **Executable docstring examples** (ADR-012) — actually executing each Example block
  against `FakeBackend` and asserting the output matches would close the loop on docs
  never going stale. Real per-module test-authoring effort; worth doing incrementally
  as modules are built, not a v1 blocker.
- **Additional transports** (HTTP/SSE) — only if a deployment scenario (remote/shared
  server) actually needs it; `stdio` covers local-agent use fully.
- **Workspace split** — revisit if module/contributor count makes independent
  per-module release cadence worth the added packaging complexity.
- **Streaming logcat** — MCP resource subscriptions could eventually support a
  "tail -f"-style push model instead of the current pull-based `read_logcat` tool;
  deferred until there's a client that benefits from it.
- **Generic policy rule DSL** (ADR-010) — revisit only once there's a real,
  demonstrated need for composable module-/category-level rules beyond what an
  explicit tool-name list covers — not speculatively.
