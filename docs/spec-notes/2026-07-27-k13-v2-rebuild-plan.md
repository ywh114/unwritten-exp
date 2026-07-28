# K13 v2 — tree-gen rebuild plan: modules, principals, verification gates

**Status:** build plan (2026-07-27, rev. 2 after brainstorming-conversation gap
analysis). Supersedes K13 v1, archived at `tmp/k13_treegen_v1_archive/`.
Brainstorming source: `tmp/biosphere_conv`.

v1 post-mortem: structural-only validation let semantic errors through
(crocodile pinned under monkey preset, sister species differing by ~0.001σ,
identity-function tradeoff coupling, no color/pattern content, no
behavior/diet axes, ~80% of knobs frozen). Same failure shape as the K11 wind
saga — whole machine built first, checked at the end.

**Method (user ruling):** every module is principled — documented interface,
rigorous tests written before the next module starts. Verification is planned
*before* implementation (this document). Each module's suite must contain at
least one test that would have caught a v1 bug. Soft properties get
planted-violation tests (prove the checker can fail).

## Scope rulings (user, 2026-07-27)

- **Strictly world-blind.** No ranges, no stress masks, no biome coupling.
  Ecogeographic rules (Bergmann/Allen/Gloger/island) are deferred to the
  dump-and-adapt rounds, not M5.
- **Dump-and-adapt / vicariance rounds and the ley magical-pin quota
  (5–15/world, vocab §14) are OUT of scope for v2.** K13 v2 = world-blind
  backbone + pins + naming + text/tree renderers.
- **Parts deferred; slots stay coordinate-less string enums.** Generics carry
  realization lists + rebind permissions; full part/slot records land with the
  illustration layer. Thousands of records won't need retrofitting.
- **Content authored in TOML** (user preference); canonical tree dump is JSON.
- **Variation is vary-by-default with a clade-steady blacklist** — never
  vary-on-expose whitelists. Stated as a default: every non-clade-steady knob
  gets a non-zero σ unless blacklisted (this is the freeze-bug fix).
- **No wallet/budget mutation mechanic** (explicitly rejected).
- Diversity bands (60/30/10 normal/cute/weird) are targets, not v2 gates —
  easily twiddled later.
- **Taste invariant (cross-cutting):** realism structural never decorative;
  pins define texture, they don't "shine"; density of the ordinary, scarcity
  of the remarkable; mundane flat and on-the-nose.

## Modules

| # | module | principal | interface doc |
|---|---|---|---|
| M0 | contracts — Node/Tree/ranks/JSON dump; slots as string enums; generics with realization lists + rebind permissions | K3 | `docs/m0-contracts.md` |
| M1 | axis registry — three-tier taxonomy (invariant/steady/labile), variation blacklist, mutation type, bounds/states, consumers, dimensionless-or-mass lint; blocks: morphometrics (B1 §§2–13), patternation, niche/activity, diet/trophic, life-history, social/behavior, ecosystem roles, sex/age/season (B1 §14) | K3 | `docs/m1-axis-registry.md` |
| M2 | content pack — **grow-as-pins-demand** (start with what pins touch, linter keeps partial coverage honest); per-preset authored data; me-authored pin→preset map; `allometry.toml` (Damuth/Lindeman/Kleiber/home-range); anti-creep record/quantity lint | subagent (tables pre-authored by K3) | `docs/m2-content-pack.md` |
| M3 | patternation — per-clade palettes, region-anchored pattern grammar (type × region × color), countershading, seasonal molt, sister-redraw; `dichromatism` is the patternation↔sex seam | K3 (design) + subagent (fill) | `docs/m3-patternation.md` |
| M4 | pins — **any-rank radiation/texture controls** (not genus-anchored); radiation = authored per-pin param; functional megafauna checklist; invented-clade budget; directional-drift derivations | subagent | `docs/m4-pins.md` |
| M5 | clock & forces — g in generations; **mutation magnitude ∝ f(g)** (novelty tail opens at high g); **stress raises g accrual**; force share ratios; g\* gates speciation. World-blind: no ecogeographic coupling | K3 | `docs/m5-clock-forces.md` |
| M6 | couplings — gate/tradeoff/anticorrelate/mutation with per-rule existence proofs; **mutation bundles** (island-flightlessness, cave, domestication); **per-world seeded weak-binding layer**; the 8 curated + 3 rejected rules (B1 §15) enumerated | K3 | `docs/m6-couplings.md` |
| M7 | backbone — kingdom root (animalia; plantae hook reserved) → phyla (authored frame map) → … → species; radiation from pins/clades; pin integration at any rank | K3 | `docs/m7-backbone.md` |
| M8 | nomenclature — tentative binomials from `specs/naming-binomial-stems.md`; **pinned = real binomials + folk names, generated = invented well-formed, never borrow real genus names**; uniqueness within-genus only; collision re-draw via K1 `Stream.child`; re-pass each round; history stored; commit at final round only | subagent | `docs/m8-nomenclature.md` |
| M9 | persistence/CLI (TOML content in, JSON tree out) | subagent | `docs/m9-persistence.md` |
| M10 | viewer — proper phylogenetic tree viewer (cladogram UX: collapse gestures, tooltip z-order/order, reset semantics) | subagent | `docs/m10-viewer.md` |
| M11 | metrics harness — planted-violation meta-tests; per-seed diff-able reports; **qualitative gate**: dump 10 random species (name, plan, 3 salient traits, one-line description), check documentary plausibility | K3 | `docs/m11-metrics.md` |
| M12 | description renderer — text species description ("a [size] [covering] [grade]-like [diet] with [salient part]"); the text-demo renderer | subagent | `docs/m12-description.md` |

