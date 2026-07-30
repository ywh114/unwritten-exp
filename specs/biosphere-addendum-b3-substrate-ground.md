# Biosphere Addendum B3 — Substrate (Ground) Derivation Pass

Status: DRAFT v0.1, awaiting owner review. Amends the derived-products
table of `unwritten-flora-engine-rfc.md` §2. Research basis:
`specs/b3_substrate_research_report.md` (external agent, 2026-07-30).

## Vocabulary (owner rulings, 2026-07-30)

- **Substrate** = the physical growth medium (soil/seabed) — what some
  plants and some animals care about. Distinct from **productivity**
  (= carrying capacity, B2, shipped) and from **biome** (WWF-style
  vegetation-climate label; biomes describe biomes, not habitats).
- Internal name: **`ground`** — `substrate_ok()` in K13/K14 already
  means ANATOMICAL substrate (a mane needs fur); reusing the word
  pollutes every future grep.
- Discrete classes are wanted: they break up the terrain.

## Architecture

Two engines run everywhere; neither has veto:

1. **Physical process layer** (parent material): the deposition
   detector (catchment accumulation × HAND — the old `soil_fertility`
   core's third and final home), slope/erosion (scree, bedrock),
   glaciation (till, outwash, from the persisted glacier fields), the
   vent field (andisol, fresh lava, vent crust, hot springs),
   endorheism/evaporation (solonchak), depth + current energy (marine
   sand vs mud), river speed (flow-sorted beds), tidal band (tidal
   flat).
2. **Biome bias** (biotic transformation): biomes create their own
   environment — grassland builds mollisol, conifer acidifies to
   podzol, rainforest strips to ferralsol, temperate broadleaf makes
   brown earth, wetlands grow peat, mangrove traps mud. The biome is
   the biasing background we run against: it pretends the climate
   considerations were already done for us. **No hard ties in either
   direction** — a temperate forest on a steep slope is scree; the
   physical layer holds regardless of what the biome prefers.
   Conjunctive biomes are mosaics: "desert xeric shrubland" = desert
   AND xeric shrubland, decomposed into their substrate shares.

Genesis (physical / biotic / mixed) is per-class METADATA, never a
constraint.

**Dune rule**: dune sand only in the most-arid fraction of arid cells
(lowest aridity-index band + depositional supply); the rest of the arid
mosaic is sand sheet / reg. Dune mobility is L1's job — dunes are
inhospitable dunes, detail comes later.

**Underwater is the same table, same machinery** — retention reads 1.0
(saturated); texture, rooting, salinity, nutrient do the work. River
gravel vs sand keys off the river-speed field (flow-sorting is the
justification — no spawning consumer exists yet). Marine sand vs mud
keys off depth + current energy.

**Soil salinity has no upstream field** (K11 `h_salinity` covers water
cells only): the sal+ column is DERIVED inside the pass from
endorheism, aridity, and coast adjacency — the one column with its own
derivation budget.

## Output & persistence

- Class map at anchor res (256²) + the **full d2 vector** (41 floats
  per cell, one `(n_classes, H, W)` array — ids implicit, no sort, no
  K decision; ~11 MB/world). This SUPERSEDES the top-2 line in B2 and
  the top-3 discussion: with 41 classes the tail is signal, not noise
  (dune vs sand sheet vs loess; fen vs bog vs gleysol), and mosaic
  cells honestly span 4–5 classes. Consumers do the consume-time
  softmax over −d2 as always (biosphere_conv ruling); the dominant
  class serves display and discreteness.
- Biomes keep shipped top-2 untouched (16 classes, strongly peaked).

## Consumers

The stress/suitability consumer (`world/stress.py`, planned P7) is NOT
implemented yet — this pass co-designs its input schema on a
greenfield. Suitability maps onto EXISTING species axes (no new ones):

- `drought_tolerance` ← effective water availability (retention)
- `waterlogging_tolerance` ← saturation (retention ≈ 1 proxies anoxia —
  intentional)
- `salinity_tolerance` ← sal+ (fauna: the `Condition.env` "salinity"
  hook, osmoreg generics)
- `fertility_requirement` ← nutrient stock
- rooting-depth gate: `root_depth_m` vs the class's rooting depth;
  anchoring need is calculable from height/woodiness (K13 ruling:
  axes that can be calculated ARE calculated)

**Hard vs soft, penetrable vs not, are per-class metadata flags**, not
columns (holdfast rooters — kelp, sponge — need hard; fossorial fauna
and SAND-SWIM need loose; hardpans — caliche, laterite — get
impenetrable for free). The class list IS the schema: every future
class proposal must name the consumer decision it changes. pH is
smuggled in as class identity (fen/bog, rendzina calcicole) — no pH
column.

**Magic-class exemptions** (per-lineage, not classes): LEY-FED is
substrate-free; PHASE-ROOT bypasses rooting/impenetrability;
BUOYANT/slot absence is substrate-free; TERRESTRIALIZE/AQUATIZE must
not be hard-blocked by the soil/seabed boundary. Heat/ice as medium
(LAVA-ADAPT, ICE-PHASE) join the vent/glacier products at consumption
time — no columns.

## Class table (41; floats are draft — the ORDERINGS are the
defensible content, consumers reading d2 are robust to ±0.1)

Terrestrial — physical:

