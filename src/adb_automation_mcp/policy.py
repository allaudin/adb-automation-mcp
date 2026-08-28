"""Decides which declared tools actually get exposed to an MCP client.

A flat allow/deny model: a tool name in `deny` always wins, otherwise a tool name in
`allow` always wins, otherwise the category default applies (destructive tools are
denied unless `allow_destructive` is set; read/write are always allowed).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Category = Literal["read", "write", "destructive"]


@dataclass(frozen=True)
class PolicyConfig:
    """Policy settings for one server instance: the destructive-category default
    posture, plus explicit tool-name overrides that win regardless of category.
    """

    allow_destructive: bool = False
    deny: frozenset[str] = field(default_factory=frozenset)
    allow: frozenset[str] = field(default_factory=frozenset)


class PolicyEngine:
    """Answers "should this tool be registered at all?" for a given server instance.

    Consulted by the registry once per tool at registration time, not per call — a
    denied tool is never registered with FastMCP, so it's invisible to the client
    rather than merely refusing to run.
    """

    def __init__(self, config: PolicyConfig | None = None) -> None:
        self._config = config or PolicyConfig()

    def is_allowed(self, module: str, tool_name: str, category: Category) -> bool:
        qualified = f"{module}.{tool_name}"
        if qualified in self._config.deny:
            return False
        if qualified in self._config.allow:
            return True
        if category == "destructive":
            return self._config.allow_destructive
        return True
