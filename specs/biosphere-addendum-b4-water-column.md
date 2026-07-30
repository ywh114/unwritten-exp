# Biosphere Addendum B4 — Water-Column Attributes

Status: DRAFT v0.1, awaiting owner review. Amends the derived-products
table of `unwritten-flora-engine-rfc.md` §2; extends B2 (productivity)
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
4. **`marine_snow` (12,H,W)** — detrital flux at the bottom:
   overlying surface productivity × `exp(-bathymetry / SNOW_REF_M)`,
   SNOW_REF_M ≈ 800 (remineralization on the sinking path). Shelf
   bottoms under upwelling therefore read high — correct, the sinking
   path is short. Zero on land.
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

## Interplay with B2 / B3

- B2 `marine_productivity` is the SURFACE (photic-layer) field —
  unchanged. The water column below is fed by B4's snow, not by the
  surface value directly.
- B3 ground keeps its own underwater derivation (depth + current
  energy); it reads the same `w_elev` bathymetry but does not depend on
  this pass. Zone/class agreement is expected, never enforced.
- OMZ (oxygen minimum zones): deferred — no consumer.

## Datapack layers

- `depth_zone`: categorical (5 classes).
- `benthic_food`: continuous, monthly, ocean mask.
- `photic_depth`: continuous, ocean mask.
- `bottom_temp_c`: tooltip only (not an overlay layer).
- Vent points: `depth_m`, `depth_zone` attrs. Spring points: `kind`.

## Implementation notes

- New self-contained module `exp/k14_flora/world/water.py`, called from
  `derived.build()` AFTER `marine_productivity` (snow reads it
  in-process) and before `build_pack`.
- Factor the plume source/advection out of `marine_productivity` into a
  shared helper — photic depth reuses it. No other refactor.
- Memory: ~2 monthly + ~4 annual anchor fields — negligible.
- Tests: bathymetry consistent with `e_norm` below sea level; snow
  monotonically non-increasing with depth along any column transect and
  zero on land; zone boundaries; vent halo exceeds snow at the vent and
  decays away; spring kind flags; determinism.

## Out of scope

Volumetric grid / 3D advection, thermocline dynamics, OMZ, lake
stratification and turnover, ice-melt holes over sublacustrine springs,
L1 underwater traversal.

## Open questions for owner

1. Springs: keep + flag (proposed) vs. mask out of standing water.
2. Zone boundaries 200 / 1000 / 4000 / 6000 — OK?
3. Draft constants: SNOW_REF_M 800, TBOT_REF_M 500, oasis productivity
   0.8, halo radius 2–3 anchor cells.
