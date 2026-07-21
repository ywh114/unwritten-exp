"""C2 — backfill: the lazy-history pipeline.

evaluate counters (K4) → sample eventfulness (C1) → generate (L1) →
validate (mechanical) → commit (K5 + K7).  History is generated at
measurement time, never simulated; the LLM narrates causes, never
numbers.  Measured: acceptance 50/50 within one retry at T1-flash —
see docs/spec-notes/2026-07-20-c2-archaeological-legibility.md.

Promoted from exp/c2_backfill (2026-07-20, verdict: works).  The exp/
directory keeps the demo, fixtures, tests, and cassettes as living
documentation.
"""

from capability.backfill.schema import (
    BackfillEvent,
    BackfillResult,
    CounterNote,
    NPCCard,
    SeasonChronicle,
    Village,
)
from capability.backfill.pipeline import backfill, build_backfill_prompt
from capability.backfill.validate import validate_chronicle
from capability.backfill.commit import commit_chronicle

__all__ = [
    "BackfillEvent", "BackfillResult", "CounterNote", "NPCCard",
    "SeasonChronicle", "Village",
    "backfill", "build_backfill_prompt", "validate_chronicle",
    "commit_chronicle",
]
