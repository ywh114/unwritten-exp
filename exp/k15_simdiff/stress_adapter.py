"""K15 — B5 flora stress adapter (the env side of the stress channel).

Evaluates biosphere addendum B5's stress function per flora record over
the world, vectorized, at ANCHOR resolution (256²). Pure functions of
(world dump, record) — no draws, no per-taxon state (B5 §2/§6), so two
runs are byte-identical.

The adapter owns the WORLD side (loading the persisted components of
B5 §3 once, then evaluating a record against them); the organism side
exposes the DerivedView (exp/k13_treegen/interface.py, req_flora.py)
that this module reads. Requirement names are ENV-defined
(exp/k15_simdiff/req_flora.py) and are used EXACTLY here; the factor
vector IS the provenance (kernel/stress composes it: F = product of
factors, s = 1 - 2F).

Resolution rules followed here (B5 §3 + the K14 deliver convention):

- water_potential / fresh_availability are persisted at delivery res;
  the adapter RECOMPUTES them at anchor via moisture.build_moisture
  (cheap, exact — never downsampled).
- ground_ph at anchor is derived via the consume-time softmax over -d2
  (the full-vector softmax dotted into the stable top-3 classes and
  renormalized — the exact recipe of build_ground's mix, TAU=1). The
  anchor top-3 mix is NOT persisted (only ground_d2 is), and the top-3
  ids cannot be reconstructed from d2 alone (sub-floor generator
  weights tie at the -log floor), so the deterministic B3 pass is
  RE-RUN at load — mix_ph/eff_props are pointwise, and the re-derived
  eff rasters are verified bit-for-bit against the persisted
  ground_eff_* rasters.
- water_ph at anchor is re-derived pointwise: ocean from anchor
  bathymetry (ocean_ph), fresh water AND land cells carrying implicit
  freshwater habitat (fresh_availability > 0) from fresh_ph over the
  anchor bed pH + windowed catchment inputs + bog-peat share. The land
  extension is the "chemistry once in" of B5 §7.2 (a bog pond reads
  blackwater pH even where no lake is mapped) — this is what lets a
  freshwater taxon score per its ph_tolerance position in unwritten
  bog hydrology (B5 §8 check 5).
- photic_depth_m (B4) at anchor from the anchor bathymetry + plume +
  provisional marine productivity (same inputs the delivery product
  was upsampled from), with the fresh-water side (lakes/rivers)
  re-derived from the bog-peat share + freshwater_productivity annual
  mean — the marine field reads 0 on every lake/river (B4 fix
  2026-08-01); the same split applies to the annual bottom temperature.

Owner rulings 2026-08-01 (stat-pass settling):

- BEST-OF-CLASS substrate semantics: the cell's top-3 ground mix is
  three physically-present patches, not an average. The substrate
  requirements (rooting, fertility, pH, salinity) read the BEST class
  in the mix (max over classes of the per-class suitability); the
  usable-substrate share U = sum w_i x prod f_i is exported as
  "substrate_share" for the engine's capacity split (K_L = K x U —
  the mix's effect on population runs through carrying capacity, not
  through suitability). Anchoring stays on hard/loose SHARES (already
  patch-probabilities); water relations stay on the mix-mean (cell
  hydrology, not a patch choice).
- Growing-season dormancy: months below GROW_T_C (5 C, the K11
  growing-season convention) are dormant — no T-distance cost for
  surface plans (a taiga winter is not niche distance; frost kill
  rides the bloom-frost and C4/CAM terms, which are likewise gated to
  the growing band). Submerged plans read the annual bottom
  temperature and carry no dormancy (the deep sea has no winter).
- Wet-land habitat: land plans with waterlogging_tolerance >=
  WLOG_INVERT_T (wet-obligate) read fresh_availability for BOTH the
  water-availability term and the inverted waterlogging requirement —
  B5 §7.2's unwritten-wetland field (a reed's water is the marsh, not
  the worst-month soil moisture).
- Climate envelope as a PURE DERIVED: temp_opt_c/temp_breadth_c/
  moisture_opt/moisture_breadth are computed from the trait bundle
  (flora.derive.effective_climate — owner ruling 2026-08-01), never
  clade metadata; when stress pushes the traits the envelope moves.
  The T requirement is SPLIT one-sided (pressure:cold / pressure:heat,
  the pH-split convention); the moisture half lives in pressure:water/
  waterlogging — nothing is double-counted. The B6 hand-wiring program
  (biosphere-addendum-b6-flora-wiring.md, 2026-08-01) reads the
  symbiosis/package/wetness/snow/layer traits as graded credits and
  relievers in the strata below, and adds the snow-load + glacier
  strata (K11 c_snow_monthly / h_glacier_mask) and the engine-side
  canopy-light pass (canopy_density x height comparison).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from exp.artifacts import require as artifact_require
from exp.k11_worldgen.units import hand_m, temp_c
from exp.k13_treegen.flora.content import ContentPack
from exp.k13_treegen.flora.derive import (
    _derived_canopy_density,
    effective_climate,
)
from exp.k13_treegen.interface import StressVerdict
from exp.k13_treegen.model import Node, Rank
from exp.k14_worldprod import moisture as _moisture
from exp.k14_worldprod import water as _water
from exp.k14_worldprod.derived import (
    GROW_T_C,
    PLUME_WEIGHT,
    _plume_source,
    _upsample,
    freshwater_productivity,
    growing_season,
    marine_productivity,
)
from exp.k14_worldprod.ground import (
    CLASS_PH,
    GROUND_ID,
    PROP_TABLES,
    eff_props,
    mix_ph,
)
from exp.k15_simdiff.req_flora import (
    REQ_ANCHORING,
    REQ_BLOOM_FROST,
    REQ_COLD,
    REQ_FERTILITY,
    REQ_FRESH_HABITAT,
    REQ_GLACIER,
    REQ_HEAT,
    REQ_MEDIUM,
    REQ_PH_HIGH,
    REQ_PH_LOW,
    REQ_ROOTING,
    REQ_SALINITY,
    REQ_SUBMERGED_LIGHT,
    REQ_WATER,
    REQ_WATERLOGGING,
    V1_FLORA,
)
from kernel.stress.stress import (
    excess_suit,
    invert,
    sat,
    shortfall_suit,
)

K11_OUT = Path(__file__).resolve().parent.parent / "k11_worldgen" / "out"
K14_OUT = Path(__file__).resolve().parent.parent / "k14_worldprod" / "out"
FLORA_TREE_REL = Path("exp") / "k13_treegen" / "out"

# ── climate stratum (B5 §4.1) ─────────────────────────────────────────
# The T requirement is SPLIT one-sided like pH (req_flora ruling
# 2026-08-01): REQ_COLD = shortfall of T below the envelope optimum,
# REQ_HEAT = excess past it; cold x heat is exactly the symmetric
# distance, and the one-sided factors let select() push the right way.
# The cold side carries the growing-season term and the C4/CAM cold
# penalty; the moisture (P) half is gone — the DERIVED moisture
# envelope (moisture_opt/moisture_breadth, pure function of the trait
# bundle — owner ruling 2026-08-01) feeds pressure:water/waterlogging,
# so nothing is lost and nothing is double-counted.
GS_REF_MONTHS = 3.0
# C4/CAM cold penalty: photosynthesis shuts down below COLD_PEN_T_C;
# the penalty saturates over COLD_PEN_SPAN_C and weighs COLD_PEN_W, so
# it is costly but never alone lethal (C3 carries none).
COLD_PEN_W = 0.4
COLD_PEN_T_C = 10.0
COLD_PEN_SPAN_C = 5.0
# bloom frost: a frost in a bloom-window month costs BLOOM_FROST_W at
# most (f >= 1 - BLOOM_FROST_W — "costly, never lethal"); the frost
# signal ramps from 0 C over FROST_SPAN_C.
FROST_T_C = 0.0
FROST_SPAN_C = 5.0
BLOOM_FROST_W = 0.5

# ── ground stratum (B5 §4.2) ──────────────────────────────────────────
# water availability: shortfall of water_potential below the plan's
# moisture need, scaled by WATER_REF (need = moisture_opt x
# (1 - drought_tolerance): drought tolerance BUYS the plan lower need).
WATER_REF = 0.35
# waterlogging for DRY plans (tolerance below WLOG_INVERT_T): excess of
# water_potential above WLOG_DRY_LIMIT, scaled by WLOG_DRY_REF.
WLOG_DRY_LIMIT = 0.75
WLOG_DRY_REF = 0.25
# waterlogging for WET plans (tolerance at/above WLOG_INVERT_T): the
# saturated end INVERTS to a requirement — read against
# fresh_availability (B5 §7.2's unwritten-wetland field), not soil
# water_potential: a wet-obligate land plan needs the marsh itself.
# The requirement ramps from WLOG_WET_LIMIT to 1.0 over WLOG_WET_REF.
WLOG_INVERT_T = 0.7
WLOG_WET_LIMIT = 0.4
WLOG_WET_REF = 0.6
# fertility: shortfall of eff_nutrient below fertility_requirement.
FERT_REF = 0.5
# pH: optimum = PH_LO + PH_SPAN x ph_tolerance (position, not width);
# breadth fixed at PH_BREADTH pH units (B5 §5.1, open question 1).
# Emitted SPLIT one-sided (req_flora: pressure:ph_low / pressure:ph_high)
# so select() can sign its response; the two factors' product is exactly
# dist_suit, so F is unchanged.
PH_LO = 4.0
PH_SPAN = 5.0
PH_BREADTH = 1.0
# salinity: h_salinity is g/kg (K11 units); the tolerance axis 0..1 is
# anchored at ocean salinity — SAL_REF_GKG normalizes the water field
# (35 g/kg -> 1.0). The excess is scaled by SAL_REF (1.0 = a unit of
# tolerance absorbs a unit of salinity).
SAL_REF_GKG = 35.0
SAL_REF = 1.0

# ── tail terms (B5 §4.3) ──────────────────────────────────────────────
# rooting: saturating excess of root_depth_m over eff_rooting_m, scaled
# by ROOT_REF_M — a deep root on a thin soil is a real cost, never a
# cutoff.
ROOT_REF_M = 1.0
# anchoring need for woody land plants: full need at ANCHOR_REF_M of
# height x woodiness (K13 ruling: calculable axes are calculated).
# Trees anchor into SOIL, so their anchor strength is (1 - eff_hard);
# holdfast plans attach to hard substrate, strength = eff_hard.
ANCHOR_REF_M = 25.0
HOLDFAST_NEED = 0.6
# wind exposure MODULATES the land-tree anchoring need (the need side,
# env-side — the requirement name and its flora responders do not
# change): need_eff = need x clip(wind_ms / WIND_REF_MS, MIN, MAX).
# wind_ms is the storm proxy: the max over months of the monthly-mean
# surface speed (windthrow is a storm phenomenon, not a mean one).
WIND_REF_MS = 8.0
WIND_MOD_MIN = 0.5
WIND_MOD_MAX = 2.0
# submerged light: shortfall of photic_depth_m below the column depth,
# scaled by LIGHT_REF_M — a seagrass below the photic zone costs ~1.
LIGHT_REF_M = 10.0
# medium boundary: a land plan on a water cell and vice versa is ~1
# always (B5 §1) — f = MEDIUM_VIOLATION_F (small, never exactly 0; the
# stress is very high, never a verdict).
MEDIUM_VIOLATION_F = 1e-3

# ── freshwater habitat stratum (B5 §4.5) ──────────────────────────────
# a water-medium plan with salinity_tolerance below this is a
# FRESHWATER plan: the medium boundary is replaced by the
# fresh_availability habitat term (graded on land, capped below mapped
# water, zero on the ocean — B5 §7.2). At/above it is a marine
# obligate: strict water cells only, medium boundary stands.
FRESH_SAL_MAX = 0.5

# ── B6 §2 hand-wiring credits (biosphere-addendum-b6-flora-wiring.md) ─
# mycorrhizal / n_fixation -> NUTRIENT CREDITS in the fertility factor:
# an acquired symbiosis grade lifts the effective nutrient of every mix
# class by its credit (each grade is a state on the axis; "none" is 0).
MYC_CREDIT = {"arbuscular": 0.12, "ecto": 0.15, "ericoid": 0.10,
              "orchid": 0.06, "none": 0.0}
NFIX_CREDIT = {"rhizobium": 0.25, "frankia": 0.25,
               "cyanobacterial": 0.15, "none": 0.0}
# nutrient_package "halophyte" -> a salinity-tolerance grade credit in
# the salinity factor (ionic side; the osmotic half still rides
# water_potential).
HALOPHYTE_CREDIT = 0.15
# drip_tips (0..1) + leaf_margin ("serrate"/"toothed" — the wet-climate
# teeth) -> wetness credits in the WATERLOGGING factor for DRY plans
# (relief from a soggy leaf/root zone in very wet cells; spinose/entire
# carry none). Documented choice in B6 §2: the bloom-frost term is a
# frost signal, not a wetness one, so the wetness relief rides the
# saturated-end term instead.
DRIP_WET_W = 0.4           # x drip_tips (scalar 0..1)
LEAF_WET_W = 0.25          # x 1 for serrate/toothed margins
# moisture_breadth (derived envelope, consumed per B6 §2): a wide
# moisture band is graded dry-side relief on the water factor and a
# smaller wet-side relief on the waterlogging factor (asymmetric dry >
# wet, mirroring the old climate P-half's two-sided distance).
MB_DRY_W = 0.5             # x moisture_breadth (0.03..0.5)
MB_WET_W = 0.25            # x moisture_breadth
# waterlogging GRADED relief below the WLOG_INVERT_T cliff (B6 §2): a
# dry plan's waterlogging_tolerance gives partial credit before the
# inversion — relief ramps from 0 at tolerance 0 to WLOG_GRADED_W at
# the inversion threshold.
WLOG_GRADED_W = 0.5

# ── B6 §3 snow-load + glacier strata (biosphere-addendum-b6) ───────────
# Snow-load tolerance (mm water-equivalent) per snow_adaptation state
# + a height term (a tree's crown rides ABOVE the pack; cushion plants
# are buried): tol_mm = state_tol + height_m x SNOW_HEIGHT_MM_PER_M.
# c_snow_monthly is the K11 snowpack in mm WE (solar.snow_pack) —
# compare like with like. Calibration (2026-08-01, seed-1 landscape
# pass): height 200 mm/m and SNOW_REF_MM 600 keep the temperate herb
# ranges alive (a 1 m herb tolerates ~200 mm WE = ~2 m of snow, the
# insulating-pack regime) while deep-snow cells (>= tol + 600) still
# cost — the "buried cushion" case. Woody plans escape: a 25 m tree
# tolerates 5000 mm + state. The term is a cold-side multiplier folded
# into REQ_COLD (snow load is a winter phenomenon; the T distance is
# dormant-gated, the snow cost is not).
SNOW_TOL_MM = {"none": 0.0, "conical_shed": 1500.0, "flexible": 1000.0,
               "cushion_mat": 800.0}
SNOW_HEIGHT_MM_PER_M = 200.0
SNOW_REF_MM = 600.0        # excess gradient width (sat at 600 mm past tol)
# Glacier habitat term: a land plan on a year-round glacier cell is
# ~1 always (never a verdict — the MEDIUM_VIOLATION_F precedent);
# snow_adaptation != none exempts (the snow-adapted grade lives at the
# ice margin).
GLACIER_EXEMPT_STATES = ("conical_shed", "flexible", "cushion_mat")

# ── B6 §3 canopy-light exposure coefficients (engine-side) ─────────────
# The layer axis modulates how hard the canopy shade reads (understory
# plans EXPECT shade: their coefficient scales the pressure down;
# canopy plans sit at the top of the height comparison and rarely read
# any shade at all). Missing/aquatic layers -> 0.5 / skipped (the
# engine pass is land-only).
LAYER_LIGHT_COEF = {"ground": 0.6, "sward": 0.6, "shrub": 0.8,
                    "subcanopy": 0.9, "canopy": 1.0}

# ── DerivedView keys the adapter reads (req_flora) ────────────────────
# temp_opt_c, temp_breadth_c, moisture_opt, moisture_breadth  [DERIVED
# envelope — pure function of the trait bundle, owner ruling 2026-08-01]
# drought_tolerance, waterlogging_tolerance, salinity_tolerance,
# ph_tolerance, fertility_requirement, growing_season_req
# root_depth_m, height_m, woodiness
# photosynthesis ("C3"/"C4"/"CAM"/...), winter_deciduous (0/1),
# leafout_month, drought_deciduous (0/1),
# bloom_start_month, bloom_length_months,
# medium ("land"/"water"/"dual"), anchoring_need (0..1), holdfast (0/1)
# PLUS the B6 hand-wiring keys (biosphere-addendum-b6-flora-wiring.md):
# mycorrhizal / n_fixation / nutrient_package (fertility + salinity
# credits), drip_tips / leaf_margin (wetness credits), moisture_breadth
# (asymmetric dry/wet relief — the derived breadth is consumed),
# snow_adaptation (snow-load tolerance + glacier exemption),
# layer (canopy-light exposure coefficient; the engine reads it),
# canopy_density (the derived the engine's shade pass reads)
# PLUS the adapter's own derived flags (absent -> term does not apply):
# submerged (0/1) — a benthic water plan that reads photic depth.
# A key may be None/absent for a given plan — the stratum then does not
# apply (e.g. no anchoring on a duckweed).

_MONTH1 = np.arange(1, 13)          # 1-based months (content convention)


def _f(v):
    """float() with None -> NaN sentinel (caller decides how to skip)."""
    return float(v) if isinstance(v, (int, float)) else float("nan")


# ── world context ─────────────────────────────────────────────────────


class WorldContext:
    """All anchor-res fields the stress function needs, loaded ONCE per
    world. Pure data: every array is float32 (or bool/int for masks)."""

    seed: int
    H: int
    W: int
    sea_level: float
    t_c: np.ndarray            # (12,H,W) degC
    p_norm: np.ndarray         # (12,H,W) monthly P on the normalized
                               # 0..1 scale (the derived moisture
                               # envelope is a position on THAT scale;
                               # consumed by the arid-band stats)
    water_potential: np.ndarray  # (12,H,W) soil water status [0,1], land
    fresh_availability: np.ndarray  # (12,H,W) unwritten-fresh habitat [0,1]
    growing_season: np.ndarray  # (H,W) months above GROW_T_C
    eff_nutrient: np.ndarray    # (H,W)
    eff_rooting_m: np.ndarray   # (H,W) m
    eff_sal_add: np.ndarray     # (H,W) [0,1]
    eff_hard: np.ndarray        # (H,W) mix share of hard classes
    eff_loose: np.ndarray       # (H,W) mix share of loose classes
    ground_ph: np.ndarray       # (H,W) soil pH (anchor mix)
    water_ph: np.ndarray        # (H,W) water pH (ocean/fresh/implicit)
    bathy: np.ndarray           # (H,W) m — ocean column depth
    depth_fresh: np.ndarray     # (H,W) m — lake/river column depth
    column_depth: np.ndarray    # (H,W) m — bathy on ocean, depth_fresh
                                # on fresh water, 0 on dry land
    photic: np.ndarray          # (H,W) m — photic depth: marine on
                                # ocean, fresh on lakes/rivers (B4 fix
                                # 2026-08-01), 0 on dry land
    sal_water: np.ndarray       # (H,W) h_salinity / SAL_REF_GKG clipped
    water_cell: np.ndarray      # (H,W) bool ocean|sea|lake
    land_cell: np.ndarray       # (H,W) bool
    hand_m: np.ndarray          # (H,W) m height above nearest drainage
    ground_class: np.ndarray    # (H,W) uint8 argmin over ground_d2
    eff_retention: np.ndarray   # (H,W) (kept for completeness/debug)
    wind_ms: np.ndarray         # (H,W) m/s storm proxy: max over months
                                # of the monthly-mean surface wind speed
    bottom_temp: np.ndarray     # (H,W) degC annual bottom temperature
                                # (ocean AND fresh water; 0 on dry land)
                                # — submerged plans read THIS for the
                                # climate T term (B4: the deep bottom
                                # has no seasons)
    mix_ids: np.ndarray         # (3,H,W) uint8 top-3 ground mix classes
    mix_w: np.ndarray           # (3,H,W) float32 mix weights — the
                                # best-of-class substrate semantics read
                                # these directly (owner ruling 2026-08-01)
    def __init__(self) -> None:
        pass


def _ground_anchor_mix(z, manifest: dict, sea: float):
    """The anchor top-3 ground mix (softmax over -d2 at TAU=1 dotted
    into the stable top-3 classes, renormalized — B5 §3's consume-time
    convention, as implemented by build_ground). The mix is NOT
    persisted (only ground_d2 is), and the top-3 ids cannot be
    reconstructed from d2 alone (sub-floor generator weights tie at the
    -log floor), so the deterministic B3 pass is RE-RUN — 0.1 s, pure
    function of (dump, manifest, seed). The persisted ground_eff_*
    rasters then verify the re-derived mix bit-for-bit."""
    from exp.k14_worldprod.derived import vents
    from exp.k14_worldprod.ground import build_ground
    vent_pts, spring_pts = vents(z, manifest)[1:]
    return build_ground(z, manifest, sea, vent_pts + spring_pts)


def load_world(seed: int) -> WorldContext:
    """Load every anchor-res world component once (B5 §3): the K11 dump
    via exp.artifacts (regenerating if absent) plus the persisted K14
    derived products; water fields re-derived at anchor resolution."""
    ctx = WorldContext()
    ctx.seed = seed
    k11_dir = artifact_require("k11", seed)
    manifest = json.loads((k11_dir / "world.json").read_text())
    ctx.sea_level = sea = float(manifest["sea_level"])
    with np.load(k11_dir / "world.npz") as zf:
        z = {k: zf[k] for k in zf.files}
    with np.load(K14_OUT / f"seed_{seed:08d}" / "derived.npz") as df:
        d = {k: df[k] for k in df.files}

    H, W = z["h_ocean_mask"].shape
    ctx.H, ctx.W = H, W

    # ── climate / masks / hydrology ──
    ctx.t_c = temp_c(z["c_T_monthly"]).astype(np.float32)
    # the derived moisture envelope (moisture_opt/moisture_breadth) is a
    # position on the normalized 0..1 P scale (c_P_monthly raw;
    # precip_mm is p*400) — the water-availability term compares like
    # with like (water_potential is on the same 0..1 scale).
    ctx.p_norm = z["c_P_monthly"].astype(np.float32)
    ctx.growing_season = growing_season(z).astype(np.float32)
    ocean = (z["h_ocean_mask"] | z["h_sea_mask"]).astype(bool)
    lake = z["h_lake_mask"].astype(bool)
    ctx.water_cell = ocean | lake
    ctx.land_cell = ~ctx.water_cell
    ctx.hand_m = hand_m(z["h_hand"], sea).astype(np.float32)
    river_any = (z["h_river_width_monthly"] > 0).any(axis=0) \
        if "h_river_width_monthly" in z else z["h_river_mask"]
    river_any = river_any.astype(bool)
    # the fresh-water domain (lakes + any-month rivers) — the fresh
    # water-column fields and fresh_ph read it; column_depth zeros on
    # dry land and hands ocean cells to bathy.
    fresh = lake | river_any
    ctx.sal_water = np.clip(z["h_salinity"].astype(np.float32)
                            / SAL_REF_GKG, 0.0, 1.0)

    # ── wind exposure at anchor (pure function of the delivered dump —
    # ── recompute, never downsample). The bottom temperature moved to
    # the water-column block below (it is fresh-aware since 2026-08-01).
    wu, wv = z["c_wind_u"], z["c_wind_v"]
    monthly_speed = np.hypot(wu, wv).mean(axis=1)      # (12,h,w) m/s
    wind = monthly_speed.max(axis=0).astype(np.float32)  # storm proxy
    if wind.shape != (H, W):
        # the delivered wind lives on its own coarser grid (wind_coarse;
        # 128² vs anchor 256² on seed 1) — bilinear-upsample the smooth
        # forcing field (the k14 marine-biome lesson: kron reads blocky)
        fy, fx = H // wind.shape[0], W // wind.shape[1]
        wind = _upsample(wind, fy) if fx == fy else \
            np.repeat(np.repeat(wind, fy, axis=0), fx, axis=1)
    ctx.wind_ms = wind.astype(np.float32)

    # ── ground properties: the anchor top-3 mix re-derived by re-running
    # ── the deterministic B3 pass, verified against the persisted
    # ── ground_eff_* rasters (B5 §3 shared precompute).
    g = _ground_anchor_mix(z, manifest, sea)
    mix_ids, mix_w = g["mix_ids"], g["mix_w"]
    ctx.mix_ids = mix_ids.astype(np.uint8)
    ctx.mix_w = mix_w.astype(np.float32)
    ctx.ground_ph = mix_ph(mix_ids, mix_w).astype(np.float32)
    eff = eff_props(mix_ids, mix_w)
    ctx.eff_retention = eff["retention"].astype(np.float32)
    ctx.eff_nutrient = eff["nutrient"].astype(np.float32)
    ctx.eff_rooting_m = eff["rooting_m"].astype(np.float32)
    ctx.eff_sal_add = eff["sal_add"].astype(np.float32)
    ctx.eff_hard = eff["hard"].astype(np.float32)
    ctx.eff_loose = eff["loose"].astype(np.float32)
    persisted = {k: d[f"ground_eff_{k}"].astype(np.float32) for k in eff}
    for k in eff:
        if not np.array_equal(persisted[k], ctx.__dict__[f"eff_{k}"]):
            raise RuntimeError(
                f"anchor eff_{k} from the re-derived mix differs from the "
                f"persisted ground_eff_{k} raster — ground pass drifted")
    ctx.ground_class = g["class_id"].astype(np.uint8)

    # ── plant water relations at anchor (moisture.build_moisture) ──
    mo = _moisture.build_moisture(
        z, sea, {"retention": ctx.eff_retention,
                 "sal_add": ctx.eff_sal_add})
    ctx.water_potential = mo["water_potential"].astype(np.float32)
    ctx.fresh_availability = mo["fresh_availability"].astype(np.float32)

    # ── water pH at anchor (pointwise re-derivation; B5 §3) ──
    ctx.bathy = _water.bathymetry_m(z, sea).astype(np.float32)
    bed_ph = ctx.ground_ph
    land_a = ctx.land_cell
    land_w = land_a.astype(np.float64)
    lsum = _water._box_mean(bed_ph * land_w, _water.PH_WINDOW_C)
    lcnt = _water._box_mean(land_w, _water.PH_WINDOW_C)
    land_mean = np.where(lcnt > 1e-9, lsum / np.maximum(lcnt, 1e-9),
                         bed_ph)
    bog_share = _water._box_mean(
        (ctx.ground_class == GROUND_ID["bog"]).astype(np.float64),
        _water.PH_WINDOW_C)
    wph = np.where(ocean, _water.ocean_ph(ctx.bathy),
                   np.where(fresh,
                            _water.fresh_ph(bed_ph, land_mean, bog_share),
                            np.where(ctx.fresh_availability.mean(axis=0) > 0,
                                     _water.fresh_ph(bed_ph, land_mean,
                                                     bog_share),
                                     0.0)))
    ctx.water_ph = wph.astype(np.float32)

    # ── water column at anchor: column depth, photic depth, and the
    # ── annual bottom temperature. Fresh water (lakes/rivers) gets its
    # OWN photic and bottom-temp derivations — the marine fields are
    # ocean-only, and reading them on fresh water used to zero every
    # submerged freshwater plan (B4 fix 2026-08-01). The fresh column
    # depth uses the lake/river h_depth decode of
    # freshwater_productivity (above-sea linear elevation segment).
    from exp.k11_worldgen.units import ELEV_MAX_M
    ctx.depth_fresh = (z["h_depth"].astype(np.float64) / (1.0 - sea)
                       * ELEV_MAX_M).astype(np.float32)
    ctx.column_depth = np.where(
        ocean, ctx.bathy,
        np.where(fresh, ctx.depth_fresh, 0.0)).astype(np.float32)
    ctx.bottom_temp = np.where(
        ocean,
        _water.bottom_temp_c(z, sea, ctx.bathy),
        _water.fresh_bottom_temp_c(z, sea, ctx.depth_fresh, fresh)
    ).astype(np.float32)
    dis_ref = max(float(np.percentile(z["h_discharge"], 99.0)), 1e-12)
    plume = _plume_source(z, ocean, dis_ref)
    mprod_prov = marine_productivity(z, _currents_payload(k11_dir))
    fprod_ann = freshwater_productivity(z, sea).mean(axis=0)
    ctx.photic = np.where(
        ocean,
        _water.photic_depth_m(ctx.bathy, plume, mprod_prov.mean(axis=0),
                              PLUME_WEIGHT),
        _water.fresh_photic_depth_m(bog_share, fprod_ann, fresh)
    ).astype(np.float32)
    return ctx


def _ensure_snow_glacier(ctx: WorldContext) -> None:
    """Attach the B6 §3 snow-load / glacier fields to *ctx*, idempotent:
    ``ctx.snow_mm`` (12,H,W) mm water-equivalent (K11 c_snow_monthly —
    the snowpack bucket of solar.snow_pack) and ``ctx.glacier`` (H,W)
    bool (h_glacier_mask). Loaded from the K11 dump on first use (the
    ctx-builder is shared with another line of work, so the strata
    self-provision rather than depend on load_world); a synthetic ctx
    that explicitly sets either field skips the load entirely.
    Deterministic: pure function of ctx.seed."""
    if hasattr(ctx, "snow_mm") or hasattr(ctx, "glacier"):
        return
    k11_dir = artifact_require("k11", ctx.seed)
    with np.load(k11_dir / "world.npz") as zf:
        ctx.snow_mm = zf["c_snow_monthly"].astype(np.float32)
        ctx.glacier = zf["h_glacier_mask"].astype(bool)


def _currents_payload(seed_dir: Path):
    """The persisted currents payload for the monthly velocity field
    (falls back to the annual mean field when absent — same convention
    as k14_worldprod.derived._currents_payload)."""
    try:
        from exp.k11_worldgen.persist import load_world
        return load_world(str(seed_dir))["world"]["currents"]
    except Exception:
        return None


# ── the DerivedView (record side) ─────────────────────────────────────


def _view_from_record(axes: dict, preset_id: str | None,
                      pack: ContentPack) -> dict:
    """The DerivedView the adapter reads from a record's axes: flora
    derive's effective_climate — the climate ENVELOPE as a pure derived
    of the trait bundle (owner ruling 2026-08-01; tolerance traits come
    from the axes) — plus the plan descriptors (medium from the plan
    registry, anchoring_need = clip(height x woodiness / ANCHOR_REF_M),
    holdfast, submerged, phenology flags). Pure function of record +
    content."""
    node_plan = str(axes.get("_plan") or "")
    plan = pack.registry.plans.get(node_plan)
    medium = plan.medium if plan is not None else "land"
    node = Node(path="", rank=Rank.SPECIES, parent=None, sid="0" * 16,
                plan=node_plan, preset=preset_id, axes=dict(axes))
    view = dict(effective_climate(node, pack))
    lp = str(axes.get("leaf_persistence") or "evergreen")
    dt = str(axes.get("deciduous_trigger") or "none")
    height = float(axes.get("height_m") or 0.0)
    wood = float(axes.get("woodiness") or 0.0)
    view.update({
        "root_depth_m": axes.get("root_depth_m"),
        "height_m": height,
        "woodiness": wood,
        "photosynthesis": str(axes.get("photosynthesis") or "C3"),
        "winter_deciduous": int(lp == "winter_deciduous"
                                or dt == "winter"),
        "leafout_month": axes.get("leafout_month"),
        "drought_deciduous": int(lp == "drought_deciduous"
                                 or dt == "drought"),
        "bloom_start_month": axes.get("bloom_start_month"),
        "bloom_length_months": axes.get("bloom_length_months"),
        "medium": medium,
        "anchoring_need": min(1.0, max(0.0,
                                       height * wood / ANCHOR_REF_M)),
        "holdfast": int(str(axes.get("root_type") or "") == "holdfast"),
        "submerged": int(str(axes.get("layer") or "")
                         == "aquatic_benthic"),
        # ── B6 hand-wiring keys (biosphere-addendum-b6; the strata
        # ── below read them) — mirrors FloraSim.derive exactly.
        "mycorrhizal": str(axes.get("mycorrhizal") or "none"),
        "n_fixation": str(axes.get("n_fixation") or "none"),
        "nutrient_package": str(axes.get("nutrient_package") or "none"),
        "drip_tips": axes.get("drip_tips"),
        "leaf_margin": str(axes.get("leaf_margin") or "entire"),
        "snow_adaptation": str(axes.get("snow_adaptation") or "none"),
        "layer": str(axes.get("layer") or "ground"),
        "canopy_density": _derived_canopy_density(node),
        # engine-side dispersal keys (K15 rounds; the stress strata
        # never read them) — mirrors FloraSim.derive.
        "dispersal_channels": axes.get("dispersal_channels"),
        "propagule_mass_mg": axes.get("propagule_mass_mg"),
        "propagule_count": axes.get("propagule_count"),
        "seed_bank": axes.get("seed_bank"),
        # per-capita space demand for the engine's density term
        "crown_spread_m": axes.get("crown_spread_m"),
        # jump-dispersal frequency (long-range hops/yr) for the engine
        "jump_rate": axes.get("jump_rate"),
    })
    return view


def species_view(node, pack: ContentPack) -> dict:
    """The DerivedView for one tree SPECIES node (radiated axes)."""
    axes = dict(node.axes or {})
    axes["_plan"] = node.plan or ""
    return _view_from_record(axes, node.preset, pack)


def preset_view(preset_id: str, pack: ContentPack) -> dict:
    """The DerivedView for an AUTHORED preset (its committed axes — the
    acceptance presets of B5 §8 are authored traits, never drifted)."""
    preset = pack.presets[preset_id]
    axes = {**preset.get("knobs", {}), **preset.get("axes", {})}
    axes["_plan"] = preset["preset"]["plan"]
    return _view_from_record(axes, preset_id, pack)


# ── strata (each returns a (12,H,W) float32 suitability in [0,1]) ─────


def _climate_factors(view: dict, ctx: WorldContext) -> dict[str, np.ndarray]:
    """B5 §4.1 as a SPLIT one-sided pair (req_flora ruling 2026-08-01):
    REQ_COLD = saturating shortfall of T below the envelope optimum —
    phenology/dormancy gated, multiplied by the growing-season term and
    the C4/CAM cold penalty; REQ_HEAT = saturating excess of T above
    the optimum. cold x heat is exactly the symmetric distance, so F is
    unchanged by the split. The moisture (P) half is gone — the derived
    moisture envelope feeds pressure:water/waterlogging instead. The
    envelope values (temp_opt_c/temp_breadth_c) are a pure DERIVED of
    the trait bundle, so they move as stress pushes the traits."""
    H, W = ctx.H, ctx.W
    opt_t = _f(view.get("temp_opt_c"))
    b_t = _f(view.get("temp_breadth_c"))
    winter_dec = int(view.get("winter_deciduous") or 0)
    leafout = view.get("leafout_month")
    photo = str(view.get("photosynthesis") or "C3")

    cold = np.ones((12, H, W), dtype=np.float32)
    heat = np.ones((12, H, W), dtype=np.float32)
    if np.isnan(opt_t) or b_t <= 0:
        return {REQ_COLD: cold, REQ_HEAT: heat}
    opt = np.float32(opt_t)
    b = np.float32(b_t)
    # submerged (benthic water) plans read the ANNUAL bottom temperature,
    # not the surface monthly field — B4: the deep bottom has no
    # seasons, shelf bottoms are damped.
    submerged = int(view.get("submerged") or 0)
    t_field = ctx.bottom_temp[None] if submerged else ctx.t_c

    cold_cost = sat((opt - t_field) / b)      # T below opt
    heat_cost = sat((t_field - opt) / b)      # T above opt
    if winter_dec and isinstance(leafout, (int, float)):
        leaf_on = (_MONTH1 >= int(leafout))[:, None, None]
        cold_cost = np.where(leaf_on, cold_cost, 0.0)  # dormant: no cold
    if not submerged:
        # growing-season dormancy (owner ruling 2026-08-01): months
        # below GROW_T_C are dormant — no T-distance cost (a taiga
        # winter is not niche distance). Submerged plans read the
        # annual bottom temperature: no winter, no dormancy.
        cold_cost = np.where(t_field < np.float32(GROW_T_C), 0.0,
                             cold_cost)
    cold = sat(1.0 - cold_cost).astype(np.float32)
    heat = sat(1.0 - heat_cost).astype(np.float32)

    # growing season (annual, saturating shortfall) — a cold-side term:
    # a short season IS cold climate. Folded into REQ_COLD.
    gs_req = _f(view.get("growing_season_req"))
    if not np.isnan(gs_req):
        f_gs = shortfall_suit(ctx.growing_season, np.float32(gs_req),
                              np.float32(GS_REF_MONTHS))
        cold = (cold * f_gs[None]).astype(np.float32)

    # C4/CAM cold penalty (C3/none/chemosymbiosis carry none); gated to
    # the growing band — below GROW_T_C every plan is dormant, so C4's
    # real disadvantage is the COOL growing season, not the winter.
    if photo in ("C4", "CAM"):
        pen = sat((np.float32(COLD_PEN_T_C) - ctx.t_c)
                  / np.float32(COLD_PEN_SPAN_C))
        pen = np.where(ctx.t_c < np.float32(GROW_T_C), 0.0, pen)
        cold = (cold * (1.0 - np.float32(COLD_PEN_W) * pen)).astype(
            np.float32)

    # B6 §3 snow-load term (folded into REQ_COLD, land plans only): a
    # winter month's snowpack above the plan's tolerance costs —
    # tol_mm = state_tol(snow_adaptation) + height_m x SNOW_HEIGHT_MM.
    # The T distance above is dormant-gated (a taiga winter is not
    # niche distance); the snow LOAD is a real winter cost, so it is
    # applied ungated. snow_adaptation is the GRADED reliever (it
    # currently only shifts temp_opt in the derive envelope — here its
    # state carries the tolerance). Tall plants ride above the pack
    # (the height term); cushion mats are buried (no height credit).
    if not submerged and view.get("medium") == "land" \
            and hasattr(ctx, "snow_mm"):
        snow_state = str(view.get("snow_adaptation") or "none")
        tol_mm = SNOW_TOL_MM.get(snow_state, 0.0) \
            + float(view.get("height_m") or 0.0) * SNOW_HEIGHT_MM_PER_M
        f_snow = excess_suit(ctx.snow_mm, np.float32(tol_mm),
                             np.float32(SNOW_REF_MM))
        cold = (cold * f_snow).astype(np.float32)
    # shape contract: every factor is (12,H,W). A submerged plan reads
    # the ANNUAL bottom temperature, so its cold/heat planes are
    # month-constant (1,H,W) — broadcast (the reduction indexes months).
    if cold.shape[0] == 1:
        cold = np.broadcast_to(cold, (12, H, W)).copy()
    if heat.shape[0] == 1:
        heat = np.broadcast_to(heat, (12, H, W)).copy()
    return {REQ_COLD: cold.astype(np.float32), REQ_HEAT: heat.astype(np.float32)}


def _bloom_frost(view: dict, ctx: WorldContext) -> np.ndarray:
    """B5 §4.1 bloom-month frost: an extra cost term in the bloom
    window (bloom_start_month .. + bloom_length_months), costly but
    never lethal (f >= 1 - BLOOM_FROST_W). Returns REQ_BLOOM_FROST."""
    start = view.get("bloom_start_month")
    length = view.get("bloom_length_months")
    if not isinstance(start, (int, float)) or not isinstance(length,
                                                             (int, float)):
        return np.ones((12, ctx.H, ctx.W), dtype=np.float32)
    bloom = ((_MONTH1 - int(start)) % 12) < float(length)   # (12,)
    frost = sat((np.float32(FROST_T_C) - ctx.t_c)
                / np.float32(FROST_SPAN_C))
    f = 1.0 - np.float32(BLOOM_FROST_W) * np.where(bloom[:, None, None],
                                                   frost, 0.0)
    return f.astype(np.float32)


def _ph_suit_split(env_ph, opt_ph: float):
    """The split one-sided pH suitability (req_flora ruling): the low
    side is the shortfall toward the optimum (env too acidic), the high
    side the excess past it (env too alkaline). low x high is exactly
    dist_suit, so the composed F is unchanged by the split."""
    opt = np.float32(opt_ph)
    b = np.float32(PH_BREADTH)
    return (shortfall_suit(env_ph, opt, b).astype(np.float32),
            excess_suit(env_ph, opt, b).astype(np.float32))


def _sal_tol_eff(view: dict, sal_tol: float) -> float:
    """Effective salinity tolerance: the axis value plus the B6 §2
    halophyte grade credit (nutrient_package == "halophyte" — the salt-
    adapted package BUYS tolerance; a pressure:salinity responder with
    no factor read until this wiring). Shared by the ground stratum
    (land/dual) and the water-chemistry stratum (water plans — the
    halophyte presets are kelp/seagrass/coral/sponge, all water)."""
    if str(view.get("nutrient_package") or "none") == "halophyte":
        return sal_tol + HALOPHYTE_CREDIT
    return sal_tol


def _substrate_suits(view: dict, ctx: WorldContext) -> dict[str, np.ndarray]:
    """Per-CLASS substrate suitabilities (3,H,W) for the plans that read
    the ground (land + dual): the top-3 mix classes are physically
    present patches, not an average (owner ruling 2026-08-01). The cell
    factor is the BEST patch (max over classes, taken by the callers);
    the usable share U = sum w_i x prod f_i goes to the engine's
    capacity split (evaluate attaches it as "substrate_share"). A
    requirement the plan does not carry is absent (= 1 in the
    product). Water-medium plans read no ground."""
    if view.get("medium") == "water":
        return {}
    ids = ctx.mix_ids
    out: dict[str, np.ndarray] = {}
    root = _f(view.get("root_depth_m"))
    if not np.isnan(root):
        out[REQ_ROOTING] = excess_suit(
            np.float32(root), PROP_TABLES["rooting_m"][ids],
            np.float32(ROOT_REF_M)).astype(np.float32)
    fert = _f(view.get("fertility_requirement"))
    if not np.isnan(fert):
        # B6 §2 fertility CREDITS: an acquired symbiosis grade lifts the
        # effective nutrient of every mix class (mycorrhizal /
        # n_fixation are pressure:fertility responders but no factor
        # read them — the credit is the read). The credit also raises
        # the substrate_share on poor soil (the plant genuinely uses
        # more of the cell), via the per-class suits below.
        credit = (MYC_CREDIT.get(str(view.get("mycorrhizal") or "none"),
                                 0.0)
                  + NFIX_CREDIT.get(str(view.get("n_fixation") or "none"),
                                    0.0))
        out[REQ_FERTILITY] = shortfall_suit(
            PROP_TABLES["nutrient"][ids] + np.float32(credit),
            np.float32(min(max(fert, 0.0), 1.0)),
            np.float32(FERT_REF)).astype(np.float32)
    ph_tol = _f(view.get("ph_tolerance"))
    if not np.isnan(ph_tol):
        opt_ph = PH_LO + PH_SPAN * min(max(ph_tol, 0.0), 1.0)
        lo, hi = _ph_suit_split(CLASS_PH[ids], opt_ph)
        if view.get("medium") == "dual":
            w_lo, w_hi = _ph_suit_split(ctx.water_ph, opt_ph)
            lo = np.minimum(lo, w_lo[None])
            hi = np.minimum(hi, w_hi[None])
        out[REQ_PH_LOW] = lo.astype(np.float32)
        out[REQ_PH_HIGH] = hi.astype(np.float32)
    sal_tol = _f(view.get("salinity_tolerance"))
    if not np.isnan(sal_tol):
        sal_env = PROP_TABLES["sal_add"][ids]
        if view.get("medium") == "dual":
            sal_env = np.maximum(sal_env, ctx.sal_water[None])
        # B6 §2: nutrient_package "halophyte" is a salinity-tolerance
        # GRADE credit (a pressure:salinity responder with no factor
        # read — this is the read).
        sal_tol_eff = _sal_tol_eff(view, sal_tol)
        out[REQ_SALINITY] = excess_suit(
            sal_env, np.float32(min(max(sal_tol_eff, 0.0), 1.0)),
            np.float32(SAL_REF)).astype(np.float32)
    return out


def _ground_terms(view: dict, ctx: WorldContext,
                  cs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """B5 §4.2 for LAND (and dual) plans: water availability and
    waterlogging (wet-obligate plans read fresh_availability for both —
    owner ruling 2026-08-01) monthly; fertility, pH, salinity annual
    best-of-class (the mix's patches, not its mean). Water terms are
    dormant-month gated (below GROW_T_C: no uptake, no waterlogging)."""
    H, W = ctx.H, ctx.W
    opt_p = _f(view.get("moisture_opt"))
    drought = _f(view.get("drought_tolerance"))
    need = np.float32(np.clip(
        (0.0 if np.isnan(opt_p) else opt_p)
        * (1.0 if np.isnan(drought) else 1.0 - min(drought, 1.0)),
        0.0, 1.0))

    wlog = _f(view.get("waterlogging_tolerance"))
    if not np.isnan(wlog) and wlog >= WLOG_INVERT_T:
        # wet-obligate land plan: the marsh IS the habitat — read the
        # unwritten-wetland field for water availability AND for the
        # inverted waterlogging requirement (the saturated end becomes
        # what the plan NEEDS, dry ground the cost).
        f_water = shortfall_suit(ctx.fresh_availability, need,
                                 np.float32(WATER_REF))
        f_wlog = invert(excess_suit(ctx.fresh_availability,
                                    np.float32(WLOG_WET_LIMIT),
                                    np.float32(WLOG_WET_REF)))
    else:
        f_water = shortfall_suit(ctx.water_potential, need,
                                 np.float32(WATER_REF))
        if np.isnan(wlog):
            f_wlog = np.ones((12, H, W), dtype=np.float32)
        else:
            f_wlog = excess_suit(ctx.water_potential,
                                 np.float32(WLOG_DRY_LIMIT),
                                 np.float32(WLOG_DRY_REF))

    # B6 §2 graded reliefs, applied to the COST (1 - f) of the one-sided
    # terms — a DRY plan's drought/moisture/wet traits buy partial
    # relief before any inversion (never a cutoff, and the wet-obligate
    # inversion above is untouched):
    #   moisture_breadth: a wide derived moisture band is asymmetric
    #       graded relief — dry side (water) x MB_DRY_W, wet side
    #       (waterlogging) x MB_WET_W (consumed, per B6 §2).
    #   waterlogging_tolerance below WLOG_INVERT_T: graded credit
    #       ramping to WLOG_GRADED_W at the inversion cliff.
    #   drip_tips (0..1) + serrate/toothed leaf_margin: wetness credits
    #       on the saturated-end cost for very wet cells (B6 §2 choice:
    #       wetness relief rides waterlogging, not bloom_frost — frost
    #       is a cold signal, not a wetness one).
    mb = _f(view.get("moisture_breadth"))
    dry_relief = 0.0 if np.isnan(mb) else MB_DRY_W * min(max(mb, 0.0), 1.0)
    wet_relief = 0.0
    if not np.isnan(mb):
        wet_relief += MB_WET_W * min(max(mb, 0.0), 1.0)
    if not np.isnan(wlog) and wlog < WLOG_INVERT_T:
        wet_relief += WLOG_GRADED_W * max(0.0, min(wlog, 1.0)) \
            / WLOG_INVERT_T
    drip = _f(view.get("drip_tips"))
    if not np.isnan(drip):
        wet_relief += DRIP_WET_W * min(max(drip, 0.0), 1.0)
    if str(view.get("leaf_margin") or "entire") in ("serrate", "toothed"):
        wet_relief += LEAF_WET_W
    wet_relief = min(1.0, wet_relief)
    f_water = np.where(dry_relief > 0.0,
                       1.0 - (1.0 - f_water) * np.float32(1.0 - dry_relief),
                       f_water).astype(np.float32)
    f_wlog = np.where(wet_relief > 0.0,
                      1.0 - (1.0 - f_wlog) * np.float32(1.0 - wet_relief),
                      f_wlog).astype(np.float32)

    # growing-season dormancy (the climate ruling applied to uptake):
    # a dormant plant does not transpire and frozen ground does not
    # waterlog roots — no water/waterlogging cost below GROW_T_C.
    if not int(view.get("submerged") or 0):
        grow = ctx.t_c >= np.float32(GROW_T_C)
        f_water = np.where(grow, f_water, np.float32(1.0))
        f_wlog = np.where(grow, f_wlog, np.float32(1.0))

    out = {
        REQ_WATER: f_water.astype(np.float32),
        REQ_WATERLOGGING: f_wlog.astype(np.float32),
    }
    # substrate requirements: the BEST patch of the mix (per-class max);
    # rooting is annual and rides the tail terms.
    for req, suits in cs.items():
        if req == REQ_ROOTING:
            continue
        out[req] = np.broadcast_to(
            suits.max(axis=0).astype(np.float32), (12, H, W)).copy()
    return out


def _water_chemistry(view: dict, ctx: WorldContext) -> dict[str, np.ndarray]:
    """The pH/salinity terms for WATER-medium plans: water_ph and the
    normalized h_salinity (the soil's eff_sal_add is the water's own
    business; the OSMOTIC half rides water_potential for land)."""
    H, W = ctx.H, ctx.W
    ph_tol = _f(view.get("ph_tolerance"))
    if np.isnan(ph_tol):
        f_ph_lo = f_ph_hi = np.ones((H, W), dtype=np.float32)
    else:
        opt_ph = PH_LO + PH_SPAN * min(max(ph_tol, 0.0), 1.0)
        f_ph_lo, f_ph_hi = _ph_suit_split(ctx.water_ph, opt_ph)
    sal_tol = _f(view.get("salinity_tolerance"))
    if np.isnan(sal_tol):
        f_sal = np.ones((H, W), dtype=np.float32)
    else:
        # B6 §2 halophyte grade credit (shared with the ground stratum
        # — the halophyte presets are water plans: kelp/seagrass/coral/
        # sponge, all salinity_tolerance ~0.9-0.95; the credit grades
        # the ionic excess, the osmotic half rides water_potential).
        sal_tol_eff = _sal_tol_eff(view, sal_tol)
        f_sal = excess_suit(ctx.sal_water,
                            np.float32(min(max(sal_tol_eff, 0.0), 1.0)),
                            np.float32(SAL_REF))
    return {
        REQ_PH_LOW: np.broadcast_to(f_ph_lo, (12, H, W)).copy(),
        REQ_PH_HIGH: np.broadcast_to(f_ph_hi, (12, H, W)).copy(),
        REQ_SALINITY: np.broadcast_to(f_sal.astype(np.float32),
                                      (12, H, W)).copy(),
    }


def _tail_terms(view: dict, ctx: WorldContext,
                freshwater: bool,
                cs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    """B5 §4.3 tail terms: rooting (best-of-class), anchoring (hard/
    loose SHARES — already patch-probabilities), the medium boundary
    (replaced by the habitat term for freshwater plans), and submerged
    light. Annual (H,W), broadcast to months."""
    H, W = ctx.H, ctx.W
    out: dict[str, np.ndarray] = {}

    if REQ_ROOTING in cs:
        out[REQ_ROOTING] = np.broadcast_to(
            cs[REQ_ROOTING].max(axis=0), (12, H, W)).copy()

    holdfast = int(view.get("holdfast") or 0)
    wood = _f(view.get("woodiness"))
    medium = view.get("medium")
    f_anchor = None
    if holdfast:
        f_anchor = shortfall_suit(ctx.eff_hard,
                                  np.float32(HOLDFAST_NEED), 1.0)
    elif medium == "land" and not np.isnan(wood) and wood > 0.0:
        need = float(view.get("anchoring_need") or 0.0)
        if need > 0.0:
            wmod = np.clip(ctx.wind_ms / np.float32(WIND_REF_MS),
                           np.float32(WIND_MOD_MIN),
                           np.float32(WIND_MOD_MAX))
            f_anchor = shortfall_suit(1.0 - ctx.eff_hard,
                                      np.float32(need) * wmod, 1.0)
    if f_anchor is not None:
        out[REQ_ANCHORING] = np.broadcast_to(f_anchor.astype(np.float32),
                                             (12, H, W)).copy()

    if freshwater:
        # the habitat term IS the medium for freshwater plans (B5 §4.5):
        # fresh_availability is monthly and graded; no boundary factor.
        out[REQ_FRESH_HABITAT] = ctx.fresh_availability.astype(np.float32)
    else:
        if medium == "dual":
            f_medium = np.ones((H, W), dtype=np.float32)
        elif medium == "water":
            f_medium = np.where(ctx.water_cell,
                                np.float32(1.0),
                                np.float32(MEDIUM_VIOLATION_F))
        else:                                   # land
            f_medium = np.where(ctx.land_cell,
                                np.float32(1.0),
                                np.float32(MEDIUM_VIOLATION_F))
        out[REQ_MEDIUM] = np.broadcast_to(f_medium, (12, H, W)).copy()

    if int(view.get("submerged") or 0):
        f_light = shortfall_suit(ctx.photic, ctx.column_depth,
                                 np.float32(LIGHT_REF_M))
        out[REQ_SUBMERGED_LIGHT] = np.broadcast_to(
            f_light.astype(np.float32), (12, H, W)).copy()
    return out


def _glacier_factor(view: dict, ctx: WorldContext) -> np.ndarray:
    """B6 §3 glacier habitat term (land plans only): a year-round
    glacier cell is ~1 always (MEDIUM_VIOLATION_F, the medium-boundary
    precedent — a very high cost, never a deletion); a snow-adapted
    plan (snow_adaptation != none) is exempt — the snow-adapted grade
    lives at the ice margin. Water/dual plans keep their own medium
    boundary (glaciers sit on land cells)."""
    H, W = ctx.H, ctx.W
    f = np.ones((H, W), dtype=np.float32)
    if view.get("medium") != "land" or not hasattr(ctx, "glacier"):
        return f
    if str(view.get("snow_adaptation") or "none") in GLACIER_EXEMPT_STATES:
        return f
    return np.where(ctx.glacier, np.float32(MEDIUM_VIOLATION_F), f)


# ── evaluation ────────────────────────────────────────────────────────


def evaluate(view: dict, ctx: WorldContext) -> dict[str, np.ndarray]:
    """Per-requirement suitability arrays (12,H,W) float32 keyed by the
    req_flora names, plus "F" (the product) and "s_env" (1 - 2F).
    Terms that do not apply to a plan (missing/None view keys) are
    omitted entirely — an absent factor is 1 (B5: the empty product is
    1, maximal vigor). Pure and deterministic: no draws, no state.

    Also "substrate_share" (H,W): the usable-substrate share U = sum
    w_i x prod f_i over the mix classes (1.0 for water-medium plans).
    CAPACITY metadata, not a stress factor — it never enters F or the
    verdict provenance; the engine splits carrying capacity by it
    (K_L = K x U, spec §6)."""
    _ensure_snow_glacier(ctx)
    medium = view.get("medium", "land")
    salinity = _f(view.get("salinity_tolerance"))
    freshwater = (medium == "water" and not np.isnan(salinity)
                  and salinity < FRESH_SAL_MAX)

    cs = _substrate_suits(view, ctx)
    factors: dict[str, np.ndarray] = {}
    factors.update(_climate_factors(view, ctx))
    factors[REQ_BLOOM_FROST] = _bloom_frost(view, ctx)
    if medium != "water":
        factors.update(_ground_terms(view, ctx, cs))
    else:
        factors.update(_water_chemistry(view, ctx))
    factors.update(_tail_terms(view, ctx, freshwater, cs))
    factors[REQ_GLACIER] = np.broadcast_to(
        _glacier_factor(view, ctx), (12, ctx.H, ctx.W)).copy()

    F = np.ones((12, ctx.H, ctx.W), dtype=np.float32)
    for a in factors.values():
        F *= a
    s_env = 1.0 - 2.0 * F
    out = dict(factors)
    out["F"] = F
    out["s_env"] = s_env.astype(np.float32)
    if cs:
        per_class = np.ones_like(next(iter(cs.values())))
        for suits in cs.values():
            per_class *= suits
        out["substrate_share"] = (ctx.mix_w * per_class).sum(
            axis=0).astype(np.float32)
    else:
        out["substrate_share"] = np.ones((ctx.H, ctx.W), dtype=np.float32)
    return out


def verdict_at(factors: dict[str, np.ndarray], y: int, x: int,
               month: int) -> StressVerdict:
    """Materialize the StressVerdict for one (cell, month) from an
    evaluate() output: the per-requirement scalars become the
    provenance, and kernel.stress.compose emits the signed s (F is the
    product, s = 1 - 2F) — the sim feed path consumes this."""
    from kernel.stress import compose
    provenance = {}
    for name, arr in factors.items():
        if name in ("F", "s_env", "substrate_share"):
            continue
        provenance[name] = float(arr[month, y, x])
    r = compose(provenance)
    return StressVerdict(s=float(r.s), provenance=r.factors)


# ── world utilities for acceptance / downstream consumers ─────────────


def annual_stress(factors: dict[str, np.ndarray]) -> np.ndarray:
    """Annual-mean signed stress (12 -> (H,W)) — what the rounds
    integrate over (B5 §1 rounds contract)."""
    return factors["s_env"].mean(axis=0)


def worst_stress(factors: dict[str, np.ndarray]) -> np.ndarray:
    """Worst-month signed stress (12 -> (H,W)): 1 - 2 x F_worst per
    cell — the engine's §5.1 reduced form (ONE aggregation for
    selection and demography). With the dormancy gate the worst month
    is automatically a growing-season month."""
    return (1.0 - 2.0 * factors["F"].min(axis=0)).astype(np.float32)