Build order: M0 → M1 → M2+M3+M4 (parallel content) → M11 skeleton → M5 → M6 →
M7 → M8 → M12 → M9+M10. M11 precedes M5: the engine cannot be verified without
the harness. Each module's passing suite is the gate for the next.

## Verification plan per module

- **M0** — round-trip identity; canonical byte-stable dumps; path uniqueness;
  strict rank order; generic rebind permissions enforced (rebind outside plan
  limits rejected). Property tests over random trees.
- **M1** — coverage audit (every axis referenced by content is registered;
  every registered axis has tier, variation class, mutation type,
  bounds/states, ≥1 consumer); **three-tier rule**: invariant axes cannot be
  perturbed by the sampler (attempt = error); **blacklist proof**: any
  non-clade-steady axis moves over N lineage steps (statistical, p≈1) — a
  frozen non-steady axis fails; **dimensionless/mass lint**: a knob carrying
  absolute units (except the one mass axis) is rejected; mutation type matches
  value type; B1 §14 interlocks (non-gonochoric zeroes dimorphism; temporal
  modifier ≤1 per dial).
- **M2** — transcription fidelity (sampled line-checks vs B1); **consistency
  linter** (reviewable data): diet guild ↔ feeding-organ compatible;
  flightless ⇒ no soaring knobs; pin overrides within preset grade magnitude
  (catches crocodile-on-monkey); behavior defaults non-contradictory
  (eusocial ⇒ group_size > 1); **record/quantity anti-creep** ("can the player
  collapse this as an individual? no → quantity layer"); allometry constants
  present. Planted-violation tests for every linter rule.
- **M3** — palette legality (regions exist for plan; colors from clade
  palette); palette constancy within order; sister color/pattern divergence ≥
  threshold; cross-clade palettes non-identical; dichromatism drives sex
  palette divergence.
- **M4** — pins may sit at any rank; radiation param honored (a `radiation: N`
  pin produces ~N descendants); every pin has relatives; authored values
  byte-exact after build (never drifted); functional checklist coverage
  (eat/threaten/carry/see-daily present); invented clades ≤ budget and all
  small-bodied; directional-drift derivations biased correctly ("horse but
  faster" → +cursorial).
- **M5** — g in generations, monotonic root→leaf; gen_time ordering
  (megafauna > small taxa); rate-multiplier distribution has both tails;
  **mutation magnitude ∝ g**: high-g lineages show novelty-axis movement that
  low-g lineages don't (planted test); **stress → g accrual** sign test;
  **diversity metrics**: median sister distance per axis ≈ authored σ within
  tolerance; within-order variance ≫ 0; between-order > within-order distance;
  force attribution (descent → clade center, runaway → ornament axes only,
  drift mean ≈ 0); g\* boundary (species beyond, subspecies below).
- **M6** — per-rule existence proof: a must-fire case where the rule
  measurably changes output + a must-not-fire case (v1's identity-function
  tradeoff fails this instantly); the 8 curated rules each enumerated and
  tested, the 3 rejected confirmed absent; mutation bundles fire as a
  correlated set (not independent); per-world weak bindings are K1-seeded and
  differ across seeds; full-build compliance sweep over all species.
- **M7** — determinism (byte-identical; different seed differs); **kingdom
  root**: single `animalia` root, all phyla descendants (plantae hook
  reserved); authored phylum→frame map enforced (tetrapod always
  inner-frame); no empty orders; radiation within soft ranges; pins integrated
  at their authored ranks; convergent-grade reachability (drift can traverse
  lobster→crab in knob space).
- **M8** — tentative names well-formed (registered stems + legal suffix),
  deterministic per seed; **uniqueness within-genus only** (cross-genus
  epithet repeats allowed — convergent *rufus*); pinned names are real
  binomials, generated names never borrow a real genus; re-pass changes a name
  only when its salient axis changed (stability metric); history log
  accumulates per pass; **nothing committed before final round**; commit marks
  the exact final set immutable; collision re-draw deterministic via K1 child.
- **M9** — round-trip, TOML-in/JSON-out, paths, CLI flags.
- **M10** — headless-browser assertions: DOM node count == expected visible
  count; unselected label boxes ≤ row height; click expands, dblclick
  collapses, reset returns to order level, arrows never toggle; tooltip paints
  above all nodes; tooltip stats alphabetical; no console errors. Screenshot
  review as last step, not the only one.
- **M11** — **meta-tested first**: synthetic tree with planted violations
  (low diversity, coupling breach, frozen axis, crocodile-on-monkey) must
  fail; clean tree must pass. Qualitative gate: 10-species dump reviewed for
  documentary plausibility. Then it is the standing gate; per-seed report
  committed and diff-able.
- **M12** — description is grammatical and matches the record (every term
  traces to a committed axis); salient-part selection picks the highest-salience
  axis; no term contradicts the record (a flightless bird isn't "soaring").

## B1 v0.3 deltas (absorbed 2026-07-27)

- **Size convention (§1)** — mass is the single size axis; every knob
  dimensionless; linear dims derived (`length ∝ mass^(1/3) × plan_factor`).
  Enforced by M1's dimensionless/mass lint.
- **Boar preset (§2)** and **decapod grade contrast (§9)** (lobster/shrimp/
  round-crab/squat-lobster; crab-form a convergent grade reachable by drift) —
  M2 content + M7 reachability test.
- **Sex/age/season (§14)** — `reproductive_mode` enum (gonochoric /
  simultaneous hermaphrodite / sequential-protandrous / sequential-protogynous
  / parthenogenetic; non-gonochoric zeroes dimorphism; sequential makes mass
  sex-determinant; flora hermaphrodite default, dioecy marked); sexual
  dimorphism record (size_dimorphism_ratio + direction, **Rensch's rule
  adopted**, dichromatism, weapon sex-linkage); temporal modifiers (≤1 of
  {juvenile-only, seasonal, age-ramped, breeding-male} per dial, sex-linkage
  orthogonal). M1 registers; M6 implements Rensch + size-advantage as
  couplings. Mutation couplings renumbered §14→§15 (M6).

## Deferred (recorded, not dropped)

- Parts/slots as full records (illustration layer); parametric SVG
  illustration (RFC §10.5); non-blob construction milestone (jointed
  tetrapod); folk-name layer for generated clades; ecogeographic rules +
  dump-and-adapt/vicariance rounds; ley magical-pin quota; diversity-band
  targets; lushness/smooth-abundance/insect-policy/zoom/gossip items (those
  belong to K11/C6/game-layer, not K13 — see `tmp/biosphere_conv` §G).

## Open items carried from v1 spec-note

`docs/spec-notes/2026-07-26-k13-treegen-fixes.md`: Savile_class (M2), fish
preset/bounds mismatches (M2), echinoderm + serpentine presets (M2, user
decision pending), viewer thresholds (M10).
