# K11 — worldgen_l0 — the raster world sketch with PNG rendering

## Goal

Generate an actual L0 world (game-layer RFC §1, A1 §3), in two passes:
pass 1 runs the full pipeline in honest dependency order (kinematic
template plates → elevation → hydrology → currents → climate on bare
ground → biomes → forest cover); pass 2 is the coarse second-order
rerun (hydrology conditioned on the pass-1 climate, climate
conditioned on the REAL pass-1 forest cover and the new water —
same K1 stream, same weather systems — then biomes/cover/aquatic/
complex re-derived). The pass-2 states are the delivered world.
Deterministic (K1 `Stream` only; no random, uuid, or
wall-clock), numpy allowed, stdlib PNG writer (no Pillow).

Sub-chunk decision (discussed 2026-07-22, specs are blank on sub-chunk
detail): bulk natural features are **density fields** (forest cover % per
cell); individual trees/rocks are deferred — bulk = counters, individuals =
samples, special ones = C5 latents.

## API

Experiment home: `exp/k11_worldgen` (not yet promoted).

- **`raster`** — `value_noise(stream, shape, cell_size)` (K1-lattice value
  noise, resolution-independent at lattice points), `fbm`, stdlib writers
  `write_png_gray/palette/rgb`, `normalize_u8`, `distance_to_mask`
  (chamfer), `nearest_values` (multi-source Dijkstra carrying boundary
  values outward).
- **`plates`** — `Plates(stream, shape, n_dots, n_plates)`: many-dots
  Voronoi fine partition evaluated at **domain-warped coordinates** (every
  boundary in the system comes out a curve, never a Voronoi straight
  line). Border fine cells are reserved for ocean BEFORE gluing (the only
  guaranteed ocean); interior cells glue into macro plates (seeded growth
  on longest shared borders). Each macro plate draws continental (base
  above sea level) or oceanic (below) — interior seas emerge.
  `build_elevation(...)`: per-plate base + shelf pull-down/push-up +
  a real continental-shelf profile (below-sea cells reshaped by
  distance to the provisional coastline: ~15 m at the shore -> 200 m
  at the break ~46 km out, then a steep rise into the plate base;
  faults carve AFTER, so active margins keep narrow shelves) +
  fault signatures by CRUSTAL-TYPE PAIR (user 2026-07-23: real fault
  behavior depends on the crust of both sides) — CC: broad uplift/rift;
  OC (Andes-type): trench offshore + coastal range inland; OO
  convergent: trench on the subducting side + volcanic ISLAND ARC on
  the overriding side (strong enough to breach — island chains); OO
  divergent: mid-ocean ridge (stays submerged). Mixed margins are no
  longer invisible. Subducting side: oceanic always dives under
  continental; OO picks the plate moving more into the other. The
  reserved border ring gets NO signature (guaranteed ocean buffer).
  Surface noise is mixed by position vs sea level (land texture in
  sparse rough patches, textured abyss + seamounts).
