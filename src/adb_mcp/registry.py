"""Module discovery via Python entry_points, and envelope-wrapping tool registration.

Tool/resource functions stay module-level and untouched by any of this — documentation
tooling and the registry meta-test both introspect them directly, before the registry
ever sees them. The registry's job is entirely at the boundary: read each module's
static manifest, apply policy, and wrap each allowed function so it always returns a
ToolResponse instead of raising.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any, Literal, TypeVar, get_type_hints

from fastmcp.exceptions import ResourceError

from adb_mcp.errors import AdbError
from adb_mcp.policy import Category, PolicyEngine
from adb_mcp.responses import ToolError, ToolResponse

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from adb_mcp.backend.protocol import AdbBackend

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "adb_mcp.modules"

F = TypeVar("F", bound=Callable[..., Any])


def category(value: Category) -> Callable[[F], F]:
    """Transparent marker decorator: sets __adb_category__ and returns the identical
    function object, unwrapped — documentation tooling, inspect.signature, and
    functools.wraps all see the real function, unchanged.
    """

    def decorator(fn: F) -> F:
        fn.__adb_category__ = value  # type: ignore[attr-defined]
        return fn

    return decorator


@dataclass(frozen=True)
class ModuleManifest:
    """A module's static declaration of what it provides: a factory for its service
    instance, and the list of tool/resource functions the registry should wire up.
    Plain data, not a side-effecting registration call — a module never registers
    itself; the registry reads this and does all registration centrally.
    """

    name: str
    service_factory: Callable[[AdbBackend], object]
    tools: list[Callable[..., Awaitable[Any]]] = field(default_factory=list)
    resources: list[tuple[str, Callable[..., Awaitable[Any]]]] = field(default_factory=list)


def discover_modules() -> list[ModuleManifest]:
    """Load every ModuleManifest registered under the adb_mcp.modules entry_point
    group — built-in and third-party modules are discovered identically.
    """
    manifests: list[ModuleManifest] = []
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        manifest = ep.load()
        manifests.append(manifest)
    return manifests


def wrap_with_envelope(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Converts a plain tool function (declares its raw data return type, returns
    data, raises AdbError) into one that returns ToolResponse[<that data type>].

    The concrete envelope type is derived here, not hand-declared per tool —
    `-> AdbAvailability` on the tool function is the truth (that's what its body
    actually returns); `ToolResponse[AdbAvailability]` is what the wrapper actually
    returns, and its __annotations__ are corrected below (functools.wraps would
    otherwise overwrite them with the original's, breaking the outputSchema fastmcp
    generates from the *wrapper*, which is what's actually registered).
    """
    hints = get_type_hints(fn, include_extras=True)
    data_type = hints["return"]
    response_cls = ToolResponse[data_type]  # type: ignore[valid-type]

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            data = await fn(*args, **kwargs)
            message = data.summary() if hasattr(data, "summary") else f"{fn.__name__} completed successfully."
            return response_cls(status="success", message=message, data=data, error=None)
        except AdbError as exc:
            logger.info("tool %s returned a domain error: %s", fn.__name__, exc)
            return response_cls(
                status="error",
                message=str(exc),
                data=None,
                error=ToolError(
                    code=exc.code,
                    details=exc.details,
                    retryable=exc.retryable,
                    remediation=exc.remediation,
                ),
            )
        except Exception:
            logger.exception("unexpected error in tool %s", fn.__name__)
            return response_cls(
                status="error",
                message="An unexpected server error occurred. This has been logged.",
                data=None,
                error=ToolError(
                    code="INTERNAL_ERROR",
                    details={},
                    retryable=False,
                    remediation="Not fixable by retrying or changing arguments; report to the server operator.",
                ),
            )

    # functools.wraps copied fn's own __annotations__ (including its raw `-> data_type`
    # return) onto wrapper; correct it to the actual enveloped return type so fastmcp's
    # outputSchema (generated from the wrapper it's actually given) matches reality.
    # Copy the dict first: on Python < 3.14, functools.wraps aliases wrapper's
    # __annotations__ to the *same* dict object as fn's (this stopped being true in
    # 3.14 under PEP 649's lazy-annotations change, which masked this on newer
    # interpreters) — mutating in place would corrupt fn's own return annotation too,
    # so a second wrap_with_envelope(fn) call for the same fn (e.g. Registry.register_tools
    # run more than once against the same discovered module in one process, as the
    # Layer 3 E2E tests do) would double-envelope into ToolResponse[ToolResponse[T]].
    wrapper.__annotations__ = dict(wrapper.__annotations__)
    wrapper.__annotations__["return"] = response_cls
    return wrapper


