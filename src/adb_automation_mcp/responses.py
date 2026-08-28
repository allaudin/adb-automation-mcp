"""The standard response envelope every tool call returns, success or failure alike."""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ToolError(BaseModel):
    """Structured error detail attached to a ToolResponse when status is "error"."""

    code: str
    details: dict[str, Any] = Field(default_factory=dict)
    retryable: bool = False
    remediation: str | None = None


class ToolResponse(BaseModel, Generic[T]):
    """The envelope every tool returns: a status, a summary message, and either the
    typed payload (on success) or a ToolError (on failure) — never both.
    """

    status: Literal["success", "error"]
    message: str
    data: T | None = None
    error: ToolError | None = None
