# RFC: Flora Engine — Phylogeny, Dispersal, and Cover over a Generated World

**Status:** Draft RFC v0.1 (2026-07-25). Requests comment, not yet normative.
**Context:** Unwritten engine. Companion to the Fauna Engine RFC (v0.2); flora lands **before** fauna in build order and exposes the interface Fauna RFC §10 assumes.
**Depends on:** K1 (hashrng), K9 (complex), K11 worldgen dumps (read-only — K11 is a sealed kernel; this RFC references only its dump artifacts, never its pipeline internals), Fauna RFC (shared phylogenetics core, §1 below).
**Non-functional budget:** the entire biosphere build (this RFC + fauna + ley) must complete in **≤ 60 s on an old laptop** — the K11 worldgen budget. See §8.

---

## 0. Principles

0. **Biomes are cartography, not ontology** (Fauna RFC Principle 0, restated): WWF classes label the map; nothing constrains flora by class membership. Habitat = whatever a species' niche vector says. (Biome *aggregates* — windbreak, transpiration — remain legitimate physics inputs upstream; they are not classifications.)
1. **Phylogenetic correctness is definitional**, as for fauna.
2. **Closed-form, no ticks, fully seeded.** All evolution is per-lineage arithmetic; all spatial dynamics are single-pass field operations.
3. **Impressionistic where possible.** Nobody scrutinizes a sward. Genus-level records suffice for the bulk; species-level detail only where pinned or fauna-dependent.
4. **Curation buys taste, generation buys volume** — same two-tier split as fauna.

## 1. Shared machinery (no rebuild)

From the Fauna RFC, reused verbatim:

- **Phylogenetics core (Fauna §3):** genetic distance g from the initial point, generation-time clock, three forces (drift / stress descent / runaway — runaway applies to flora display organs: flowers), per-clade speciation cutoff g\* in generations, hash-stable IDs. Flora generation length derives from architecture axes (annual herbs clock fast, canopy trees slow — the grass/oak tempo split is emergent).
- **Niche & stress (Fauna §4):** preference vector in the shared 24-dim month-vector space, weighted saturating stress. Flora extension axes: salinity band, HAND/inundation (mangrove/wetland grades), elevation-above-treeline, growing-season length (months above threshold — from derived products, §2), soil fertility, and (post-insect round) pollinator availability.
- **Trait vectors on parts (Fauna §3.2), flora-edited:** body plans here are **growth forms** — terrestrial {tree, shrub, herb, grass/sward, rosette/mat, succulent, vine, epiphyte, fern-grade, moss-grade, fungus (honorary)} + aquatic {benthic rosette, rhizome/hardscape, runner-meadow, floating-leaf, floater, macroalgae/holdfast}; marginals (reeds) are terrestrial plans with high HAND tolerance. Vine/epiphyte are second-round-only (need canopy). Slots: architecture (height, layer, woodiness), leaf (shape, persistence/deciduousness), root (tap/fibrous/mat/aerial/storage), display (flower shape/color — the `signal` generic), fruit/seed (dispersal morphology per channel, §3), defense (thorns, toxins), metabolism (succulence, nitrogen-fixing, carnivory).
- **Generics (Fauna §6.3):** same interface layer — `signal` (flower), `support` (architecture), `feeding organ` (root/leaf chemistry), `defense`, `storage` (tubers/bulbs/rhizomes, succulent water tissue, seed endosperm — couples to seasonality stress and provision density), `locomotor` → replaced by `dispersal`. Ley lifting uses the same operator mechanism (§6, Fauna RFC) with flora-appropriate rebinds.

## 2. Derived-products layer (precompute, new)

One stage computed per world from the K11 dump, stored as `derived.npz` + manifest section. Read-only for everything downstream; algorithms tunable behind this interface. All single-pass raster or graph operations (~5 s total):

