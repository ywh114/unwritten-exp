# K14 Flora Engine — Build Plan (2026-07-29)

Goal: the flora half of the biosphere, up to sim-diff readiness — a committed
flora tree with full records, plus the world-facing layers that let dispersal
rounds start. Sources: `specs/unwritten-flora-engine-rfc.md` (v0.1),
`specs/biosphere-vocabulary-proposal.md` PART II (v1.0, owner-resolved §14).

## Rulings carried over (from K13 fauna, do not re-litigate)

- Drift-and-commit: children draw an N-σ cloud around the parent's committed
  record; clade ranks are lineage points, not attractors.
- Trait/derived/metadata partition: traits stored, derived recomputed at
  consumption, `[niche]`-style climate baselines are metadata only.
- All randomness from K1 (`kernel/hashrng`); seeded streams per lineage.
- No hard caps; leaky envelopes (mass/size analog: height envelope per plan).
- Organ layer with defaults + preset bindings; substrate legality gates
  (a trap needs carnivory, serotiny needs fire regime, etc.).
- Pins are content, committed byte-exact + jitter; binomial-genus anchoring.
- Naming: unnamed bulk is FINE for flora (RFC: genus-level folk labels,
  "a sedge", "white-flowered shrub"); binomials where computed; no species
  goes unnamed *when named* — the same guaranteed-construction rule.
- Subagent constraint: every module below is one tight prompt — file paths,
  interface signatures, acceptance tests stated here; implementer does not
  design.

## Reuse map

| From | What | How |
|---|---|---|
| `kernel/hashrng` | K1 streams | import |
| `exp/k13_treegen/model.py` | Node/Tree/Rank/NameRecord, JSON round-trip | import (ranks map: phylum=line, class=growth-form plan) |
| `exp/k13_treegen/seeding.py` | stage streams | import |
| `exp/k13_treegen/forces.py` | evolve/drift machinery, substrate gates, rebinds | import; flora rates via its own constants |
| `exp/k13_treegen/registry.py`, `content.py`, `lint.py` | registry/pack/lint shapes | import; flora TOML dirs |
| `exp/k13_treegen/nomenclature.py` | naming engine (synonym chains, context stems, guaranteed fallback) | import; flora stems content |
| `exp/k13_treegen/metrics.py` | check shapes (frozen axis, pin integration, plan legality) | import + flora checks |
| `exp/k13_treegen/viewer/tree.html` | tree viewer | reused unchanged (reads any K13-shaped JSON) |
| `exp/k11_worldgen` dumps | world.npz + world.json (read-only) | P6 input only, never pipeline internals |

## Modules

### P0 — skeleton & contracts (S)
`exp/k14_flora/{__init__.py, model.py, CONTRACTS.md}`.
model.py re-exports K13 Node/Tree/Rank; CONTRACTS.md states the partition,
the pass order (F0 backbone → D0 products → F1 dispersal → …), and the JSON
schema version. Acceptance: imports work, `python -m exp.k14_flora --help`.

### P1 — content pack: plans, axes, palettes, constraints (L)
`content/{plans.toml, axes_core.toml, axes_parts.toml, palettes.toml,
constraints.toml, presets/**, pins.toml, stems_flora.toml}`.
- **Plans (v1)** — terrestrial: tree, shrub, herb-forb, grass-sward,
  rosette-mat, succulent, fern-grade, moss-grade; aquatic: runner-meadow,
  floating-leaf, floater, macroalgae-holdfast; sessile-marine: coral-grade,
  sponge-grade (flora owns corals/sponges per vocabulary §14.3 — the tree
  is world-blind, marine placement is a rounds concern, so these are IN);
  honorary: fungus, lichen. DEFERRED: vine/epiphyte (2nd-round-only),
  phytoplankton (counters only), tube-worm-grade (vent ecology). Each
  plan: slots (architecture, leaf, root, display, fruit_seed, defense,
  storage, covering, phenology) + generics table (dispersal replaces
  locomotor).
