"""L1 — cost log: the fixed schema every downstream experiment reads.

One `CostEntry` per LLM call (including T0 local calls, all zeros).
Entries carry NO wall-clock time — determinism forbids it; callers pass
a logical `clock`. Cost is computed from token counts and the tier price
table, never from API-reported dollars, so replays recompute identically.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from llm.llm_client.tiers import PRICE_TABLE, Tier


def call_id_for(canonical_request_json: str) -> str:
    """Deterministic call id: content hash of the canonical request."""
    return hashlib.sha256(canonical_request_json.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class CostEntry:
    """One LLM call's accounting. This schema is FROZEN by the L1
    done-when: downstream (L2, C1–C5, the orchestrator audit) reads it."""

    call_id: str            # content hash of the canonical request
    clock: int              # logical clock supplied by the caller
    purpose: str            # caller tag, e.g. "backfill", "demo"
    tier: str               # Tier value
    model: str              # model id, or "local" for T0
    thinking: bool
    attempts: int           # 1 + validation retries used
    prompt_tokens: int
    cached_input_tokens: int
    uncached_input_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    cost_usd: float
    source: str             # "live" | "record" | "replay" | "local"


def compute_cost(model: str, cached: int, uncached: int, output: int) -> float:
    """USD for one call from the tier price table."""
    cached_rate, uncached_rate, out_rate = PRICE_TABLE[model]
    return (cached * cached_rate + uncached * uncached_rate + output * out_rate) / 1e6


class CostLog:
    """Append-only cost log, JSONL on disk."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.entries: list[CostEntry] = []

    def append(self, entry: CostEntry) -> None:
        self.entries.append(entry)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(asdict(entry), sort_keys=True) + "\n")

    def totals(self) -> dict:
        """Aggregate tokens and dollars across all entries."""
        return {
            "calls": len(self.entries),
            "prompt_tokens": sum(e.prompt_tokens for e in self.entries),
            "cached_input_tokens": sum(e.cached_input_tokens for e in self.entries),
            "uncached_input_tokens": sum(e.uncached_input_tokens for e in self.entries),
            "completion_tokens": sum(e.completion_tokens for e in self.entries),
            "reasoning_tokens": sum(e.reasoning_tokens for e in self.entries),
            "cost_usd": sum(e.cost_usd for e in self.entries),
        }
