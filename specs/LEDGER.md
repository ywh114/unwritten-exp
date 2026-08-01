# Unwritten — Ledger

**The one mutable document.** Base specs are immutable; addenda amend by
reference; RFCs are proposals until adopted; spec-notes are lab
write-backs. This file is the unified index of what is decided, what is
pending, and what is next.

**Update rule:** this ledger is updated in the SAME commit as the work it
records. An experiment is not done until its row flips; a document is not
adopted until its fold-state row moves. A missing ledger update means the
task is incomplete.

## Precedence

1. **Base specs** (engine v1.1, lab v0.4) — immutable foundation.
2. **Addenda** (A1, A2, …) — normative on adoption; amend parents by
   reference. Their "amendments stated, not applied" sections are the
   amendment queue tracked below.
3. **RFCs** — proposals; become normative only when folded into an
   addendum.
4. **Spec-notes** (`docs/spec-notes/`) — implementation verdicts from the
   lab; folded into the next addendum (or engine-spec revision).

**Newer = overwrite** (user rule, 2026-07-21): when normative documents
conflict, the newer document wins, and this ledger applies the ruling at
adoption time. Applied 2026-07-21: experiment numbering follows A2 §11
(2026-07-20), superseding the lab spec's implied numbering and this
ledger's earlier proposals. Conflicts this rule cannot settle land in the
conflict log (table 4).

## 1. Document registry

