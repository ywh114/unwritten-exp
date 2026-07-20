"""K5 — promise record: the single formalism for all narrative constraints.

Design spec §4: canon facts, NPC speech acts, orchestrator intents, summoned-
terrain obligations, prophecies, and rumors are all the same record type —
(scope, predicate, window, strength, provenance) — ordered by authority:
measurement > canon > hard orchestrator > soft orchestrator > NPC utterance.

Two consequences fall out:
* Plots aren't scripts, they're colliding promises.
* Promise density drives the attention economy (cadence, queue priority,
  prefetch).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import StrEnum

from kernel.promise_ledger.predicates import Predicate

# ---------------------------------------------------------------------------
# Authority ordering (higher integer = higher authority; design spec §4.2)
# ---------------------------------------------------------------------------

AUTHORITY_ORDER: dict[str, int] = {
    "npc":                   0,
    "soft_orchestrator":     1,
    "hard_orchestrator":     2,
    "canon":                 3,
    "measurement":           4,
}

# Provenance strings may carry a colon-suffix slug, e.g. "npc:blacksmith".
# The _prefix_ determines the rank; the slug is identity for the graveyard
# and density index.


def authority_rank(provenance: str) -> int:
    for prefix, rank in AUTHORITY_ORDER.items():
        if provenance == prefix or provenance.startswith(prefix + ":"):
            return rank
    return -1  # unrecognised


# ---------------------------------------------------------------------------
# Lifecycle states
# ---------------------------------------------------------------------------

class PromiseState(StrEnum):
    ACTIVE = "active"
    DISCHARGED = "discharged"   # fulfilled / committed as fact
    EXPIRED = "expired"         # window elapsed
    SUSPENDED = "suspended"     # overridden by higher authority, may reconcile
    BROKEN = "broken"           # violated


# ---------------------------------------------------------------------------
# Promise record
# ---------------------------------------------------------------------------

@dataclass
class Promise:
    """One constraint on the world.

    id
        Short hex UUID — the handle everything else references.
    scope
        Region slug the promise constrains, or None for world-scope.
    predicate
        The ground fact this promise asserts / obligates.
    window
        (start_time, end_time_or_None).  None end = perpetual.
    strength
        [0, 1].  1.0 = absolute (measurement, canon).  Soft promises
        can be 0.0 (a whisper) to 0.9 (a vow).
    provenance
        Authority tag (see AUTHORITY_ORDER).  Optional colon-suffix
        carries identity: "npc:miller", "hard_orchestrator:dm".
    state
        Current lifecycle state.
    note
        Human provenance detail for the graveyard / chronicle.
    depends_on
        Promise ids this one transitively depends on — if any of them
        suspends or breaks, this promise cascades.
    suspended_by
        Promise id that suspended this one, if state == SUSPENDED.
    """

    id: str
    scope: str | None
    predicate: Predicate
    window: tuple[float, float | None]  # (start, end_or_None)
    strength: float
    provenance: str
    state: PromiseState = PromiseState.ACTIVE
    note: str = ""
    depends_on: tuple[str, ...] = ()
    suspended_by: str | None = None

    @property
    def authority(self) -> int:
        return authority_rank(self.provenance)

    def active_at(self, t: float) -> bool:
        """Is this promise in force at absolute time `t`?"""
        if self.state != PromiseState.ACTIVE:
            return False
        start, end = self.window
        return t >= start and (end is None or t <= end)


def make_id() -> str:
    return uuid.uuid4().hex[:12]
