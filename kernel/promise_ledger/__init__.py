"""K5 — promise_ledger: the constraint engine.

The heart of the Unwritten constraint system.  Promises are the single
formalism for all narrative constraints — canon facts, NPC speech acts,
orchestrator intents, summoned-terrain obligations, prophecies, and rumors
— ordered by authority.  The ledger enforces hard consistency, suspends
lower-authority conflicts (TMS-lite), drives the attention economy via a
density index, and archives discharged promises to the graveyard.

Pure logic.  No LLM, no positions, no engine.
"""

from kernel.promise_ledger.predicates import Predicate, PredicateKind
from kernel.promise_ledger.promise import Promise, PromiseState, make_id
from kernel.promise_ledger.ledger import PromiseLedger

__all__ = [
    "PredicateKind",
    "Predicate",
    "Promise",
    "PromiseState",
    "PromiseLedger",
    "make_id",
]
