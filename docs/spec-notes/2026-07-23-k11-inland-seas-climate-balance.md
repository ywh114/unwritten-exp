# K11 — inland seas, two-layer wind, real-world precipitation (2026-07-23)

Design decisions from the post-halfway review round. See
`2026-07-23-k11-units-wwf-biomes.md` for the units doctrine (never tune
units or classifier thresholds; tune generation).

## Inland seas are not abyss
- Enclosed below-sea basins sat on oceanic plate bases (base 0.16–0.22 →
  ~1.9 km deep) and flooded to their rim sill — a phantom surface
  hundreds of meters ABOVE sea level, which then saturated the lake
  shading ("enclosed oceans look very dark blue"). Real inland seas are
  shallower than open ocean (Great Lakes 200–400 m, Caspian ~1 km max
  vs 4 km abyss).
- Fix, three parts (plates/hydrology/render):
  1. Enclosed basin floors compressed toward the waterline BEFORE fault
     signatures (×0.35), so rift lakes (Baikal/Tanganyika) keep tectonic
     depth while ordinary basins bottom at a few hundred meters.
  2. `_cap_inland_seas`: any filled basin whose floor dips below sea
     level is capped AT sea level — per whole filled component, so
     surfaces stay equipotential. The water balance is judged on the
     capped surface. Accepted inland seas become ENDORHEIC terminals
     (rivers flow in, nothing flows out — Caspian); rejected basins
     keep the flood surface so their wetland flats still drain through
     to the ocean (a capped-but-dry basin would otherwise trap flow).
  3. Lakes render on the SAME bathymetric gradient as the ocean (bed
     elevation), just a fresher tint — not "darken with true depth".
- Side effect: capping strands interior bumps as speck islets (blocky
  anchor-cell artifacts). `_submerge_islets` sinks land components ≤ 8
  cells fully enclosed by a lake into it at its surface (sandbars/
  guyots); larger islands stay.

## Two-layer wind (Q2)
- User's prompt: "Middle East has deserts because layers." A single
  terrain-blocked flow cannot park dry air over warm seas.
- LOW layer: unchanged (terrain-deflected, monsoon, carries moisture).
- HIGH layer (`WindLibrary.sample_high`): zonal-dominant (×1.4), shares
  the low layer's random gyre phases (same systems aloft), NO land–sea
  breeze, NO terrain interaction.
- The subtropical-high band (lat ~0.72, migrating ±0.05 seasonally)
  seeds a subsidence field S advected by the high layer
  (`_subsidence`: band-recharged, slowly decaying, semi-Lagrangian) —
  chosen over a static mask ("whatever is more realistic").
- Drying in `_advect`: recharge ×(1−0.65·S), rain-out ×(1−0.75·S).
- The static aridity belt dropped 0.40 → 0.20: it is now only the
  mean-state background; structure comes from the advected highs.

## Real-world precipitation level (G2)
- The adaptive gain pinned land-mean P at 0.34 normalized = 136 mm/month
  ≈ 1630 mm/yr — ~2× the real land average (~65–80 mm/month). Effects:
  every cell matched wet-forest prototypes, grassland (25 mm/month
  prototype) could never win, the flooded-grassland override (≥150
  mm/month) fired routinely.
- Pin lowered to 0.19 (~76 mm/month, `_TARGET_LAND_P`), plus one
  corrective gain rescale so the pin holds despite [0,1]-clip
  saturation on windward spikes.
- Cold-water evaporation steepened to real Clausius–Clapeyron-ish
  ratios: ~0 at −3 °C, ~20% at 0 °C, full by +10 °C (was ~40% at 0 °C).

## Temperature profile and biome balance
- Taiga prototype was the Siberian extreme (Jan −20, annual −2): it won
  wherever winters dropped below ~−10 °C — unrealistic. Retargeted to
  the boreal-belt centroid (Jan −15, Jul +15). Temperate broadleaf got
  continental winters (Jan −2: Beijing/Chicago are broadleaf too).
- Climate profile knobs (t_span, t_pow, t_amp) swept across seeds
  1/3/5 against land biome shares; default now (0.90, 0.40, 0.09):
  ice+tundra ≈ 13–18% (upper third), taiga ≈ 13–19%, temperate
  broadleaf+conifer ≈ 20–33%, deserts appear (~5–12%, realistic).
  Northern-positioned continents (seeds 3, 5, 7) stay taiga-heavy —
  that is geography, not a knob failure.

## Loading screens are live (G1)
- `LoadingSink` is passed down the demo build; each `load_NN.png` lands
  as its stage completes (climate intermediates via a `stage_hook`
  inside `build_climate`), with `load.png` repointed per stage (verified
  by polling the symlink during a build). `render_loading` remains the
  batch path for the re-render subcommand; both share `load_stage_draw`.

## Delivery anti-aliasing (G4)
- Bicubic delivery patches are only C1; their 4×4 block seams read as a
  grid in flat areas and in the hillshade. One gentle K1-seeded rotated
  fbm pass (±30 m, base cell 12 px) on the delivered elevation breaks
  the regularity; masks/biomes re-derive from the noised field so
  coasts/lake edges get organic wiggle. Anti-aliasing, not geology:
  sub-cell terrain FORM remains refinement's job.
- fbm octaves also clamp lattice spacing at ≥ 2 cells (Nyquist) — finer
  lattices alias into per-cell white speckle that upscales as a block
  grid — and every octave samples in its own golden-angle-rotated frame
  (separable value noise otherwise streaks along the grid axes).
