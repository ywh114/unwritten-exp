# Biosphere Addendum B4 — Water-Column Attributes

Status: v0.1 IMPLEMENTED 2026-07-30 (K14 `world/water.py` + K11 trench
exaggeration; draft rulings and constants applied as written —
owner-tunable). Amends the derived-products table of
`unwritten-flora-engine-rfc.md` §2; extends B2 (productivity)
and B3 (ground, underwater).

## Vocabulary (owner rulings, 2026-07-30)

- Ocean cells get stratified **attributes**, not volumetric layers.
  The 3D pelagic grid is **rejected**: all machinery stays `(H,W)` /
  `(12,H,W)`. Deep water is predictable (dark, ~2–4 °C); the spatial
  variation that matters already lives in the 2D fields we have (SST,
  bathymetry via `w_elev`, surface productivity, upwelling). Everything
  a consumer needs reads as *(depth zone, bottom temperature, food
  flux)*.
- **Marine snow** = the detrital food flux reaching the bottom —
  the deep sea's productivity field. Deep consumers read marine snow
  (and vent benthos), NOT the surface productivity above them.
- **Benthic food** = the composite bottom-food field: marine snow
  everywhere, overridden locally by vent chemosynthesis.

## Products

All at anchor resolution, delivered and packed like the other K14
products. Ocean cells only unless stated.

1. **`bathymetry_m` (H,W)** — real meters below sea level from
   `elev_m(w_elev, sea)` on ocean/sea cells. NOTE: `h_depth` is a
   lakes/rivers field (constant 1.0 sentinel on ocean) — this pass must
   NOT read it for ocean depth.
2. **`photic_depth_m` (H,W, annual)** — how deep light reaches:
   clear-water base (≈150 m open ocean, ≈60 m shelf), reduced by
   turbidity — river-plume concentration (factor the plume computation
   out of `marine_productivity` into a shared helper) and the surface
   bloom (overlying productivity). Bounded [10, 250] m. Feeds the
   `bottom_lit` flag (below); consumers (benthic algae, seagrass,
   visual hunters) read the raw value.
