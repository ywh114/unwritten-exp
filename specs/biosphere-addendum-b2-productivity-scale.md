# Biosphere Addendum B2 — Productivity on an Absolute Scale

Status: DRAFT v0.2, awaiting owner review. Amends the derived-products
table of `unwritten-flora-engine-rfc.md` §2.

## Problem

The existing derived productivity fields (K14 `world/derived.py`) are
**rank/normalized within their mask**. Every value is relative to the
current world's best cell, so the scale has no absolute meaning and
compresses toward the middle — "low values everywhere." They also use
no biomes: a region's real productivity depends on its history, and
history is what biomes encode.

Symptom: an open-ocean cell in July (near-24 h sunlight, 5 °C, ice-free)
reads 0.03 while an upwelling cell reads ~1 — the monthly `_norm01`
anchors the whole ocean to its single best pixel, and the Eppley
temperature term (optimum 25 °C) throttles polar summer to quarter
speed, when real polar seas bloom hardest at 0–5 °C given light.

## Vocabulary (owner ruling, 2026-07-30)

- **Productivity = carrying capacity.** One number per cell; the
  trophic bound flora/fauna read.
- **Substrate type** — what some plants and some animals care about —
  is a SEPARATE derivation pass (future addendum), not a productivity
  number. It subsumes what the old `soil_fertility` field pretended to
  be. The substrate pass produces its own class map with persisted
  top-2 d2 distances, and consumers read functions of substrate type
  via the same soft-match machinery as biomes here.
- The old abiotic deposition detector (`accumulation × (1−HAND)`) is
  neither fertility nor substrate — it is the **productivity bonus**
  on top of the biome priors (alluvial plains genuinely out-produce
  their biome baseline).

## Design (rework the EXISTING fields in place — no new fields)

    productivity = w1·prior[b1] + w2·prior[b2] + g·F

- `b1, b2`: the two closest biome/aquatic classes from the persisted d2
  fields (`w_biome_d2_1`, `w_biome_d2_2`, `w_biome_second`).
  (Clarification: only TERRESTRIAL biomes have persisted d2 — aquatic
  classes are hard pointwise classes with no similarity field, so
  marine/freshwater priors look up the anchor-level aquatic class id
  directly. The substrate pass, when it lands, persists its own top-2
  d2 and joins the soft-match pattern.)
- Weights: inverse-distance over the two — `w1 = d2/(d1+d2)`,
  `w2 = d1/(d1+d2)`. Equidistant → 50/50, exact match → pure. No extra
  knob.
- `prior[]`: curated per-class table (below) — the region's carrying
  capacity given its history. Soil history is folded in IMPLICITLY
  (the biome exists where it is because of it); there is no separate
  fertility column. **The table is the main knob set.**
- `F`: the field's abiotic logic, **de-ranked and bounded by
  construction** (caps, exponentials, reference values — never rank or
  `_norm01`), acting as the visible bonus on top of the prior.
- `g`: per-field gain, tuned so the abiotic bonus is *visible*
  (within-biome texture, seasonal variation) but never reorders the
  biome baseline. No second normalization anywhere.

**Scale anchor**: 1.0 = reference-best class (tropical upwelling
marine; tropical moist forest terrestrial). All downstream consumers
read one absolute, comparable scale.

## Field by field

- **Terrestrial productivity**: priors + bounded climate terms (light ×
  temperature × water) + the deposition bonus (catchment accumulation,
  HAND waterlogging penalty — the de-ranked old `soil_fertility` core).
- **Marine productivity** (monthly): **open ocean has NO prior** — it
  is sunlight-based (persisted insolation × sea-ice-free fraction ×
  the fixed temperature response). Other marine classes carry priors;
  upwelling/plume nutrient advection stays as the bonus (absolute,
  capped — no `_norm01`).
- **Freshwater productivity** (lake/river aquatic classes): priors +
  existing warmth/inflow/shallowness terms, de-ranked; ice-free
  fraction cut stays.
- **`soil_fertility` product: REMOVED** (no consumers — verified
  2026-07-30: only the viewer datapack layer and its own test; the
  `fertility_requirement` axis in the flora tree generator is a
  species trait, not a field consumer). Its deposition logic lives on
  as the bonus term above. The substrate-type pass (future addendum)
  takes over soil-as-niche.
- **Temperature response fix** (shared): replace the 25 °C-optimum
  Eppley curve with a cold-tolerant plateau — full rate from ~10 °C
  up, gentle roll-off below (2–10 °C must not be a 4× penalty), zero
  at freezing. One curve, two knobs (plateau edge, roll-off rate).

## Draft prior table (owner tunes)

| biome | productivity |
|---|---|
| tropical moist forest | 1.00 |
| tropical dry forest | 0.55 |
| tropical conifer forest | 0.60 |
| temperate broadleaf forest | 0.75 |
| temperate conifer forest | 0.65 |
| boreal taiga | 0.40 |
| tropical grassland | 0.50 |
| temperate grassland | 0.55 |
| flooded grassland | 0.65 |
| montane grassland | 0.35 |
| tundra | 0.15 |
| mediterranean scrub | 0.45 |
| desert xeric (hot) | 0.08 |
| desert xeric (cold) | 0.08 |
| mangrove | 0.70 |
| rock | 0.02 |
| ice | 0.00 |

| aquatic class | productivity |
|---|---|
| open ocean | — (sunlight-based) |
| polar shelf | 0.45 |
| temperate shelf | 0.55 |
| tropical shelf | 0.50 |
| coral reef | 0.65 |
| temperate upwelling | 0.90 |
| tropical upwelling | 1.00 |
| inland sea | 0.40 |
| salt lake | 0.10 |
| large lake | 0.50 |
| polar lake | 0.20 |
| montane lake | 0.30 |
| tropical lake | 0.60 |
| temperate lake | 0.55 |
| delta | 0.70 |
| coastal river | 0.45 |
| floodplain river | 0.55 |
| upland river | 0.35 |
| polar river | 0.20 |
| montane river | 0.30 |
| xeric river | 0.25 |

## Knobs (complete list)

1. The prior table (per class).
2. Per-field abiotic gain `g` (terrestrial, marine nutrient,
   freshwater).
3. Temperature curve: plateau edge, roll-off rate.
4. Bounds inside `F` (reference catchment, HAND decay, precip cap).

## Non-goals

- No new derived fields; no normalization passes of any kind.
- Substrate-type derivation pass — separate future addendum (its own
  classes, own persisted top-2 d2, consumers read functions of it).
- Vents/hot springs stay a separate product (volcanic ash is a
  SUBSTRATE signal, for that pass — not a productivity source here).
- d2 similarity machinery itself is unchanged (consume-time transform
  over the persisted top-2 distances, per the biosphere_conv ruling).