| document | status | amends / feeds | fold state |
|---|---|---|---|
| `unwritten-engine-design-specification.md` v1.1 | base | amended by A1 §17, A2 §11, spec-notes K2/K3/K5 | amendments unapplied |
| `unwritten-lab-experiments-repo-spec.md` v0.4 | base | experiment list extended by A2 §11 (K2b, K8, K9, C6, C7) and RFCs | A2 numbering adopted 2026-07-21 |
| `unwritten-generation-addendum-spec.md` (A1) v0.1 | normative-draft | amends engine spec (§17 queue); open questions §18 | adopted 2026-07-20 |
| `unwritten-addendum-a2-topology-items-ecology.md` (A2) v0.1 | normative-draft | amends engine spec + A1 (§11/§13 queues); open questions §12 | adopted 2026-07-20 |
| `rfc-fauna-generator.md` v0.1 | proposal | feeds experiment C6; refines A2 §4 | under review |
| `rfc-game-layer.md` v0.1 | proposal | feeds future Addendum A3; answers A1 §18 q6 partially | under review |
| `unwritten-fauna-engine-rfc.md` v0.3 | proposal | supersedes rfc-fauna-generator; feeds C6 | under review (with W2) |
| `unwritten-flora-engine-rfc.md` v0.1 | proposal | companion to fauna RFC; lands first in build order | under review (with W2) |
| `biosphere-vocabulary-proposal.md` v1.0 | proposal | content companion to fauna/flora RFCs; feeds C6 + naming | pending user decision (with W2) |
| `biosphere-addendum-b1-morphometrics.md` v0.3 | proposal | amends biosphere-vocabulary-proposal; within-plan generation knobs + sex/age/season modifiers + mutation-coupling bindings; feeds C6 / tree-of-life builder | pending user decision (with W2) |
| `biosphere-addendum-b2-productivity-scale.md` v0.2 | proposal | amends flora RFC §2 derived-products table: productivity = carrying capacity on absolute scale (biome priors + bounded abiotic bonus, no rank normalization); `soil_fertility` product removed (deposition logic becomes the bonus); substrate-type pass split off as future addendum; open-ocean marine sunlight-based; cold-tolerant temperature curve | implemented in K14 derived (2026-07-30); prior tables remain owner-tunable |
| `biosphere-addendum-b3-substrate-ground.md` v0.1 | proposal | amends flora RFC §2: substrate (`ground`) derivation pass — 41 classes with float property rows, physical + biome-bias engines, full d2 vector persisted (supersedes B2's top-2 note for substrate), underwater integrated; research basis `specs/b3_substrate_research_report.md` | implemented in K14 ground.py + viewer categorical layer (2026-07-30); class table owner-tunable; display map re-derived at delivery res from interpolated evidence + delivered categorical fields (de-blocked, 2026-07-30); rule tunes after distribution audit: point-based vent evidence with K1 dormancy roll (fresh lava/vent crust crater-confined), reef hard-override, bog cold gate + fen warm counterpart, reg arid², dune terminal-fan gate (was unreachable), mollisol steppe tolerance (2026-07-30); 42nd class pillow basalt — submarine active-vent bowls depth-split vs vent crust (crossover ~2667 m) — and cold-seep two-component provenance: vent ring shelf-gated ≥200 m (uncapped below, hadal seepage real) + vent-independent passive-margin hydrate band 300–3000 m over sedimented slopes (2026-07-30); pH promoted from class-identity smuggle to explicit property column (42 rows, cell pH = top-3 mix-weighted mean; feeds P7 ph_tolerance + pigment-chemistry flower color) (2026-07-30); sand-sheet cold gate — warm-ramp floor 0.15 (cold-arid falls to reg; hot ≥20 °C bit-identical; cold-desert sheet dominance 2.48→0 % on seed 3, sheet>mollisol on cold grassland 12.5→0 %) (2026-08-01); dune gate fix — most-arid band (full ≤ ~255 mm/yr, zero ≥ ~375), true-terminus supply via h_flow_dir downstream (was: any 10-cell catchment saturated), (1−cold)(1−glac) tails (48 glacier cells cleared), coastal littoral (1−slope)²; subhumid dune cells 172→0, dune reachable 3,829 cells (2026-08-01); lake littoral fetch gate — per-lake wave = f(effective fetch from component area, F0 12 / F1 35 km) × supply (0.6+0.4·glac); small ponds read lake mud (was 90 % sand), large lakes keep sandy shores, mixed shorelines from per-cell dep/slope/glac/depth (2026-08-01) |
| `biosphere-addendum-b4-water-column.md` v0.1 | proposal | amends flora RFC §2; extends B2/B3: pelagic stratification as per-column ATTRIBUTES (volumetric grid rejected) — bathymetry, photic depth, depth zones + `bottom_lit`, marine-snow flux (vertical settling; currents advection rejected) + downslope routing (K14 scope), bottom temp, vent benthos halo + `benthic_food` composite; nutrient-return loop: deep routing polar sources → upwellings, bounded [0.5,1.5] modifier on upwelling bonus (amends B2); spring kind flags; K11 trench-exaggeration prerequisite (hadal unreachable today, max 5153 m) | implemented 2026-07-30: K11 trench exaggeration (OO/OC signatures ~2.3×, e_norm floor −0.35 → 11.9 km max, 5/8 seeds hadal) + K14 `water.py` (all products, conveyor exits pinned as sinks, two-phase marine, shared ground dormancy roll) + datapack/viewer layers (depth_zone categorical, benthic_food monthly, photic_depth, bottom_temp tooltip-only); constants owner-tunable; draft rulings applied: springs keep+flag, Earth-standard zones; `water_ph` column pH added 2026-07-30 (ocean depth gradient re-derived at delivery res; fresh = 0.6·bed + 0.4·catchment soil − 1.3·peat share, humic blackwater; distinct from B3 `ground_ph` bed reading; viewer "water" mask) |
| `biosphere-addendum-b5-flora-stress.md` v0.1 | proposal | amends flora RFC §2/§7; supersedes build-plan P7 paragraph; syncs B3 §Consumers; defines the P7 stress primitive — continuous cost (driver not filter: P8 diffusion bias, rounds shrink+adapt, P9 competition via productivity; NO passable/costly/blocked masks, no audit/viability machinery); 3-stratum function (monthly climate + annual ground + tail terms, probabilistic-OR); new `ph_tolerance` position axis; pigment chemistry (pathway order-invariant + expression labile) with `flower_color` demoted to derived; fire/shade deferred | spec written 2026-07-30 (brainstorm options Q1–Q4 adjudicated by owner; backprop-audit branch rejected); amended same day: stress acts on vital rates not movement (kernels stress-blind; two-density accounting — cheap propagule rain vs established density, vanguard at s ≈ 0), SIGNED scale s ∈ [−1, +1] (vigor gradient preserved), density stress as round-time term s_realized = s_env + c·(demand/N) (close suitabilities coexist at ratio, large margins take over); stress function implemented 2026-07-31/08-01: `kernel/stress/` (3-stratum function), K15 `stress_adapter.py` (env side), FloraSim adapter + `stress_response.toml` (org side), pH split one-sided (ph_low/ph_high), bottom-temp climate for submerged plans + wind-modulated anchoring; rounds engine pending per `k15-simdiff-engine.md` v0.2 |
| `biosphere-addendum-b6-flora-wiring.md` v0.1 | proposal | amends flora RFC §2/§7 + B5: the flora wiring table — every authored axis → its env consumer (41 wired, 15 fauna-pending, 3 fire-pending, 8 engine-pending, 17 display), every stress factor → responder rows; fertility/salinity/wetness credits, moisture_breadth asymmetric relief, graded waterlogging, snow-load, glacier exclusion, engine canopy-shade stratum | implemented 2026-08-01 (ticket 0002): K15 stress_adapter credits/reliefs + new strata, engine shade pass (selection + demographic), FloraSim vital dials (growth_rate/wood_density), axes_core consumer labels corrected (32); breadth bases widened B_T 6→20 / P_B 0.08→0.26 + documented re-authors under ticket 0001 (0 zero-cell presets, min 63 cells) |
| `k15-simdiff-engine.md` v0.8 | proposal | amends/feeds B5 + flora RFC; the K15 engine build spec — genesis rain, dispersal (channel pmf + stress-gated pull + jump), population update (B5 rates, birth suppressed by negative stress only, per-year rate compounding fixed), TreeAuthority + reflog, merge/split rulings; v0.3: substrate capacity split K_L = K·U (best-of-class suitability, split capacity), growing-month worst-month, settled GENESIS_F 0.5 / EST_F_MIN 0.3, content authoring conventions; v0.4: rule B+ founding/differentiation — gene-flow-keyed minting (contiguous spill joins, jump mints with vicinity absorption, sustained remote landings join through a VERDICT gate TH = DIFF_D·(1+MOB_K·mobility)), failed-gate cells incubate as divergent sub-ranges and split only at DIFF_MIN_CELLS (sliver suppression), §8 rain-bridge connectivity | spec written 2026-08-01 (v0.2 folds critic review, 23 findings — 5 blockers incl. space-blind merge fix and K(c) equilibrium); v0.3 same day folds the stat-settling pass (statpass.py, 35 presets × seeds 1-3: 0/35 NO_RANGE seed 1, 4/35 seed 2, 2/35 seed 3, all gaps genuine world content); v0.4 same day: rule B+ knobs calibrated on seed-1 round-0 founding data (old rule 1173 mints, median 1 cell → DIFF_D 0.2 / MOB_K 1.0 / DIFF_MIN_CELLS 32); engine implemented per v0.4; v0.5–v0.6 same day (WIP retention, packet colonization "tentacles not dots" — owner ruling); v0.7 same day (ticket 0008): g-currency divides per fauna RFC §1 (wholesale g-promotion; trait clouds never split at SUB_D — measured), scalar-only merge gate MERGE_D 0.045 calibrated on the measured same-blob noise floor (agent-58), CONSOL sweep gated; v0.8 same day (ticket 0004): genesis seeds the radiated tree (~150 species nodes; zero-range extinct at genesis, 4/150; CONSOL merge-candidate bucketing per lineage) — fast 469 + slow 4 green at each step |
| `GUIDE.md` v0.1 | index | reading map over the corpus: document table (core/addendum/reference/note), task→reading map, new-agent read order; mirrors this LEDGER for routing — on disagreement fix the LEDGER first | written 2026-08-01 |
| `docs/spec-notes/2026-07-19-k2-drift-field-verdict.md` | write-back, final | amends engine spec §3.1 drift-field language | unfurled → fold queue (W1) |
| `docs/spec-notes/2026-07-19-k3-demotion-policy.md` | write-back, final | amends engine spec §3.4 (demotion) | unfurled → fold queue (W1) |
| `docs/spec-notes/2026-07-19-k5-predicate-vocabulary.md` | write-back, final | settles promise predicate vocabulary | unfurled → fold queue (W1); A1 §9.1/§12 and game-layer §5 EXTEND the vocabulary (see W1) |
| `docs/spec-notes/2026-07-20-l1-deepseek-v4-pricing.md` | write-back, final | confirms §7.5 flash rates; corrects pro rates | unfurled → fold queue (W1) |
| `docs/spec-notes/2026-07-20-l2-prefix-cache-mechanics.md` | write-back, final | §7.2/§7.5 cache mechanics (128-token blocks) | unfurled → fold queue (W1) |
| `docs/spec-notes/2026-07-20-c1-eventfulness-calibration.md` | write-back, final | amends engine spec §5.2 (calibration table) | unfurled → fold queue (W1) |
| `docs/spec-notes/2026-07-20-c2-archaeological-legibility.md` | write-back, final | answers Q-legible (with reviewer addendum) | unfurled → fold queue (W1) |
| `docs/spec-notes/2026-07-28-constraint-solver-design.md` | write-back, design | solver-above-levels over located records; present/absent/unwritten; query-vs-generate duality; feeds L1+ structure tier | discussion folded 2026-07-28 |

## 2. Work items

Status pipeline: `pending → spec-written → implemented → verified → promoted`.

### Experiment queue (numbering per A2 §11, newer = overwrite)

| id | item | source | status |
|---|---|---|---|
| K1 | hashrng | lab spec §2 | **promoted** (`kernel/hashrng.py`) |
| K2 | gmm_dynamics | lab spec §2 | **promoted** (`kernel/gmm_dynamics/`) |
| K2b | merge policy for split-strategy GMMs (component cap, moment-matched merges, mass-preserving) | A2 §2.2, §10, §12 q1 | pending |
| K3 | collapse | lab spec §2 | **promoted** (`kernel/collapse/`) |
| K4 | counters | lab spec §2 | **promoted** (`kernel/counters/`) |
| K5 | promise_ledger | lab spec §2 | **promoted** (`kernel/promise_ledger/`); A1 §9 amendments queued in W1 |
| K6 | gossip_transport | lab spec §2 | **promoted** (`kernel/gossip_transport/`); note: contact graph = route graph at assembly (A2 §1.1) |
| K7 | wiki_store | lab spec §2 | **promoted** (`kernel/wiki_store/`) |
| K8 | **route dynamics**: edge first-passage (inverse-Gaussian), bridge sampler, competing leak hazards, node flow rates | A2 §2.1–2.3, §11 | pending (after K9) |
| K9 | **complex**: topological data structure (nodes/edges/patches + incidence), three-state cover, subdivision/refinement (never rewire), commit-time defect audit, versioning | A2 §1, §11 | **promoted** (`kernel/complex/`) — unblocks C5 placement |
| K10 | structure_registry: presets+params, content-addressed, promise-backable | A1 §4 (lab B1 candidate, not A2-numbered) | proposed — after C5 |
| K11 | worldgen_l0: staged terrain pipeline (plates→hydrology→climate→biomes) + complex derivation + PNG renders | A1 §3, game-layer RFC §1 | **implemented** (`exp/k11_worldgen/`, not yet promoted; built by K3 2026-07-22 — PNG visual gate needs multimodality) |
| K12 | naming_corpora: curated-corpus hash-seeded naming; **custom simple impl, NOT an Ara lift** | A1 §8, P5 | proposed — **deferred** (user 2026-07-21) |
| K13 | tree-of-life (fauna + flora): blind phylogenetic backbone, pins, organs+derive partition, generic rebinds, nomenclature, viewer; flora kit at `flora/` (backbone/constraints/derive/metrics/content/naming), content packs at `content/fauna/` + `content/flora/` | fauna RFC, flora RFC, B1, vocabulary PART I+II | **implemented** (`exp/k13_treegen/`, 223 tests: 201 fauna + 22 flora; flora absorbed 2026-07-30 — restructure spec-note) |
| K14 | world products derived from K11: D0 productivity (B2), ground substrate (B3), water column (B4), k11pack datapack | B2/B3/B4 addenda | **implemented** (`exp/k14_worldprod/`, 62 tests; re-scoped from "flora engine" 2026-07-30 — flora tree moved to K13, world products kept and flattened) |
| K15 | sim-diff: stress adapter + dispersal + cover + rounds (flora P7–P9, fauna A-rounds); consumes K11 + K14 products + K13 trees; shared stress math in `kernel/stress/` | B5, build plan decision 2 | **spec-written** (`specs/k15-simdiff-engine.md` v0.4, 2026-08-01); landed: `kernel/stress/` + req_flora view contract + stress adapter (best-of-class substrate + capacity split, growing-season dormancy for climate AND water terms, wet-land fresh_availability) + FloraSim adapter + `statpass.py` calibration harness + authority (TreeAuthority + reflog) + population + genesis + dispersal kernels + engine round loop (rule B+ founding/dressing per v0.4); content settled through stat-pass E (moisture niches re-anchored to the c_P scale, marine pH to 7.9, K14 ground table deepened); acceptance tests green (fast 469 + slow 4 incl. 20-round determinism, per v0.8); v0.5–v0.8 landed same day (WIP retention, packet colonization, g-currency divides, radiated-tree genesis); biodiversity measured at v0.8 (20 rounds, seed 1: 126/150 lineages alive, cell richness median 5/max 22, productive biomes 75–83 lineages, ocean depauperate 6 — content debt not tuning; no knob changes needed); pending: rounds demo |
| L1 | llm_client | lab spec §3 | **promoted** (`llm/llm_client/`) |
| L2 | prefix_bench | lab spec §3 | **promoted** (`llm/prefix_bench/`) — §7.5 envelope confirmed |
| C1 | eventfulness | lab spec §4 | **promoted** (`capability/eventfulness/`) |
| C2 | backfill | lab spec §4 | **promoted** (`capability/backfill/`) |
| C3 | performance | lab spec §4 | pending (stacks on K6, K7, L1) |
| C4 | orchestrator_core | lab spec §4 | pending (stacks on K5, L1, L2) |
| C5 | latent_summon | lab spec §4; A1 §5 amends z-schema | pending (stacks on L1; **soft-dep on K9** — placement solve targets the complex; do K9 first, user 2026-07-21) |
| C6 | ecology counters + fauna table | A2 §4, §11; rfc-fauna-generator | **blocked**: RFC not yet adopted (W2) |
| C7 | item ledger: promotion gates, provenance chains, discovery hazard | A2 §5, §11 (stacks on K5) | pending |

### Non-experiment items

| id | item | source | status |
|---|---|---|---|
| W1 | fold queues into engine spec v1.2 / A3: spec-notes (K2/K3/K5/L1/L2/C1/C2) + A1 §17 + A2 §11/§13. Notably: A1 §9.1 decay classes, §9.2 `prior` state, §9.3 class-weighted density (K5 extensions); A1 §12 geographic relation vocabulary; game-layer §5 `knows_language`; void-creature trust-undecidable register (K7) | this ledger | pending |
| W2 | adopt/reject rfc-fauna-generator (unblocks C6) | rfc | pending user decision |
| W3 | adopt/reject rfc-game-layer (feeds A3) | rfc | pending user decision |
| W4 | commit specs/ move | repo | **done** (commit 03afc0b) |
| W5 | C2 backfill stress tests: harder prompts (larger k, more dead NPCs, contradictory counter anchors) — make the validator fail live | user 2026-07-20 | pending |
| W6 | adopt/reject biosphere-vocabulary-proposal + biosphere-addendum-b1 (folds with W2; also unblocks the tree-of-life builder first step) | specs/ | pending user decision |
| W7 | ley-proximity mutation legalization (user 2026-07-28): near ley lines, mutations that are illegal in the base registry become legal — N/A reactivation without an authored pin, palette breaches (blue mammal), drift beyond 3σ. The legality envelope becomes spatial. Gated on the ley/magical system (out of K13 v2 backbone scope; see rounds spec-note) | user | future |

### Consistency review 2026-07-21 (specs vs. implemented libraries)

- **K3 collapse ↔ A1 §10**: consistent — silhouettes are samples, identity
  refinement is promotion; refine/coarsen honors §10.3's culling and
  §10.4's "distant sight commits nothing."
- **K6 gossip ↔ A1 §11**: consistent — per-node beliefs preserve
  contradiction structurally ("no silent reconciliation"). Assembly note:
  contact graph = route graph (A2 §1.1).
- **K5 ↔ A1 §9**: gaps queued in W1 (decay classes, `prior` state,
  class-weighted density, geographic relations from §12).
- **K2 ↔ A2 §2**: consistent — split strategy is the cited empirical
  basis; merge policy (K2b) is the owed follow-up.
- **K7 ↔ game-layer §6**: void-creature "trust-undecidable" claims are a
  new register the current trust scalar doesn't express — queued in W1.

## 3. Open questions

| id | question | source | owner | state |
|---|---|---|---|---|
| Q-drift | affine drift vs. terrain richness | lab spec K2 | K2 | **answered** → spec-note K2 |
| Q-demote | demotion policy (timing, anchor, tier-3 target) | lab spec K3 | K3 | **answered** → spec-note K3 |
| Q-vocab | minimal predicate set for politics | lab spec K5 | K5 | **answered** → spec-note K5; extended by A1 §12 + game-layer §5 (W1) |
| Q-counters | who authors counter laws/parameters | design conversations | K4 | **answered** → K4 README |
| Q-legible | "archaeologically legible" as checkable property | lab spec C2 | C2 | **answered** → spec-note C2 |
| Q-merge | merge-policy parameters (cap, threshold) | A2 §12 q1 | K2b | open |
| Q-leaknum | first-passage + leakage numerics exactness | A2 §12 q2 | K8 | open |
| Q-A1 | A1 §18 open questions | A1 §18 | A3 / game-layer RFC | partially answered by rfc-game-layer; rest open |
| Q-A2 | A2 §12 open questions (mobility class count, ecology granularity, item promotion UX, sheet count) | A2 §12 | unassigned | open |
| Q-fauna | rfc-fauna-generator §7 (5 questions) | rfc | C6 / user | open, gated on W2 |
| Q-game | rfc-game-layer §8 open questions | rfc | A3 / user | open, gated on W3 |

## 4. Conflict log

| date | conflict | ruling |
|---|---|---|
| 2026-07-21 | experiment numbering: ledger proposals (K8 topo_complex, K9 worldgen) vs. A2 §11 (K8 route dynamics, K9 complex) | newer = overwrite → A2 numbering adopted |
| 2026-07-22 | K9 audit assumed route-network semantics: river sources/outlets flagged as dangling; patches without committed boundary edges flagged isolated | audit amended: `source`/`outlet` added to terminus vocabulary; `isolated_patch` skipped when no patch commits boundary edges (K11 spec-notes) |
| 2026-07-22 | K1 draws keyed by (clock, index) only — independent fields from the same stream at the same coordinates are identical | kernel/hashrng amended: `Stream.child(context)` derives substreams by extending the context digest; every independent field gets its own child (K11 spec-notes) |