| class | retention | rooting m | sal+ | nutrient | genesis |
|---|---|---|---|---|---|
| dune sand | 0.05 | 0.3 | 0 | 0.15 | most-arid deposition only |
| sand sheet | 0.10 | 0.5 | 0 | 0.20 | arid |
| reg / desert pavement | 0.05 | 0.2 | 0 | 0.15 | winnowing |
| scree | 0.05 | 0.10 | 0 | 0.05 | slope override |
| bedrock outcrop | 0.02 | 0.05 | 0 | 0.02 | erosion |
| alluvium | 0.65 | 2.0 | 0 | 0.80 | deposition |
| loess | 0.55 | 1.5 | 0 | 0.70 | glacial-margin wind |
| silt | 0.60 | 1.2 | 0 | 0.65 | low-energy deposition |
| clay | 0.65 | 0.8 | 0 | 0.55 | still water (plant-available, not total) |
| vertisol | 0.75 | 1.2 | 0 | 0.70 | shrink-swell smectite, seasonal cracks |
| till | 0.45 | 0.8 | 0 | 0.50 | glacial |
| outwash gravel | 0.15 | 0.4 | 0 | 0.35 | glaciofluvial |
| andisol | 0.80 | 1.0 | 0 | 0.70 | vent proximity (allophane: high water, P fixed) |
| fresh lava | 0.05 | 0.1 | 0 | 0.30 | active fault |
| rendzina | 0.30 | 0.4 | 0 | 0.55 | limestone (calcicole; absorbs chalk) |
| laterite cuirasse | 0.10 | 0.2 | 0 | 0.10 | plinthite hardpan, tropical |
| caliche | 0.12 | 0.25 | 0 | 0.20 | petrocalcic hardpan, semi-arid |
| solonchak | 0.10 | 0.3 | 1.0 | 0.05 | endorheic/coastal evaporite (absorbs sabkha) |
| solonetz | 0.35 | 0.5 | 0.45 | 0.25 | sodic, dispersed clay |
| coastal sand | 0.10 | 0.4 | 0.3 | 0.20 | littoral |

Terrestrial — biotic / mixed:

| class | retention | rooting m | sal+ | nutrient | genesis |
|---|---|---|---|---|---|
| mollisol | 0.70 | 2.2 | 0 | 0.95 | grassland |
| podzol | 0.45 | 0.9 | 0 | 0.25 | conifer/taiga |
| ferralsol | 0.55 | 1.5 | 0 | 0.15 | rainforest (nutrients in biomass) |
| brown earth | 0.60 | 1.5 | 0 | 0.65 | temperate broadleaf |
| fen | 0.92 | 0.5 | 0 | 0.45 | groundwater-fed peat |
| bog | 0.98 | 0.3 | 0 | 0.05 | rain-fed Sphagnum dome (carnivory's home) |
| gleysol | 0.85 | 0.3 | 0 | 0.30 | groundwater waterlogging |
| gelisol | 0.60 | 0.4 | 0 | 0.30 | permafrost + cryoturbation |
| mangrove mud | 0.90 | 0.5 | 0.6 | 0.50 | mangrove |
| montane ranker | 0.35 | 0.4 | 0 | 0.40 | thin upland soil |

Underwater (retention 1.0 saturated; sal+ = the water's salinity):

| class | retention | rooting m | sal+ | nutrient | genesis |
|---|---|---|---|---|---|
| marine mud | 1.0 | 0.3 | sea | 0.40 | marine snow, quiet shelf |
| abyssal clay | 1.0 | 0.2 | sea | 0.10 | pelagic, food-starved |
| marine sand | 1.0 | 0.3 | sea | 0.25 | high-energy shelf |
| reef carbonate | 1.0 | 0.4 | sea | 0.35 | coral |
| rocky bottom | 1.0 | 0.05 | sea | 0.20 | high energy / kelp holdfast |
| vent crust | 1.0 | 0.1 | sea | 0.90 | hot sulfide chemosynthesis |
| cold seep | 1.0 | 0.3 | sea | 0.85 | methane chemosynthesis + carbonate |
| tidal flat | 1.0 | 0.15 | 0.5 | 0.55 | tide-sorted, brackish gradient |
| lake mud | 1.0 | 0.4 | lake | 0.60 | deposition + biotic |
| river gravel bed | 1.0 | 0.2 | 0 | 0.30 | flow-sorted |
| river sand bed | 1.0 | 0.3 | 0 | 0.25 | flow-sorted |

Renames from earlier drafts: volcanic ash → andisol, salt pan →
solonchak, peat → fen + bog (split). Rejected candidates (L1 detail,
not classes): ultisol row, playa crust, palsa, drumlin, karst pavement,
tufa, beach ridges, fjord anoxic sediment, seagrass-meadow sediment,
glacial-marine diamicton, brine pool, marine gravel — see the research
report for verdicts.

## Knobs

1. The class table (property rows + metadata flags) — the main knob set.
2. Derivation bounds (deposition, slope, energy, aridity bands, dune
   gate).
3. Soil-salinity derivation parameters (endorheism, evaporation, coast
   adjacency).
4. d2 softmax temperature (consume time).

## Non-goals

- Habitat pass — after plantae runs (WWF biomes are not habitats;
  organic media — litter, dead wood, saprotroph substrates — belong
  there, not here).
- No changes to productivity (B2) or the biome machinery.
- No dune mobility modeling (L1), no pH column, no per-class time
  series.
- Fauna substrate axes: K13 has none yet (moisture only) — the pass
  serves the hooks that exist (`Condition.env` salinity, vertical
  stratum gating) but does not author fauna axes.
