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
