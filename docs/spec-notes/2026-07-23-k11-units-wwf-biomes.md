# K11 — units layer + WWF metric biome classifier (2026-07-23)

## Decision

The biome classifier went through two discarded designs before this one:

1. **Prototype-vector match on normalized curves** — each biome a curated
   12-month (T, P) vector, cell = nearest weighted-Euclidean prototype.
   Worked mechanically, but the "parameters" were unmoored numbers, and
   reviewing the output meant re-calibrating prototypes until the MIX
   looked right.
2. (Aborted) tuning those prototypes so the final distribution resembles
   Earth's. The user stopped this: "I never asked for the final
   distribution to match the real world, I just want the parameters to
   match the real world."

The adopted design has two parts:

- **`units.py` — the fixed normalized→metric mapping.** Temperature
  0..1 → −30…+35 °C (per-month values), precipitation 0..1 →
  0…400 mm/month, elevation → −4000…+6000 m around sea level, linear per
  segment. This module is the ONLY place physical units exist, and it is
  never a tuning knob: "if we need to adjust, we won't adjust units, but
  rather the gradient/variation" (user, 2026-07-23).
- **`biomes.py` — a Köppen-flavoured decision tree in metric units**,
  labelled with the WWF / Olson & Dinerstein (1998) terrestrial
  vocabulary (the 14 biomes listed on Wikipedia's Biome article, which
  the user pasted). Thresholds are real-world parameter values:
  - tropical = coldest month ≥ 18 °C (Köppen A)
  - rainforest = driest month ≥ 60 mm, monsoon edge 100 − MAP/25 (Af/Am)
  - aridity boundary MAP = 20·MAT + {280 summer-rain / 140 even / 0
    winter-rain} mm; desert below half, steppe below (Köppen B)
  - temperate = coldest month 0–18 °C (C); continental < 0 °C (D)
  - polar = warmest month < 10 °C: tundra 0–10 °C, ice cap < 0 °C (ET/EF)
  - mediterranean = driest summer month < 40 mm and < ⅓ wettest winter
    month (Cs); boreal = ≤ 3 months ≥ 10 °C (Dfc)
  - overrides in meters: rock > 5000 m, snow peak > 2500 m with warmest
    month < 4 °C, cloud forest > 1500 m with wettest month ≥ 200 mm,
    flooded grassland < 50 m with wet season ≥ 150 mm, mangrove =
    frost-free (coldest ≥ 18 °C) tidal fringe < 10 m; alpine tundra
    (T_warm 0–10 °C, > 1500 m, non-polar) → montane grassland.

## Sources

- Biome list: user-pasted WWF grouping from Wikipedia's "Biome" article
  (Olson & Dinerstein 1998 / WWF Global 200). The 12 freshwater and 5
  marine (neritic) biome types were noted and deliberately NOT
  implemented — ocean/lake/river masks suffice at L0; neritic sub-typing
  (latitude + shelf distance) is a cheap later refinement.