- **`hydrology`** — `priority_flood` (lake surface = outlet-sill height,
  equipotential by construction), `_cap_inland_seas` (a filled basin
  whose floor dips below sea level is capped AT sea level — real inland
  seas are shallow and never stand at a phantom rim-sill surface;
  judged by the water balance on the capped surface, accepted ones
  become ENDORHEIC terminals — rivers flow in, nothing flows out —
  rejected ones keep the flood surface and drain through),
  `_submerge_islets` (speck islets stranded by the cap are sandbars,
  not blocky artifacts), `flow_direction` (D8 + BFS flat
  resolution, returns flat-depth), `flow_accumulation` (sorted by
  descending (w, flat-depth) — exact on flats), `strahler_order`,
  `build_hydrology`: lakes first — 1-cell puddles dropped (small ponds
  are the small-lake smattering, user 2026-07-23), then a water-balance
  filter keeps a basin as a lake only if inflow ≥ α·area AND it fits a
  per-basin K1-drawn size cap (25 + 425·u⁴ cells — mega-lakes exist but
  are special, never routine); lakes 8-connected to the ocean are
  ABSORBED into it (bays/lagoons) — then rivers = accumulation above an
  elevation-biased threshold OUTSIDE lakes. Rivers carry discharge,
  Strahler order, width class (1–3); sources are headwaters or lake
  outlets, sinks ocean or lake inlets. `classify_salinity` then grades
  every water cell 0..1: ocean = 1, rivers = 0 (estuary band on the
  sea = brackish 0.25), lakes fresh when the drainage walk reaches the
  ocean (EXORHEIC) or salted when it terminates in the basin
  (ENDORHEIC — level falls with the flushing ratio inflow/area, so a
  giant inflow keeps even a terminal lake brackish, Caspian-style).
  Relational, decided at the anchor grid; carried to delivery.
  `refine_hydrology` (second pass, after climate — user 2026-07-24):
  precipitation-conditioned small features, ADDITIVE only. Ponds the
  uniform balance rejected are re-judged on P-weighted inflow vs
  temperature-scaled evaporation (taiga hollows fill, hot basins
  don't); streams sprout where the P-weighted discharge clears the
  area threshold at mean land wetness, so drainage density follows
  the rain (a wet highland feeds trunk streams through dry country
  downstream — Nile effect). Also computes the P-weighted discharge
  the river-mouth marks are ranked by. Order/width/salinity/HAND are
  recomputed afterwards; routing surfaces are untouched.
- **`climate`** — `WindLibrary` (precomputed wind patterns: the
  prevailing flow is a chaotic through-flow — the rim
  streamfunction is a few seeded low harmonics around the
  perimeter, so air enters and leaves at several broad arcs: no
  single prevailing direction, no sources/sinks, divergence-free;
  k=1 dominant and persistent, higher modes drift faster. The LOW
  layer is GROUND-RELATIVE (_terrain_flow): the free stream
  propagated through the terrain with kinetic-energy accounting —
  climbing costs, descending returns, unclimbable rises rotate
  parcels onto the contour (routing around massifs, ridge winds)
  — slope in the path, never absolute altitude — plus
  chaotic gyres from stream-function curl + land–sea breeze;
  mountains DEFLECT and DAMP the sampled low-layer flow —
  momentum sees terrain, not just the moisture accounting; a HIGH layer
  — through-flow inverted, no terrain, no breeze — advects the
  subsidence field seeded by the mean surface wind's divergence,
  drying the low layer where it descends: subtropical deserts can
  sit beside warm seas),
  `build_climate(elev, hydro, sea_level, seed, coarse, n_samples,
  t_knobs, realistic, center_lat, shrink, currents, green)`: temperature first
  (wind-independent; profile knobs t_north/t_span/t_pow/t_amp are
  generation-side variation, tuned against the classifier's real-world
  prototypes — OR `realistic=True` earth-patch mode: the map is a
  northern-hemisphere patch of the real Earth, row → latitude from
  `center_lat` (unset = 45°N +
  per-seed wiggle, ±5 leaky) and a planet `shrink`× smaller (6× →
  ~55° span), temperature interpolated from zonal-mean Earth
  anchors (`_lat_profile`, climate.py); winds stay random in both
  modes), monsoon strength per month read off the ACTUAL
  land–sea heating anomaly, N chaotic snapshots per month advect
  moisture on the coarse grid (64², upsampled/smudged; ocean recharge
  scales with water temperature — cold seas barely evaporate;
  convection rains where the air is hot), then
  `refine_climate` runs ONE damped conditioning round — snow-albedo
  feedback, evaporative/cloud cooling, cloud swing damping — T
  conditioned on P, never iterated (see spec-notes). `green` is the
  forest cover the water cycle feels (evapotranspiration,
  interception, windbreak) — a SECOND-ORDER input, supplied only by
  the pass-2 rerun from the real pass-1 biomes; pass 1 runs bare.
  Land-mean
  precipitation is pinned to ~0.19 normalized (~76 mm/month, the
  real-world land average) by an adaptive gain with one corrective
  rescale. Canonical output
  = 12 monthly (T, P) mean curves per cell. Per-day states are a
  gameplay concern and are NOT generated.
- **`units`** — the FIXED normalized→metric mapping (temperature 0..1 →
  −30…+35 °C per month, precipitation 0..1 → 0…400 mm/month, elevation →
  −4000…+6000 m around sea level). The only place physical units exist;
  never a tuning knob — adjust generation gradients, not the units.
- **`biomes`** — month-vector classifier: each cell's 12-month (T, P)
  curve goes through the units layer (°C, mm/month) and is matched by
  weighted Euclidean distance against prototype MONTH VECTORS built
  from real-world climate normals (Singapore for tropical moist,
  Siberia for taiga, páramo for montane grassland — seasonal phase
  included, so Mediterranean winter-rain and monsoon burst signatures
  are first-class). The vocabulary is exactly the WWF / Olson &
  Dinerstein terrestrial classes (14 biomes + the abiotic land zones,
  split into "rock" and "ice");
  ocean/lake are water masks, not biomes. Nearest-distance in 24-dim
  climate space keeps boundaries organic (a threshold tree draws
  straight isotherm bands — rejected on review, 2026-07-23). The only
  overrides are the geographic classes: flooded grassland (inundation),
  mangrove (frost-free tidal fringe < 10 m), rock (nival relief above
  the vegetation line), ice (never above freezing). Earlier extras
  (montane forest, cloud forest, snow peak) were dropped into the WWF
  classes. WWF freshwater/marine lists not modelled. River cells keep
  their land biome (see spec-notes).
- **`complexify`** — `derive_complex(hydro, biome_map, names)`: river
  sources/confluences/outlets → K9 nodes, downstream walks → river edges
  with GRID-TRUE polylines (edge `quality` = mean width class; the
  committed geometry stays on the raster so the audit's
  nodeless-intersection invariant holds — seeded de-gridding wiggle is
  applied at rasterization, see deliver.river_raster), same-biome
  components ≥ 16 cells → patches.
- **`render`** — `render_all` writes the 1024² set (elevation / depth /
  temperature / precipitation / biomes / forest_cover / hydrology);
  `render_monthly` writes the unaveraged monthly curves to
  `out/monthly/`; `render_plates` draws the tectonic diagram (plates.png);
  `render_world` draws **world.png** (2048×1024: hillshaded biome map on
  land — water is NEVER hillshaded, ocean and lakes share one
  bathymetric gradient on bed elevation (lakes in a fresher tint) —
  plus rivers, RIDGE LINES
  (1 px black polylines connecting high peaks wherever a high-enough
  ridge path exists — ranges are terrain, not fault lines), 2 px white
  plate lines, and landmark markers on the left; legend with seed /
  stats / two-column (column-major) biome key / landmark key on the
  right — hand-rolled 5×7 bitmap font, stdlib only);
  `LoadingSink` writes `out/loading/load_01..16.png` — one image
  per pipeline stage, each NAMED in the top-left corner, following
  the computation DAG: pass 1 (PLATES, ELEVATION, CARVE — with the
  carved notches tinted, HYDROLOGY — water+rivers composite,
  CURRENTS — the absolute vorticity-seeded field, PRECIP 1, TEMP 1,
  BIOMES 1) then the pass-2 second-order
  rerun (CURRENTS 2 — the wind-correlated field with speed-delta
  tints against the seeds-only baseline, WETLANDS, PRECIP 2, TEMP 2,
  BIOMES 2, AQUATIC) and DELIVERY
  ELEV / DELIVERY BIOMES — LIVE
  as each build stage
  completes (the demo passes the sink down the pipeline), copying each
  to `seed_N/load.png` (a real file, not a symlink, so watchers that
  can't follow symlink swaps still refresh); `render_loading` is the
  batch path for the re-render subcommand (the dump holds the final
  world, so the pass-1 scaffold screens 6-8 are demo-live only);
  the demo also links
  `out/world_<seed>.png` -> the seed's world sheet.
- **`marks`** — `compute_marks(delivered, hydro, sea_level, factor)`:
  the N highest peaks (spaced regional maxima, meters via units), the
  deepest ocean point, the M largest lakes (km²), the L lowest
  terrestrial points, and the biggest river mouths by basin area;
  `compute_range_lines(delivered, sea_level)`: ridge polylines between
  ALL summits above a threshold (spaced regional maxima, capped) —
  candidate edges to k nearest neighbors, BFS-killed when no
  high-enough ridge exists, crest walk back along the highest reached
  neighbor, then a maximum spanning forest over saddle heights so
  already-connected peaks keep only the highest path (no tangled web).
- **`persist`** — `save_world(out_dir, ...)` dumps a built world to
  `seed_N/world.json` (human-inspectable manifest: params, stats,
  marks, plates metadata, full complex, checks, array inventory) +
  `seed_N/world.npz` (compressed rasters). The dump is the COMPLETE
  world state: elevation/hydro/climate/biome/cover/aquatic rasters,
  plates arrays, delivered grids, the full ocean-current state
  (per-source stream functions + blend weights, annual velocity,
  upwelling rise, depth, gyre parameters, vmax — `velocity_field(month)`
  works from a loaded dump — plus `r_rise_m`, the monthly upwelling
  field: the nutrient-circulation store for downstream kernels), and the weather
  pattern proper — the N chaotic surface-wind snapshots per month
  (`c_wind_u`/`c_wind_v`, (12, n_samples) at the coarse climate grid)
  that the monthly T/P means average over; gameplay interpolates
  between a month's snapshots instead of re-deriving weather. `load_world` /
  `load_complex` read them back. Basis for the `render` subcommand and
  for future kernels that consume world state.

## Demo

`uv run python -m exp.k11_worldgen demo --seed 1 [--json]
[--check-determinism] [--realistic [--center-lat D] [--shrink S]]`
builds the world and writes everything under
`exp/k11_worldgen/out/seed_<seed>/`:
the seven main PNGs plus world.png (2048×1024 sheet with legend),
plates.png, `monthly/`, `loading/`, and the **world dump**
(`world.json` manifest + `world.npz` rasters). `--realistic` switches
temperature to the earth-patch mode (northern hemisphere; winds stay
random); the mode is recorded in the dump's `stats.climate_mode`.
`uv run python -m exp.k11_worldgen render --seed 1` re-renders all
PNGs FROM THE DUMP in ~3 s — iterate on draw logic without the ~30 s
world build (dump format: persist.py). It then runs nine checks:
ranges_exist (high-relief fraction, or
one >3.6 km peak — slim arcs fail the area test but are still ranges),
large_ocean (25% < ocean < 75%), rivers_exist,
drains_to_ocean_or_lake (flow walk from every river cell),
rivers_avoid_lakes, lakes_equipotential (w constant per lake component),
biome_coherent (≥5-of-9 same-biome neighbors), complex_audit_clean (no
fatal defect classes), complex_nontrivial. Exit 0 iff all pass. A tenth
check, determinism (rebuild + byte-compare, doubles runtime), runs only
with `--check-determinism`.
~30 s per seed (was ~90–120 s: the lattice-noise draws go through the
K1 batch mixer `Stream.u64_batch` — 9e6 scalar BLAKE2b calls were 70%
of the build; the pass-1 climate scaffold runs at half samples while
the final pass-2 climate keeps the full weather library; biome
accumulation is float32).

Scale semantics (user, 2026-07-22): the L0 ANCHOR grid is 256² at **4 km
cells** (map = 1024×1024 km — a continent); DELIVERY is 1024² at **1 km
cells**, produced by the resolution ladder (deliver.py). Small rivers,
groves, boulders and other sub-cell features are NOT generated here;
they arrive at refinement (K9 subdivision / C5 latents). K11 rivers are
the major drainage only.

### The resolution-ladder rule
An upscale step may only do MECHANICAL work; anything relational must be
finished before it ("intensive = lower scale", user 2026-07-22):
- **Relational/intensive** (plates, faults, flood, accumulation, water
  balance, advection, Strahler): computed ONCE at the anchor grid
  (climate even coarser, 64² — weather systems are synoptic-scale).
  Never recomputed after upscaling.
- **Continuous state fields** (elevation, water surface, monthly T/P):
  bicubic interpolation, inventing no detail (sub-cell detail is L1's
  explicit job). A gentle fine-noise anti-aliasing pass was tried here
  and REVERTED (2026-07-23): it did not actually de-grid coastlines,
  and it re-speckled lake interiors.
- **Derived/pointwise** (masks, biomes, cover): re-derived at the target
  resolution from the interpolated parents. Never interpolate a mask
  (half-water cells) or a class map (blocky borders). The AQUATIC layer
  splits along the same line: marine classes (shelf zonation, coral,
  upwelling) are pointwise in depth/temperature/rise and are recomputed
  at the delivered grid; only the relational classes (lakes/seas per
  component, rivers from anchor order/width) ride the anchor→kron path,
  with a distance-ordered nearest spread across the boundary band.
  Exception: LAKE
  EXTENT is an anchor-level decision (water balance is relational):
  the lake interior is the carried fact (eroded anchor mask), only the
  boundary band re-derives from the interpolated fields, and small
  enclosed land specks are filled back in (delivery re-speckles what
  the anchor drowned).
- **Vector geometry** (river network with discharge/Strahler/width,
  complex nodes/edges): resolution-free — coordinates scale ×4,
  polylines get seeded interior-vertex wiggle (against D8 diagonal
  lock) + Chaikin smoothing, rasterized on demand. Rivers are
  never 4×4 blocks of "water pixels".
- The test for any future field: does its definition involve neighbors?
  Yes → below the upscale line; no → above it.

Consequence: **a river cell is not water**. It means "major drainage
crosses this cell" — the cell keeps its land biome (riparian forest,
marsh, farmland-to-be), and rivers render as an overlay (hydrology.png:
yellow edge polylines; blue fill is standing water only). Refinement sees
the land biome underneath and places the actual channel inside the cell.

## Verdict

**works** (2026-07-22; frame revised thrice same day, seasonal climate
added). 19 tests: PNG round-trips (gray/palette/rgb, signature + pixel
equality), noise determinism + lattice-point resolution independence +
fbm bounds, plates (border ring reserved for ocean, plates contiguous or
island-ringed, guaranteed-continental hygiene, faults carry signed
convergence), elevation frame (border deep ocean, land inside, relief
clustered near faults, determinism), priority flood (w ≥ h, bowl
equipotential), flow walk reaches ocean or lake, rivers lakes-first +
discharge non-decreasing + width classes, climate (deterministic from
seed, 12-month curve shapes, north-cold, altitude cooling, seasonality
present, interior not rain-shadow desert), biome water overrides +
rivers stay land, complex derivation clean + deterministic, diagonal
X-crossings expanded through corners, bicubic upsampling (constants
exact, planes exact away from the clamped border), delivery smoke
(shapes, mask consistency, rivers avoid lakes, determinism). One
slow-marked test runs the full demo checks.

Demo seed 1 passes all ten checks; PNGs visually verified at the
delivered 1024² (smooth organic coastlines, textured relief, thread
rivers, broad biome regions, latitude stack from ice cap through
tundra/montane bands to temperate forest — see the units spec-note for
why tropics are honestly absent under the current climate variation).
Repo-wide: 256 pass, 4 deselected (slow-marked, expected).

## Spec-notes

### Kernel audit changes (2026-07-22)
- `kernel/complex/audit.py` terminus vocabulary extended with `source` and
  `outlet` — river endpoints are legitimate degree-1 termini by
  construction.
- `isolated_patch` is now skipped when **no** patch commits boundary edges
  (`any(adj.values())`): a complex that never claimed edge-committed patch
  adjacency is not faulted for lacking it. K11 patches are biome components
  whose adjacency is raster-derived at L0 (`boundary_edges=()`); it becomes
  edge-committed at L1.

### L0 fidelity
- `disconnected_component` is expected at L0: each watershed is a disjoint
  drainage tree; roads connect basins at L1/C5. The demo treats only
  `dangling_edge`, `nodeless_intersection`, `isolated_patch` as fatal.
- D8 diagonal steps are expanded through corner cells in edge polylines:
  two anti-diagonals in one cell would geometrically cross without a node
  (raster artifact flagged by the K9 audit).
- Patches carry `DriftField(mu=centroid, theta=(0.1,0.1), sigma=(1,1))`
  placeholders; real patch dynamics are K8's business.
- Plates are kinematic **templates** (equilibrium passes only), never
  simulated tectonics (RFC §1).

### Climate model (user, 2026-07-22)
- **Climate is chaotic; we sample it, never simulate it.** A small wind
  library is precomputed (latitude zonal base + gyre curls + land–sea
  breeze); N=8 snapshots per month interpolate randomly across the
  library (K1 phases); semi-Lagrangian advection yields each snapshot's
  precipitation. Month is the CANON time period; the canonical store is
  the 12 monthly N-sample mean (T, P) curves.
- **Per-day states are gameplay's concern, not K11's** — the game
  interpolates between adjacent canonical samples with a random-walk
  mix (uniform in space, random in amount): weather looks similar before
  the Lyapunov horizon, diverges after, and grand-scale patterns stay
  authoritative.
- **Biomes use metric month-vectors** (user, 2026-07-23): monthly
  (T, P) curves go through the units layer (°C, mm/month) and match
  prototype 24-dim month-vectors (real-world climate normals per
  biome) by weighted Euclidean distance. The vocabulary is exactly
  the WWF/Olson terrestrial classes; only the geographic classes
  (flooded grassland, mangrove, rock, ice) enter as overrides.
  History: (1) normalized prototype vectors — parameters unmoored;
  (2) Köppen threshold tree in metric — real parameters, but
  axis-aligned thresholds draw straight isotherm/isohyet bands across
  continents ("clearly straight lines across boundaries", rejected on
  review); (3) current: metric vectors — real parameters AND organic
  boundaries. The biome MIX is never calibrated: an absent biome is an
  honest statement about the world's climate, fixed via climate
  GRADIENTS/VARIATION, never via units, thresholds, or prototypes.
- Wind/advection run at 64² (upsampled — refinement smudges anyway);
  more samples per month are affordable at coarse granularity.
- **Base circulation is randomized per world, semi-stable** (user note
  2026-07-22): fantasy world — no ocean streams, no rest-of-world, so
  hardcoded westerlies are unjustified. Bearing/strength/band are drawn
  once per world and held stable across months; only gyres and breezes
  vary per sample. This removed the systematic west-coast wet bands.
- Main PNGs (`temperature.png`, `precipitation.png`) render the ANNUAL
  means; the unaveraged monthly curves (the canonical store) render to
  `out/monthly/m{01..12}_{T,P}.png`, the monthly subsidence (drying)
  field to `out/monthly/m{01..12}_sub.png`.
- Seasonal surface states (winter snow on tundra/seasonal forests) are
  runtime decoration on the monthly curves — game-side, not K11.
- River seasonal metadata (size change / dry-out / flood by weather) is
  deferred to the detailed decoder; K11 rivers keep discharge, Strahler
  order, and width class only.
- Moisture physics still applies: climate sees the water surface as
  terrain (no coastal cliff); lakes/wide rivers are weak moisture
  sources; inland precipitation equilibrium is pinned by the recycling
  term.
- Sunshine/albedo/actual latitude band: deferred to a refinement pass —
  it swaps the zonal curve and T_lat, nothing else.
- **Monsoon wind reversal** (user 2026-07-23, revised same day): in
  real life prevailing winds can reverse seasonally, and the
  chaotic-gyre blend alone just averages out. Solution: (a) the base
  circulation bearing OSCILLATES seasonally (±0.4–1.2 rad around the
  per-world bearing), (b) the land–sea term is a CONTINENTAL monsoon
  flow (heavily smoothed land gradient), and (c) its strength is read
  off the ACTUAL land–sea heating ANOMALY per month
  (clip(12·ΔT_anom, ±1.2)) — temperature is computed first precisely
  so wind can condition on it. The anomaly (not absolute contrast) is
  what matters: the constant altitude-lapse offset would otherwise pin
  the flow offshore year-round. Result: land precipitation swings
  ~35% summer-ward and m01/m07 rainfall patterns correlate only ~0.5.
- **Wind–terrain momentum coupling** (user 2026-07-23): previously
  only the moisture accounting saw terrain (orographic rate +
  depletion); the wind vectors blew through ranges at full speed.
  Now `WindLibrary.sample` DEFLECTS flow around high ground (removes
  ≤70% of the upslope component, ramping in above ~900 m) and DAMPS
  it (≤40% slower) — rain shadows sharpen, ranges steer storm tracks.
- **2nd-order conditioning round** (user 2026-07-23):
  `refine_climate(T_m, P_m, T_lat)` runs ONCE after the one-pass
  prior, at the coarse grid: snow-albedo feedback (sub-zero months
  carry snow; snow cools, more under stronger equatorward sun),
  evaporative/cloud cooling (wet months cooler), cloud swing damping
  (wet cells pulled toward their annual mean). Damped (relaxation
  0.7), small coefficients, never iterated — conditioning, not
  simulation. Vegetation → climate feedback is explicitly deferred
  (biomes don't exist yet at climate time; would need a stale prior).
- Seasonal swing kept moderate (user 2026-07-23): profile
  0.05 + 0.25·sin(π·lat) (mid-lat peak ≈ ±16 °C), land contrast
  0.30·T_amp_lat. Illinois-grade −35…+35 °C swings are real but
  dominate the map's character; mid-latitudes now read more European.
- **Lakes** (user 2026-07-23, revised same day): the water-balance
  filter stays (inflow ≥ α·area, α=4.0), but the hard 150-cell cap is
  replaced by a per-basin K1-drawn cap (25 + 425·u⁴ cells) — mega-lakes
  exist but are rare; 1-cell puddles are dropped but small ponds stay
  (the small-lake smattering); and any lake 8-connected to the ocean is
  absorbed into it (bays/lagoons — a lake with an open connection to
  the sea is not a lake). At delivery, lake boundaries are still
  re-derived from the interpolated FIELDS (w − elev contour, confined
  to anchor-lake neighborhoods).
- **Climate extremes need map scale** (user 2026-07-22): at 1 km cells
  (260 km) no seed could span tundra-to-desert. At 2 km cells (512 km)
  the latitude T range stretches 0.12→1.0 and a subtropical aridity belt
  (−40% P around lat ≈ 0.78) makes deserts actually appear; ice, tundra,
  boreal belts follow. Biome regions stay broad (smooth climate fields +
  3-pass majority filter); the only sharp biome borders are the mountain
  ladder — orographic borders are SUPPOSED to be sharp.
- **Mountains**: fault bias amplitude 0.40. Mountain abundance varies by
  seed (weak-convergence seeds get gentler ranges — legitimate variance,
  not a bug; seeds 1–6 span 1k–6k mountain cells).
- **Units layer** (user, 2026-07-23): normalized pipeline fields become
  physical quantities in exactly one place (`units.py` — temperature
  −30…+35 °C, precipitation 0…400 mm/month, elevation −4000…+6000 m).
  The mapping is FIXED: "if we need to adjust, we won't adjust units,
  but rather the gradient/variation." First consequence: with real
  thresholds the current climate variation yields a subarctic-to-
  temperate world (seasonal swing grows equatorward, so the coldest
  month never reaches 18 °C and Köppen-A tropics cannot exist; rain is
  summer-peaked everywhere so mediterranean/desert are rare). Those are
  climate-generation knobs, deliberately left untouched here.

### K1 substreams (2026-07-22)
K1 draws are keyed by (clock, index) only — two fields drawn from the
SAME stream at the same coordinates are byte-identical. K11 hit this
twice (identical warp fields, correlated noise/modulation). Every
independent random field must use its own context: `Stream.child(ctx)`
(kernel/hashrng) derives a substream by extending the context digest.

### World-frame notes (fourth frame, 2026-07-22)
- Frame history: (1) rim ring + straits — artificial; (2) radial cores —
  triangular, rim cut-offs; (3) many-dots + border-ring reservation with
  flat ocean and all-land interior — rejected on review; (4) current:
  domain-warped partition + emergent interior seas.
- **Domain-warp the ASSIGNMENT, not the fields** (user): adding noise on
  top of a piecewise-linear partition can't hide it — evaluate the
  Voronoi dot-distance comparison at warped coordinates and every
  downstream boundary (plates, faults, coasts, biome patches) curves.
- **A continental plate has both ocean and land** (user): plates draw a
  continental/oceanic TENDENCY, but membership and elevation are
  separate: rim fine cells glue into macro plates like any other (the
  reservation only forces their base height down — no merged
  rim-ocean mega-plate), and per-fine-cell bias adds mild local variance
  plus occasional strong draws — sea pockets in continental plates,
  island arcs in oceanic ones. Marine basins emerge inside the map. The
  ocean floor gets its own relief (abyssal fbm + trench/ridge at sea-sea
  faults) — it is not a fixed low constant.
- **Enclave plates are folded** (user 2026-07-23): a plate bordering
  exactly ONE other plate is fully surrounded — never 'mostly convex'.
  `_defragment` now folds it into that neighbor (cascading, smaller
  folds into larger), then compacts ids so folded-away plates don't
  linger in outputs.
- **World edge** (rfc-game-layer §1: "ocean margins, rim mountain
  barrier, then void"; user 2026-07-23): the anchor reservation keeps
  the deep-ocean margin (re-hardened after smoothing — the box smooth
  bled continental base into ring cells and land crept back into the
  reserved zone), and delivery adds the minimal rim: the outermost
  1 km ring is smooth "rock" ~12 m above sea level — land may
  approach the border but never gets cut off by it; the map edge is a
  rock wall to the void. A real rim RANGE from the plate pass (the RFC
  justifies it as a boundary plate margin) is a later refinement.
- **Land noise is subtractive** (user 2026-07-23): purely additive
  relief meant nothing ever dipped below its plate base — no Death
  Valleys, and the lowest-land marks pinned at 0 m. Land detail is now
  centered (0.10 + 0.32·(noise − 0.5)·roughness): rift/sea-pocket
  floors can fall below sea level, and underfed ones fail the water
  balance and stay DRY below-sea basins — the LW marks go negative.
  exactly ONE other plate is fully surrounded — never 'mostly convex'.
  `_defragment` now folds it into that neighbor (cascading, smaller
  folds into larger), then compacts ids so folded-away plates don't
  linger in outputs.
- **Detail follows elevation, not plate labels** (user 2026-07-23):
  island arcs (and any sea-plate cells standing above sea level) used
  to keep the flat abyssal recipe — visible as un-noised land. Now the
  shelf pull-down/push-up runs on the pre-detail base FIRST (both
  sides converge to the waterline), then land/sea noise is mixed
  linearly by elevation vs sea level (full land noise above, full sea
  noise below a shallow ramp).
- **Latitude gradient and seasons** (user 2026-07-23, revised twice):
  the SPATIAL delta is the point of the bigger map — T_lat spans
  0.12→1.0 (floor raised from 0.02: the north is cold (~−22 °C annual)
  without a Siberia-scale taiga band — "move the reference point
  southward"). The seasonal swing peaks at MID-LATITUDES
  (0.05 + 0.25·sin(π·lat)) and is minimal at both rims: the north
  stays frozen year-round, the southern tropics stay warm year-round
  (real equatorial swing is a few °C — the earlier equatorward-growing
  swing made Köppen-A climates impossible). Land–sea contrast is part
  of the swing and scales with it (0.30·T_amp_lat on land).
- **Climate sees the water surface, not the sea floor** (user): lift and
  advection run on max(elev, water level), so there is no coastal cliff
  and rates stay sane. Lakes/wide rivers are weak moisture sources
  (lake-effect rain downwind).
- **Lakes need a water balance** (user): priority flood fills every basin
  to its brim — at 1 km cells that's hundred-km² puddle-seas. A basin
  stays a lake only if inflow ≥ α·area (α=1.5); underfed basins become
  wetland flats with the river running through.
- Moisture calibration: inland precipitation equilibrium is pinned by the
  recycling term, not the rate — tune recycling to wet interiors, rate
  for coastal/orographic contrast.
- Accumulation on flat surfaces (lake surfaces) is corrupted by plain
  descending-w processing order (ties donate partial subtrees
  downstream); sorting by descending (w, BFS flat-depth) makes donations
  exact — discharge is then non-decreasing along every river walk.
- Domain-warped fine cells can split off tiny exclaves; macro plates are
  ≥90% contiguous, which is all the L0 sketch needs.
- Mountain biomes emerge from the vectors: altitude lapse cools peaks,
  so montane grassland (cold, small swing — páramo-style) caps the
  ranges, forest classes flank them, and the abiotic zones are the
  split WWF classes: "rock" (barren nival ground — alt > 4500 m, or
  alt > 2500 m with warmest month < 4 °C) and "ice" (never above
  freezing at any altitude). No separate mountain
  classes — the old montane/cloud-forest/rock/snow-peak extras were
  dropped (2026-07-23).
- Historical invariants from the rim frame (still true of priority flood):
  a closed ring of high ground floods its interior into one lake; the
  outlet sill sets the interior water level; drainage needs a regional
  gradient or noise valleys flood into shallow seas.
