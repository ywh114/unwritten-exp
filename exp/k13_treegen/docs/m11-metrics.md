# M11 — metrics harness (the standing gate)

Interface doc. The metrics harness judges GENERATED trees the way `lint.py`
judges AUTHORED content. It precedes M5 in build order because the engine
cannot be verified without it: every M5/M6/M7 acceptance check lands here as
a registered checker, and each module's suite is gated through it.

## Discipline

- **A checker that cannot fail is decorative.** Every checker ships with a
  planted-violation meta-test: a synthetic tree built to trip exactly that
  check must fail it; a clean tree must pass everything.
- Checks consume `(tree: Tree, pack: ContentPack)` and return violation
  strings (empty == clean). They read committed Node records only — no
  sampler internals.
- The report is **byte-stable and diff-able** per seed: sorted checks,
  sorted violations, canonical counts. The per-seed report becomes a
  committed artifact once M9 gives the CLI somewhere to write it.

## Skeleton check set (pre-engine)

The four planted-violation classes named in the rebuild plan, in their
minimal tree-level form:

| check | flags | planted class |
|---|---|---|
| `diversity` | <2 species, or all species under one preset | low diversity |
| `frozen_axis` | a mutable axis with ≤1 distinct value across same-plan species | frozen axis (v1 bug) |
| `coupling_breach` | flightless preset committed to active flight | coupling breach |
| `pin_coherence` | pinned node mass beyond ×100 of its preset grade | crocodile-on-monkey |

Thresholds are deliberately minimal; the real battery lands with the engine
modules (M5: g-clock monotonicity, force attribution, sister-distance ≈ σ;
M6: coupling existence proofs + weak-binding sweep; M7: rank census,
radiation counts, pin integration). Each module ADDS checkers to the
registry — this skeleton is the registry plus the meta-test habit.

## Qualitative gate (lands after M7+M12)

Dump 10 random species (name, plan, 3 salient traits, one-line M12
description) per seed; human review for documentary plausibility. The dump
mechanism is part of the report; it has no content until the backbone and
renderer exist.
