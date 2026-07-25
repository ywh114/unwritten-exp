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
- The SAME speckle is reborn at delivery: the waterline re-derivation
  (interpolated fields + fine noise, 40 m depth threshold) flips
  shallow bed bumps inside a lake back to land — blocky holes inside
  LK-class lakes (seed 6 had 24). Fix in `deliver.upscale_world`: the
  eroded anchor lake interior is always water (the boundary band alone
  re-derives from fields), and `_fill_lake_holes` fills enclosed land
  specks ≤ 64 delivered cells — the anchor's submersion rule applied
  to delivery artifacts. Verified: 0 enclosed holes.
- RECTANGULAR LAKES (seed 6): rejected basins kept their priority-flood
  surface w0 (needed for through-drainage), and delivery re-derived
  waterlines from it — the whole dry basin read as "water", so the
  near-lake confinement became load-bearing and clipped small lakes to
  a Chebyshev-square front that ignores terrain. Fix: hydro returns
  TWO surfaces — `w` (what is actually WET: lake cells at lake level,
  everything else at terrain) and `w_route` (what flow routes on:
  rejected basins keep w0). Delivered waterlines now follow the true
  elevation contour; small lakes are organic ponds instead of
  rectangles, and no phantom water exists downstream of hydrology.

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

## Temperature profile and biome balance- Taiga prototype was the Siberian extreme (Jan −20, annual −2): it won
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

## Delivery anti-aliasing (G4) — tried and REVERTED
- Bicubic delivery patches are only C1; their 4×4 block seams read as a
  grid in flat areas and in the hillshade. A gentle K1-seeded fbm pass
  (±30 m) on the delivered elevation was added to break the regularity
  — and removed the same day: it did NOT de-grid coastlines (its
  actual goal), and by flipping shallow lake beds across the waterline
  it caused/amplified the delivered lake speckle that then needed the
  ad-hoc `_fill_lake_holes`. The hole fill and the eroded-core interior
  stay (they are correct against interpolation wiggle alone); the
  noise is gone. Grid-aligned coasts/elevation at delivery remain an
  OPEN issue (options: shade-space smoothing, or leave to refinement).
- fbm octaves also clamp lattice spacing at ≥ 2 cells (Nyquist) — finer
  lattices alias into per-cell white speckle that upscales as a block
  grid — and every octave samples in its own golden-angle-rotated frame
  (separable value noise otherwise streaks along the grid axes).

## Void margin (border-kissing land)
- The reserved border ring (base pinned down, no fault signatures) was
  not enough: seamount detail could breach inside it, and islands in
  adjacent fine cells settled 1-4 px from the map edge.
- Two layers now: a smooth taper pulls the outermost 2 anchor cells
  below the surface (guaranteed ocean moat behind the 1 px rock rim),
  and the whole reserved ring is hard-submerged against breaching
  seamounts. Land may approach the border but always across water.
- Landmark legend (user): 4 peaks (not 5), DP moved after the LK
  entries and reported negative (DP -4058M), matching LW.

## Meridional circulation reframe (user, same day)
- The random-bearing zonal jet + bolted-on trades was replaced by a
  band-organized MERIDIONAL circulation: 2-3 semi-stable bands of
  north-south flow with random sign/strength/center/width (one-time
  draws), per-snapshot angle wobble, no zonal jet. Not an Earth clone:
  convergence/wet belts and divergence/dry belts land wherever the draw
  puts them. The two OUTERMOST cells are constrained equatorward
  (polar surface outflow -> dry polar high; trades -> equatorial
  convergence) — free signs left half of all worlds with a desert
  equator and the pole as wettest zone.
- Subsidence highs park at the flow's ACTUAL divergence zones
  (dvy > 0); the static aridity belt was deleted (multiplier kept as
  1.0 for the gain-pin interface).
- Moisture thermodynamics: recharge AND rain capacity scale with
  temperature (same Clausius-Clapeyron-ish curve) — advected moisture
  wrings out on entering cold cells (polar-front snow; the frozen rim
  is no longer the wettest zone). Rain falls over water too (baseline
  rate everywhere, oro ~ 0 over flat water), and rain depletes the
  parcel everywhere — ocean rain wrings the flow before landfall.
- Moisture concentrates under convergence (bounded x0.6-1.8 per step),
  which is what makes ITCZ-class wet belts emerge; divergence dilutes.
- Wind circulates heat: one damped advection pass per T snapshot
  (30% upwind blend) — maritime moderation, interiors keep extremes.
- T profile: equatorial plateau (soft-min cap ~27 degC, no 35 degC
  rim); equatorial seasonal swing reduced (big swings drive monsoon
  reversal and kill year-round rim rain).
- Moist-forest prototype moved from Singapore-flat-200 (aseasonal
  extreme) to Amazon/Congo modal (26.5 flat, 160+-70 seasonal).
- Result (seed 3): bimodal P structure (storm track lat 0.2-0.3 ~120,
  ITCZ lat 0.9 ~135 mm/mo), pole dried (67), tropical belt present
  (moist forest token-rare, conifer/dry/savanna solid), deserts park
  at divergence zones. Rainforest scarcity is now mostly prototype
  arithmetic (160 mm/mo base vs ~130 deliverable).

## Geographic classes removed from the climate match (user, same day)
- Root cause of the flooded-grassland plague: it was a climate
  PROTOTYPE, so any warm cell with a Pantanal-like flood pulse
  classified as flooded grassland regardless of geography (seed 3:
  3.4% of the world). Same for the mangrove proto. The vector match is
  now CLIMATE-ONLY — flooded grassland, mangrove, rock and ice, lake
  and ocean are excluded from the prototypes and exist purely via
  geographic overrides / water masks.
- Flooded grassland override tightened to special-place criteria:
  directly water-adjacent (dilate 1, not 2), alt < 10 m, wettest month
  >= 220 mm. Seed 3: 36040 -> 37 cells (0.004% — Pantanal-rare, as it
  should be).
- Mangrove: frost-free (T_cold >= 18) AND (tidal land bordering the
  sea, alt < 10 m) OR (sea fringe next to land, bed above -8 m).
  Diag showed the bed drops from -3 m straight to abyss (no -3..-15 m
  cells at all), so a depth window alone could not thin it — the
  adjacency-to-land clause does. Rivers no longer carry mangroves
  inland, and the modal filter now runs BEFORE the overrides so it
  can neither erase them nor grow them past their criteria. Seed 3:
  173418 -> 1031 cells, all coastal; seed 1: mangrove returned (1824).
- render_world repaints mangrove cells over the bathymetry so
  shallow-sea stands stay visible.
- 254 tests green; seeds 1 and 3 regenerated, verdict PASS.

## Montane/tundra altitude split (user, same day)
- The two elevation-confused zonal classes are split at the montane
  altitude line (800 m), matching WWF semantics (WWF lumps ALPINE
  tundra into montane grasslands):
  - classified tundra ABOVE the line -> montane grassland (alpine
    tundra is montane, not arctic)
  - classified montane grassland BELOW the line -> second-nearest
    climate prototype (the cold/small-swing montane signature also
    fits subpolar maritime lowlands, which are not montane anything)
  - `_Acc.classify2` now returns (nearest, second-nearest) via one
    argpartition; `classify()` keeps the old interface.
- Seed 3 polar-lowland diag (pre-fix): mean T -8 degC, swing ~14 —
  classified 69 rock and ice (polar summer ~-1 => T_warm < 0), 55
  montane at sea level, 1 tundra. Post-fix tundra is strictly lowland
  (q95 = 267-764 m both seeds) and montane strictly highland (q05 =
  ~1000 m).
- Tundra is now RARE (30-1150 cells): it is squeezed between the ice
  cap (polar summers sit near/below 0 degC) and taiga. That is the
  invented-climate temperature regime, not the classifier — deferred.

## FUTURE: earth-patch "realistic mode" (user, same day — NOT NOW)
- Treat the map as a 1024x1024 km patch of the real Earth (northern
  hemisphere) and generate TEMPERATURES accordingly (latitude bands,
  realistic gradients), while winds stay random/semi-stable as now.
- Must be an OPTIONAL mode alongside the current invented climate,
  not a replacement.

## Realistic (earth-patch) mode — IMPLEMENTED (user, same day)
- `build_climate(realistic=True, center_lat=45.0, shrink=4.0)`: the map
  is a northern-hemisphere patch of the real Earth; row -> latitude
  from center_lat and a planet shrink x smaller (span = 1024 km *
  shrink / 111.19 deg), then zonal-mean Earth anchors (annual mean +
  seasonal half-swing by latitude, interpolated) replace the invented
  profile (`_lat_profile`, climate.py). Winds stay random in both
  modes; invented mode is untouched and remains the default. CLI:
  `demo --realistic [--center-lat D] [--shrink S]`; mode recorded in
  the dump's `stats.climate_mode`.
- Default center 45 degN at shrink 4 spans ~27..63 degN: subtropics /
  temperate / taiga in one map (tundra/ice only on high ground).
  Started at 53.5, then 50; each step equatorward widened the warm
  band, which was getting eaten by mid-latitude highlands.
- Bugs found on first light: (1) map size passed to the latitude
  mapping used the COARSE grid rows x cell_km (512 km instead of
  1024), halving the span; (2) the argparse default lagged the
  function defaults, so a center change silently did nothing.
- Verified on seeds 11/12: north rim ~-9 degC annual, south rim ~+20;
  latitude bands read clearly on world.png; seed 11's southern plateau
  (2000 m) correctly goes montane/taiga (Tibet effect) — warm-biome
  scarcity on a given seed is terrain, not the profile.
- Slow-test invariant "only standing water is a water biome" updated:
  mangrove legitimately stands on shallow sea (tidal flats) since the
  azonal-biome rework.