3. **`depth_zone` (categorical, per ocean cell)** — by bathymetry:

   | zone | bottom depth |
   |---|---|
   | epipelagic bottom | 0–200 m |
   | mesopelagic bottom | 200–1000 m |
   | bathypelagic bottom | 1000–4000 m |
   | abyssal bottom | 4000–6000 m |
   | hadal | >6000 m (reserved — unreachable at today's DEPTH_MAX_M) |

   Plus a derived boolean **`bottom_lit`** = bathymetry <
   photic_depth. Complementary to the aquatic classes (shelf/upwelling
   describe surface water; zones describe the column below it).
4. **`marine_snow` (12,H,W)** — detrital flux at the bottom, in two
   steps:
   a. **Vertical settling**: overlying surface productivity ×
      `exp(-bathymetry / SNOW_REF_M)`, SNOW_REF_M ≈ 800
      (remineralization on the sinking path). **Currents advection of
      snow is rejected at L0** (owner ruling): our currents are surface
      currents — advecting deep snow by them would be confidently
      wrong; shelf snow sinks in days (sub-cell drift); abyssal snow
      is too smooth to benefit.
   b. **Downslope redistribution** (owner ruling: this is K14 scope —
      it is what makes deep benthos possible): a slope-gated fraction
      of the deposited snow exports downhill each step, routed over
      bathymetry with the same accumulation pattern as terrestrial
      `h_accumulation`, concentrating at canyon mouths and slope bases
      — deep-sea fans become benthic oases (Monterey-style), which is
      where much real abyssal biomass sits. Routed on the annual-mean
      vertical snow once; the monthly planes scale by their month's
      vertical fraction (the deep sea has no seasons of its own).
   Zero on land. Shelf bottoms under upwelling read high — correct,
   the sinking path is short.
5. **`bottom_temp_c` (H,W, annual)** — shelf bottoms track annual-mean
   SST, damped; deep bottoms tend to ≈2 °C:
   `T_bot = T_DEEP + (SST_ann − T_DEEP) · exp(−bathymetry / TBOT_REF_M)`,
   T_DEEP = 2.0, TBOT_REF_M ≈ 500. One annual field — the deep ocean
   has no seasons at L0 granularity. Tooltip material, not an overlay.
6. **Vent benthos** — vent points gain `depth_m` and `depth_zone`
   attributes. Around each ACTIVE vent (the B3 ground pass already
   rolls dormancy per point — reuse that roll, never the raw fault
   field), a decaying chemosynthetic halo (2–3 anchor cells) at a fixed
   oasis productivity (~0.8 draft). **`benthic_food` (12,H,W)** =
   `max(marine_snow, vent_halo)` — the consumer-facing composite; the
   two raw fields stay in the npz for analysis.
7. **Spring classification (owner question 2026-07-30)** — hot springs
   currently spawn on lake (6/40, seed 1) and river (10/40) cells
   because the vent extractor treats every non-ocean cell as land.
   Emergent, not designed — but sublacustrine springs (Yellowstone
   Lake, Baikal) and thermal streams are real. **Proposal: keep +
   flag.** Points carry `kind`: `terrestrial` / `sublacustrine` /
   `riverine`. No thermal modeling at L0 — no lake-ice melt holes, no
   warmed water; the flag is for L1 and fauna.
8. **`water_ph` (H,W, annual)** *(revision 2026-07-30, added alongside
   B3's pH column)* — the column's pH, distinct from B3 `ground_ph`
   (the bed/pore reading). Ocean: 8.1 at the surface easing to 7.8 with
   depth (old deep water) on the fixed 4000 m reference, RE-DERIVED at
   delivery res from delivered bathymetry (the depth-zone ruling —
   bilinear across the coastline leaves zero holes). Fresh (lakes and
   rivers): bed- and catchment-driven — `0.6 × bed pH (B3 class rows) +
   0.4 × surrounding land-soil mean − 1.3 × peat share`, the catchment
   proxied by a 2-anchor-cell box window; humic blackwater means bog
   drainage reads pH 4.5–5.5, not the bed's ~7. Zero on land.

## Interplay with B2 / B3

- B2 `marine_productivity` is the SURFACE (photic-layer) field. The
  water column below is fed by B4's snow, not by the surface value
  directly — and the two fields are **never summed by a consumer**:
  they answer different questions for different feeders (surface
  grazers vs. benthos). High values at the same cell (Peru-margin
  pattern: rich surface over rich benthos) are consistency, not double
  counting.
- **Nutrient-return loop** (owner ruling 2026-07-30: upwelled
  nutrients were deposited as snow somewhere upstream — the loop is
  spatially explicit). One deep-routing pass, computed annually:
  - **Sources**: polar bottom-water formation — cold shelf cells with
    sea-ice cover (brine-rejection proxy).
  - **Routing**: hydrology-style flow routing over pit-filled
    bathymetry from sources toward upwelling cells, accumulating the
    deposited snow inventory along the path. Deep flow is quasi-steady
    — annual, not monthly.
  - **Effect**: the upwelling nutrient bonus in `marine_productivity`
    is multiplied by a bounded inventory modifier, clipped to
    [0.5, 1.5]. The B2 scale stays anchored, but upwellings fed by
    rich polar seas out-produce ones fed by poor ones — world history,
    not another local proxy. Full mass-balance bookkeeping
    (subtracting snow from the surface as it sinks) is **rejected**:
    no consumer, and it makes the scale untunable.
- B3 ground keeps its own underwater derivation (depth + current
  energy); it reads the same `w_elev` bathymetry but does not depend on
  this pass. Zone/class agreement is expected, never enforced.
- OMZ (oxygen minimum zones): deferred — no consumer.

## Datapack layers

- `depth_zone`: categorical (5 classes).
- `benthic_food`: continuous, monthly, ocean mask.
- `photic_depth`: continuous, ocean mask.
- `bottom_temp_c`: tooltip only (not an overlay layer).
- `water_ph`: continuous, "water" mask (ocean|sea|lake|river), same
  acid→alkaline ramp as B3's `ground_ph`.
- Vent points: `depth_m`, `depth_zone` attrs. Spring points: `kind`.

## Implementation notes

- New self-contained module `exp/k14_flora/world/water.py`, called from
  `derived.build()` and before `build_pack`. TWO-PHASE marine
  computation: provisional `marine_productivity` (local rise-strength
  bonus) → water column (snow, downslope routing, deep-return
  inventory) → final `marine_productivity` (inventory modifier applied
  to the upwelling bonus). The provisional field is never persisted.
- The two routings share one pit-filled bathymetry and one flow-dir
  pass (hydrology.py's pattern, second home); compute once, use for
  both the downslope redistribution and the deep-return inventory.
- Factor the plume source/advection out of `marine_productivity` into a
  shared helper — photic depth reuses it. No other refactor.
- Memory: ~2 monthly + ~5 annual anchor fields — negligible.
- Tests: bathymetry consistent with `e_norm` below sea level; snow
  monotonically non-increasing with depth along any column transect
  (pre-routing) and zero on land; downslope routing concentrates snow
  at slope bases; inventory modifier bounded and moves upwelling bonus
  with polar productivity (synthetic: rich-pole world > poor-pole
  world, same rise field); zone boundaries; vent halo exceeds snow at
  the vent and decays away; spring kind flags; determinism.

## K11 prerequisite — trench exaggeration

Measured maxima (seeds 1–3): 4250 / 5153 / 4350 m — **hadal is
unreachable** (`elev_m` bottoms out at exactly −6000 m at `e_norm=0`),
abyssal is 0.5–2.4 % of ocean, and the modal deep floor sits at
bathypelagic depths (3000–4000 m) where Earth has abyssal plains. The
plates trench signature is only −0.22/−0.20 normalized (OO/OC
convergent), further eaten by convergence clipping and coastal
segmentation. Work item, sequenced BEFORE this pass (zones must be
computed on final bathymetry):

- Deepen the OO/OC convergent trench signature (~2–2.5×, sharper
  profile) so active subduction trenches breach 6000 m; let `e_norm`
  go slightly negative with `elev_m` extended piecewise below zero.
  Consequence: **hadal = trench-only**, and trenches are exactly where
  the vent extractor already looks — hadal vents fall out for free.
- Keep Earth-standard zone boundaries; after regen, check the zone
  histogram — if abyssal is still <5 % of ocean, nudge the oceanic
  base floor down ~500 m as a separate, smaller tune.
- Full regen + re-verify (hydrology's deep-trench water-fill rule
  likes deeper trenches, but coastlines shift downstream).

## Out of scope

Volumetric grid / 3D advection, thermocline dynamics, OMZ, lake
stratification and turnover, ice-melt holes over sublacustrine springs,
L1 underwater traversal.

## Open questions for owner

1. Springs: keep + flag (proposed) vs. mask out of standing water.
2. Zone boundaries 200 / 1000 / 4000 / 6000 — OK? (Kept Earth-standard
   in the spec; the trench-exaggeration regen may shift the histogram.)
3. Draft constants: SNOW_REF_M 800, TBOT_REF_M 500, oasis productivity
   0.8, halo radius 2–3 anchor cells, inventory modifier clip
   [0.5, 1.5], trench signature ~2–2.5× current.