def wrap_resource(fn: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
    """Converts a plain resource function (returns data, raises AdbError) into one
    that raises fastmcp's ResourceError on failure instead.

    Deliberately lighter-weight than wrap_with_envelope (ADR-011): a resource read
    either returns its content directly or fails with a plain-text message — no
    ToolResponse envelope, since there's no "data vs error" branch for a client to
    switch on the way there is for a tool call result.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except AdbError as exc:
            logger.info("resource %s returned a domain error: %s", fn.__name__, exc)
            message = str(exc) if not exc.remediation else f"{exc} {exc.remediation}"
            raise ResourceError(message) from exc
        except Exception:
            logger.exception("unexpected error in resource %s", fn.__name__)
            raise ResourceError(
                "An unexpected server error occurred. This has been logged."
            ) from None

    return wrapper


class Registry:
    """Wires discovered modules up to a running FastMCP instance.

    Three responsibilities, kept together because they happen at the same moments
    in a process's life: at startup, register_tools and register_resources each
    read every module's manifest, ask the PolicyEngine whether each tool/resource is
    allowed, and hand the allowed ones (wrapped in their respective envelopes) to
    FastMCP; later, build_services constructs one service instance per module from
    the shared backend, once the backend exists.
    """

    def __init__(self, policy: PolicyEngine) -> None:
        self._policy = policy

    def register_tools(self, mcp: FastMCP, manifests: list[ModuleManifest]) -> None:
        for manifest in manifests:
            for fn in manifest.tools:
                tool_category: Literal["read", "write", "destructive"] = getattr(
                    fn, "__adb_category__", "read"
                )
                if not self._policy.is_allowed(manifest.name, fn.__name__, tool_category):
                    logger.info(
                        "policy denied %s.%s (category=%s) — not registered",
                        manifest.name,
                        fn.__name__,
                        tool_category,
                    )
                    continue
                mcp.add_tool(wrap_with_envelope(fn))

    def register_resources(self, mcp: FastMCP, manifests: list[ModuleManifest]) -> None:
        # Every resource is implicitly category "read" (ARCHITECTURE.md §7) — a
        # resource is by definition an idempotent, addressable read, so there's no
        # per-function @category marker to look up the way there is for tools; the
        # policy engine's explicit allow/deny-by-name overrides still apply.
        for manifest in manifests:
            for uri, fn in manifest.resources:
                if not self._policy.is_allowed(manifest.name, fn.__name__, "read"):
                    logger.info(
                        "policy denied resource %s.%s (uri=%s) — not registered",
                        manifest.name,
                        fn.__name__,
                        uri,
                    )
                    continue
                # Every resource here returns typed, structured data (mirroring
                # tools) rather than raw text/binary, so application/json is the
                # correct mime type uniformly — fastmcp defaults to text/plain
                # otherwise, which would mislabel the actual JSON content.
                mcp.resource(uri, mime_type="application/json")(wrap_resource(fn))

    def build_services(
        self, backend: AdbBackend, manifests: list[ModuleManifest]
    ) -> dict[str, object]:
        return {manifest.name: manifest.service_factory(backend) for manifest in manifests}
