"""Generic Result type for "succeeded with value, or failed with message" returns.

Why this exists:
    Pure-Python idioms often use ``(value, error)`` tuples to signal success vs
    failure without exceptions. That works, but it's untyped, easy to unpack
    wrong, and impossible to distinguish from a real two-element tuple of data.

    ``Result[T]`` makes the intent explicit, type-checkable, and IDE-friendly:

        result = fetch_text(url)
        if not result.is_ok:
            return error_response(result.error)
        text = result.value

Why not raise exceptions instead:
    The failure modes here (bad URL, blocked source, oversized response) are
    *expected user-facing outcomes*, not exceptional programmer errors. Using
    exceptions for normal control flow obscures the happy path and forces
    callers to catch broad exception types just to surface friendly messages.

Why not a third-party Result library (e.g. returns):
    A 25-line dataclass is enough; pulling a dependency for this would be
    over-engineering at this scale.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class Result(Generic[T]):
    """Either ``value`` is set (success) or ``error`` is set (failure).

    Construct via the :meth:`ok` / :meth:`fail` classmethods rather than the
    raw initializer — they make the intent obvious at the call site.
    """

    value: Optional[T] = None
    error: Optional[str] = None

    @property
    def is_ok(self) -> bool:
        """True when this result represents a success."""
        return self.error is None

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        """Wrap a successful value."""
        return cls(value=value)

    @classmethod
    def fail(cls, error: str) -> "Result[T]":
        """Wrap a user-facing error message describing the failure."""
        return cls(error=error)
