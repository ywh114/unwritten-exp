"""K7 — wiki store: trust-scored facts with deterministic vector recall.

The store is the single access point for world facts shared by the
orchestrator, characters, and the game runner.  It provides:
- write / supersede / forget (archive, never delete)
- recall via vector similarity with mechanical filtering
- chronicle (graveyard view of archived facts)
- promise ingestion (K5 → wiki fact)
- JSON round-trip serialisation

This is a partial port of Ara's `memory/wiki.py` — behaviours ported
are marked `# ARA: memory/wiki.py`.  The LLM subagent, TOML ingestion,
and ChromaDB dependency are intentionally NOT ported.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from kernel.promise_ledger.promise import Promise

from kernel.wiki_store.facts import Fact, FactState, close, make_fact
from kernel.wiki_store.index import HashedIndex

# ---------------------------------------------------------------------------
# Querier context — mechanical bounds only
# ---------------------------------------------------------------------------


@dataclass
class QuerierContext:
    """Mechanical hard bounds on what a querier can retrieve.

    Deliberately thin — entity-specific nuance (character disposition,
    expertise, hidden knowledge) is the LLM reframer's job in C3, not
    K7's.  See the design decisions in the spec / README.
    """

    allowed_provenances: set[str] | None = None  # None = allow all
    trust_floor: float | None = None              # drop facts below this


# ---------------------------------------------------------------------------
# WikiStore
# ---------------------------------------------------------------------------


@dataclass
class WikiStore:
    """Trust-scored world-fact store with deterministic vector recall."""

    _facts: dict[str, Fact] = field(default_factory=dict)
    _index: HashedIndex = field(default_factory=HashedIndex)

    # ---- write -------------------------------------------------------------

    def write(self, fact: Fact) -> str:
        """Upsert a fact by id.  Returns the id."""
        if fact.state == FactState.ACTIVE:
            self._index.add(fact.id, fact.text)
        else:
            self._index.remove(fact.id)
        self._facts[fact.id] = fact
        return fact.id

    def supersede(self, new_fact: Fact, old_id: str) -> tuple[str, str | None]:
        """Close `old_id` via `new_fact` and write the new fact.
        Returns (new_id, old_id)."""
        old = self._facts.get(old_id)
        if old is None:
            raise KeyError(f"unknown fact id {old_id}")
        if old.state != FactState.ACTIVE:
            raise ValueError(f"fact {old_id} is already {old.state.value}")
        closed = close(old, new_fact.valid_from, superseded_by=new_fact.id)
        self.write(closed)
        self.write(new_fact)
        return new_fact.id, old_id

    def forget(self, fact_id: str, t: float) -> str:
        """Close a fact at time `t`.  Never deletes — the graveyard
        is the content (design decision; diverges from Ara's hard-delete)."""
        fact = self._facts.get(fact_id)
        if fact is None:
            raise KeyError(f"unknown fact id {fact_id}")
        if fact.state != FactState.ACTIVE:
            raise ValueError(f"fact {fact_id} is already {fact.state.value}")
        closed = close(fact, t)
        self.write(closed)
        return fact_id

    # ---- recall ------------------------------------------------------------

    def recall(
        self,
        query: str,
        querier: QuerierContext | None = None,
        k: int = 3,
        max_distance: float = 0.65,
        as_of: float | None = None,
        exclude_ids: set[str] | None = None,
    ) -> list[Fact]:
        """Vector recall with mechanical filtering.

        Pipeline: vector search → distance cap → temporal validity
        → exclude_ids → querier provenance/trust bounds.
        Results are ordered by (distance, id) — deterministic.
        """
        candidates = self._index.query(query, k * 3)  # over-fetch for filtering
        results: list[tuple[float, Fact]] = []
        for fact_id, dist in candidates:
            if dist > max_distance:
                continue
            fact = self._facts.get(fact_id)
            if fact is None or fact.state != FactState.ACTIVE:
                continue
            # temporal
            if as_of is not None:
                if as_of < fact.valid_from:
                    continue
                if fact.valid_until is not None and as_of > fact.valid_until:
                    continue
            # exclusions
            if exclude_ids and fact_id in exclude_ids:
                continue
            # querier bounds
            if querier is not None:
                if querier.allowed_provenances is not None:
                    if not any(fact.provenance == p or fact.provenance.startswith(p + ":")
                               for p in querier.allowed_provenances):
                        continue
                if querier.trust_floor is not None and fact.trust < querier.trust_floor:
                    continue
            results.append((dist, fact))
        # sort by (distance, id) — deterministic
        results.sort(key=lambda x: (x[0], x[1].id))
        return [f for _, f in results[:k]]

    # ---- formatting  (ARA: memory/wiki.py) ---------------------------------

    def format_recall(self, facts: list[Fact], annotate_trust: bool = True) -> str:
        """Ara's output convention: `- (trust: x) text` lines.  # ARA: memory/wiki.py"""
        lines: list[str] = []
        for f in facts:
            if annotate_trust:
                lines.append(f"(trust: {f.trust:+.2f}) {f.text}")
            else:
                lines.append(f.text)
        if not lines:
            return "No relevant wiki entries found."
        return "\n".join(f"- {line}" for line in lines)

    def chronicle(self, scope_prefix: str | None = None) -> str:
        """Graveyard view: archived facts as a dry-register chronicle,
        ordered by closing time then id:
           [t=...] text (provenance)

        `scope_prefix` filters by provenance prefix (e.g. "npc:" for the
        rumor archive) — fact ids are content hashes and not meaningful
        to filter on."""
        archived = [f for f in self._facts.values()
                    if f.state == FactState.ARCHIVED]
        if scope_prefix is not None:
            archived = [f for f in archived
                        if f.provenance.startswith(scope_prefix)]
        archived.sort(key=lambda f: (f.valid_until or float("inf"), f.id))
        lines: list[str] = []
        for f in archived:
            t_str = f"t={f.valid_until:.4g}" if f.valid_until is not None else "t=?"
            lines.append(f"[{t_str}] {f.text}  ({f.provenance})")
        return "\n".join(lines) if lines else "(chronicle empty)"

    # ---- K5 integration ----------------------------------------------------

    def ingest_promise(self, promise: Promise, t: float) -> str:
        """Turn a discharged/expired/broken K5 `Promise` into a wiki fact.

        Returns the fact id.  The promise's `predicate.narrative()` becomes
        the fact text; provenance, trust (strength), and window carry over.
        """
        fact = make_fact(
            text=promise.predicate.narrative(),
            trust=promise.strength,
            importance="notable",
            provenance=promise.provenance,
            valid_from=promise.window[0],
            valid_until=promise.window[1],
            state=FactState.ACTIVE,
            promise_id=promise.id,
        )
        self.write(fact)
        return fact.id

    # ---- serialisation -----------------------------------------------------

    def to_dicts(self) -> list[dict]:
        """JSON-able round-trip of every field."""
        return [
            {
                "id": f.id,
                "text": f.text,
                "trust": f.trust,
                "importance": f.importance,
                "provenance": f.provenance,
                "valid_from": f.valid_from,
                "valid_until": f.valid_until,
                "state": str(f.state.value),
                "promise_id": f.promise_id,
                "superseded_by": f.superseded_by,
            }
            for f in self._facts.values()
        ]

    @classmethod
    def from_dicts(cls, dicts: list[dict]) -> "WikiStore":
        """Restore a store from `to_dicts` output."""
        store = cls()
        for d in dicts:
            f = Fact(
                id=d["id"],
                text=d["text"],
                trust=d["trust"],
                importance=d["importance"],
                provenance=d["provenance"],
                valid_from=d["valid_from"],
                valid_until=d["valid_until"],
                state=FactState(d["state"]),
                promise_id=d.get("promise_id"),
                superseded_by=d.get("superseded_by"),
            )
            store.write(f)
        return store
