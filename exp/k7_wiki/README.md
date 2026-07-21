# K7 — wiki_store (Ara port)

## Goal

Trust-scored world-fact store with deterministic vector recall — a port
of Ara's `memory/wiki.py`, rebuilt without ChromaDB, LLM subagent, or
TOML ingestion.  Facts are content-addressed (SHA-256 ids), trust is
world-POV (orchestrator view, never per-character belief), and archival
is the graveyard — facts close, never delete.

## API

Library home: `kernel.wiki_store` (promoted 2026-07-20 per lab spec §6).

- **`Fact(id, text, trust, importance, provenance, valid_from,
  valid_until, state, promise_id, superseded_by)`** — immutable record.
  `make_fact(text, trust, provenance, ...)` for construction with
  content-addressed id.  `close(fact, t)` → archived copy.
- **`HashedIndex`** — deterministic bag-of-words vector index:
  256-dim BLAKE2b projections, cosine distance.  Swap-point for a
  future ChromaDB backend at assembly.
- **`WikiStore`**:
  - `write(fact)` — upsert.
  - `supersede(new, old_id)` — close old, write new.
  - `forget(id, t)` — close at t (never deletes).
  - `recall(query, *, querier, k, max_distance, as_of, exclude_ids)`
    — vector recall with mechanical filtering (distance cap,
    temporal validity, querier provenance/trust bounds).
  - `format_recall(facts, annotate_trust=True)` — Ara-style
    `(trust: x) text` lines.  `# ARA: memory/wiki.py`
  - `chronicle(scope_prefix)` — graveyard view of archived facts,
    ordered by closing time.
  - `ingest_promise(promise, t)` — K5 Promise → wiki fact.
  - `to_dicts()` / `from_dicts(dicts)` — JSON round-trip.
- **`QuerierContext(allowed_provenances, trust_floor)`** — thin
  mechanical bounds only.  Entity-specific nuance is C3's job.

## Demo

`uv run python -m exp.k7_wiki demo --seed 1 [--json]`

Five stages over a 30-fact village wiki:
1. **Recall** "what happened to the bridge?" — the superseding
   "bridge burned" recalls; the closed "bridge intact" is absent.
2. **Querier contexts** — a guard (npc+canon) sees more than a
   cleric (canon only); provenance filter applied.
3. **The lie** — the fabricated "miller's wife is a witch" rumor
   (trust −0.80) is recalled *verbatim*, with its trust annotation.
   No inversion or rewriting.
4. **K5 integration** — the king's-court mini-scenario (king rules,
   duke owes fealty, king dies) → suspended promises ingested as
   facts → chronicle prints the graveyard register.
5. **Round-trip** — `to_dicts` → `from_dicts` → identical recall.

## Verdict

**works** (2026-07-20).  23 tests: record validation (trust range,
content-addressed id stability), recall (relevance, distance cap,
deterministic ordering), temporal filtering (as_of, archived
exclusion), forget (close + graveyard, chronicle shows closing time),
supersede (old closed, new active, recall returns only new), querier
bounds (provenance filter, trust floor), no-inversion (negative-trust
facts returned verbatim, text never negated), promise ingestion
(provenance/window/promise_id aligned), chronicle ordering
(by closing time, byte-identical), round-trip fidelity (5 seeded
queries), HashedIndex (self-query ≈ 0, token overlap beats
disjoint, insertion-order-independent).

## Spec-notes

### Design decisions (user-settled)

- **Trust is world-POV**, never per-character belief.  A lie is stored
  with negative/low trust because the *orchestrator* knows it is
  fabricated; NPCs may still relay it as truth.  No code path inverts,
  negates, or rewrites negative-trust facts.
- **Filtering is two-layer.** K7 provides mechanical bounds only
  (provenance, trust floor); entity-specific filtering moves to C3's
  LLM reframing.  K7 returns full metadata so C3 has everything it
  needs.
- **Forget never deletes.** Ara hard-deleted; Unwritten closes
  (`valid_until`, state → archived).  The graveyard is the content.

### Ara divergences

- No ChromaDB dependency (lab implementation uses `HashedIndex`;
  ChromaDB is deferred to assembly, swap-point documented in
  `index.py`).
- No LLM subagent (`filter_for_querier` is not ported — its spirit
  moves to C3).
- No TOML ingestion or `ingest_narrative_state`/`ingest_invented_facts`
  (content pipeline is external to the kernel).
