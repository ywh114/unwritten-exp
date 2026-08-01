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

V1_FLORA = (
    REQ_COLD, REQ_HEAT, REQ_BLOOM_FROST, REQ_WATER, REQ_WATERLOGGING,
    REQ_FERTILITY, REQ_PH_LOW, REQ_PH_HIGH, REQ_SALINITY, REQ_ROOTING,
    REQ_ANCHORING, REQ_MEDIUM, REQ_SUBMERGED_LIGHT, REQ_FRESH_HABITAT,
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
# Engine-side dispersal keys (K15 rounds; the stress strata never read
# them — threaded through the same view per the owner ruling
# 2026-08-01: every trait the engine directly needs rides the view):
#   dispersal_channels ({local, wind, water, animal, jump} pmf),
#   propagule_mass_mg, propagule_count (emission quantity/yr),
#   seed_bank, crown_spread_m (per-capita space demand),
#   jump_rate (long-range hops/yr)
# Env may read a key that is None/absent for a given plan — the
# stratum then does not apply (e.g. no anchoring on a duckweed).