- Colors: there is NO official WWF color scheme (confirmed by searching;
  even the QGIS biome-expressions community only standardizes biome
  numbering 1–14). The palette approximates the de-facto colors of WWF
  terrestrial-ecoregion maps; the user pre-approved this ("I don't know
  if there's an official colorscheme").
- Climate thresholds: Köppen–Geiger boundary formulas (2·MAT+{0,7,14} cm
  aridity boundaries, 18 °C tropical boundary, 10 °C polar boundary,
  60 mm rainforest boundary, Cs dry-summer rule).

## Consequences (honest output, deliberately not "fixed")

With real parameters, the current climate variation produces a
subarctic-to-temperate world across seeds 1/2/7/42:

- **No tropics.** The seasonal amplitude grows equatorward (0.08→0.40,
  +0.18 land contrast), so even the hottest coasts swing through winters
  far below 18 °C — Köppen A cannot exist. On Earth the equatorial
  swing is a few °C; ours is inverted. This is a climate-GRADIENT knob
  (`T_amp_lat` in climate.py), not a units or classifier issue.
- **Desert/mediterranean rare.** Precipitation is summer-peaked nearly
  everywhere (advection + monsoon), and the subtropical aridity belt
  (lat ≈ 0.78) is mild relative to the real subtropical highs.
- **Temperate broadleaf dominates** — a legitimate consequence of a wet,
  strongly seasonal mid-latitude climate.

If a livelier mix is wanted, the sanctioned knobs are the climate
gradients/variation (seasonal-amplitude profile, aridity belt, zonal
curve) — explicitly NOT the units mapping and NOT the classifier
thresholds.

## Follow-up 1 (same day): the variation knob was turned

The user confirmed the tropical absence was unwanted ("Temp swing for
the south should not be that large"), so the climate GRADIENT changed —
exactly the sanctioned place: the seasonal amplitude profile went from
equatorward-growing (0.08→0.40) to mid-latitude-peaked
(0.05 + 0.35·sin(π·lat)), with land–sea contrast scaled into it
(0.45·T_amp_lat replacing the flat 0.18). The north still stays frozen
year-round; the southern lowlands now hold coldest-month ≥ 18 °C, so
Köppen-A tropics exist. Units and classifier thresholds untouched, as
agreed.

## Follow-up 2 (same day): threshold tree rejected, back to vectors

The Köppen-tree version of the classifier drew "clearly straight lines
across boundaries" (user review): axis-aligned thresholds on single
fields (coldest month, MAP) become straight isotherm/isohyet bands
across whole continents. The user restated the original brief:
"month-vectors, biomes assigned based on nearest distance."

The final design keeps the units layer and the real-world parameters
but drops the tree: each WWF biome is a 24-dim prototype month-vector
built from real climate normals (Singapore, Siberia, páramo, Serengeti,
Mediterranean basin...), matched by weighted Euclidean distance
(~12 °C ≈ ~100 mm ≈ one unit). Distance-space boundaries between
smooth fields are organic curves.

The vocabulary was also cut to exactly the 15 WWF terrestrial classes
(14 biomes + "rock and ice"); the legacy extras (montane forest, cloud
forest, rock, snow peak, ice cap) were folded into the WWF classes,
and ocean/lake are labelled water masks, not biomes. Only geographic
classes remain overrides: flooded grassland (inundation), mangrove
(tidal fringe), rock and ice (nival/ice-cap). The world-sheet legend
now lists the FULL vocabulary per seed (absent biomes show 0 cells)
after the user spotted taiga silently missing from a histogram-only
legend.

## Follow-up 3 (same day): climate couplings + gentler swing

Approved as a bundle after discussion:

- **Swing reduced**: seasonal amplitude profile 0.05 + 0.25·sin(π·lat)
  (was 0.35), land factor 0.30 (was 0.45). Illinois-grade −35…+35 °C
  swings are real but dominated the map; mid-latitudes now read more
  European (±16 °C oceanic, ±21 °C continental).
- **Mountains**: rock-and-ice is unconditional above 4500 m (real
  vegetation limit ~4500–4800 m even in the tropics); 2500–4500 m is
  climate-decided (warmest month < 4 °C). Wind now interacts with
  terrain: `WindLibrary.sample` deflects (≤70% of the upslope
  component removed above ~900 m) and damps (≤40%) — previously only
  the moisture accounting saw terrain while momentum blew through
  ranges at full speed.
- **T → wind coupling**: temperature is computed first (it is
  wind-independent), and the monsoon strength is read off the actual
  land–sea heating ANOMALY per month (clip(12·ΔT, ±1.2)). Absolute
  contrast fails — the constant lapse offset pins the flow offshore
  and the clip eats the seasonal variation (caught by the P-seasonality
  test dropping below threshold).
- **refine_climate**: the 2nd-order conditioning round. One damped
  pass over the coarse monthly fields: snow-albedo feedback,
  evaporative/cloud cooling, cloud swing damping. Not iterated —
  conditioning, not simulation. Vegetation → climate feedback deferred
  (biomes don't exist at climate time).

Two regression tests added: refine_climate determinism/cooling/swing
damping, and wind-library terrain blocking (blocked wind never exceeds
free wind, cell by cell).

## Follow-up 4 (same day): the big coupling batch

Approved as a batch after discussion ("I'm fine, I'm on the most
expensive plan now"):

- **Rain-shadow erosion fixed**: the uniform +0.04/step moisture
  recycling (the requested inland-equilibrium pin) was the main shadow
  eraser — barren lee basins recovered as fast as forest. Recycling is
  now proportional to moisture already present (evapotranspiration
  feedback: wet stays wet, dry stays dry), and the baseline rain rate
  halved (0.12→0.06) so depleted air barely rains. Gain rebalanced
  3.5→4.0.
- **Two-pass precipitation with forests**: pass 1 on bare ground gives
  a provisional forest cover (the biome month-vector match at the
  coarse grid); pass 2 lets forests join the water cycle —
  evapotranspiration boosts recycling (0.15→0.40·M·(1−p)), canopy
  interception lowers local rain-out (rate ×(1−0.3·green)) so forests
  dry locally and moisten downwind, and forests act as windbreaks
  (wind ×(1−0.25·green)). K1 draws are pure hash lookups, so pass 2
  replays identical wind randomness.
- **Reference point moved south**: T_lat floor 0.02→0.12 (north edge
  ~−22 °C annual instead of ~−29 °C) — shrinks the Siberia-scale
  taiga/tundra bands.
- **Three-type fault system**: real fault behavior depends on the
  crustal type of BOTH sides, and the old code skipped mixed margins
  entirely — where Earth's most dramatic terrain is. Now: CC broad
  uplift/rift; OC (Andes) trench offshore + coastal range inland; OO
  convergent trench on the subducting side + island arc on the
  overriding side (amplitude 0.24 — crests breach into island chains;
  the old ridge could never breach by 0.03 and arcs come from
  CONVERGENCE, not ridges); OO divergent underwater ridge. The
  reserved border ring gets no signature (frame guarantee).
- **Terrain texture**: land roughness in sparse patches (low-frequency
  mask, quadratic concentration); abyss detail doubled with 6 octaves
  plus sparse seamount bumps.
- **Lakes**: see README (drawn caps, speckle kept, ocean absorption).
- **world.png**: water is never hillshaded (lakes read as rippling
  land before) — ocean is a bathymetric gradient, lakes darken with
  true depth; convergent CC/OC faults render as range lines; the
  "(N OCEANIC)" plate categorization is gone (island arcs invalidated
  it); and landmarks are marked + keyed: 5 highest peaks (meters via
  the units layer), deepest ocean point, 3 largest lakes (km²), 2
  lowest terrestrial points, 2 biggest river mouths by basin area.

## Follow-up 5 (same day): performance + persistence

- **Lattice noise was 70% of the world build** (9e6 scalar BLAKE2b
  calls ≈ 50 s of 70 s, measured by cProfile). K1 gained a separate
  vectorized draw mode, `Stream.u64_batch` — a keyed splitmix64-style
  numpy mixer over coordinate arrays. Values differ from u64() at the
  same coordinates (separate mode, documented as such); all K11 worlds
  change, same-version determinism holds. Build is now ~28–32 s/seed.
- Pass 2 runs at half the wind samples (it is a conditioning pass, not
  new information); biome accumulation is float32.
- **Adaptive precipitation gain**: raw advection scale is free, so the
  gain is pinned per world to land-mean 0.32 after the aridity belt
  (cap 16) — the mm the classifier reads via units means the same
  thing in every world; no more per-layout gain chasing.
- **Two-sided oceanic hygiene**: at most a third of plates may draw
  oceanic (lowest-u wins), joining the existing "at least two
  continental" rule — an uncapped 0.28 draw sank 75%+ of one seed.
- **World dump**: `seed_N/world.json` (inspectable manifest: params,
  stats, marks, plates metadata, full complex, checks, array
  inventory) + `seed_N/world.npz` (26 MB compressed rasters). The
  `render` subcommand re-renders all PNGs from the dump in ~3 s —
  draw-logic iteration no longer needs a world build; future kernels
  can load world state via `persist.load_world` / `load_complex`.
  (Deviation from the literal ask of "all data into world.json": the
  rasters live in the NPZ sidecar — ~100 MB of base64 inside a .json
  would defeat the repo's JSON-inspectable convention.)
- **Slow markers**: the six world-building K11 tests (~56 s) are
  `@pytest.mark.slow`; the default suite is now ~8 s.

## Follow-up 6 (same day): below-sea land, connected ocean, the rim

- **Land noise was purely additive** (fbm ∈ [0,1] only pushed terrain
  up) — nothing could dip below its plate base, so the lowest-land
  marks pinned at 0 m. Land detail is now centered
  (0.10 + 0.32·(noise − 0.5)·roughness).
- **The real blocker was definitional**: `ocean = elev < sea_level`
  makes below-sea land a contradiction. Ocean is now the
  border-CONNECTED sub-sea component (`connected_ocean`); enclosed
  below-sea basins are land — lake beds if the water balance feeds
  them, DRY depressions (Death Valley) if not. Biome classification,
  delivery (carried mask — connectivity is relational), and the
  delivered-ocean test all updated. LW marks now read e.g. −1815 m.
- **The rim** (rfc-game-layer §1: "ocean margins, rim mountain
  barrier, then void"): anchor keeps the deep-ocean margin
  (re-hardened after smoothing — the smooth bled continental base into
  reserved ring cells), and delivery adds the minimal rim: outermost
  1 km ring is smooth "rock and ice" ~12 m above sea level — land may
  approach the border but never gets cut off by it. A real rim RANGE
  from the plate pass (the RFC's boundary-plate-margin justification)
  is a later refinement.
- Noted, unfixed: climate sees the phantom flood surface (w) over dry
  basins, and below-sea land gets no altitude WARMING (alt_c clips at
  0) — real deep basins are hot. Both are cheap later knobs.

## Follow-up 7 (same day): depression depth in the real-world range

The LW marks hit ~-1800 m (real dry basins bottom out ~-430 m, Dead
Sea). Decomposing the lowest cells showed the depth was NOT the
subtractive noise (already damped 4x): seed 1's floor was a full-
amplitude CC divergent rift (-0.395 of -0.40), seed 7's were oceanic
trench floors exposed by the water-balance "wetland flat" rule. Fixes:

- CC divergence rifts at 0.35x amplitude (uplift unchanged).
- Water-balance rule extended: basins deeper than ~340 m mean depth
  are lakes REGARDLESS of inflow (Baikal/Caspian style) — deep floors
  can never be dry land. Side effect: large inland seas appear where
  enclosed oceanic basins exist (seed 7 has a 26k km2 one, Tanganyika
  scale); the drawn size caps do not apply to the deep-basin rule.
- Climate terrain uses the water surface only where standing water
  exists (w is the flood FILL level for every basin, fed or not — a
  phantom surface over dry basins), and altitude may go negative
  (floor -0.3) so the lapse term WARMS deep basins.

Result: LW marks read -83..-275 m — Dead-Sea scale. Also this round:
inline comments swept of conversational references ("user 2026-07-23,
same day") — comments must stand alone; dated/user annotations belong
in README and spec-notes (like this one), not in code.
