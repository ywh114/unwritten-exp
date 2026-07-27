# K13 v2 — tree-gen rebuild plan: modules, principals, verification gates

**Status:** build plan (2026-07-27). Supersedes K13 v1, archived at
`tmp/k13_treegen_v1_archive/`. v1 post-mortem: structural-only validation let
semantic errors through (crocodile pinned under monkey preset, sister species
differing by ~0.001σ, identity-function tradeoff coupling, no color/pattern
content, no behavior/diet axes). Same failure shape as the K11 wind saga —
whole machine built first, checked at the end.

**Method (user ruling):** every module is principled — documented interface,
rigorous tests written before the next module starts. Verification is planned
*before* implementation (this document is that plan). Each module's suite must
contain at least one test that would have caught a v1 bug. Soft properties get
planted-violation tests (prove the checker can fail).

**User rulings incorporated:**
- Variation is **vary-by-default with a clade-steady blacklist** — never
  vary-on-expose whitelists (v1's envelope-gated drift froze ~80% of knobs).
- Tree is kingdom-rooted: one **animalia** root joining all phyla (and
  **plantae** when flora lands) — not N disjoint phylum forests.
- Nomenclature is its own module: single-pass **tentative** names at backbone
  time (distribution/salience axes don't exist yet); a nomenclature pass runs
  after **every** sim-diffuse round; name history stored as reference; names
  are **committed only when treegen is fully finished** ("names are immutable
  once committed" ⇒ nothing is committed mid-build).

## Modules

| # | module | principal | interface doc |
|---|---|---|---|
| M0 | contracts (record model: Node/Tree/ranks/JSON) | K3 | `docs/m0-contracts.md` |
| M1 | axis registry — every axis: variation class (blacklist), mutation type, bounds/states, consumers; blocks: morphometrics, patternation, niche/activity, diet/trophic, life-history, social/behavior, ecosystem roles | K3 | `docs/m1-axis-registry.md` |
| M2 | content pack — full per-preset authored data across all blocks (incl. diet guild, behavior, life history); me-authored pin→preset map | subagent (data tables 100% pre-authored by K3) | `docs/m2-content-pack.md` |
| M3 | patternation — per-clade palettes, region-anchored pattern grammar (type × region × color), countershading, seasonal molt, sister-redraw rules | K3 (design) + subagent (content fill) | `docs/m3-patternation.md` |
| M4 | pins pack — anchors with relatives (pins sit in real genera, seeded sisters) | subagent | `docs/m4-pins.md` |
| M5 | clock & forces — g in generations (no years conflation), g\* gates speciation, force share ratios, ecogeographic rules as stress couplings | K3 | `docs/m5-clock-forces.md` |
| M6 | couplings — gate/tradeoff/anticorrelate/mutation with per-rule existence proofs | K3 | `docs/m6-couplings.md` |
| M7 | backbone — kingdom root → phyla (authored frame map) → … → species; radiation; pin integration | K3 | `docs/m7-backbone.md` |
| M8 | nomenclature — tentative binomials from `specs/naming-binomial-stems.md` (genus = clade name, epithet = salient accessible axis); re-pass each round; history stored; commit at final round only | subagent | `docs/m8-nomenclature.md` |
| M9 | persistence/CLI | subagent | `docs/m9-persistence.md` |
| M10 | viewer — proper phylogenetic tree viewer (cladogram UX done right: collapse gestures, tooltip z-order/order, reset semantics) | subagent | `docs/m10-viewer.md` |
| M11 | metrics harness — planted-violation meta-tests, per-seed diff-able reports | K3 | `docs/m11-metrics.md` |

Build order: M0 → M1 → M2+M3+M4 (parallel content) → M11 skeleton → M5 → M6 →
M7 → M8 → M9+M10. M11 precedes M5: the engine cannot be verified without the
harness. Each module's passing suite is the gate for starting the next.

## Verification plan per module

- **M0** — round-trip identity; canonical byte-stable dumps; path uniqueness;
  strict rank order. Property tests over random trees.
- **M1** — coverage audit (every axis referenced by content is registered;
  every registered axis has variation class, mutation type, bounds/states, ≥1
  consumer); **blacklist proof**: any axis not declared clade-steady moves over
  N lineage steps (statistical, p≈1) — a frozen non-steady axis fails;
  schema soundness (mutation type matches value type).
- **M2** — transcription fidelity (sampled line-checks vs B1); **consistency
  linter** (reviewable data): diet guild ↔ feeding-organ compatible;
  flightless ⇒ no soaring knobs; pin overrides within preset grade magnitude
  (catches crocodile-on-monkey); behavior defaults non-contradictory
  (eusocial ⇒ group_size > 1). Planted-violation tests for the linter.
- **M3** — palette legality (regions exist for plan; colors from clade
  palette); palette constancy within order; sister color/pattern divergence ≥
  threshold; cross-clade palettes non-identical.
- **M4** — every pin has ≥1 sister relative; authored values byte-exact after
  build (never drifted); coherence vs preset envelope.
- **M5** — g in generations, monotonic root→leaf; gen_time ordering
  (megafauna > small taxa); rate-multiplier distribution has both tails;
  **diversity metrics**: median sister distance per axis ≈ authored σ within
  tolerance; within-order variance ≫ 0; between-order > within-order distance;
  force attribution (descent → clade center, runaway → ornament axes only,
  drift mean ≈ 0); g\* boundary (species beyond, subspecies below).
- **M6** — per-rule existence proof: a must-fire case where the rule
  measurably changes output + a must-not-fire case (the v1 identity-function
  tradeoff fails this instantly); full-build compliance sweep over all species.
- **M7** — determinism (byte-identical; different seed differs); **kingdom
  root**: single `animalia` root, all phyla descendants (plantae hook
  reserved); authored phylum→frame map enforced (tetrapod always
  inner-frame); no empty orders; radiation within soft ranges; pins integrated.
- **M8** — tentative names: well-formed (registered stems + legal suffix per
  `naming-binomial-stems.md`), deterministic per seed, unique within tree;
  re-pass changes names only when the salient axis changed (stability
  metric); history log accumulates per pass; **nothing marked committed
  before final round**; commit marks the exact final set immutable.
- **M9** — round-trip, paths, CLI flags. Trivial.
- **M10** — headless-browser assertions: DOM node count == expected visible
  count; unselected label boxes ≤ row height; click expands, dblclick
  collapses, reset returns to order level, arrows never toggle; tooltip paints
  above all nodes; tooltip stats in fixed (alphabetical) order; no console
  errors. Screenshot review as last step, not the only one.
- **M11** — **meta-tested first**: synthetic tree with planted violations
  (low diversity, coupling breach, frozen axis) must fail; clean tree must
  pass. Then it is the standing gate. Per-seed report committed and diff-able.

## Open items carried from v1 spec-note

`docs/spec-notes/2026-07-26-k13-treegen-fixes.md` items fold into module
scopes: Savile_class (M2), fish preset/bounds mismatches (M2), echinoderm +
serpentine presets (M2, user decision pending), viewer thresholds (M10).
