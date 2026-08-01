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
   Conjunctive biomes are mosaics: "desert xeric (hot)" = desert
   AND xeric shrubland, decomposed into their substrate shares.

Genesis (physical / biotic / mixed) is per-class METADATA, never a
constraint.

**Dune rule**: dune sand only in the most-arid fraction of arid cells —
a hard aridity BAND (full weight only in the lowest aridity-index band,
ramped to zero by the subhumid band) plus depositional supply at a TRUE
drainage terminus (a flow direction ending in standing water or
off-grid — the terminal wadi fan); the rest of the arid mosaic is sand
sheet / reg. Cold and glacier tails close the frozen ends: no deflation
under frost, no dunes on ice. Dune mobility is L1's job — dunes are
inhospitable dunes, detail comes later.

**Sand sheet rule**: sand sheet needs warmth. The cold gate docks the
sheet to a 0.15 floor below ~5 °C annual (the cold-desert band — the
cold-desert biome centroid sits at 4 °C, hot-desert at 24 °C) and zeroes
it at freezing ((1-cold)); cold-arid cells fall through to reg, which
keeps its symmetric cold-desert bias and arid² rule. Hot deserts
(≥20 °C) read unchanged. Owner ruling 2026-08-01: real cold deserts are
reg/pavement, not sand seas — the sheet's pure-precipitation rule read a
~200 mm/yr / 5 °C cold grassland as sand sea (arid 0.87, sheet beat
mollisol on arid seeds 2/3).

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

- Class map at anchor res (256²) + the **full d2 vector** (42 floats
  per cell, one `(n_classes, H, W)` array — ids implicit, no sort, no
  K decision; ~11 MB/world). This SUPERSEDES the top-2 line in B2 and
  the top-3 discussion: with 42 classes the tail is signal, not noise
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
- `ph_tolerance` ← pH (the calcicole/calcifuge split — a first-order
  niche axis real ecology has and the axis set was missing)
- `fertility_requirement` ← nutrient stock
- rooting-depth gate: `root_depth_m` vs the class's rooting depth;
  anchoring need is calculable from height/woodiness (K13 ruling:
  axes that can be calculated ARE calculated)

**Hard vs soft, penetrable vs not, are per-class metadata flags**, not
columns (holdfast rooters — kelp, sponge — need hard; fossorial fauna
and SAND-SWIM need loose; hardpans — caliche, laterite — get
impenetrable for free). The class list IS the schema: every future
class proposal must name the consumer decision it changes. pH was
originally smuggled in as class identity (fen/bog, rendzina calcicole);
the 2026-07-30 revision promotes it to an explicit property column —
the classes were already pH-diagnostic, so the column is one float per
row and cell pH is the mix-weighted mean (see Revisions).

**Magic-class exemptions** (per-lineage, not classes): LEY-FED is
substrate-free; PHASE-ROOT bypasses rooting/impenetrability;
BUOYANT/slot absence is substrate-free; TERRESTRIALIZE/AQUATIZE must
not be hard-blocked by the soil/seabed boundary. Heat/ice as medium
(LAVA-ADAPT, ICE-PHASE) join the vent/glacier products at consumption
time — no columns.

## Class table (42; floats are draft — the ORDERINGS are the
defensible content, consumers reading d2 are robust to ±0.1)

Terrestrial — physical:

| class | retention | rooting m | sal+ | nutrient | pH | genesis |
|---|---|---|---|---|---|---|
| dune sand | 0.05 | 0.3 | 0 | 0.15 | 6.5 | most-arid, terminus-fed deposition only |
| sand sheet | 0.10 | 0.5 | 0 | 0.20 | 6.5 | arid, warm-gated (cold → reg) |
| reg / desert pavement | 0.05 | 0.2 | 0 | 0.15 | 7.8 | winnowing |
| scree | 0.05 | 0.10 | 0 | 0.05 | 6.8 | slope override |
| bedrock outcrop | 0.02 | 0.05 | 0 | 0.02 | 7.0 | erosion |
| alluvium | 0.65 | 2.0 | 0 | 0.80 | 6.8 | deposition |
| loess | 0.55 | 1.5 | 0 | 0.70 | 7.8 | glacial-margin wind |
| silt | 0.60 | 1.2 | 0 | 0.65 | 6.8 | low-energy deposition |
| clay | 0.65 | 0.8 | 0 | 0.55 | 6.5 | still water (plant-available, not total) |
| vertisol | 0.75 | 1.2 | 0 | 0.70 | 7.8 | shrink-swell smectite, seasonal cracks |
| till | 0.45 | 0.8 | 0 | 0.50 | 6.8 | glacial |
| outwash gravel | 0.15 | 0.4 | 0 | 0.35 | 6.5 | glaciofluvial |
| andisol | 0.80 | 1.0 | 0 | 0.70 | 5.5 | vent proximity (allophane: high water, P fixed) |
| fresh lava | 0.05 | 0.1 | 0 | 0.30 | 6.5 | active fault |
| rendzina | 0.30 | 0.4 | 0 | 0.55 | 7.8 | limestone (calcicole; absorbs chalk) |
| laterite cuirasse | 0.10 | 0.2 | 0 | 0.10 | 5.0 | plinthite hardpan, tropical |
| caliche | 0.12 | 0.25 | 0 | 0.20 | 8.2 | petrocalcic hardpan, semi-arid |
| solonchak | 0.10 | 0.3 | 1.0 | 0.05 | 8.5 | endorheic/coastal evaporite (absorbs sabkha) |
| solonetz | 0.35 | 0.5 | 0.45 | 0.25 | 9.0 | sodic, dispersed clay |
| coastal sand | 0.10 | 0.4 | 0.3 | 0.20 | 7.5 | littoral |