| Product | Derivation | Consumers |
|---|---|---|
| **Vent field** (raster + point list) | distance band around convergent/subducting oceanic faults + depth threshold (`r_depth_m`), intensity decaying from fault; terrestrial hot-spring points at land volcanoes and fault–river intersections | ley sites, trench clades, `LAVA-ADAPT` themes |
| **River speed field** | Manning-flavored: slope^½ (elevation drop along `flow_dir`) × depth^⅔, calibrated to speed classes | aquatic niches, water-channel dispersal rate |
| **Waterfalls & rapids** (point list) | river cells with `flow_dir` drop over threshold (falls vs rapids by magnitude, width-scaled); record drop height, Strahler order, basin id | aquatic dispersal **barriers** (fish vicariance), landmarks, ley candidates |
| **Marine productivity (monthly)** | `r_rise_m` upwelling advected by monthly currents with decay; river-mouth plume injection (discharge-weighted) + clarity penalty band | marine flora/fauna carrying capacity, ley triggers |
| **Soil fertility** | deposition geometry (low HAND, high accumulation, width ≥ 2), volcanic-ash bonus, leaching penalty at extreme precip | flora carrying capacity |
| **Freshwater productivity** | lake inflow × basin fertility ÷ area; salinity penalty | lake flora/fauna |
| **Climate overlays** | persistent fog/cloud cores (moisture × stability proxy), ice-free corridor masks, growing-season length | ley triggers, flora phenology axis |

## 3. Dispersal (the flora-specific module)

Flora can't walk; range dynamics = propagule transport. Per species, a kernel = weighted mixture of four channels (weights are clade axes), executed as **single-pass geodesic operations** — never iterative convolution (see §8 for why):

**Range update per round = stress mask + geodesic distance budget + analytic taper.**

