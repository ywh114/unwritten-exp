"""L2 — batch-flush policies.

A policy decides when the accumulated event tail is sent. Batching
amortizes the prefix read across more events per call; flushing too
rarely starves the game of freshness. Urgent events always flush
immediately.
"""

from __future__ import annotations

from dataclasses import dataclass

URGENT = "urgent"


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) for budget decisions."""
    return max(1, len(text) // 4)


@dataclass(frozen=True)
class EveryN:
    """Flush when N events are pending (or the event is urgent)."""

    n: int

    def should_flush(self, pending: int, est_tokens: int, priority: str | None) -> bool:
        return priority == URGENT or pending >= self.n


@dataclass(frozen=True)
class TokenBudget:
    """Flush when the tail exceeds an estimated token budget."""

    budget: int

    def should_flush(self, pending: int, est_tokens: int, priority: str | None) -> bool:
        return priority == URGENT or est_tokens >= self.budget


@dataclass(frozen=True)
class OnPriority:
    """Flush only on priority events (and the final forced flush)."""

    level: str = URGENT

    def should_flush(self, pending: int, est_tokens: int, priority: str | None) -> bool:
        return priority == self.level