- **Axes (v1 cut)** — architecture: height, woodiness, growth_rate,
  longevity, shade_tolerance, pioneer_climax (CSR scalar); leaf: shape,
  persistence, size_class, margin_toothed; root: type, depth, mycorrhizal,
  n_fix; display: flower_symmetry, flower_color, inflorescence,
  pollination_syndrome (one enum pulling the whole bundle), bloom window
  (start,length); fruit_seed: fruit_type, channel weights {local, wind,
  water, animal, jump}, propagule_mass, seed_bank, serotiny, masting;
  defense: mechanical (thorn/spine/prickle enum), chemical_class, potency;
  storage: organ enum, clonal_spread; covering: bark_thickness, cuticle;
  niche tolerances: drought, salinity, waterlogging (HAND band), fertility
  requirement, growing_season_req, fire_strategy.
- **Palettes** — flower colors per plan (full gamut allowed; wind-pollinated
  plans get the dull set — enforced by constraint, not palette).
- **Constraint rules** (vocab §8.10, as sampler legality like the fauna
  substrate gates): CAM↔succulence, C4↔warm-open, wind-syndrome↔small
  petal-less, serotiny↔fire regime, spinescence↔aridity, large leaves↔
  warm-wet, toothed↔cold, pneumatophores↔waterlogging, buttress↔tropical
  emergent, giant-rosette↔high-elevation.
- **Presets (archetypes, ~20)**: oak-grade, conifer-grade, palm-grade,
  bamboo-grade, sedge, tussock-grass, forb, thistle-grade, legume-grade,
  cactus-grade, aloe-grade, heath-grade, reed-grade, waterlily-grade,
  duckweed-grade, kelp-grade, seagrass-grade, agaric-grade, bracket-grade,
  crust-lichen-grade, sphagnum-grade. Hallé grammar tuple at Order rank,
  scalar params at Family rank (vocab §14.6).
- **Pins (tier-1 curated)** — two kinds per owner ruling 2026-07-29:
  (a) COMMON cover — the everyday flora a world feels broken without,
  pinned at genus rank with radiation so the genus is findable and
  widespread: oak, pine, birch, willow (trees); bramble, heather
  (shrubs); meadow-grass, reed, sedge (grasses/marginals); bracken
  (fern); sphagnum, cushion-moss (mosses); water-lily, ludwigia,
  sword-plant, duckweed (aquatics); field-agaric, bracket-conk (fungi);
  (b) LANDMARK species (species-rank, findable not common): yarrow,
  wild carrot, sword-iris, thread-leaf chive, ice-crown, stonecrop,
  grave-flower. Each = full record; radiation targets on (a).
Acceptance: lint clean (registered axes, plan-legal bindings, palette
legality, constraint coverage); `preview.py` prints 5 preset records.

### P2 — backbone build (drift-and-commit) (M)
`backbone.py`. Lines: seed-plants / spore-plants / decomposers (fungi+
lichen) as phyla; class = growth-form plan; order = clade-steady tuple
(flower architecture, fruit family, root family, chemistry, photosynthesis
grade, mycorrhizal dependence, Hallé tuple); family = narrowed params;
genus; species. Background radiation small (genus-level bulk, RFC §0.3 —
species only where pinned). Height envelope (leaky, per plan). Constraint
rules enforced in evolve (legality gate, same pattern as fauna strata).
Acceptance: determinism (byte-identical replay), census sane (no empty
orders), constraint violations = 0 across 3 seeds, pins placed + jittered.

### P3 — derive layer (S)
`derive.py` (flora): Raunkiær life form (from height/woodiness/storage),
fire strategy (bark + lignotuber + serotiny), provision profile (mast /
graze / browse / nectar / shelter — from fruit, leaf, phenology, height),
clonality class, growth-form silhouette id (Hallé → render hint).
effective_climate(node, pack): baseline from [niche] metadata + tolerance
axes (drought/salinity/HAND/growing-season) — the rounds' stress input.
Acceptance: existence proofs + monotonicity (bark↑ → resprouter;
nectar syndrome → nectar provision).

### P4 — nomenclature (S)
Reuse K13 engine. `content/stems_flora.toml`: leaf-shape stems
(acerifolius/pinifolius/graminifolius…), flower-color synonyms (same latin
color pools, new axis names), habitat/context stems shared with fauna file,
folk genus label table (sedge/wort/chive/reed/cap…). Folk labels: genus
nodes get folk names from the table by salient trait; species unnamed by
default except pins (RFC §5 naming stack).
Acceptance: pins named; binomials well-formed; zero sid-fallback where
named; folk label matches a real trait of the genus.

