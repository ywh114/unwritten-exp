# K5 — promise_ledger

## Goal

The constraint engine — the heart of the Unwritten promise formalism
(design spec §4).  All narrative constraints (canon facts, NPC speech
acts, orchestrator intents, summoned-terrain obligations, prophecies,
rumors) are the same record type `(scope, predicate, window, strength,
provenance)`, ordered by authority.  Plots aren't scripts; they're
colliding promises.  Promise density drives the attention economy.

The ledger enforces hard consistency (a small, non-Prolog set of conflict
rules), suspends lower-authority conflicts (TMS-lite), cascades
suspension through `depends_on` chains, provides a `reconcile()` pass
that restores promises whose blockers are gone, archives discharged /
expired / broken promises to the graveyard, and exposes a `density()`
index that ranks regions by active-promise strength.

Pure logic.  No LLM, no positions, no engine.

## API

Library home: `kernel.promise_ledger` (promoted 2026-07-19 per lab spec §6).

- **`PredicateKind`** — 10-member `StrEnum`: `OWNS`, `CONTROLS`, `IS`, `FEALTY`,
  `HOSTILE`, `ALLIED`, `LOCATED`, `DISPUTED`, `BOUND`, `HOLDS`.
- **`Predicate(kind, subject, object="", detail="")`** — one ground fact.
- **`Promise`** — `(id, scope, predicate, window, strength, provenance, state,
  note, depends_on, suspended_by)`.
- **`PromiseLedger`**:
  - `assert_(predicate, *, scope, window, strength, provenance, note, depends_on)` → `id`
    (the weaker side of an authority mismatch is auto-suspended but kept in
    the ledger; a same-authority conflict raises). `PromiseLedger(seed=N)`
    makes ids deterministic via the K1 hashrng stream.
  - `discharge(id)` / `break_(id)` / `expire(at_time)` → terminal states.
  - `suspend(id, *, suspended_by)` / `reconcile()` → TMS-lite override & restore.
  - `validate()` → list of conflicting active pairs.
  - `density(region)` → sum of active-promise strengths touching a region.
  - `density_ranking()` → regions ranked by density descending.
  - `graveyard(*, scope)` → non-active promise archive.
  - `active(*, scope)` / `get(id)` / `all()` → queries.

## Demo

`uv run python -m exp.k5_promise_ledger demo --seed 1 [--json]`

Ten-promise King's Court scenario:
1. King Eldric IS ruler (canon)
2. Duke Aldric CONTROLS Northmarch (canon)
3. Duke owes FEALTY to King (hard, depends_on: #1)
4. King promises Westvale to Lord Beric (hard, depends_on: #1)
5. King also promises Westvale to Lady Cerys (soft) → collider!  Cerys SUSPENDS
6. Gareth HOLDS Captain of the Guard (hard, depends_on: #1)
7. King IS dead (measurement) → #1 suspends, cascade #3 #4 #6
8. Reconcile → nothing restores (root dep still suspended)
9. Aldric claims throne (hard, IS ruler)
10. Aldric confirms Gareth (hard, depends_on: #9)

Prints the state after each phase, the density ranking (westvale and
capital score high), and a graveyard view of the suspended/broken
regime.

## Verdict

**works** (2026-07-19).  26 tests: lifecycle (assert/discharge/break/
expire/suspend/reconcile), authority ordering (higher-overrides-lower,
lower-rejected, same-rejected), cascade suspension through depends_on
chains, block-reconciliation-while-dep-suspended, conflict rules (dead vs
ruler/controller, banished vs located, hostile vs allied, order
insensitivity), density index (sums, ranking), graveyard filtering,
the full kingdom scenario (exact expected states), and the two vocabulary
tests (20 canonical facts expressible; 10 kinds are mutually distinct).

## Spec-notes

The vocabulary question is answered in
`docs/spec-notes/2026-07-19-k5-predicate-vocabulary.md`.  Summary:

10 predicate kinds cover ≥20 canonical political facts.  Each kind is
semantically irreducible — no two can be expressed as the other.  The set
is deliberately small (10 members, 7 of which carry a subject+object,
3 allow a free `detail` qualifier) because every additional kind grows
the conflict-rule checker quadratically.  The `detail` field on `IS`,
`BOUND`, and `HOLDS` gives extensibility without adding kinds: new
statuses ("excommunicated", "cursed"), oath types, and titles are
strings, not schema changes.

The K5 library deliberately does NOT include:
- Temporal reasoning beyond window-expiry (sequencing is the orchestrator's
  job).
- Probabilistic or partial satisfaction (strength is a scalar for density
  weighting, not a belief state).
- Inference / transitivity / modus ponens (this is a constraint ledger,
  not a theorem prover — the LLM supplies narrative coherence).