Terrestrial — biotic / mixed:

| class | retention | rooting m | sal+ | nutrient | pH | genesis |
|---|---|---|---|---|---|---|
| mollisol | 0.70 | 2.2 | 0 | 0.95 | 6.8 | grassland |
| podzol | 0.45 | 0.9 | 0 | 0.25 | 4.5 | conifer/taiga |
| ferralsol | 0.55 | 1.5 | 0 | 0.15 | 5.0 | rainforest (nutrients in biomass) |
| brown earth | 0.60 | 1.5 | 0 | 0.65 | 6.0 | temperate broadleaf |
| fen | 0.92 | 0.5 | 0 | 0.45 | 6.2 | groundwater-fed peat |
| bog | 0.98 | 0.3 | 0 | 0.05 | 4.0 | rain-fed Sphagnum dome (carnivory's home) |
| gleysol | 0.85 | 0.3 | 0 | 0.30 | 5.5 | groundwater waterlogging |
| gelisol | 0.60 | 0.4 | 0 | 0.30 | 5.5 | permafrost + cryoturbation |
| mangrove mud | 0.90 | 0.5 | 0.6 | 0.50 | 6.5 | mangrove |
| montane ranker | 0.35 | 0.4 | 0 | 0.40 | 5.5 | thin upland soil |

Underwater (retention 1.0 saturated; sal+ = the water's salinity; pH =
pore/water-column pH — seawater-buffered ~8, vent crust acid):

| class | retention | rooting m | sal+ | nutrient | pH | genesis |
|---|---|---|---|---|---|---|
| marine mud | 1.0 | 0.3 | sea | 0.40 | 7.8 | marine snow, quiet shelf |
| abyssal clay | 1.0 | 0.2 | sea | 0.10 | 7.8 | pelagic, food-starved |
| marine sand | 1.0 | 0.3 | sea | 0.25 | 8.0 | high-energy shelf |
| reef carbonate | 1.0 | 0.4 | sea | 0.35 | 8.2 | coral |
| rocky bottom | 1.0 | 0.05 | sea | 0.20 | 8.1 | high energy / kelp holdfast |
| vent crust | 1.0 | 0.1 | sea | 0.90 | 5.5 | hot sulfide chemosynthesis |
| cold seep | 1.0 | 0.3 | sea | 0.85 | 7.2 | methane chemosynthesis + carbonate |
| pillow basalt | 0.10 | 0.1 | sea | 0.10 | 8.0 | submarine eruption (quenched pillow lava) |
| tidal flat | 1.0 | 0.15 | 0.5 | 0.55 | 7.5 | tide-sorted, brackish gradient |
| lake mud | 1.0 | 0.4 | lake | 0.60 | 7.0 | deposition + biotic |
| river gravel bed | 1.0 | 0.2 | 0 | 0.30 | 7.2 | flow-sorted |
| river sand bed | 1.0 | 0.3 | 0 | 0.25 | 7.2 | flow-sorted |

Renames from earlier drafts: volcanic ash → andisol, salt pan →
solonchak, peat → fen + bog (split). Rejected candidates (L1 detail,
not classes): ultisol row, playa crust, palsa, drumlin, karst pavement,
tufa, beach ridges, fjord anoxic sediment, seagrass-meadow sediment,
glacial-marine diamicton, brine pool, marine gravel — see the research
report for verdicts.

## Revisions (2026-07-30)

**42nd class: pillow basalt.** Real submarine eruptions quench to
pillow lava, so the active submarine crater bowl splits by depth:
shallow bowls read pillow basalt (`vent_core × ocean × (1 − ½·depthn)`),
deep (abyssal/hadal) bowls keep vent crust (`vent_core × ocean ×
depthn`) — vent crust is properly the sulfide cap of deep, long-lived
hydrothermal systems, not every submarine bowl. Land bowls keep fresh
lava. Pillow basalt is the one underwater row with retention below 1.0
(bare rock, not sediment).

**Cold seep is now two provenances.** (a) Vent-adjacent hydrothermal
seepage — the ring around every vent, gated off above ~200 m (no
methane-hydrate stability on shallow shelves), uncapped downward (hadal
vent seepage is real). (b) Passive-margin seeps decoupled from vents —
a smooth hydrate-stability band (~300–3000 m) × sediment × a mild slope
preference; real cold seeps cluster on sediment-rich continental
slopes, not as concentric rings around every volcano.

**pH is promoted to a property column.** The classes were already
pH-diagnostic (caliche/solonchak alkaline, podzol/bog/ferralsol acid,
rendzina base-rich, vent crust hydrothermal-acid), so the column is one
draft float per row — the ORDERING (bog < fen, podzol < brown earth,
laterite < rendzina, solonchak < solonetz) is again the defensible
content. Cell pH is the top-3 mix-weighted mean of the class rows
(`mix_ph`, pointwise — derived at anchor and delivery res from the
persisted mix, no extra field derivation budget); land reads soil pH,
underwater reads pore/water pH with vent cells coming out acid from the
class row alone. This supersedes the "pH smuggled as class identity"
line above and feeds the planned P7 stress pass (`ph_tolerance`, the
calcicole/calcifuge split) and pigment-chemistry flower color
(anthocyanin expression is pH-dependent — hydrangea logic).

## Revisions (2026-08-01)

**Sand sheet gets a cold gate.** Its rule was pure-precipitation
arid^1.5 — no temperature term — so a cold grassland (~200 mm/yr,
~5 °C) read arid 0.87 and the sheet outvoted mollisol (owner report,
arid seeds 2/3). Real cold deserts are reg/pavement, not sand seas
(owner ruling 2026-08-01): the sheet's physical rule now multiplies by
`(1-cold) · (0.15 + 0.85·warm)` — warm = 0 below 5 °C annual docks the
sheet to the 0.15 floor (the cold-desert centroid sits at 4 °C; hot
deserts at ≥20 °C read warm = 1 and are unchanged), and (1-cold) zeroes
the frozen tail (no deflation under frost). Cold-arid cells fall
through to reg. **Bias stays symmetric** (hot + cold desert ×1.5):
measured on seeds 1-3, cold-desert/grassland sheet dominance was
0-2.5% before and the physical gate alone flips it to ~0 — the floor
keeps cold sand sheet possible but rare, the same idiom as dune's
hot-only bias comment.

## Revisions (2026-08-01, dune gate + littoral dock)

**Dune gets the most-arid band, a terminus-gated supply, and cold/glacier
tails.** The old gate weighted by the smooth arid² — arid = 1 − p/1500
leaves 0.32–0.54 at 400–650 mm/yr, so subhumid dune outvoted mollisol
(172 seed-1 cells read dune at p > 400 mm, 91% of them on a saturated
supply term). Three fixes (owner ruling 2026-08-01):
- **Arid band** replaces arid²: full weight only at/above arid 0.83
  (~255 mm/yr — the 150–250 mm arid band and everything drier), a hard
  band ramping to zero by arid 0.75 (~375 mm/yr — the subhumid
  400–650 mm band reads ~0). Same band idiom as the sheet's cold gate.
- **Supply only at true drainage termini**: the supply term was
  clip(acc/10) — acc is the plain upstream cell count (land max 56 on
  seed 1), so ANY 10-cell catchment saturated it and 93% of implausible
  dune cells carried it. Supply now requires the persisted K11 flow
  direction to terminate in standing water or off-grid — the terminal
  wadi fan. DUNE_ACC_REF stays 10: desert terminal catchments run acc
  p95 ~10 and interiors max out near ~20 cells, so REF opens only true
  drainage termini (the flat/dry self-gate still covers basin-interior
  deflation ergs).
- **Cold and glacier tails**: (1−cold) zeroes the frozen tail (no
  deflation under frost) and (1−glac) clears glacier cells — 48 dune
  cells sat ON the glacier mask at t −6…−9 °C / ~430–510 mm before the
  ruling. The sheet's warm floor is NOT copied: dunes get the cold tail
  only, no floor — the sheet's floor exists because cold-desert sand
  seas are rare-but-real; mobile dune sand needs warmth, and cold
  deserts fall through to reg.

**Coastal sand gets a steeper littoral slope dock.** The ocean-littoral
term's (1−slope) left cliff coasts (slope > 0.3, a 24% grade) docked to
0.7 only; 629 seed-1 coastal cells read share > 0.2 at slope > 0.3 (422
of them humid). The OCEAN term now docks (1−slope)², dropping cliff
coasts toward scree/bedrock while gentle beaches keep their coastal
sand. The LAKE-shore ring term is untouched — the lake littoral is an
open owner decision.

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
