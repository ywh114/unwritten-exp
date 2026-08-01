# Specs Reading Guide

Reading map for the design corpus. **Read the entry, then the listed
spec, BEFORE designing or implementing** (AGENTS.md rule 1). Precedence
per `LEDGER.md`: base specs > addenda > RFCs; **newer = overwrite**
(user rule 2026-07-21). Addendums amend — and where noted, supersede —
the core doc they extend. `tmp/tickets/open/` is the live work queue;
`specs/LEDGER.md` is the one mutable index of what is decided/pending.

## Document table

| file | status | purpose | read when… |
|---|---|---|---|
| `LEDGER.md` | core (index) | unified ledger: precedence, document registry, work items, open questions, conflict log | first, for anything — says what is decided vs pending |
| `unwritten-engine-design-specification.md` v1.1 | core (base) | engine spec: ontology, promise ledger, collapse, wiki, cost model | engine-level machinery: K2/K3/K5/K6/K7, L1/L2, cost envelope |
| `unwritten-lab-experiments-repo-spec.md` v0.4 | core (base) | experiment repo spec: contracts for kernels (K1–K10), LLM (L), capabilities (C) | understanding what each experiment is and its done-when |
| `unwritten-generation-addendum-spec.md` (A1) | core (addendum, adopted) | game type + generative substrates: staged terrain L0/L1/L2, entities, features | K11 worldgen; terrain staging; feature latents; structure templates |
| `unwritten-addendum-a2-topology-items-ecology.md` (A2) | core (addendum, adopted) | topological complex, movement classes, ecology, items; experiment numbering | K9 complex; K6 gossip (contact graph = route graph); ecology/items |
| `unwritten-fauna-engine-rfc.md` v0.3 | core (authoritative) | fauna machinery: phylogeny core (g, three forces, g\*), body plans, generics, niches/ranges, ley lifting, naming stack | fauna traits, speciation/mutation, ranges, naming, magic — the biosphere spine |
| `unwritten-flora-engine-rfc.md` v0.1 | core (authoritative) | flora machinery: shared core, derived-products layer §2, dispersal, competition/cover, tiers, pass order §7 | flora; derived fields (read B2–B5 as its amendments); dispersal |
| `biosphere-vocabulary-proposal.md` v1.0 | core (content) | authored axis/part/slot/generic lists the machinery consumes (Part I fauna, II flora); rent rules | authoring content; adding an axis/part; consumer-rent audit |
| `biosphere-addendum-b1-morphometrics.md` v0.3 | addendum → vocabulary | within-plan morphometric knobs (dimensionless ratios), presets, sex/age/season modifiers, mutation couplings | body-plan-level generation knobs, size/proportions, preset authoring |
| `biosphere-addendum-b2-productivity-scale.md` v0.2 | addendum → flora RFC §2 | productivity = carrying capacity on absolute scale; soil_fertility product removed | K14 `derived.py`; productivity fields flora/fauna read |
| `biosphere-addendum-b3-substrate-ground.md` v0.1 | addendum → flora RFC §2 (supersedes B2's substrate note) | ground substrate pass: 42 classes, property rows, pH; two engines | K14 `ground.py`; substrate-dependent niches; `ground` field |
| `biosphere-addendum-b4-water-column.md` v0.1 | addendum → flora RFC §2; extends B2/B3 | water-column attributes: bathymetry, photic depth, marine snow, bottom temp, vent benthos | K14 `water.py`; ocean/depth/bottom-dependent niches |
| `biosphere-addendum-b5-flora-stress.md` v0.1 | addendum → flora RFC §2/§7 (supersedes build-plan P7) | P7 stress primitive: signed s ∈ [−1,+1], 3 strata, ph_tolerance, pigment chemistry | K15 stress; `kernel/stress/`; stress_response.toml; ph/pigment |
| `k15-simdiff-engine.md` v0.6 | core (K15 build spec) | K15 engine: genesis rain, dispersal packets, population update, TreeAuthority commit | implementing/touching K15 rounds, sim-diff mechanics, split rules |
| `rfc-fauna-generator.md` v0.1 | superseded (per LEDGER, by fauna RFC v0.3) | early fauna RFC: authored cladogram + clade-conditional sampling | historical only; cite the fauna RFC instead |
| `rfc-game-layer.md` v0.1 | proposal | game layer RFC: world template, player verbs, horizon decisions; feeds future A3 | game-level/world-shape decisions; not machinery |
| `naming-binomial-stems.md` v0.1 | reference (draft) | researched binomial stem register + composition rules for the epithet formula | binomial generation, epithet rules (K13 nomenclature) |
| `monster-corpus-v3.md` | reference | monster/wonder content corpus: everyday, majestic, lifted | monster content; what phylogeny + lifting do not own |
| `b3_substrate_research_report.md` | reference | external research basis for B3: taxonomy completeness + consumer scan | substrate class justification, B3 background |
| `docs/spec-notes/README.md` | note (convention) | spec-notes convention: dated amendments, lab write-backs | orientation in spec-notes |
| `docs/spec-notes/2026-07-19-k2-drift-field-verdict.md` | note, final | K2 verdict: affine OU drift fields, piecewise schedules (amends engine spec §3.1) | drift-field mechanics, K2 |
| `docs/spec-notes/2026-07-19-k3-demotion-policy.md` | note, final | K3 verdict: demotion policy — schedule-snap (amends engine spec §3.4) | collapse/demotion, K3 |
| `docs/spec-notes/2026-07-19-k5-predicate-vocabulary.md` | note, final | K5 verdict: minimal 10-kind promise predicate vocabulary | promise predicates, K5 |
| `docs/spec-notes/2026-07-20-c1-eventfulness-calibration.md` | note, final | C1 verdict: eventfulness calibration constants (amends engine spec §5.2) | backfill event-count rolls, C1 |
| `docs/spec-notes/2026-07-20-c2-archaeological-legibility.md` | note, final | C2 verdict: archaeological legibility = provenance coverage (answers Q-legible) | backfill QA, C2 |
| `docs/spec-notes/2026-07-20-l1-deepseek-v4-pricing.md` | note, final | L1 write-back: DeepSeek V4 price table (flash/pro) | cost model, L1 |
| `docs/spec-notes/2026-07-20-l2-prefix-cache-mechanics.md` | note, final | L2 verdict: 128-token prefix-cache blocks (amends engine spec §7.2/§7.5) | cache discipline, L2 |
| `docs/spec-notes/2026-07-23-k11-units-wwf-biomes.md` | note, design | K11 units doctrine (never tune units) + WWF/Köppen biome classifier | K11 biomes, unit mapping |
| `docs/spec-notes/2026-07-23-k11-inland-seas-climate-balance.md` | note, design | K11 post-halfway rulings: inland seas, two-layer wind, precipitation | K11 terrain/hydrology/climate details |
| `docs/spec-notes/2026-07-27-k13-v2-rebuild-plan.md` | note, build plan (supersedes K13 v1, archived) | K13 v2 module plan: vertical modules, principals, verification gates | K13 treegen architecture, module layout |
| `docs/spec-notes/2026-07-27-k13-v2-integration-contract.md` | note, design | K13 v2 horizontal contracts: AxisSpec schema, Tree state, determinism | K13 module composition, AxisSpec schema |
| `docs/spec-notes/2026-07-27-k13-rounds-fragmentation.md` | note, design | rounds/fragmentation/food-web rulings: diet_spectrum, abiotic-first | sim rounds design, diet/movement axis types |
| `docs/spec-notes/2026-07-28-constraint-solver-design.md` | note, design | constraint solver over located records (Overpass-QL-like) | future query/constraint layer |
| `docs/spec-notes/2026-07-29-k14-flora-build-plan.md` | note, build plan (P7 superseded by B5; pre-restructure scope) | K14 flora build plan as scoped before the restructure | K14 history, rulings carried; use restructure note for current scope |
| `docs/spec-notes/2026-07-30-k13-k14-k15-restructure.md` | note, rulings | owner rulings: K13 = tree engine, K14 = world products, K15 = sim-diff; dependency K11 → K14 → K15 ← K13 | which experiment owns what, module boundaries |

## Task → reading map

- **Touching flora/fauna trait trees (K13), traits or derived stats** →
  fauna RFC §1–§3 (phylogenetics core, traits/parts) and flora RFC §1
  (shared machinery, growth forms) + vocabulary proposal (axes, rent
  rules) + B1 (knobs) + K13 v2 rebuild plan and integration contract
  (AxisSpec, module layout) + restructure note (ownership).
- **Touching speciation / mutation** → fauna RFC §1 (the `g` currency,
  three forces, per-clade g\*) + K13 rounds-fragmentation note
  (diet_spectrum, enum→set audit) + k15 spec §commit (TreeAuthority
  split/merge rules).
- **Touching world fields (substrate / water / productivity)** → flora
  RFC §2 (derived-products table) as amended by B2 (productivity), B3
  (ground; research basis in the B3 report), B4 (water column); K14
  `worldprod` for implementation.
- **Touching K15 engine mechanics** → `k15-simdiff-engine.md` (v0.6) +
  B5 (stress primitive) + restructure note; `req_flora.py` view contract.
- **Touching flora stress / ph / pigment** → B5 §1–§5 + k15 spec; the
  build plan's P7 wording is superseded.
- **Touching naming / binomials** → fauna RFC §9 (naming stack) +
  `naming-binomial-stems.md` + vocabulary [name]-tagged axes.
- **Touching ley magic / lifting** → fauna RFC §6 + flora RFC §6.
- **Touching worldgen (K11)** → A1 §3 (staged terrain) + game-layer RFC
  §1 (world template) + K11 spec-notes (units/biomes; inland seas) + A2 §1
  (the complex).
- **Touching kernels K2–K7 / promises / gossip / collapse** → engine
  spec + lab spec + A1/A2 + the K2/K3/K5 verdict notes.
- **Touching game-layer / horizon decisions** → `rfc-game-layer.md`
  (feeds future A3).
- **Viewer / datapack** → no dedicated spec; see restructure note + B4
  (categorical viewer layers) + K14 `datapack.py`; tree renderer in the
  K13 v2 rebuild plan.

## New-agent read order

1. `specs/LEDGER.md` — what is decided, what is pending
2. `unwritten-engine-design-specification.md` + `unwritten-lab-experiments-repo-spec.md` (skim)
3. A1 (`unwritten-generation-addendum-spec.md`), then A2 (`unwritten-addendum-a2-topology-items-ecology.md`)
4. `unwritten-fauna-engine-rfc.md`, then `unwritten-flora-engine-rfc.md`
5. `biosphere-vocabulary-proposal.md`, then B1
6. B2 → B3 → B4 → B5 (in order; each amends what precedes)
7. `k15-simdiff-engine.md` + the K13/K14/K15 restructure note
8. Open tickets in `tmp/tickets/open/` for what is actually in flight

## Maintenance

When adding, replacing, or re-scoping a spec, update its row here in
the same change: bump the status when a proposal is adopted or a
document supersedes another, and mark fold-state changes. Keep rows to
one line. `LEDGER.md` remains the authoritative registry — this guide
mirrors it for routing; if they disagree, fix the LEDGER first.