1. Stress field per species (vectorized 24-dim weighted distance; cheap), thresholded into passable / costly / blocked — species-relative barriers.
2. **Chamfer geodesic distance transform** from occupied cells through passable cells (O(cells), one pass — the pattern K11's `distance_to_mask` already demonstrates). Geodesic-through-mask routes around barriers: ranges hug coastlines, funnel through corridors, pool in refugia.
3. Range edge = distance contour (this round's budget) ∩ stress taper (soft edges, habitable enclaves).

Channels:

- **Local (gravity/clonal):** chamfer with small budget — meadow creep, forest-edge advance.
- **Wind:** seed set displaced by release-month mean advection (lookup into stored monthly wind fields, not simulation), then chamfer around displaced seeds. Release **phenology** (which months a species drops seed) selects which monthly field advects it — storm-season vs calm-autumn sisters disperse differently. Windbreak-shadowed cells receive less.
- **Water:** downstream-only geodesic along `flow_dir` (one precomputed downstream-distance field per world, shared), speed from the derived river-speed field; seeds lodge at low-velocity cells (floodplains, inlets, confluences — already K9 nodes). Coastal species ride stored current fields. **Waterfalls are hard upstream barriers** — instant drainage-basin vicariance.
- **Animal vectors:** zero-weight during flora-first build; a coupling round post-fauna adds a multiplier for berry/nut clades (interface reserved).
- **Rare long jumps:** per round, seeded low-probability jump to a distant in-band cell (storms over straits). Jump rate is a clade axis (dust-seeded high, heavy-fruited near zero). This channel makes barriers semi-permeable and gives the same climate on two landmasses **different floras** — contingent biogeography.

## 4. Competition, cover, succession

- **Layered capacity:** per cell, independent capacities for canopy / shrub / sward / ground layers. Species occupy layers via architecture axes. Canopy shades; a **shade-tolerance axis** decides understorey membership. Diversity = layers × microsite partitioning.
- **Establishment rule:** realized suitability (1 − stress). Incumbents hold committed cover; a challenger establishes only if suitability beats the least-suitable incumbent's by a seeded per-clade margin (weeds small, climax trees large), taking cover from that incumbent. Below the margin: **trace abundance** (seed bank) — no cover, but present, observable, and primed to expand.
- **Negative density dependence:** effective suitability declines with own share of layer cover (`suit_eff = suit − k·share`, k per clade — host-specific pests/pathogens tax the dominant). Competition strength scales with site benignity (`× (1 − site_stress)`). Emergent gradient: harsh sites → few tolerators dominate canopy, understory diverse (taiga pattern); benign sites → many co-dominants, none holding a layer (temperate/tropical pattern).
- **Disturbance resets:** regime events (fire, flood, storm — and ley lift events count locally) clear cover by layer. Recolonization = one closed-form reassignment pass ordered by (dispersal speed × growth rate × suitability): pioneers first, climax later. Succession without ODEs; r/K axis shared with fauna counters.
- **Output (what fauna reads):** per-patch cover mix by layer, structural class fractions, and **provisions** (mast, graze-able sward, browse, nectar, shelter) computed from the actual species mix — including succession and disturbance history. Plus the productivity bound for the trophic base.

## 5. Two tiers

**Ranks (standard taxonomy):** **Phylum** = line (seed / spore / decomposer) → **Class** = growth-form plan → **Order** = clade-steady traits (flower architecture, fruit family, root family, chemistry, photosynthesis grade, mycorrhizal dependence) → **Family** = narrowed parameter ranges → **Genus** = folk label ("sedge," "wort," "chive") → **Species**. Each rank commits; descendants inherit; pins may sit at any regular rank. Pin test as fauna: *"would the world feel broken if the generator never made this?"*

**Tier 1 — pinned flora (curated, human-authored).** Same job description as fauna anchors: pinning is **authoring a record**, not naming one. The curator sets clade slot and salient trait fields (clade defaults provided); the name is an opaque label attached afterward (locale-tagged; English first). The engine never infers traits from names. Salience computation is available as an authoring aid. Real-plant-inspired pins (yarrow, wild carrot, sword-iris, thread-leaf chive, ice-crown, stonecrop, grave-flower) land here, one per record; anchors need to be *findable*, not common.

**Tier 2 — generated flora (raw output).** The bulk: canopy trees, sward grasses, shrubs, weeds. Genus-level records, mostly unnamed ("a sedge," "white-flowered shrub"); species-level only where pinned or where a fauna dependency demands it.

**Naming:** the Fauna RFC §9 stack unchanged — unnamed default, nickname micro-vocabulary, trait-keyed binomials, curation-only real names.

**Pollinator coupling (one round):** the insect foundation (fauna build) publishes pollinator ranges; flora runs one adaptation round where `signal` axes (flower shape/color) and phenology can descend toward pollinator-matching. Written as a reserved channel, executed once.

## 6. Ley flora

**No pinned magicals** (Fauna RFC §6.2, restated): ley flora is always emergent. A pinned regular plant (e.g. the grave-flower) may carry `RESONANT`-eligible traits, but its lifted forms are generator output.

Ley lifting uses the Fauna RFC §6 machinery unmodified: ley sites sample flora (sessile stock — the vagrant channel is seed dispersal itself), lifted lineages leave the regular tree with pullback reminders, magic operators rebind generics. Flora has one extra property worth stating: **ley-lifted flora can itself become a ley site modifier** (a giant-tree grove is already a listed trigger) — one seeded recursion, capped.

Flora lifts lean **landscape-scale** (fauna lifts make encounters; flora lifts make places). Operator table (each is a concrete record delta — axes changed, slots lost, flags set):

| Operator | Target | Record effect | Flavor |
|---|---|---|---|
| `BUOYANT` | `support` | gas-bladder scaffold; architecture layer → aerial/low; root/stem axes vestigial | floating flowers, sky-meadows |
| `REDUCE [slot]` | any slot | slot removed or shrunk to vestige; recorded in pullback | flower-only organisms, rootless rock-flowers |
| `TERRESTRIALIZE` | medium + `support` | medium += land; support scaffolded for air | coral highlands, land-anemones |
| `AQUATIZE` | medium | inverse: land plans gain submersion | sunken meadows |
| `CLONAL BLOOM` | clonality axis | axis → unbounded; **one entity, area-valued** (counters treat as singleton with extent); synchronous phenology | flower sea, single-organism forest |
| `GIANT` / `TINY` | `support` | scale ×k / ÷k outside bounds | god-tree grove; moss-grade trees in a rock crack |
| `GLOW` / `PULSE` | `signal` | hue/intensity from site palette on display organs; `PULSE` adds rhythm (a flower sea pulses in waves) | luminous meadows, lantern-fruit |
| `SPORE-FOG` | dispersal | spore output ×, luminous/persistent; local ambience flag | glowing spore-fog forests; visible dispersal |
| `LEY-FED` | `sustenance` | field-fed; nutrient axes inert; range-locked, substrate-free | flowers on bare rock, flora on statues |
| `MANA-FILTER` | `feeding organ` | carnivorous trap → mana-prey; root → siphon | ley pitcher-plants |
| `RESONANT` | `sensor array` (tropism) | growth/bloom intensity ∝ ley gradient | divining flowers (the grave-flower's home), explorer's compass |
| `PHASE-ROOT` | root slot | roots penetrate any substrate | cliff-face gardens |
| `EVERBLOOM` | phenology | bloom window → always-on, or inverted: one day/year (date seeded — festival flower, rumor bait) | the always-blooming grove; the one-day bloom |
| `VOLATILE` | seed/fruit slot | hazard-grade fruit (explosive pods scaled, spore bursts) | dangerous meadows |
| `MIRROR-GROW` | architecture | growth form copies a nearby plan's silhouette | coral-shaped forests |
| `SEED-RAFT` | dispersal | seeds/fruits become buoyant rafts (water, or aerial with `BUOYANT`) | drifting seed-islands |

Rules: one-entity-vs-many is always stated; combos produce named place-types (`TERRESTRIALIZE`+coral = coral highlands; `CLONAL BLOOM`+`PULSE` = the flower sea; `GIANT`+`LEY-FED` = the god-tree); renderer and field guide read the same delta — nothing is prose-only.

## 7. Pass order (biosphere; interleaved with fauna/ley)

Each stage = one pure function, one hero visualization, committed inputs only. (Fauna/ley stages shown for position; specified in the Fauna RFC.)

| # | Stage | Loading screen |
|---|---|---|
| D0 | Derived products (§2) | "reading the world" sheet: vents, falls, plumes |
| F0 | Flora backbone + pins | cladogram diagram |
| F1 | Flora dispersal, round 1 | colonization movie, frame 1 |
| A0 | Fauna backbone + anchors | cladogram + anchor ranges |
| A1 | Fauna dump, round 1 (herbivores; flora-aware) | range fields |
| L1 | Ley lifts, round 1 | lift markers (site × source stock) |
| F2 | Flora round 2 (succession after L1 disturbance) | colonization frame 2 |
| A2 | Fauna round 2 (predators, insect foundation) | range fields |
| L2 | Ley lifts, round 2 | lift markers |
| F3 | Flora round 3 (pollinator coupling) | colonization frame 3 |
| A3 | Fauna round 3 (background, full web) | range fields |
| L3 | Ley lifts, round 3 (wildcards upweighted) | lift markers |
| F4 | Flora cover, final | cover mix map (layer fractions) |
| A4 | Fauna web, final | abundance heatmap |
| — | Deliver / persist | delivery sheets |

Determinism: one K1 master seed, stage-scoped substreams; the DAG replays byte-identical. Stage dumps are the persistence units — re-run the biosphere from any boundary without touching the world dump.

## 8. Performance (NFR)

Budget: **≤ 60 s total biosphere build on an old laptop** (the K11 worldgen envelope). Rules:

1. **No iterative convolution, ever.** Range dynamics = stress field (vectorized) + chamfer geodesics (O(cells) per species per round). ~10³ species × ~10⁵ ops ≈ single-digit seconds.
2. **Shared precompute:** downstream-distance field, wind displacement lookups, transport matrices, stress components — once per world, amortized across all species.
3. **Species budget:** backbone ≤ ~500 flora genera; active-lineage cap per round (only new arrivals / expanding fronts smear).
4. **Fixed round count** (3–4). No run-until-convergence loops.
5. **Raster passes budgeted:** stress fields ~1–2 s; chamfer passes ~5–10 s all rounds; competition/cover (the one true raster pass, ~10–30 candidates per cell) 3–8 s; final paint a few seconds. Headline estimate **15–25 s**, leaving slack.
6. First dial under pressure: species counts (invisible below density), never round count (rounds are the visible texture).

## 9. Non-goals

- Pairwise species-interaction matrices (margin-vs-incumbents mean-field instead; O(n²) curation for marginal fidelity; seed-bank mechanics recover most dynamics).
- Flora-internal physiology simulation, photosynthesis models, soil ODEs.
- LLM-composed species or trait inference from names.
- Animal-vector dispersal before fauna exists (reserved channel only).
- Re-running climate per flora state (delivered climate is the fixed stage; the cover→climate feedback was already closed upstream).

## 10. Open questions

1. Growth-form plan list: terrestrial {tree, shrub, herb, grass, rosette/mat, succulent, vine, epiphyte, fern-grade, moss-grade, fungus(honorary)} + aquatic {benthic rosette, rhizome/hardscape, runner-meadow, floating-leaf, floater, macroalgae/holdfast} — vine/epiphyte are second-round-only plans (need canopy). Right cut?
2. Jump-rate calibration per clade: what frequency makes island floras related-but-distinct rather than identical or unrelated?
3. Shade-tolerance as one axis or two (seedling vs adult)?
4. Margin + NDD calibration: target fraction of trace species per cell at steady state; target dominance curve per climate band (taiga duopoly vs temperate mixed canopy)?
5. Fire return-interval coupling: does flora get a say in fire frequency (fuel axis feeding the A2 fire regime), or is fire purely exogenous?
6. Ley-flora recursion cap (§6): exactly one round, or two?
7. Carnivorous-plant clade: fauna-coupled (needs insect counters) or self-contained provision math?
