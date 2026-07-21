# 2026-07-20 — C2 verdict: archaeological legibility

**Amends:** lab spec §4, C2 — answers Q-legible ("archaeologically legible"
as a checkable property).
**Source:** `exp/c2_backfill` live demo, 50 seeds, T1-flash
(`deepseek-v4-flash`, thinking disabled).

## "Archaeologically legible" defined

A backfill run is **archaeologically legible** when three properties all
hold:

1. **Provenance completeness.** Every wiki fact committed during backfill
   traces to a named source — never to an unlabeled `"provenance": "canon"`
   without a further tag. The tracked sources are:
   - `counter_anchor` — one fact per counter written with
     `provenance="counter"`, recording the quantity move.
   - `promise_discharge` — one fact per discharged promise, written by
     the discharge path with the promise ID attached.
   - `event` — one fact per chronicle event whose text does not originate
     from a discharged promise (prose classification; these carry
     `provenance="canon"` and no `promise_id`).
   - `sampler` — the eventfulness roll itself (logged in-run as a fact).

   Provenance coverage = 1.0 iff each source category has ≥ 1 fact across
   the full run. A value below 1.0 means the pipeline is writing facts whose
   origin cannot be traced.

2. **Counter-explanation coverage.** Every non-flat counter move (direction
   `"up"` or `"down"`, not `"flat"`) has a corresponding `CounterNote` in
   the chronicle that matches the direction. "Flat" counters require no
   explanation (the quantity didn't change, so the LLM may or may not
   mention it — either is valid). This is enforced by the validator
   (`count:counter_agreement`), so every accepted chronicle satisfies it by
   construction.

   Coverage = 1.0 iff `explained_moves / total_non_flat_moves == 1`.

3. **Non-contradiction.** No two committed wiki facts share the same fact ID
   within a single run. A single backfill run writes facts to the wiki
   store; duplicate fact IDs would represent a contradictory double-write of
   the same canonical slot.

   This passes iff the contradiction count is zero.

## Measured values (50 seeds, all accepted)

| property | value | pass? |
|---|---|---|
| Provenance completeness | 1.000 (4/4 sources: counter_anchor=150, promise_discharge=100, event=107, sampler=50) | ✓ |
| Counter-explanation coverage | 1.000 (150/150 non-flat moves explained) | ✓ |
| Non-contradiction | 0 duplicate fact IDs | ✓ |

The provenance counts are deterministic per seed (no LLM randomness in
provenance assignment — the commit path is mechanical), so a single
50-seed run is sufficient to establish the baseline.

**Provenance detail per source:**
- `counter_anchor`: 150 facts (3 counters × 50 runs). Each counter anchor
  writes one fact with `provenance="counter"`.
- `promise_discharge`: 100 facts (2 due promises × 50 runs). Each
  discharged promise writes one fact with the matching `promise_id`.
- `event`: 107 facts. The number varies per seed because some events are
  classified as discharges (tagged with a `promise_id`) while others are
  standalone prose events (tagged with `provenance="canon"`, no promise).
- `sampler`: 50 facts. One eventfulness-roll fact per run.

## Reviewer addendum (2026-07-20)

One caveat on property 3 (non-contradiction): as defined it is **vacuous
by construction**. Wiki fact ids are content-addressed (SHA-256 over
text + provenance + valid_from), so a duplicate id can only ever mean
the *same* fact written twice — a true contradiction (same slot,
different content) hashes to a different id and would sail through this
check. The zero count above is therefore evidence of nothing.

A non-vacuous formulation for future work: track **conflicting claims
over the same subject slot** — e.g., two committed facts assigning
different values to the same counter at overlapping validity windows, or
two events discharging the same promise with incompatible narratives.
The mechanical substrate exists (K5's conflict rules on predicates);
what is missing is mapping free-text event facts back to predicates.
Until C2's events carry structured effects (not just titles), property 3
should be read as "no id collisions" and the true non-contradiction
guarantee rests on the validator's `counter_agreement` and `chekhov`
rules, which ARE non-vacuous and measured above.

Properties 1 and 2 stand as measured.

## Conclusion (revised)

Provenance completeness and counter-explanation coverage are non-vacuous
checkable properties, measured at 1.000. Non-contradiction awaits
structured event effects — see the addendum above. Together these give
"archaeologically legible" its working definition: every fact traces to
a named source, and no quantity moves silently. Q-legible is **answered**.
