"""K15 — flora requirement vocabulary (env-defined names, v1).

The provenance names the flora stress adapter emits and flora-side
select() dispatches on. Requirement names are ENV-defined (interface
ruling); organism-side code reads them, never computes them. All v1
flora names are the DEFENSIVE class ("pressure:"); the pull class
arrives with food-web signals (fauna), not plants.

One name per B5 §4 stratum/term — the granularity select() needs to
route pressure to different driftable responders.
"""

# ── climate stratum (B5 §4.1; monthly, compensable) ──────────────────
# The climate envelope (temp_opt_c/temp_breadth_c) is a pure DERIVED of
# the trait bundle (owner ruling 2026-08-01) — when stress pushes the
# traits, the envelope moves. The T requirement is SPLIT one-sided like
# pH: a symmetric distance factor is space-blind — select() cannot tell
# which side of the optimum the cell sits on. Two one-sided factors
# (cold = shortfall toward the optimum, heat = excess past it; their
# product is the symmetric distance) let the responders push toward the
# right side directly. The moisture (P) half lives in pressure:water /
# pressure:waterlogging (the derived moisture envelope feeds those).
REQ_COLD = "pressure:cold"              # T below optimum (growing-season
                                        # + C4/CAM cold terms folded in)
REQ_HEAT = "pressure:heat"              # T above optimum
REQ_BLOOM_FROST = "pressure:bloom_frost"    # extra cost term, never lethal

# ── ground stratum (B5 §4.2, rewired 2026-07-31) ──────────────────────
# Substrate requirements (fertility, pH, salinity, rooting) are
# BEST-OF-CLASS (owner ruling 2026-08-01): the cell's top-3 ground mix
# is three physically-present patches — the plan reads the best patch;
# the usable share rides "substrate_share" (capacity metadata for the
# engine's K split, never a stress factor). Wet-obligate land plans
# (waterlogging_tolerance >= WLOG_INVERT_T) read fresh_availability for
# BOTH water and waterlogging (the marsh is the habitat).
REQ_WATER = "pressure:water"                # water_potential dry end
REQ_WATERLOGGING = "pressure:waterlogging"  # saturated end (inverts)
REQ_FERTILITY = "pressure:fertility"        # best-patch nutrient shortfall
# pH is SPLIT one-sided (owner ruling 2026-08-01): a symmetric distance
# factor is space-blind — select() cannot tell which side of the optimum
# the cell sits on, so a single "pressure:ph" cannot be signed. Two
# one-sided factors (their product is exactly dist_suit) let the
# responder push ph_tolerance in the right direction directly.
REQ_PH_LOW = "pressure:ph_low"              # env too acidic for position
REQ_PH_HIGH = "pressure:ph_high"            # env too alkaline for position
REQ_SALINITY = "pressure:salinity"          # ionic (osmotic half is in
                                            # water_potential already)

# ── tail terms (B5 §4.3; steep, cost -> ~1, never a verdict) ──────────
REQ_ROOTING = "pressure:rooting"            # root_depth vs best patch
REQ_ANCHORING = "pressure:anchoring"        # holdfast/exposed trees
REQ_MEDIUM = "pressure:medium"              # medium boundary (~1 always)
REQ_SUBMERGED_LIGHT = "pressure:light"      # below photic depth

# ── freshwater habitat stratum (B5 §4.5) ──────────────────────────────
REQ_FRESH_HABITAT = "pressure:habitat"      # fresh_availability

# ── glacier stratum (B6 §3; habitat exclusion, like REQ_MEDIUM) ───────
# A land plan on a year-round glacier cell is ~1 always (f =
# MEDIUM_VIOLATION_F, never a verdict); a snow-adapted plan
# (snow_adaptation != none) is exempt. No driftable responder — the
# medium does not drift (same ruling as pressure:medium).
REQ_GLACIER = "pressure:glacier"            # h_glacier_mask (land cells)

# ── canopy light (B6 §3, engine-side — NOT in the adapter cache) ───────
# The shade factor is a DYNAMIC per-round term (depends on every
# instance's density and height — the adapter is per-lineage blind), so
# it is emitted by the ENGINE in _verdict_feed, not by evaluate(). The
# name lives here so select() routes it once: shade_tolerance up,
# height_m up (grow out of the shade). REQ_SUBMERGED_LIGHT already uses
# the same name for the photic term; the two never co-occur on one
# instance (submerged water plans skip the engine pass).
REQ_LIGHT = "pressure:light"                # canopy shade (engine, land)

V1_FLORA = (
    REQ_COLD, REQ_HEAT, REQ_BLOOM_FROST, REQ_WATER, REQ_WATERLOGGING,
    REQ_FERTILITY, REQ_PH_LOW, REQ_PH_HIGH, REQ_SALINITY, REQ_ROOTING,
    REQ_ANCHORING, REQ_MEDIUM, REQ_SUBMERGED_LIGHT, REQ_FRESH_HABITAT,
    REQ_GLACIER,
)

# ── the view the adapter expects from flora expose() ──────────────────
# Keys of the DerivedView the adapter reads (flora-side expose wraps
# derive.effective_climate plus plan/medium descriptors):
#   temp_opt_c, temp_breadth_c, moisture_opt, moisture_breadth   [derived
#       envelope — pure function of the trait bundle, never metadata]
#   drought_tolerance, waterlogging_tolerance, salinity_tolerance,
#   ph_tolerance, fertility_requirement, growing_season_req,
#   root_depth_m, height_m, woodiness,
#   photosynthesis ("C3"/"C4"/"CAM"), winter_deciduous (0/1),
#   leafout_month, drought_deciduous (0/1),
#   bloom_start_month, bloom_length_months,
#   medium ("land"/"water"/"dual"), anchoring_need (0..1),
#   holdfast (0/1)
# B6 wiring keys (2026-08-01 hand-wiring program — the strata read
# them; see biosphere-addendum-b6-flora-wiring.md):
#   mycorrhizal ("arbuscular"/"ecto"/"ericoid"/"orchid"/"none") —
#       fertility credit, n_fixation (…/"rhizobium"/"frankia"/
#       "cyanobacterial"/"none") — fertility credit,
#   nutrient_package ("halophyte" -> salinity credit),
#   drip_tips (0..1) + leaf_margin ("serrate"/"toothed" -> wetness
#       credit in the waterlogging term for dry plans),
#   moisture_breadth (derived envelope; graded dry/wet relief in the
#       water terms — B6 §2),
#   snow_adaptation (state; the graded snow-load reliever) + layer
#       (canopy/subcanopy/shrub/sward/ground/aquatic_*; the canopy-light
#       exposure coefficient), canopy_density (derived; the engine's
#       shade pass reads it)
# Engine-side dispersal keys (K15 rounds; the stress strata never read
# them — threaded through the same view per the owner ruling
# 2026-08-01: every trait the engine directly needs rides the view):
#   dispersal_channels ({local, wind, water, animal, jump} pmf),
#   propagule_mass_mg, propagule_count (emission quantity/yr),
#   seed_bank, crown_spread_m (per-capita space demand),
#   jump_rate (long-range hops/yr)
# Env may read a key that is None/absent for a given plan — the
# stratum then does not apply (e.g. no anchoring on a duckweed).