### P5 — metrics, CLI, viewer (S)
`metrics.py` (flora checks: constraint violations, pin integration,
guaranteed naming where named, frozen axes excl. derived), `__main__.py`
(seed → k14_seedNNNNNNNN.json + .report). tree.html loads the JSON as-is
(screenshot check).
Acceptance: `uv run python -m exp.k14_flora 1` writes JSON+report OK.

### P6 — derived-products layer D0 (M) — world-facing
`world/{derived.py, manifest}`. Reads a K11 dump (seed dir), writes
`derived.npz` next to it: vent field + hot-spring points, river-speed
field, waterfalls/rapids point list (drop, Strahler, basin), marine
productivity (monthly, upwelling advected + river plumes), soil fertility,
freshwater productivity, growing-season length. All single-pass raster/
graph ops on the 1024²/256² fields.
Acceptance: on seed-1 dump — deterministic rerun; waterfalls only on
river cells with real drops; productivity > 0 at upwelling cells (r_rise_m
maxima); soil fertility peaks on low-HAND high-accumulation cells.
Budget ≤ 5 s.

### P7 — flora stress field (M)
`world/stress.py`: per species, 24-dim month-vector distance + flora
extension axes (salinity band, HAND, growing season, fertility from D0) →
stress raster → passable/costly/blocked masks (leaky thresholds, no hard
cuts). Vectorized per species; shared precompute per world.
Acceptance: a mangrove-grade species passes exactly the high-HAND coastal
band of seed 1; a xeric-grade fails wetlands; determinism.

### P8 — dispersal F1 (L) — the sim-diff beachhead
`world/dispersal.py`: range update per species = stress mask ∩ chamfer
geodesic budget ∩ analytic taper. Channels: local chamfer; wind (release
month → stored monthly wind field lookup + windbreak shadow); water
(downstream-only geodesic along flow_dir, lodge at low-velocity, waterfalls
hard upstream barrier); rare jumps (seeded, clade jump-rate axis). Animal
channel = zero-weight stub (reserved). Output: per-genus range masks at
1024², persisted npz + a colonization PNG (hero visualization).
Acceptance: ranges never cross own blocked mask except via jumps; two
same-climate separated coasts get related-but-distinct floras on ≥1 seed;
water-riding species never appear upstream of a waterfall within its
basin; byte-identical replay; ≤ 10 s for ~500 genera on seed 1.

### P9 — competition/cover/succession + provisions (L) — sim-diff core
`world/cover.py`: layered capacity (canopy/shrub/sward/ground),
establishment vs incumbents (suitability margin, trace abundance below),
negative density dependence (`suit − k·share`, k × (1−site_stress)),
disturbance reset + one-pass recolonization (pioneers first). Output:
per-cell cover mix by layer + provisions (from P3 provision profile).
Acceptance: harsh cells → few dominants + diverse understory, benign →
co-dominants (emergent gradient, measured on seed 1); trace species
present-but-no-cover recorded; provisions match species mix; ≤ 8 s.

## Sequencing & staffing

1. P0–P5 first (flora tree, world-blind) — 6 module prompts, each with the
   acceptance tests above. P1 content is the only taste-heavy one; keep
   v1 cuts as listed, do not expand.
2. P6–P8 (world-facing, needs the seed-1 K11 dump — exists).
3. P9 last; it closes the "flora ready for sim-diff" state.
Out of scope (later plans): fauna rounds A0–A4, ley flora operators,
animal-vector channel, cover→climate feedback, phytoplankton counters.

## Interface mirroring (owner ruling 2026-07-29 #4)

K14 mirrors K13's public surface 1:1 wherever the concept exists:
`content.load_content/merged_pin/merged_preset`, `backbone.build(seed,
pack)`, `derive.derive_tree/effective_climate`, `nomenclature.assign_names`
(K13 engine reused directly), `metrics.run_checks`, `__main__ generate(seed,
pack)` with the same CLI shape, and the same node/tree JSON schema (meta.
generator = "k14_flora"). A reader who knows K13 knows K14.

## User decisions needed

1. ~~`exp/k14_flora/` as the home~~ — APPROVED (K14 = flora engine).
2. ~~Pin list~~ — APPROVED + common-cover pins added (see P1).
3. ~~Coral-grade deferred~~ — REJECTED by owner: corals/sponges are IN
   (the tree is world-blind; marine placement is a rounds concern).
4. Folk-label table English-first (RFC); Latin binomials for genera like
   fauna — keep both (mirrors fauna, per owner).