## Wikipedia biome palette (user nit, same day)
- The 15 terrestrial classes now use the Wikipedia / Global-200 legend
  colors (Olson & Dinerstein scheme, e.g. taiga #2CA05A, montane
  #C6AFE9, mangrove #D400AA, desert #FFF6D5). Water masks keep the
  house blues. Palette lives in BIOMES (biomes.py); legend/world.png
  pick it up automatically.

## Palette reverted + center 40 (user, same day — supersedes the
## Wikipedia-palette note above)
- The Wikipedia scheme popped too much; back to the house palette with
  the rule "lush = dark green, arid = sand, NO BROWNS": montane
  grassland (180,140,110) -> sage (150,170,115), mediterranean scrub
  (180,160,85) -> olive (150,170,80). Everything else unchanged.
- Realistic-mode default center_lat 45 -> 40 degN (span ~22..58 degN):
  the arctic band leaves the map entirely; alpine (montane / rock and
  ice) now exists by default only on large mountains, which the user
  prefers. Result on seeds 11/12: green-dominated worlds, taiga ~20%,
  montane 5-9%, broadleaf/conifer/grassland all present.

## Salinity classifier + world.png params panel (user, same day)
- `classify_salinity` (hydrology.py): 0..1 salinity per water cell,
  decided at the anchor grid (relational — per water body, never
  recomputed after upscale). Ocean 1.0; rivers 0.0 with a brackish
  0.25 estuary band 8-adjacent to the sea; lakes EXORHEIC-fresh
  (drainage walk from the max-accumulation cell reaches the ocean) vs
  ENDORHEIC-salted (walk terminates in the basin) with the level
  falling as log of the flushing ratio inflow/area — a Volga-scale
  inflow keeps a terminal lake brackish (Caspian ~1.2%), underfed
  terminals go full salt (Aral/GSL). Delivered as `salinity`
  (carried, re-masked; estuary band re-derived pointwise), persisted
  as h_/d_salinity. Render: saline lakes tint the bathymetry toward
  pale salt-pan pink in proportion to salinity.
- Seed 11: 1163 fresh / 23 brackish / 472 saline lake cells, 37
  estuary river cells. Synthetic test: open bowl fresh (0.02),
  below-sea enclosed bowl salted, ocean 1.0.
- world.png top section now logs generation parameters and climate
  trivia (climate mode + earth-patch span, land annual T min/max/mean,
  land P mm/yr) and is TWO-COLUMN for headroom when the freshwater/
  marine biome classes land. Bitmap font lacks '+' and '[', so the
  lines avoid them.

## Salinity in real units + landmark key (user, same day)
- Salinity is g/kg end-to-end (units.SALINITY_OCEAN_GKG = 35):
  exorheic lakes 0.5, endorheic 220*exp(-flushing/120) with NO hard
  caps (user design rule: no hard caps, no magic constants) — terminals
  run saltier than the sea (test asserts > 35), Volga-scale inflows
  flush toward fresh. Estuary salinity is a mixing ratio on the
  river's own discharge: 35 * Q_half/(Q_half + Q), Q_half = 50
  upstream cells — big rivers flush their estuary, tidal creeks stay
  nearly seawater. Render tint weight 1 - exp(-gkg/60), also unbounded.
- world.png legend: world type prominent under the seed (EARTH-PATCH
  40N X4 SPAN 22-58N / INVENTED CLIMATE); stats grouped two-column
  (geography left, measures + climate trivia right); MAX STREAM ORDER
  dropped (always 3, uninteresting); LAND T/P labeled AVG; landmarks
  keyed ONE PER KIND (all markers still drawn).
- Landmark set finalized at 6 kinds: top 5 peaks (back from 4), 2
  largest lakes, 2 deepest ocean points (DP1/DP2, spaced, partition of
  the deepest 2000 candidates), 2 lowest terrestrial points, 3 river
  mouths, and the new SL1 — saltiest lake by component-mean salinity,
  only marked when genuinely salt (> 10 g/kg).

## Seeded center-lat wiggle (user, same day)
- `--center-lat` is now optional: unset means 40N + a per-seed wiggle
  (`resolve_center_lat`, own K1 substream — climate draws untouched):
  triangular draw in +-8 deg with a LEAKY cap at +-5 (slope 0.3, no
  hard clamp), so most worlds center 35..45N and a rare one leaks
  past. The EFFECTIVE center is what lands in stats.climate_mode and
  on world.png (seed 11 -> 37.7N, seed 12 -> 39.4N). Explicit values
  pass through untouched.
- SALT LAKES line removed from the world.png stats — SL1 covers it.

## Landmark merge + wiggle calibration (user, same day)
- SL folds into LK when both point at the same component (one marker,
  e.g. seed 3: "LK1 23217KM2 213 G/KG"); separate SL1 otherwise.
- Center-lat wiggle rescaled to a +-12 triangular draw (leaky cap at
  +-5 slope 0.3): measured mean abs deviation 2.98 deg (user target
  ~3), max leak ~7.

## Inland seas, HAND floodplains, meanders (user, same day)
- INLAND SEA class: saline (> 10 g/kg) AND >= 5000 km^2 (Aral-scale
  class line, hydrology.classify_salinity sets sea_mask). Drawn on the
  OCEAN bathymetric ramp (a Caspian is a piece of ocean that lost its
  outlet), never salt-tinted; SE landmark kind replaces its LK entry
  and always carries the salinity ("SE1 23217KM2 213 G/KG", seed 3).
  Salt-fold rule extended: saltiest-in-LK merges labels (no stacked
  markers); saltiest-is-sea already has it.
- HAND (height_above_drainage, hydrology.py): per-cell drop to the
  water surface its flow path first reaches, downstream-first over the
  routing surface. Flooded-grassland override now reads the floodplain
  (HAND < 10 m) instead of a fixed dilate ring — Pantanal is a
  floodplain, not "land near water". Carried to delivery as `hand`.
- Dead-end river diagnostic (user observation): VERIFIED CLEAN on
  seed 11 — all river chains exit to ocean (37) or lake (99), zero
  dry endings; 26/1356 cells absent from the complex polylines are all
  isolated single-cell rounding gaps, not missing rivers. Rivers that
  visually vanish are entering standing water (the line submerges at
  the waterline by design).

## River rendering system (final form, user-reviewed same day)

The knot saga is consolidated here; the fix-by-fix chronology was
noise. Root causes, in the order they were actually proven (anchor
ASCII dump + hydrology.png FIRST, render last):

1. Sine meander applied to edges shorter than one wavelength -> ball
   of yarn. Gate: meander only when edge length >= 2 lambda.
2. The corridor clump was NOT meander: a 1-cell out-and-back spur in
   the anchor flow path (flat-BFS routing artifact), magnified x4 and
   stamped thick, plus genuinely dense topology (4 edges in a 4-cell
   confluence pocket). Fixed ONCE by `_simplify` (Ramer-Douglas-Peucker,
   tol ~1.25 cells) on the render path. The corridor density is real
   and no render pass should hide it.

The render stack (frozen by the user — "no more fixes"):
- grid-true complex + K9 audit: the real non-intersection guarantee.
- `_simplify` (RDP): removes anchor spur artifacts.
- chaikin + width-scaled jitter (mag 1.4 / width class): de-gridding
  (the original diagonal-lock complaint); wide rivers stay smooth.
- width taper: each edge ramps from its upstream course's width
  (feed_q) — a river widens ALONG its course, never jumps a class at
  an edge boundary ("no wide rivers from nowhere").
- meander, gated three ways (length >= 2 lambda, valley slope < 2
  m/km from path max-min drop, not marsh): lam ~ 10 width-classes
  (Leopold), belt ~ 2 widths.
- self-avoidance (user-required "by design"): stamping tracks the
  owner edge; a candidate center that hits its own old path or
  another edge falls back toward the base path (1, .5, .25, 0) with
  4-point hysteresis (no sawtooth); the last 4 points before an
  edge's end node are a JOIN ZONE — confluences are the only legal
  contact. Edges stamp wide-first so creeks avoid main stems.
- phantom-flood cells (rejected-lake wetland flats) stamp width 1:
  marsh channels anastomose thin (Okavango/Biebrza) and marsh edges
  do not meander (no valley for the sine to fit into).

hydrology.png is the river-debug view (network at a glance); node
dots are colored by role: source green, confluence orange, outlet
violet.

## Gorge carving + aquatic biomes + ocean currents (user, same day)
- `carve_gorges` (hydrology.py): a river is a VECTOR — it does not
  climb; when its momentum (largest inflow's arrival direction) points
  into HIGHER LAND and the flow bends away, that cell is a sill wall.
  Multi-pass (reflood -> notch -> reflood): erode the wall
  asymptotically toward the river's own level, 3 passes, accumulation
  >= the width-2 line. Dry land only — standing water is never
  eroded. Seed 3: 216 notches (median 32 m, max ~2 km gorges).
- Aquatic biome LAYER (aquatic.py, separate from the terrestrial map
  — a water cell has a class AND a climate zone): WWF freshwater
  (lakes: inland sea / salt / large / polar / montane / tropical /
  temperate; rivers: delta / coastal / floodplain / upland / polar /
  montane / xeric) and neritic marine (polar / temperate / tropical
  shelf, coral, temperate+tropical upwelling). Relational per water
  body at the anchor, carried to delivery by nearest-value spread.
  world.png: water recolored toward class colors over the bathymetry,
  rivers in class colors, legend sections TERRESTRIAL / FRESHWATER /
  MARINE (compact rows, sub-8-cell classes hidden).
- Ocean currents (currents.py, spawned right after elevation): 2-3
  gyres in deep water (random rotation/strength, curl of Gaussian
  stream functions, shelf-damped). `advect_sst`: the latitude baseline
  transported semi-Lagrangian along the flow with thermostat
  relaxation, deep-cold mixing where the stream RISES (upwelling),
  3 coarse diffusion passes. Climate reads SST over ocean (damped
  seasonal swing); aquatic reads the rise field — upwelling = top
  decile of shelf rise (world-relative), coral excluded there.
- temperature.png now shows swirled SST structure instead of a flat
  latitude gradient over water.

## Monthly currents (user, same day)
- SST is now computed PER MONTH: the baseline carries the (maritime-
  damped) seasonal swing, and each gyre's strength breathes +-30%
  with a per-gyre K1-drawn phase (`velocity_field(currents, month)`;
  normalization against the annual-mean max speed so speeds stay
  comparable). 12 advections ~= +12 s build time. Seed 11: ocean
  mean T swings 0.63 -> 0.75 (Jan -> Jul), Jan/Jul pattern
  correlation only 0.38 — the swirls visibly shift.
- advect_sst now takes (u, v, rise) directly; build_currents stores
  the gyre list (center/sigma/amp/phase), vmax, depth_m, ocean_mask.

## Lowland reshape: t^2 remap of above-sea elevation (user, 2026-07-24)
- Complaint: median land altitude ~2.1-2.7 km (seeds 1/3/11) — a
  plateau planet; temperate lakes nearly absent (need fresh + <800 m).
  Goal: lowlands near ~1 km median, peaks still reaching 4-5 km.
- Fix: a monotonic t^2 remap of the above-sea component at the end of
  `build_elevation` (after the border taper and the rim-plate pin):
  2.4 km -> ~1 km, 4 km -> 2.7 km, 5.5 km -> 4.9 km. Monotonic, so
  flow topology / fill / drainage are unchanged by construction; only
  gradients and altitude-conditioned downstreams shift (lapse rate,
  800 m montane lines, 2500/4500 rock-and-ice gates) — intended.
- Verified (seeds 1/3/11): land median 762/1186/761 m, max
  4525/5177/4631 m, P1 marks 4531/5203/4679 m. Temperate-lake cells
  185/193/601 (seed 11 was near-zero). Montane grassland out of the
  top 3 on seeds 1/11. Full suite 260 passed; all three demos verdict
  PASS.
- Note: the deep-basin lake keep rule (mean depth > ~180 m) now sees
  compressed depths — lake counts can drop slightly; accepted.

## Rock/ice split + domain-relative legend (user, 2026-07-24)
- The WWF abiotic "rock and ice" class is split into two L0 classes:
  "rock" (barren nival ground above the vegetation line — alt > 4500 m,
  or > 2500 m with warmest month < 4 C) and "ice" (permanent ice cap —
  never above freezing at any altitude). Ice applies after rock so a
  frozen summit reads as ice-covered, not bare. The delivery rim is
  "rock" (it sits ~12 m above sea level; it is a rock wall, not an ice
  sheet).
- world.png legend: each section now reports shares of its own domain
  — TERRESTRIAL (% LAND), FRESHWATER (% INLAND WATER = lakes + river
  cells), MARINE (% OCEAN). The ocean/lake water-mask entries are gone
  from the terrestrial list. Sub-0.05% classes still fall back to raw
  cell counts.
- Legend layout tightened (stats rows 26 -> 22 px, terrestrial 27 ->
  24, aquatic 24 -> 20, section header advance 56/46 -> 46/40) so all
  sections + landmarks fit the 1024 px panel on aquatic-heavy seeds.

## Finalize pass: shelves, wind-current coupling, T advection, loading (user, 2026-07-24)
- Continental shelves are real now. Diagnosis: the coast converged to
  the waterline at ~460 m and reached the 2600 m plate base within
  ~30 km, and the detail step then pushed coastal water ~1 km deep —
  below-sea cells inside the land-grain mix ramp took the LAND recipe
  (+0.10 emergence offset). Only ~1% of ocean classified as shelf
  (<200 m); Earth is ~7.5%. Fix (plates.py): below-sea cells always
  take the sea recipe; the sea detail is depth-aware (shelves are
  wave-swept sediment flats, abyss carries relief); and a shelf
  profile reshapes below-sea cells by distance to the provisional
  coastline (15 m at the shore -> 200 m at the break ~46 km out, then
  a steep rise into the plate base; faults carve AFTER, so active
  margins keep narrow shelves). Result: 5-15% shelf, coral and
  upwelling classes ~10x more area. Coastlines moved a few km seaward
  (the emergence offset no longer inflates land).
- Wind-current coupling (currents.py): the drawn gyres now ride on a
  fraction (0.25) of the mean annual low-layer wind — surface currents
  are wind-driven (Ekman drift), so the streams correlate with the
  persistent circulation. Pass order changed: currents moved AFTER
  hydrology (the wind library needs the hydro masks);
  climate.mean_surface_wind() reuses the same K1 stream as
  build_climate, so the wind library is draw-identical (clocks 500+
  never collide with the passes' 1000+).
- Air-temperature advection (climate.py): the old one-step 0.3 blend
  moderated only ~8-12 km of coastline (measured). Replaced by a short
  semi-Lagrangian transport (4 steps, relax 0.35) — maritime influence
  reaches ~30-60 km downwind. A 10-step/0.25 run overshot: poleward
  continents sit near the year-round-freeze threshold, and the extra
  numerical diffusion flipped seed 1's north to 12.4% ice; 4/0.35
  lands at ~6% (a real ice cap that keeps its taiga belt).
- Loading screens: 1 logic pass = 1 png (11 stages: plates, elevation,
  carve, hydrology, currents, precipitation, temperature, biomes,
  aquatic, delivered elevation, delivered biomes). The pass-1
  precipitation and vegetation-prior intermediates are gone from the
  sequence (and from the climate dict). load.png is now a real file
  copy, not a symlink (viewers that can't follow symlink swaps).
  Currents u/v/rise are persisted to the dump for the batch re-render.
- Pre-existing broken test fixed: test_persist_roundtrip never
  supplied "aquatic" to save_world (broken since the aquatic-biomes
  commit); now supplies aquatic + currents and asserts the currents
  round-trip.

## refine_hydrology + dump completeness + loading names (user, 2026-07-24)
- Second hydrology pass (hydrology.refine_hydrology, after climate):
  precipitation-conditioned small features, additive only. Ponds the
  uniform water balance rejected are re-judged on P-weighted inflow vs
  temperature-scaled evaporation (taiga hollows fill, hot basins
  don't); streams sprout where P-weighted discharge clears the area
  threshold at mean land wetness — drainage density follows the rain,
  and a wet highland feeds trunk streams through dry country
  downstream (Nile effect). Routing surfaces untouched; order, width,
  salinity, HAND recomputed. It also owns the P-weighted discharge
  now. Rivers +20-35% and lakes +14-41% of cells on seeds 1/11;
  new ponds concentrate in the wet/cold north (seed 11: polar lakes,
  temperate lakes up).
- The world dump is now COMPLETE state: currents persisted in full
  (u/v/rise/depth_m/drift arrays + gyre params/vmax in the manifest)
  — velocity_field(month) works from a loaded dump. Everything a
  downstream kernel needs is in world.json/world.npz; no re-derivation
  required.
- Loading screens are named (top-left stamp: PLATES ... WETLANDS ...
  DELIVERY BIOMES), 12 stages with the wetlands pass included;
  render_plates refactored to share _plates_rgb with the stage draw.
- Legend section headers carry the domain's world share:
  TERRESTRIAL (45% LAND), FRESHWATER (1.8% INLAND WATER),
  MARINE (53% OCEAN); rows remain shares within the domain.

## Chamfer, center lat 45, aquabiomes.png, convective rain, flooded gate (user, 2026-07-24)
- Blocky shelves: root cause was the 4-connected (Manhattan) chamfer
  in raster.distance_to_mask — diamond iso-distance contours became
  square terraced depth bands. Now an 8-connected chamfer with
  sqrt(2) diagonal weights; shelf contours are rounded at the source.
- Realistic-mode default center latitude 40 -> 45 degN (stronger
  circulation made 40 too tropical); wiggle/cap unchanged.
- aquabiomes.png joins the main PNG set (delivered-resolution aquatic
  classes over dim elevation); the demo prints each pipeline step to
  stderr as it runs.
- Flooded grassland was too common (~4-5% of land): the rule now
  requires the ACTIVE FLOODPLAIN of a real river (within ~3 cells of
  a width-2+ channel, ~8 m of the drainage surface) AND >= 240 mm in
  the wettest month. Down to 0.1-0.5% — rare, as it should be.
- Tropical moist forest was ~0%: the climate never produced
  year-round-wet tropics (driest month < 15 mm everywhere) because
  rain only came from wind wringing — the Hadley-cell thunderstorm
  budget was missing. _advect now carries a convective rain term
  (heat-scaled, kicks in ~20 degC, full ~10 degC hotter; still
  suppressed by subtropical-high subsidence): the deep tropics rain
  year-round, mid-latitudes get summer thunderstorms. The moist
  prototype was also broadened (140 +- 100 mm/month — real moist
  broadleaf spans a short dry season). Moist forest now appears
  without orographic forcing (0.1-0.8%, seed-varying).
- refine_hydrology equipotential fix: pond candidates touching an
  existing lake (or an earlier new pond) are skipped — adjacent
  basins accepted at different levels read as one lake with two
  surfaces (lakes_equipotential check caught it on seeds 1/11).

## Second-order pipeline restructure (user, 2026-07-24)
The pipeline is now explicitly two-pass. PASS 1 = the full pipeline in
honest dependency order: plates -> elevation -> carve -> hydrology ->
currents -> climate (bare ground — forests do not exist yet, and are
no longer fabricated: _vegetation_prior is gone) -> biomes -> forest
cover. PASS 2 = the coarse second-order rerun (NOT circular, never
iterated): hydrology conditioned on the pass-1 climate
(refine_hydrology's ponds/streams), then climate rerun with the REAL
pass-1 forest cover (green=) and the new water — same K1 stream, so
same weather systems under new surface conditions — then discharge
(P-weighted by the FINAL climate), biomes, cover, aquatic, complex
re-derived. The pass-2 states are the delivered world. n_samples is
the weather library itself: pass 2 keeps the full 8/month, the
pass-1 scaffold runs lean at 4.
- refine_hydrology pond fix: candidates are evaluated per EQUIPOTENTIAL
  LEVEL, not per component at max level (a component spanning several
  sub-basins at different flood levels used to drown the lower ones
  and their streams under the highest level).
- Loading screens now follow the computation DAG (15 named stages:
  pass-1 PLATES..BIOMES 1, pass-2 WETLANDS..AQUATIC, DELIVERY). CARVE
  draws the delta (notches tinted); HYDROLOGY draws the water+rivers
  composite. Batch re-render skips the pass-1 scaffold screens (the
  dump holds the final world only).
- Blocky shelves/ocean (seed 11/12 "perfect squares"): the abyss fbm's
  value-noise LATTICE showed on flat seafloor, exposed by the shelf
  rework's depth-aware texture damping. The abyss noise is now
  domain-warped (~1/3 lattice cell); iso-bands bend.
- Shelf width is a field: low-frequency multiplier (0.3-2x),
  compressed near convergent margins (fault_conv x fault_dist decay).
- Mountains/trenches, no hard caps: CC uplift 0.40 -> 0.55; the peak
  soft-cap moved to 0.85 with asymptote 1.2 (leaky — strong draws
  exceed 6 km; 17 cells hit the 1.0 normalization bound on seed 1);
  trench amplitudes up (OO -0.18 -> -0.22, OC -0.16 -> -0.20) and
  DEPTH_MAX_M 4000 -> 6000 (real trenches run 6-11 km; the abyss
  median moves toward Earth-like depths).

## Pass-2 conditioning fixes (user, 2026-07-24)
- Pass-2 precip was invisible because build_climate re-pinned its own
  adaptive gain to the same land-mean target, normalizing the forest
  feedback back out. The gain is now a WORLD CONSTANT: computed in
  pass 1 (bare ground), reused by the pass-2 rerun (build_climate
  takes gain= and returns it). Measured on seed 1: land-mean P
  0.210 -> 0.218, local deltas to 0.17, 21.6% of land changes biome.
- refine_climate now takes green= (the real pass-1 forest cover):
  canopy snow-masking (boreal forests lose less heat to the
  snow-albedo feedback than open tundra) and transpiration cooling of
  the warm months. Pass-2 T was previously identical to pass 1
  except via P.
- refine_hydrology "zero delta" was a measurement artifact (the
  function mutates the hydro dict in place — both sides of the diff
  were post-refine). Proper snapshot: lakes 1102 -> 1322, rivers
  661 -> 928 on seed 1.
- Straight-diagonal rivers: the refine streams (2-6 cell headwaters)
  render as raw D8 diagonals because RDP/chaikin/meander all need
  length to curve anything. river_raster now skips edges shorter
  than 6 anchor cells (24 km): sub-L0 creeks are the refinement
  layer's job to draw; they remain in the hydro fields for
  discharge/HAND.

## River centerline wobble (user, 2026-07-24)
- Long exact-45-degree diagonals persisted because RDP collapses a
  straight D8 run to two endpoints, and jitter/chaikin/meander cannot
  curve two points. river_raster now resamples the simplified path to
  <= 6 px segments, then gives EVERY edge a gentle long-wave wobble
  (lam ~ 24+ px, amp ~ 2 px per width class; D8 centerlines are
  diagonal-locked even in steep terrain), with the slope-gated valley
  meander still applied on top. The sub-6-anchor-cell edge suppression
  from the previous note stands (creeks are L1's job).
- PRECIP 1 vs 2 verification (pixel diff of the loading screens):
  58% of pixels differ, mean 2.6 gray levels, p99 20, max 245 — the
  conditioning is real but modest per cell (forest cover is ~12% of
  land; recycling coefficient 0.25). The macro pattern is identical
  BY DESIGN: same K1 stream = same weather systems, same world gain.

## Strahler through lakes + loading deltas (user, 2026-07-24)
- strahler_order treated only river cells as upstreams, so a river's
  order reset to 1 every time it crossed a lake (a Strahler-3 river
  visibly "turned into 1" at the outlet). Lake cells now act as order
  CONDUITS: they carry the max incoming order through without
  incrementing (the lake is one body); lakes with no river inflow
  count as no upstream (their outlet is a headwater). Gorge carving
  was never the right layer for this — it notches terrain sills, the
  abruptness was a mask/order artifact.
- Loading pass-2 screens now draw DELTAS over the base render (the
  pass-1 fields are in the stage bag): WETLANDS tints new ponds cyan
  and new streams orange; PRECIP 2 / TEMP 2 tint green where the
  conditioned field rose, red where it fell; BIOMES 2 brightens
  flipped cells. Batch re-render falls back to the plain render (the
  dump holds the final world only).

- Backward-compat cleanup: currents/salinity/sea_mask/aquatic/discharge
  are now mandatory world components — persist and render index them
  directly instead of `.get(...)` fallback chains, and
  `upscale_world(aquatic=...)` is a required argument. Dumps from before
  the currents era are no longer loadable; regenerate instead. Kept the
  genuinely-optional guards (wind drift may be absent; batch re-render
  skips pass-1 scaffold stages because the dump holds the final world
  only — that is a data-availability boundary, not compat).

- Wind snapshots are now DELIVERED: `_precip_pass` returns the
  per-(month, sample) surface-wind fields alongside the raw rates, and
  `build_climate` exposes them as `wind_u`/`wind_v` (12, n_samples) at
  the coarse grid — float32, post-monsoon/terrain/windbreak, i.e. the
  exact fields that move weather. They ride the generic climate
  persistence, so every dump now carries the weather pattern the
  monthly T/P means average over (gameplay interpolates between a
  month's samples; snapshot (m, j) remains K1-reproducible via clock
  1000+m*16+j). Pass 1 keeps the reduced scaffold sample count; the
  delivered pattern is pass 2's full set.

- Colder north (invented mode): t_north 0.12 -> 0.06 — the north-rim
  annual mean moves from -22 degC to -26 degC. Convection now carries
  tropical rain on its own, so the global evaporation budget no longer
  needs a milder Arctic; the latitudinal delta sharpens (more ice and
  tundra up north, taiga pushed further from the rim). Generation knob
  only — units and classifier untouched. Realistic mode unaffected
  (Earth zonal anchors).

- Aquatic squares fix (seed 14 diagnosis): the marine classes were
  classified at the 256 anchor and kron-stamped to 1024, so single-cell
  threshold speckle (2 degC polar-shelf line, top-decile upwelling cut)
  became 4-20 px squares, and the max-id boundary fill leaked high
  class ids (upwelling > tropical > shelf) further outward. Fix follows
  the delivery rule the module already states: marine classes are
  POINTWISE, so classify_marine() recomputes them at the delivered
  grid from smooth bicubic parents (rise upsampled, plume radii scaled
  by factor); only lakes/seas (per-component) and rivers (anchor
  order/width) ride the kron path, and the boundary-band fill is now
  distance-ordered nearest (mode of filled neighbors, ties to lowest
  id) instead of max-id. Terrestrial biomes already worked this way
  (classify_streaming, which now also returns the coldest-month field
  for the marine pass).
  Follow-up: the carry is per-CHANNEL (lake channel, river channel,
  each nearest-spread across its own boundary band) because the
  delivered lake extent reaches over anchor river cells at inflow
  sills — a shared kron map classed those delivered lake cells as
  montane river (caught by the new deliver-smoke family assertions).

- Land friction (WindLibrary, land_friction=0.35): the low layer now
  slows over land (real over-land surface winds run ~60-70% of
  over-ocean values at the same pressure gradient — roughness + deeper
  boundary layer). Lightly smoothed land mask (3 passes, vs the
  breeze's continental 10): full strength inland, a taste of it on
  coastal water. High layer untouched — the free troposphere feels no
  surface. Saved wind snapshots carry the friction, and the T/P
  advection both see it (drier deep interiors relative to coasts;
  land-mean P still pinned by the adaptive gain). Rain-shadow status
  check: shadows exist via orographic wringing + proportional-recovery
  depletion + momentum blocking; NOT modelled: foehn (no descent
  drying term) and lee wind wakes (field is pointwise, no downstream
  memory).

- Foehn, both halves: _advect now suppresses rain on descent
  (_FOEHN_DRY * sink, floor 0.2 — dry adiabat steeper than the moist
  one, so descent dries harder than lift wets) and the T loop warms
  descending parcels (_FOEHN_WARM — lee runs warmer than windward at
  the same altitude, feeding back into moisture capacity). Rain
  shadows are now depletion + active drying, not depletion alone.

- Currents land treatment (_process, shared by build_currents and
  velocity_field so every month sees identical behavior): the raw
  gyre field was previously just erased on land — streams stopped at
  shore and resumed full-strength behind peninsulas. Now a SLIP WALL
  projects out the into-land momentum at coast cells (streams bend
  along shores — boundary currents), and a LEE SHADOW advects the
  removed momentum downstream (24 steps, recharge 0.25, decay 0.05,
  damp floor 0.8) so struck coasts cast a wake. Source is normalized
  by the world's own p99 current so weak drift casts weak shadows.
  Upwelling rise derives from the deflected, shadowed field. Unit
  tests: map-wide no-into-land at coasts, bar deflection + local wake,
  foehn slope-direction asymmetry.

- Wind lee wake (WindLibrary.sample): the upslope momentum the
  deflection step strips (cut, previously discarded) is now the source
  of a wake advected downstream by the SHARED deficit-advection
  tooling — lee_shadow moved to climate.py, parametrized; currents
  keeps its own constants via a thin wrapper. Wind constants:
  12 steps, recharge 0.25, decay 0.20 (1-3 coarse cells — wakes mix
  out over tens of km), damp 0.6. Saved wind snapshots carry the wake.

- River diagonal-bearing diagnosis (seed 1 dump): 45% of river cells
  route via the FLATS BFS (only 12% of land does — rivers live on
  priority-flood fills), and the BFS assigns each flat cell a pointer
  along its expansion wavefront = geometric BEELINES to the outlet
  (the "short circuit" the user suspected). The other 55% is steepest-
  descent D8: greedy lowest-neighbor quantizes bearing to 45 degrees
  with no inertia. River step bearings: 41.5% diagonal, 58.5%
  cardinal — the only two flavors D8 allows. Proposals on the table:
  (1) route flats on raw-h micro-relief instead of BFS hop distance
  (Garbrecht-Martz-style flat masking — biggest leverage, changes
  topology); (2) D-infinity geometry at polyline extraction (vertex
  offset along the continuous w-gradient inside the D8 corridor —
  dequantizes bearing, zero physics change); (3) inertial tie-band in
  steepest descent on gentle slopes (meander physics, needs care).

- River bearings, both fixes in: (1) _resolve_flats is now a
  multi-source DIJKSTRA over equal-w cells with edge cost
  1 + 1000 * raw-h climb — drainage on priority-flood flats winds
  through the bed's micro-lows instead of BFS beelines to the outlet
  (a 0.01 climb ~= a 10-cell detour; cost strictly increases upstream
  so cycles/orphans are impossible, and flow_accumulation's upstream
  ordering now sorts on the float cost). flow_direction(w) gained a
  required raw-h argument. Unit test: a micro-ridge across the
  beeline forces a detour, no orphan pockets. (2) river_raster adds
  _smooth_centerline (pinned-endpoint moving average, window
  2*factor+1) after _simplify: a D8 staircase alternating the two
  ticks bracketing the true flow angle averages to that angle — the
  45-degree bearing lock disappears without touching the committed
  (grid-true) complex. Routing change alters rivers/accumulation/
  discharge downstream — regen all seeds.

- Currents loading screen now draws FLOW LINES over the speed render
  (_flow_lines, render.py): K1-jittered particle grid advected along
  the annual velocity_field, plotted at sub-cell resolution. Vertical
  motion rides as hue — the rise field is mirrored into a sink term
  (depth increasing along the flow): cyan trails = welling up, violet
  = diving, and the strongest of each get ring-dot (up, out of the
  page) / ring-cross (down, into it) markers, greedily spaced like
  landmark marks. Render-only; works from a dump (render --seed).
  Straight shelf class edges on seeds 11+ diagnosed as REAL tectonic
  features (polygonal plate/fault traces stepping bathymetry across
  the 30 m coral / 200 m shelf thresholds) — user: no fix wanted.
  Iteration: speed-scaled steps read as short straight dashes (user:
  "these are just straight lines?") — trails now walk the DIRECTION
  field at unit speed (0.6 cell x 140 steps) so slow gyre cores curve
  as much as fast rims; brightness still carries speed, hue vertical
  motion.

- Currents REBUILT on real fluid dynamics (user: "there is 0 fluid
  dynamics"): the velocity field is no longer drawn and masked —
  vorticity is drawn (same K1 gyre blobs, now vorticity sources) and
  the flow SOLVED: per-source Poisson ∇²ψ = ζ (red-black SOR at 64²,
  currents are huge), transport = curl ψ upscaled bicubic, velocity =
  transport / depth at the anchor (shelves and straits ACCELERATE —
  barotropic continuity, replacing the old depth damping). Land is a
  streamline by construction; the per-landmass FREE constant (area
  mean of the unobstructed solve, island-rule style) keeps net
  transport alive: pinning all land to one value makes Δψ = 0 between
  boundaries and stagnates every strait (measured: right sub-basin at
  0.4% of left). Wind correlation per the two-pass philosophy, NOT a
  stand-in estimate: mean_surface_wind + wind_drift + drift_coeff
  DELETED (invent-then-discard); refine_currents adds the curl of the
  world's OWN delivered wind pattern (climate["wind_u"/"wind_v"]
  means) as a vorticity source after pass-1 climate (Sverdrup), so
  pass-2 climate/aquatic read the refined field. Slip-wall and
  lee-shadow hacks removed (cosmetic continuity breakers; the wind
  lee wake stays — air is different). Persistence: per-source psi
  arrays + weights replace drift; velocity_field(month) blends psi
  per gyre phase. Tests: SOR residual, per-landmass streamline
  constants, strait threading (right basin alive), Venturi
  acceleration (>2x approach), refine determinism/correlation.
  Render iteration: the barotropic shelf jet outruns the deep gyres
  ~60:1 in VELOCITY (physical — abyssal cm/s vs boundary m/s), so the
  flow-line render now seeds/brightnesses on TRANSPORT (velocity *
  depth, same direction field) with a sqrt scale; velocity-view left
  the interior ocean empty. Seed 11 shows closed eddies, coastal
  upwelling ribbons, and strait threading with markers.

- Loading DAG is 16 stages: CURRENTS 2 (stage 9) shows the
  wind-correlated field with speed-delta tints against the seeds-only
  baseline (vmax_seeds kept in the dict/manifest so both stages render
  from one dump); the rest renumbered. aquabiomes.png now draws the
  current flow lines on top (nutrients ride the streams).
- Verification (seed 11): currents mix heat (SST anomaly std ~6 degC
  vs zonal baseline), wind moderates (interior seasonal swing 28.2 vs
  coast 25.6 degC), wind->current delta aligns with the wind-source
  transport. But the upwelling cooling term was UNSTABLE: -0.1*rise
  goes |1-0.1*rise| > 1 for rise > 20 m/cell (the stream-function
  field's boundary-current slopes give rise to 200+) — oscillating
  blowup, masked only by the climate T clip (measured delivered
  upwelling cooling was -0.1 degC). Fixed as a bounded relaxation:
  rr = 1-exp(-rise/p95), T += 0.1*rr*(T_deep - T) — upwelling sites
  now -3.4 degC mean, -12 max, elsewhere -0.5, field finite.

- Marine nutrient store persisted: rise_monthly(currents) — the
  monthly upwelling field (12, anchor) from the seasonal-breathing
  velocity — saved as r_rise_m and reconstructed on load (roundtrip
  asserted, seasonality asserted). Ecology kernels read where deep
  water surfaces, and that place moves with the seasons.

- Wind is fluid dynamics now (same architecture as the currents):
  the rotational (pure-curl) part of WindLibrary solves ∇²ψ = ζ at a
  64² psi grid — vorticity sources are the meridional bands (as a
  vorticity profile, solved at seasonal = ±1 and linearly
  interpolated) and the K1 fbm gyres (solved at the surface, raw
  aloft). High terrain is a free-constant obstacle, so the stream
  bends AROUND ranges (island-rule flavor) instead of the old
  upslope projection / terrain damp / lee-wake pretending layer
  (deleted wholesale). Divergent terms (monsoon breeze) and surface
  friction stay outside the solve. The rim-closed solve weakens the
  sources, so each solved ψ is rescaled to the mean open-air
  transport of the field it replaces (seed-1 snapshot speed back to
  mean 0.52 / max 2.53 vs 0.60 / 2.45 pre-refactor).
- Magic rim, semi-porous: the world-edge rock ring is not terrain.
  The coarse water mask runs to the domain edge and the Poisson rim
  condition is Robin — ghost = (2ρ−1)·ψ_rim, ρ = _RIM_POROSITY = 0.5
  — interpolating wall (ψ = 0, all flow redirected, boundary
  currents recirculate and pile heat onto the poleward rim) and open
  water (zero normal gradient, through-flow free). Motivation: the
  closed box trapped the N–S boundary currents and overheated the
  north in winter; the void leaks and replenishes. All four edges
  (opening only N–S would not fix it).
- Test updates for the new physics: terrain-blocking asserts the
  solved-stream semantics (psi-constant massif interior carries no
  rotational wind, flow deflects along the range front) instead of
  cellwise momentum removal; the currents streamline test compares
  psi against the solver's own leaky-rim mask (_coarse_grids).

- biomes.png draws MEAN ANNUAL wind streamlines (_wind_lines in
  render.py), the wind counterpart of aquabiomes.png's current lines:
  K1-jittered particles, unit-step direction tracing of the
  month/sample-mean of the persisted wind store, sqrt speed
  brightness, luminance-flipped ink (light on dark biomes, dark on
  ice/desert). render_all takes climate=; the overlay factor derives
  from the wind-store resolution, palette-only fallback without it.
- Wind solve gets the same semi-porous rim as the currents
  (_RIM_POROSITY): weather systems arrive from beyond the map and
  leave it — a closed rim trapped every gyre into a pronounced
  standing whirlpool. Interior swirls remain by construction (the
  fbm gyre SOURCES are vortices; their blend weight is the lever if
  they should read weaker against the band flow).

- Wind tuning (user: "wind enters, swirls due to terrain, leaves"):
  _RIM_POROSITY_AIR = 0.8 (the sky over the magic rim is open — air
  exchanges freer than water leaks); _BLOCK_ALT_M = 1000 m (real
  low-level flow splits around terrain once it approaches the
  boundary-layer depth, Froude < 1 — was 2100 m, only big ranges
  deflected); _GYRE_WEIGHT 2.4 -> 0.6 (six gyres at +-0.5 alpha still
  summed past the band at 1.2; terrain swirl should dominate the
  look, not the chaotic sources).
- Pytest speed: _poisson_sor iters now scale with grid diameter
  (min(600, max(150, 10*N)) — 64² production grids unchanged at 600,
  small test grids converge proportionally); the wind-blocking test
  drops to 32² (13.3s -> 3.7s); test_currents_and_sst marked slow.
  Fast suite 38s -> ~17-22s.

- Salinity now feels temperature (pass 2 only): the Clausius-Clapeyron
  evaporation factor is extracted to climate.evap_factor (one curve,
  two consumers — the moisture pass and the salt balance), and
  refine_hydrology feeds mean-annual T through it into
  classify_salinity. Effective flushing = inflow per unit
  evaporation: cold basins stay fresh on modest inflow (Titicaca),
  trickle-fed cold terminals still brine (Uyuni). Seed 1: salt cells
  above 1500 m top out at 187 g/kg (was 219), marginal brines flushed
  below the salt threshold (773 -> 756 cells). Pass-1 call unchanged
  (evap=None -> factor 1).

- No hardcoded axes anywhere (user: sources enter from ANY side +
  rot jitter):
  - Currents: 4-6 vorticity gyres (was 2-3) plus a THROUGH-FLOW
    source — two orthogonal unit Dirichlet-ramp solves
    (_poisson_sor rim_values=; _land_constants learns psi_open= and
    rim_to_zero= for the analytic open solution); by linearity any
    direction is a cos/sin blend, so the seeded prevailing direction
    theta AND its seasonal direction jitter (+-0.35 rad) cost no
    re-solve — velocity_field rotates the pair's weights per month.
    Ramp metadata round-trips through persist (manifest "ramp").
  - Wind: the bands now ride a SEEDED prevailing frame (any angle,
    own K1 slot) — along-axis flow entering one side and leaving,
    no rim taper (the porous rim lets it exit); the outermost-band
    constraint projects to "equatorward meridional component",
    vacuous for zonal frames. Subsidence sourcing switched from
    meridional() dvy to band_divergence() (directional derivative
    along the axis) — dry belts park wherever the frame puts them.
  - Wind gyres DRIFT: each gyre precomputed at _GYRE_PHASES=4
    quarter-domain rolls of its fbm texture (re-solved per phase),
    snapshots draw a random phase angle — weather systems move
    between snapshots and cancel in the annual mean instead of
    parking at fixed spots (the mean-field swirls complaint).

- Relief obstacles + over-the-top bleed (seed-3 fix: a high
  continent was one big psi-constant obstacle and the interior got
  ZERO wind). What blocks low-level flow is the RISE, not the
  altitude (Mongolia windy at 1500 m, a 500 m escarpment makes a
  foehn): the obstacle mask is now local relief (_BLOCK_RISE_M =
  500 m over _RELIEF_WINDOW = 8 psi cells, sliding-window range), so
  rims/cores deflect and flat plateau interiors stay open. Where
  terrain IS blocked, sample() blends in the high layer weighted by
  bleed = _BLEED_MAX(0.5) * (1 - exp(-(alt_m - _BLOCK_ALT_M(1000))+ /
  _BLEED_SCALE_M(800))) — asymptotic, no cap; Froude < 1 stops the
  surface flow, not the column above. block_alt param retired.
  Helmholtz drag considered and rejected (gauge dependence + wide
  plateaus still windless). Blocking test now asserts the new
  semantics: collapse at the rise, continued flow in the interior.

- Fauna/flora direction (user, for the future ecology kernel —
  refines rfc-fauna-generator): CURATED pinned megafauna (horses and
  kin, livestock, apex) + SEEDED phylogenetic solve for subspecies
  and critters (many); same two-tier split for flora. Placement is a
  multi-step lived-in simulation (speciation/dispersal/extinction
  over the L0 terrain). Game-facing: a critter-dex — plentiful
  species curated- or LLM-named from phylogenetics, the PLAYER names
  rare ones. LLM names, never speciates (P5 holds).

- Climate memory terms (all four approved; passes kept clean):
  - Thermal LAG: circular exponential filter over the year
    (_thermal_lag; land tau 1 mo, ocean 3) — closed-form periodic
    steady state, Dec wraps into Jan exactly, no spin-up. Applied to
    T_m before the precip passes.
  - SOIL moisture: leaky monthly bucket (_soil_schedule; rain in,
    C-C demand out, S/(S+half) recycling in _advect), spun up 3x over
    the year from the annual-mean state. Pipeline: precip pass ->
    gain pin -> soil schedule -> ONE corrective precip pass with
    soil (same K1 clocks — delivered wind snapshots identical, only
    the water cycle shifts), gain reused.
  - KATABATIC drainage: downslope potential (breeze-shaped) gated by
    the sub-freezing anomaly (_KATA_STR 0.8, span 0.15 norm) —
    ice-cap interiors are no longer dead air (the 6000 m cap on seed
    3 read 0.004 mean wind). Heat-transport loop skips it
    (second-order there; the delivered snapshots carry it).
  - HADLEY closure: the high layer's band stream enters anti-phase
    and weakened (_HIGH_BAND_RETURN -0.5) — subsiding dry air rides
    the return current, not the surface flow's tailwind.

- Metric wind/current + monthly store (user: no exact pins — preset
  default average, seeded wiggle, leaky cap). units.wiggle_metric
  generalizes the resolve_center_lat pattern (triangular draw, leaky
  band). Wind: build_climate calibrates the delivered snapshots to
  m/s against a wiggled target around WIND_MEAN_OCEAN_MS = 7 (Earth
  ocean-mean surface wind); wind_scale kept for provenance;
  consumers were already scale-invariant (direction/curl). Currents:
  vmax_ms wiggled around CURRENT_VMAX_MS = 1.5 (boundary-current
  peak), persisted in the manifest; velocity_ms() is the metric
  reader for downstream. Precip: the gain pin's target is now a
  wiggle around _TARGET_LAND_P = 0.19 (own K1 substream, drawn once
  in pass 1, pass 2 reuses the gain). monthly/ now also writes
  m##_wind.png and m##_current.png — mean speeds in m/s on fixed
  physical gray scales (0..15, 0..2) so months/worlds compare.
  Seed 1: wind ocean-mean 6.7 land 2.7 m/s; current vmax 1.35,
  ocean-mean 0.037 m/s (abyssal cm/s + boundary m/s, physical).
  Watch item: snapshot wind max ~65 m/s (chaotic tail of the scaled
  field) — hurricane-force, plausible but hot; revisit if gameplay
  reads extremes.

- Vectorization (numpy batching, BITWISE-IDENTICAL output — A/B
  verified against a pre-change dump, all 69 arrays equal):
  - _poisson_sor/_land_constants batch independent sources into one
    SOR loop (wind: 24 gyre phases + 2 bands in 2 calls; currents:
    gyres + ramps stacked). Landmass labeling runs once per set.
  - _precip_pass/_subsidence/_advect and the T-transport loop batch
    the month's snapshots; accumulation keeps the old loop's
    association order (Python-sum over the batch).
  - Traps hit and fixed: (K, n) axis-1 reductions round 1 ulp
    differently than flat 1D means (kept per-source scalar means);
    NumPy-2 weak scalars make np.where(water, 0.0, pin) follow pin's
    dtype — zeros_like(po3) made float32 pins for float32 sources
    and ran the whole solve in float32 (float64 pins restored);
    np.stack shape gotchas in pad/broadcast.
  - _bilinear batch path: batched gathers (take_along_axis, row
    fancy) benchmark 2.3x SLOWER than per-snapshot 2D fancy
    indexing, so the batch loop wraps the original 2D form.
  - Net: demo ~1m58 -> 1m54, solves ~2x fewer Python iterations.
  - 267 fast + 10 slow pass; seed 1 verdict PASS.

- float32 working precision on the hot blocks (user direction, L0
  needs no more than ~1e-6 relative): _poisson_sor, _advect,
  _subsidence, T transport, advect_sst, WindLibrary precomputed
  fields. NumPy-2 weak scalars keep python-float constants from
  upcasting; array inputs are cast at function entry. The earlier
  float64-pin fix is now deliberately reversed (pins follow the
  solve precision). Output changes by design; deterministic
  run-to-run. Iteration trims (user direction): _advect 36->24,
  _subsidence 24->16, advect_sst 48->32 steps. Demo 1m58 (float64)
  -> 1m37 (float32) -> 1m19 (trims); 267 fast pass, seed 1 verdict
  PASS, world sheet healthy. Knobs documented for the user in-chat:
  iters formula, step counts, coarse grids (128/64), n_samples.

- Aridity round (user hand tweaks + subsidence delivery): the user
  applied the desert-knob suggestions directly — _subsidence decay
  0.012 -> 0.006, wet/dry floors 0.65/0.75 -> 0.75/0.85, convective
  budget gated by (1 - 0.9*sub) (a subtropical high caps convection
  FIRST), t_pow 0.40 -> 1.0 (linear ramp: cold north third), f_cap
  0.88 -> 0.92, realistic shrink 4 -> 6, psi_coarse 64 -> 48,
  build_climate coarse 128 -> 96, SOR iters 600 -> 400. Follow-ups
  here: the (1 - 0.9*sub) gate crashed on sub=None (unit tests call
  _advect bare) — guarded as cap_conv alongside wet/dry. Subsidence
  is now DELIVERED: _precip_pass returns the snapshot-mean sub field
  per month, build_climate delivers sub_monthly (12, coarse grid,
  0..1, persisted as c_sub_monthly), rendered monthly/mNN_sub.png on
  the fixed 0..1 gray scale. Band migration soft-constrained: the
  fixed 0.03 solstice swing is now a seeded triangular draw (K1
  clock 5 indices 22-23), mean 0.02, leaky-squashed above 0.03 at
  slope 0.25 — most worlds' highs dwell more, a rare one leaks past.
  shrink defaults aligned to 6.0 across build_climate/__main__ (the
  _lat_profile edit alone was inert — build_climate always passes
  shrink explicitly). Seed 1: verdict PASS, sub band visibly parked
  (m01 vs m07 shift small), desert 0.1% (was ~0), ice cap 12% — the
  thirds layout is knob territory now. 267 fast + 2 climate slow
  pass.

- Rim tube BC (user design): the annual-mean wind render showed
  streamlines crossing every border near-PERPENDICULAR — the
  porous-rim ghost in _poisson_sor blends Neumann (kills tangential
  velocity) and Dirichlet (kills normal), so any diagonal prevailing
  flow was decomposed into axis-aligned inflows at the borders
  ("winds from N/S AND W/E" from ONE axis). Fix is a velocity-space
  correction after the solve, not a new solver: _rim_bc treats the
  domain as a tube along the seeded band axis — the two walls the
  axis points through are OPEN (rim velocity extrapolated from the
  adjacent interior ring; corners from the diagonal interior cell),
  the two axis-parallel walls WEAKLY BINDING (v_new = v_parr -
  (1-porous)*v_perp for normal outflow only; _RIM_BIND_POROUS = 0.65
  stolen by the void, rest reflected; inflow and tangential
  untouched). Applied at the end of sample() and sample_high() on
  the total field; the solve's own ghost stays (air 0.8, water 0.5 —
  currents unchanged). Band hardcodes removed (user: "don't hard
  code the bands"): the equatorward-override of the outermost bands
  is gone — no baked-in ITCZ, convergence zones happen where the
  random signs converge. Gyres stay fully random at 0.6 (the
  sign-flip "averaging out" is a non-issue at monthly granularity).
  Unit test test_rim_bc_tube covers reflect/steal, inflow-pass,
  tangential-untouched, extrapolation, corners, both orientations.
  268 fast pass.

- Renderer u/v transposition (the "perpendicular border" bug was
  COSMETIC): _wind_lines and _flow_lines stepped particles py += u,
  px += v, but the delivered convention is standard (u = x-velocity,
  v = y-velocity) — every streamline was mirrored across the
  diagonal, so glancing border flow rendered as perpendicular
  crossing and the rim tube looked broken. Caught via a synthetic
  +u field (rendered vertical) and a decisive empirical convention
  test (seed 21, near-perfectly meridional axis: mean flow entirely
  in v => u is the x-component). Physics verified correct
  throughout: npz rim checks (no binding-wall outflow, open-wall
  extrapolation) had already passed. Fixed both drawers; the
  current lines on aquabiomes.png were mirrored the same way
  (invisible on gyres; upwelling markers landed on mirrored
  positions). Dumps unaffected — `render --seed N` re-renders in
  seconds. 268 fast pass; border crops now show wall-hugging flow
  at binding rims and oblique crossing at open rims.

- Proper-curl fix for currents + open-tube air solve (user caught
  two real bugs): (1) _transport returned the SWAPPED curl
  (u=ψ_x, v=−ψ_y), so solved currents crossed coastlines instead
  of hugging them — empirically 0.74 into-land vs 0.52 along-coast
  on seed 18's stored psi, inverted to 0.52/0.74 with the proper
  curl. The renderer's own u/v transposition had masked it
  visually. _transport now returns the proper curl (u=∂ψ/∂y,
  v=−∂ψ/∂x); the wind-conditioning zeta (∂wv/∂x−∂wu/∂y) was
  already proper and now pairs correctly; ramp through-flow
  directions shift per world (theta is a uniform seeded draw —
  statistically identical). The wind library KEEPS its matched
  zeta/extraction pair: the band field's speed varies ALONG its
  flow, which is divergent by design (that divergence is the
  subsidence source, read analytically), so no pure-curl
  representation exists — warning comment left in
  WindLibrary._rotational. (2) The air solve's Robin ghost
  (rim_porosity 0.8) damped the crossing component at every rim —
  "4 dampening sides". _poisson_sor gains ghost="linear": the
  ghost ring is a linear extrapolation of the two innermost rings
  (zero curvature, corners diagonal), rim cells join the solve,
  porosity machinery skipped; WindLibrary.solve_batch uses it and
  _RIM_POROSITY_AIR is gone (water keeps 0.5). Boundary behavior
  lives entirely in _rim_bc now. Verified: seed 21 open rims carry
  −0.26 mean v vs −0.27 interior (true source/sink). New test
  test_transport_hugs_coast. 269 fast pass.

- Wall-driven prevailing wind (user design, replaces the band
  machinery wholesale): the band vorticity construction, band
  stream, band migration and band_divergence are DELETED. The rim
  tube's two open walls are fully partitioned into seeded segments
  (2-4 per wall, random cut points) — PERFECT SOURCES (prescribed
  inflow: wall-normal, speed = per-world default 0.5-1.0 x per-
  segment jitter 0.7-1.3, angular jitter +-0.2 rad triangular,
  seasonal wobble +-30% own phase) and PERFECT SINKS (purely
  absorptive: outflow passes, inflow zeroed, never emits). At
  least one source per world (forced if the draws give none).
  The prevailing field is a POTENTIAL FLOW: _poisson_sor gains
  `edge_flux` (prescribed outward normal flux via a ghost offset,
  +2*flux per touched edge; boundary fluxes must balance) and
  solves div-grad phi = 0 monthly (per-segment phases are not
  linear in `seasonal`, so no two-extreme interpolation — one
  batched 12-solve), terrain pinned as obstacles exactly like the
  gyres; velocity = gradient (no curl-convention ambiguity).
  High layer: same segments inverted at _HIGH_BAND_RETURN,
  terrain ignored. Gyres unchanged (kept the historical swapped
  extraction — statistically inert for noise). _rim_bc now takes
  src (absolute prescription) + sink (pass-outflow, zero-inflow)
  instead of extrapolating open walls. Subsidence source is now
  the DIVERGENCE of the month's mean surface wind (90th-
  percentile scaled), computed in _precip_pass after the snapshot
  loop. Verified: mass balance ~0 all months, source rings exact,
  interior not windless, seed 1 (3 north sources, south all-sink)
  and seed 18 (south all-source, north all-sink) both show a
  clean coherent through-flow with terrain deflection; the
  streamline pinch-point singularities are gone. Tests:
  test_rim_bc_tube rewritten for src/sink, new
  test_segment_prevailing_flow (partition contiguity, balance,
  prescription, interior strength). 270 fast + 3 slow (climate/
  biome/persist) pass, both demo verdicts PASS.

- Subsidence de-speckling (user caught biome patching): the new
  subsidence source — divergence of the month's mean surface wind —
  was dominated by small-scale terms (coastal monsoon-breeze
  dipoles, pinned-terrain edge artifacts, katabatic streaks, gyre
  residue), and the 90th-percentile scaling saturated that speckle
  to 1, printing speckled dry patches into the biome map. The dry
  belts are synoptic features: the mean wind is now pooled 4x and
  box-smoothed (_box3, 4 passes) BEFORE the derivative, then
  upsampled back — coastal dipoles and terrain edges are gone, the
  lobes are smooth. Render: wind trails on biomes.png are now
  colored by direction along the open axis (amber =
  east/southbound, steel blue = west/northbound; the open pair is
  read off the net rim fluxes, bright/dark variant by local biome
  luminance). 270 fast pass, seed 18 verdict PASS, sub renders
  smooth.

- Seasonal rotation for the segment wind (user: no monthly jitter
  visible): two omissions fixed. (1) Boundary wobble: each interior
  segment cut breathes +-2% of the wall (gap-limited so segments
  never cross/switch) with its own seeded phase — the circulation
  pattern rotates gently through the year; _seg_bounds(w, month) is
  used by both _edge_flux and _rim_prescription, and the sink mask
  is per-month now (sink_masks). (2) The per-snapshot angle jitter
  (same K1 draw (clock, 8)) now rotates the PREVAILING field as
  well as the gyres, in sample and sample_high — one coherent
  whole-field tilt instead of gyres-only, so monthly means swing a
  few degrees. Single-direction worlds are a draw outcome (one
  wall all-sink, ~25-50% likely), not a bug; the mass return is
  aloft. Verified: monthly prevail mean-direction breathes ~+-1 deg
  (boundary wobble), snapshots swing +-3-4 deg coherently, bounds
  contiguous all months, 270 fast pass.

- Per-wall source+sink guarantee (user): the earlier ">=1 source
  per wall" still allowed an all-source wall (seed 18's south was
  all sources). Now every open wall carries at least one source
  AND at least one sink — all-source draws get their smallest
  segment flipped to a sink, all-sink draws their largest to a
  source. Binding-wall porosity back to the historical air value
  0.8 (_RIM_BIND_POROUS 0.65 -> 0.8; more reflection piles wind up
  against the wall). Test asserts both constraints. 270 fast pass,
  seeds 1+18 verdict PASS; seed 18 shows amber/southbound and
  steel/northbound streams meeting in convergence zones.

- Algebraic braiding of the wall segments (user design): one wall
  draws a braid bar — a partition with widths floored at 60%/n (no
  slivers; fixes the 1% corner-sink draw) and ALTERNATING
  source/sink types; the opposite wall gets the same partition
  with a seeded matching of disjoint adjacent swaps applied to the
  types. Swapped pair = braid crossing (streams shear diagonally
  into neighboring sinks); unswapped pair = head-on opposing
  sources whose air cannot escape -> vortex/stagnation singularity,
  so unswapped sources are damped (_HEADON_DAMP = 0.4). Magnitudes
  decided after the topology. Boundary wobble now wobbles one
  SHARED base partition (the braid breathes as a unit). Binding
  porosity corrected to 0.4 (REFLECT 0.6 — user meant the
  reflection share: porosity 0.8 = reflect 0.2 acted as a vacuum
  and piled wind against the wall). Test asserts braid structure
  (disjoint adjacent swaps only, damping on unswapped sources,
  width floor, alternating types). 270 fast pass, seeds 1+18
  verdict PASS; renders show clean diagonal braid crossings, no
  stagnation pinches, smoother biome zones.

- Mirror-invert walls (user simplification, replaces the swap
  braid): pinching persisted with the swap matching, so the
  construction is now: one wall draws the partition (width floor
  60%/n, alternating types), the opposite wall takes the SAME
  partition with types INVERTED — X Y X over Y X Y, every source
  faces a sink directly, no source-source opposition can exist at
  all, so no head-on vortex or stagnation pinch by construction.
  The swap matching and _HEADON_DAMP are gone (dead code removed).
  Test asserts the inverted mirror. 270 fast pass, seeds 1+18
  verdict PASS; both renders are pinch-free with clean crossing
  braids.

- Ramp through-flow prevailing wind (replaces the wall segments
  entirely): the segment model — even mirror-inverted — was
  inherently singularity-prone (a sink is too local; flow that
  misses it curls back and forms stagnation pinches and local
  hurricanes). The prevailing flow is now a UNIFORM THROUGH-FLOW:
  two orthogonal Dirichlet-ramp solves (the exact machinery of the
  ocean currents' through-flow — _poisson_sor rim_values=ramps,
  landmass pins from _land_constants with psi_open=ramps,
  rim_to_zero=False) blended per month by the seeded direction
  theta (seasonal jitter +-0.2..0.5 rad, strength wobble +-30%),
  curl-extracted with the proper _transport. Divergence-free, no
  sources, no sinks, hugs relief through the solve's obstacle pins;
  the field is normalized per ramp by its max transport so the
  blend direction is exact in open water (test: per-cell cosine =
  1.0). The HIGH layer is the same blend on the RAW ramps (no
  solve, terrain ignored) scaled by _HIGH_BAND_RETURN. Dead code
  removed: segments, _edge_flux/_rim_prescription/_seg_bounds/
  _open_walls, boundary wobble, sink masks, the edge_flux plumbing
  in currents._poisson_sor/_land_constants. 271 fast pass, seeds
  1+18 verdict PASS; peak snapshot wind 26 m/s (gusts, was 53.6
  pre-limiter), no funnel clustering.

- No walls at all (follow-up simplification): with the ramps
  deciding where air enters and leaves, the rim TUBE split
  (two open + two binding walls, _RIM_BIND_POROUS reflect-steal,
  the frame/axis/open_x draws) is obsolete. _rim_bc is now a plain
  transparent extrapolation on ALL four sides (corners diagonal) —
  it exists because the curl's central difference leaves the rim
  ring at zero and the semi-Lagrangian advection samples through
  it. The flow-line hue detection in the render was already
  data-driven (net rim fluxes) and adapts unchanged. 271 fast
  pass.

- Chaotic rim-harmonic through-flow (replaces the single-direction
  ramp blend): a nameable world-wide direction ("the wind comes
  from the X") was too orderly — wind may enter and exit anywhere,
  soft-constrained. The rim streamfunction is now a seeded harmonic
  series over the perimeter angle, psi_rim(s, m) = sum_k A_k
  cos(k s + phi_k + drift_k m), k = 1.._RIM_MODES(3): k=1 fixed at
  amplitude 1.0 (a loose persistent backbone), higher modes on a
  soft falloff (A2 ~ 0.25..0.6, A3 ~ 0.1..0.35, seeded) so the
  entry/exit arcs stay few and broad; per-mode phase drift
  (+-0.06k rad/month, seeded sign) makes k=1 lap in ~9 years
  (persistent) and k=3 in ~3 (chaotic seasons). Two batched
  Dirichlet solves: the unobstructed harmonic extension (landmass
  pins AND the high layer) and the obstacle solve against the
  relief pins. Same smooth-distributed forcing as the ramps, so
  still no funnels/singularities — but several inflow/outflow
  arcs instead of one. theta/theta_jitter/theta_phase draws gone
  (rim_amp/rim_phase/rim_drift/wobble_phase instead). On the
  all-ocean 48 test grid: max/interior speed ratio ~1.35 (funnel
  bound is 4), cos(month0, month1) = 0.998 and cos(month0, month6)
  = 0.94 (persistent, evolving), 10 rim-flux sign changes (5
  inflow + 5 outflow arcs). Test asserts all four properties.
  271 fast pass.

- Ground-relative low layer (user redesign of the whole persistent
  wind system): the low-layer wind is wind RELATIVE TO THE GROUND,
  so absolute altitude can never block — only terrain SHAPE along
  the path may. The pin-solve propagation (all-or-nothing obstacle
  islands, sub-threshold slopes invisible) and the altitude-keyed
  over-the-top bleed are gone. New _terrain_flow: the rim-harmonic
  free stream (unobstructed harmonic extension — also the high
  layer, now pinless) is propagated by semi-Lagrangian sweeps with
  kinetic-energy accounting per hop: ascent v'^2 = v^2 -
  _CLIMB_COST*Δa, descent v'^2 = v^2 + _CLIMB_COST*|Δa|
  (_CLIMB_COST = 1.0 in normalized-altitude units: unit-speed flow
  exactly stalls over the full ~6 km range, pays ~8% over 500 m).
  A parcel whose next step is unaffordable ROTATES exactly (speed
  conserved — re-stalling would bleed the face jet to zero over
  sweeps) onto the local contour in open air before the rise;
  along-face sign keeps the parcel's drift, ties break toward the
  descending contour. Parcels that cannot afford a hop do not
  arrive — a _STALL_SEEP (0.1) share leaks (never hard walls).
  Blocking, drag, rain-shadow winds, ridge winds and valley
  channeling all emerge from slope in the path; foehn acceleration
  off descents emerges too. Verified on synthetic terrain: gentle
  3 km ramp crossed at ~0.74 speed; full-range wall gives a
  meridional face jet + 0.12-speed lee; flow routes around an
  isolated block's ends at full speed; constant-shifting the
  terrain changes nothing (altitude irrelevance). High layer:
  unobstructed solve, curl is solve residue only (test) — no
  singularities aloft. Known sketch artifact: a thin full-height
  block leaks a full-speed wake via diffusion + descent gain.
  Strength normalization switched to per-month MEAN transport
  (floored at 0.25x the year median) — modal interference in the
  rim forcing made months 4/10 collapse under max-normalization
  (seed 18). Gyres keep the pin solves (transient mechanics
  unchanged); breeze/katabatic/frontal-lift/subsidence/friction
  untouched. 272 fast pass.

- Flow-line gridlines fix (same system): the first _terrain_flow
  advected the FIELD itself — self-advection of a smoothly-varying
  field is not idempotent, so over flat ground it re-solved
  transport from the rim by characteristics and the interior
  striped into discrete rim-cell bundles (the gridline render
  complaint). Relaxing toward the free stream fixed the stripes
  but washed out path energy (climb loss recovered in place —
  wrong; kinetic energy is a path property). Final form: advect
  the DEVIATION from the free stream along the total field, work
  it, no decay — flat ground keeps the prescribed field exactly
  (verified 0.0 deviation on a sinusoidal field), the ramp keeps
  its ~0.74 terminal speed, the face jet runs at ~0.94, the lee
  shadow persists at ~0.12 with the seep. 272 fast pass.

- Wind cost trim + climate grid 64^2: profiling the demo (95s
  total under cProfile) put moisture _advect at 28.7s (the
  elephant), _terrain_flow at 9.6s, SOR 11.9s, advect_sst 9.6s.
  _terrain_flow is now batched over the 12 monthly free streams
  (one call, bitwise-identical to per-month calls — the batched
  gather idiom), the contour direction and descending-side
  tie-break sign are precomputed once per grid (static — 6
  gathers/sweep down to 4), and sweeps run at max(ph, pw) (64 vs
  128 sweeps differ ~3% on a full-wall test — conditioning, not
  convergence). The climate coarse grid (moisture advection, T/P,
  delivered snapshots) drops from 128^2 to 64^2 (build_climate
  coarse default 96 -> 64, an exact integer pool of the 256
  anchor): 4x less advection work. The wind psi grid is 64^2
  either way (f_psi becomes 1), so the solves are unchanged.
  272 fast pass.

- Forest wind: cover now enters the pass-2 propagation as a weak
  effective rise (_FOREST_RISE = 0.02 of the normalized range,
  ~120 m-equivalent — flow pays a climb cost into forest and
  prefers routing around big forest masses; verified: ~1% field
  delta localized to the block), and the post-sampling windbreak
  drag strengthens 0.25 -> 0.4. Desert/ocean-rain diagnosis
  (seed 18 + 1 measurements): the subsidence drying oscillates
  seasonally (0.75 winter / 0.16 summer, katabatic+monsoon
  driven) and cancels annually (corr(sub, P) over land = -0.08);
  the thermal overturning that would organize stationary belts
  runs at ~10% strength under the fixed x8 gradient clip
  (continental grad T ~ 0.01); and the chaotic multi-arc wind
  delivers marine moisture everywhere over the year. Open ocean
  is dry because capacity stays high with no lift and only
  weak/patchy convergence — the ITCZ analog is the same muted
  overturning. All three share one root: the persistent-structure
  term is weak.

- Propagation damping (_terrain_flow `drag` parameter): the
  propagation was fully conservative before (climb cost returned
  on descent; only sinks were the stall seep and post-sampling
  friction). Now an optional quadratic roughness-drag field
  decays the TOTAL field per distance traveled (1 - c*speed per
  hop — slow air is not over-damped), so absorbed momentum is
  never returned and the free stream itself arrives weaker
  downwind of rough ground. Forest cover (pass 2) uses it:
  _FOREST_DRAG = 0.1 at full cover (~65% loss over 10 cells,
  ~90% over 20 — real canopy is a very effective windbreak),
  alongside the _FOREST_RISE reroute. Verified: a forest band
  cuts unit flow to 0.42 at the exit and it STAYS 0.42
  downstream (absorption, no recovery); drag=None reproduces the
  old path bitwise. The post-sampling 0.4 windbreak multiplier
  stays for the gyre/breeze terms the propagation does not
  touch. 273 fast pass, seed 1 verdict PASS.

- Land friction moved into the propagation: bare land now absorbs
  along the path (_LAND_DRAG = 0.03 quadratic — ~25% lost over 10
  cells, giving flow a routing preference for smooth surfaces and
  sea lanes), and the post-sampling multiplier drops to a 0.2
  residual covering only the unpropagated terms (gyres, breeze,
  katabatic, overturning) so the prevailing is not double-counted.
  273 fast pass, seed 1 verdict PASS.

- Agreement-seeded subduction (_sub_seed): the subsidence band is
  now seeded only where the surface wind DIVERGES and the
  high-layer wind CONVERGES over the same spot (min of the two,
  4x-pooled and smoothed, p90-scaled). Shallow circulations
  (breeze, katabatic, friction dipoles) fail the high-layer vote
  and drop out; the thermal overturning passes by construction.
  Result on seed 18: the seasonal flip-flop is GONE (month means
  0.05-0.21, was 0.75 winter / 0.16 summer) and the annual field
  has real sparse structure — but the overall level is low
  (mean ~0.12), so drying is still too weak to carve desert
  biomes (land P mean 0.19, 17% of land < 0.1, no desert class
  in the top shares; corr(sub, P) = -0.05). The veto works
  mechanically; levels, not structure, are now the limiter.

- Rain-fueled subsidence (replaces the divergence seeds): the
  subsidence seed is LAST MONTH'S RAIN ANOMALY (mean + 1 std, one
  light box pass, p90-normalized) — rainfall is the measured
  exhaust of rising air; what rains must come down. Month m seeds
  from this pass's m-1; January wraps from the previous pass's
  December (pass A scaffold: dry seed; pass B wraps exactly).
  Transport rewritten twice: the old band-recharge rule saturated
  S to near-1 wherever the band was appreciable (0.7-0.95
  everywhere); relax-to-band kept S on the rain cores themselves
  (corr +0.6 — drying the wet zones). Final form: pure
  advect-decay plumes (_SUB_DECAY 0.98, 24 steps, seed gain
  _SUB_GAIN 2.0) that CONCENTRATE where the high-layer flow
  converges (descent = convergence aloft). Seed 18: sub p50 0.04
  / p90 0.58 / p99 1.0 (right-shaped distribution), corr(sub, P)
  over land -0.07, sensible seasonal structure (summer highs).
  Still no desert biome class at scale — the saturated zones
  cover ~1% of cells; the next lever is drying response or seed
  gain, not structure.

## 2026-07-24: revert-and-graft (wind system rollback)

The saga above ended with the wind system measurably WORSE than the
committed baseline (fewer biome classes, no deserts, no moist tropical
forest, singularity-prone fields). Call: revert wind/climate to the
committed code and graft onto it only the mechanisms that had proven
themselves in isolation. Not a git revert — the committed currents
renderer had an x/y transposition bug that sent flow lines into land,
so the fix was: restore committed `climate.py` + `test_worldgen.py`
from HEAD, keep the uncommitted current/render/terrain fixes, then
re-apply the graft list by hand.

Kept (uncommitted, unrelated to the wind regression):
- `currents.py` — current fixes incl. the u=x/v=y renderer correction
- `render.py` — current-flip fix, `(sub)tropical` legend labels,
  resolution-independent flow lines
- `plates.py` — land grain 0.32 -> 0.45
- `__main__.py` — `P_prev` wiring between the two precip passes
- `persist.py` — climate dict keys (incl. the new `sub_monthly`)
  round-trip as `c_*` arrays

Grafts re-applied onto the committed wind stack:
- Coherent, breathing gyres: gyre cells WOBBLE (_GYRE_WANDER cells)
  instead of teleporting between months, alpha keeps a fixed sign per
  gyre, and each solved gyre contributes a divergence field
  (`gyre_div`, psi>0 = anticyclone = diverge) blended into the
  rotational flow — cyclones wet, anticyclones dry by construction
- Rain-fueled subsidence (`_rain_seed` + plume advect-decay with
  high-layer convergence concentration) — the end state of the saga
  above, kept because its distribution was right-shaped
- Forest windbreak as quadratic path drag (`_drag_flow`,
  _FOREST_DRAG 0.1, 16 sweeps): canopy absorbs momentum, absorbed
  momentum is never returned — flow leaves forests weaker and routes
  around; the old per-cell multiplicative damp is replaced in pass 2
- Ascent rain (_ASCENT_RAIN 0.15): convergent low-layer flow rains
  directly — the gyre cells' wet/dry signature
- Moisture recycling 0.15 -> 0.30, advect baseline 0.06 -> 0.03
- Climate grid 64^2 (was finer), sub_monthly delivered in the climate
  store (coarse (12,64,64)) for downstream ecology layers

Dropped (saga machinery, not coming back): Hadley overturning term,
frontal lift, `_terrain_flow` mechanical propagation, rim source/sink
segments and braided wall partitions, porous/reflecting boundary
variants, Helmholtz-pure band flow.

New tests: `test_rain_seed` (cores seed, ordinary rain does not),
`test_drag_flow` (momentum absorbed along path, zero drag = identity).

Addendum (same day, later): two mechanisms added during the
post-graft debugging were REMOVED on review — a heat-low (ITCZ)
inflow term and a hot-land evapotranspiration loop (_CONV_EVAP).
Decomposition of the persisted wind showed the heat-low term was
itself the hot belt's winter-divergence driver: in winter the
annual-hottest land is not hot, so a term keyed on the temperature
anomaly pushes air OUT of it (month 0: +0.42 of the +0.8 total).
Ruling: tropics are not a circulation parameter — they show up
naturally where mountains force rain; a flat hot belt staying dry
forest/savanna is correct output, not a bug. Kept from that round,
because it is parameter-free: subsidence plumes cannot stack over
active low-level convergence (sub *= 1 - ascent, reuses
_ASCENT_DIV) — the ITCZ and a subtropical high never share a
column, and orographic convergence keeps its rain. Verified across
seeds: moist forest 0.17% (seed 2), 0.09% (seed 5), 0% on seed 1
(flat hot belt, mean 287 m — dry forest 8.4% instead), 0% on
seed 18 (realistic patch centered 40 degN — no true tropics in the
patch by design). All demo verdicts PASS.

## 2026-07-25: wind rebuilt as a two-layer fluid (WindLibrary deleted)

The kinematic wind stack (prescribed bands + random fbm gyres + stapled
divergence terms + scalar friction, psi pinned on a boolean obstacle
mask) is GONE. Replacement: exp/k11_worldgen/wind.py, a two-layer
rigid-lid fluid at 128^2 (was 64^2), developed test-first
(exp/k11_worldgen/test_wind.py — 9 physics tests, all green before
integration).

Surface layer: semi-Lagrangian momentum advection, thermal pressure
forcing (hot = low, force = +ALPHA*grad(T)), constant-f Coriolis
(seeded sign — this is what spins convergence into cyclones), Brinkman
drag -u/K(x) with K continuous from local relief + altitude + forest
cover (terrain is NEVER a step function; trees are windbreaks in the
surface drag field), pressure projection to a TARGET divergence
D = -(u.grad h)/H_EFF - buoyancy*(T - spatial mean) — not to zero;
the vertical-motion budget survives the solve. Projection is exact
(backward-div / forward-grad compose the 5-point Laplacian, solved
spectrally via DST built on numpy FFT, Dirichlet-zero rim = porous).

Middle layer: mass compensation only (div(H_s*u_s + H_m*u_m) = 0),
no thermal forcing, no terrain. Middle-layer convergence = descent
into the surface column — the subsidence seed (as ANOMALY above
mean+std, cores only; the raw D is a smooth seasonal blanket that
dries nothing). Momentum exchange between layers proportional to w
(rising air carries momentum up, subsiding brings it down), bounded
transfer fraction; tanh speed governor against runaway cells.

High layer: untouched role — a non-interacting highway (blended fbm
curls + weak drift) transporting subsidence plumes.

Momentum budget: sources = thermal pressure work + the constant
background drive (a rim velocity hold alone CANNOT sustain flow
against drag — pressure work does; measured: through-flow decays to
zero in ~6 cells on land without a drive); sinks = ground drag
(terrain form drag, canopy) + rim outflow; Coriolis and the
projection redistribute.

Pipeline: build_climate computes equilibrium T, simulates ONE wind
trajectory through the year (_wind_ensemble), transports T along it,
runs both precip passes against the SAME ensemble. Deleted: bands,
gyres, gyre_div, breeze/katabatic/bleed/friction staples, psi
obstacle solve, smudge, _drag_flow, _rain_seed, band_divergence,
P_prev wiring.

Known deltas vs the old stack: biome mix runs wet (desert classes
rare — accepted, see conversation; the drying side comes only from
structured subsidence now, and the fluid distributes moisture
efficiently). Demo runtime roughly doubled (fluid at 128^2 + 4x
advect cost). Seed 2 ranges_exist marginal-fail is terrain-side
(max peak 0.709 vs 0.72 bar), not wind.

## 2026-07-25 (final): resolution layout, volcanoes, K11 sealed

Resolution split after the blockiness review (marine classes read
coarse-field threshold contours directly as class edges; terrestrial
biomes classify nearest-distance and escape it):

- 64^2: wind fluid, moisture advect, subsidence transport
- 128^2: T transport, gain pin, soil, delivered monthly T/P
- 256^2: anchor world, currents fields
- 1024^2: delivery/biomes/render
Demo ~60s (was 2m27 at the fluid's first integration).

Volcanoes: build_volcanoes (plates.py) stamps 4-7 seeded cones
(2.2-4.5 km, crater dip) on convergent faults right after elevation,
before carve/hydrology — rivers route around them for free. Metadata
in world.json ("volcanoes"), tallest marked VO1 on world.png, rest
textless red dots; new WT1 (wettest point) landmark evens the legend.

End of K11.

## 2026-07-25 (addendum): parked circulation pair + gain-pin loosening

Deserts and moist tropical forest now exist by MECHANISM: a parked
ITCZ low (seeded among the hottest coastline cells) and 1-2 parked
subtropical highs (seeded on warm-half coasts) enter the fluid as
permanent divergence features (WindModel.parked, D units) — the low's
convergence rains, the high's anticyclone exports moisture, the
rigid-lid closure + highway carry the spent air between them.
Seed 1: desert 10.8%, moist tropical forest 0.15%. The seasonal
sub-swap is gone (the parked component anchors the field).
Air mass conserved by the rigid-lid closure (physics tests); water
redistributed, not created. Gain-pin bounds loosened [2,24] ->
_GAIN_LO/_GAIN_HI [1,64] (the clamp left paired worlds dry).
