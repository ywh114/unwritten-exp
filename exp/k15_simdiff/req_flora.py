"""K15 — flora requirement vocabulary (env-defined names, v1).

The provenance names the flora stress adapter emits and flora-side
select() dispatches on. Requirement names are ENV-defined (interface
ruling); organism-side code reads them, never computes them. All v1
flora names are the DEFENSIVE class ("pressure:"); the pull class
arrives with food-web signals (fauna), not plants.

One name per B5 §4 stratum/term — the granularity select() needs to
route pressure to different driftable responders.
"""

# ── climate stratum (B5 §4.1; monthly, compensable, phenology-gated) ──
REQ_CLIMATE = "pressure:climate"            # T/P distance from [niche]
REQ_BLOOM_FROST = "pressure:bloom_frost"    # extra cost term, never lethal

# ── ground stratum (B5 §4.2, rewired 2026-07-31) ──────────────────────
REQ_WATER = "pressure:water"                # water_potential dry end
REQ_WATERLOGGING = "pressure:waterlogging"  # saturated end (inverts)
REQ_FERTILITY = "pressure:fertility"        # eff_nutrient shortfall
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
REQ_ROOTING = "pressure:rooting"            # root_depth vs eff_rooting_m
REQ_ANCHORING = "pressure:anchoring"        # holdfast/exposed trees
REQ_MEDIUM = "pressure:medium"              # medium boundary (~1 always)
REQ_SUBMERGED_LIGHT = "pressure:light"      # below photic depth

# ── freshwater habitat stratum (B5 §4.5) ──────────────────────────────
REQ_FRESH_HABITAT = "pressure:habitat"      # fresh_availability

V1_FLORA = (
    REQ_CLIMATE, REQ_BLOOM_FROST, REQ_WATER, REQ_WATERLOGGING,
    REQ_FERTILITY, REQ_PH_LOW, REQ_PH_HIGH, REQ_SALINITY, REQ_ROOTING,
    REQ_ANCHORING, REQ_MEDIUM, REQ_SUBMERGED_LIGHT, REQ_FRESH_HABITAT,
)

# ── the view the adapter expects from flora expose() ──────────────────
# Keys of the DerivedView the adapter reads (flora-side expose wraps
# derive.effective_climate plus plan/medium descriptors):
#   temp_opt_c, temp_breadth_c, moisture_opt, moisture_breadth   [niche]
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
#   seed_bank, crown_spread_m (per-capita space demand)
# Env may read a key that is None/absent for a given plan — the
# stratum then does not apply (e.g. no anchoring on a duckweed).
