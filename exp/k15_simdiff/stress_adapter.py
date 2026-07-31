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
  was upsampled from).
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from exp.artifacts import require as artifact_require
from exp.k11_worldgen.units import hand_m, temp_c
from exp.k13_treegen.flora.content import ContentPack
from exp.k13_treegen.interface import StressVerdict
from exp.k14_worldprod import moisture as _moisture
from exp.k14_worldprod import water as _water
from exp.k14_worldprod.derived import (
    PLUME_WEIGHT,
    _plume_source,
    _upsample,
    growing_season,
    marine_productivity,
)
from exp.k14_worldprod.ground import (
    GROUND_ID,
    eff_props,
    mix_ph,
)
from exp.k15_simdiff.req_flora import (
    REQ_ANCHORING,
    REQ_BLOOM_FROST,
    REQ_CLIMATE,
    REQ_FERTILITY,
    REQ_FRESH_HABITAT,
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
    W_P_DEFAULT,
    W_T_DEFAULT,
    excess_suit,
    invert,
    sat,
    shortfall_suit,
)

K11_OUT = Path(__file__).resolve().parent.parent / "k11_worldgen" / "out"
K14_OUT = Path(__file__).resolve().parent.parent / "k14_worldprod" / "out"
FLORA_TREE_REL = Path("exp") / "k13_treegen" / "out"

# ── climate stratum (B5 §4.1) ─────────────────────────────────────────
# drought_tolerance widens the moisture breadth on the DRY side by this
# many breadth units per unit tolerance (asymmetric: wet-side breadth is
# untouched — a drought-adapted plant is not more wet-tolerant).
DROUGHT_DRY_WIDEN = 0.5
# drought_deciduous drops leaves in the dry season: its dry-side P cost
# is relaxed by this fraction (1.0 = the dry season never costs).
DROUGHT_DECID_RELAX = 0.75
# growing_season_req -> saturating term against the D0 growing-season
# length (months); the reference is how short a season docks fully.
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
# saturated end INVERTS to a requirement — the plan needs
# water_potential above WLOG_WET_LIMIT (invert(excess_suit)).
WLOG_INVERT_T = 0.7
WLOG_WET_LIMIT = 0.55
WLOG_WET_REF = 0.45
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

# ── DerivedView keys the adapter reads (req_flora) ────────────────────
# temp_opt_c, temp_breadth_c, moisture_opt, moisture_breadth  [niche]
# w_T/w_P (per-plan [niche] override, optional)
# drought_tolerance, waterlogging_tolerance, salinity_tolerance,
# ph_tolerance, fertility_requirement, growing_season_req
# root_depth_m, height_m, woodiness
# photosynthesis ("C3"/"C4"/"CAM"/...), winter_deciduous (0/1),
# leafout_month, drought_deciduous (0/1),
# bloom_start_month, bloom_length_months,
# medium ("land"/"water"/"dual"), anchoring_need (0..1), holdfast (0/1)
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
                               # 0..1 scale (niche moisture_opt is a
                               # position on THAT scale, not mm)
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
    photic: np.ndarray          # (H,W) m — ocean photic depth, 0 elsewhere
    sal_water: np.ndarray       # (H,W) h_salinity / SAL_REF_GKG clipped
    water_cell: np.ndarray      # (H,W) bool ocean|sea|lake
    land_cell: np.ndarray       # (H,W) bool
    hand_m: np.ndarray          # (H,W) m height above nearest drainage
    ground_class: np.ndarray    # (H,W) uint8 argmin over ground_d2
    eff_retention: np.ndarray   # (H,W) (kept for completeness/debug)
    wind_ms: np.ndarray         # (H,W) m/s storm proxy: max over months
                                # of the monthly-mean surface wind speed
    bottom_temp: np.ndarray     # (H,W) degC annual bottom temperature
                                # (ocean; 0 on land) — submerged plans
                                # read THIS for the climate T term (B4:
                                # the deep bottom has no seasons)
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
    # the [niche] moisture_opt/moisture_breadth are positions on the
    # normalized 0..1 P scale (c_P_monthly raw; precip_mm is p*400) —
    # the climate term compares like with like.
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
    ctx.sal_water = np.clip(z["h_salinity"].astype(np.float32)
                            / SAL_REF_GKG, 0.0, 1.0)

    # ── wind exposure + bottom temperature at anchor (pure functions
    # ── of the delivered dump — recompute, never downsample).
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
    ctx.bottom_temp = _water.bottom_temp_c(
        z, sea, _water.bathymetry_m(z, sea)).astype(np.float32)

    # ── ground properties: the anchor top-3 mix re-derived by re-running
    # ── the deterministic B3 pass, verified against the persisted
    # ── ground_eff_* rasters (B5 §3 shared precompute).
    g = _ground_anchor_mix(z, manifest, sea)
    mix_ids, mix_w = g["mix_ids"], g["mix_w"]
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
                   np.where(lake | river_any,
                            _water.fresh_ph(bed_ph, land_mean, bog_share),
                            np.where(ctx.fresh_availability.mean(axis=0) > 0,
                                     _water.fresh_ph(bed_ph, land_mean,
                                                     bog_share),
                                     0.0)))
    ctx.water_ph = wph.astype(np.float32)

    # ── water column at anchor: column depth + photic depth ──
    # fresh column depth uses the lake/river h_depth decode of
    # freshwater_productivity (above-sea linear elevation segment).
    from exp.k11_worldgen.units import ELEV_MAX_M
    ctx.depth_fresh = (z["h_depth"].astype(np.float64) / (1.0 - sea)
                       * ELEV_MAX_M).astype(np.float32)
    ctx.column_depth = np.where(
        ocean, ctx.bathy,
        np.where(lake | river_any, ctx.depth_fresh, 0.0)).astype(np.float32)
    dis_ref = max(float(np.percentile(z["h_discharge"], 99.0)), 1e-12)
    plume = _plume_source(z, ocean, dis_ref)
    mprod_prov = marine_productivity(z, _currents_payload(k11_dir))
    ctx.photic = _water.photic_depth_m(
        ctx.bathy, plume, mprod_prov.mean(axis=0),
        PLUME_WEIGHT).astype(np.float32)
    return ctx


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
    """The DerivedView the adapter reads from a record's axes + the
    preset's [niche] metadata: flora derive's effective_climate logic
    (niche METADATA never drifts; tolerance traits come from the axes)
    plus the plan descriptors (medium from the plan registry,
    anchoring_need = clip(height x woodiness / ANCHOR_REF_M), holdfast,
    submerged, phenology flags). Pure function of record + content."""
    meta = pack.presets.get(preset_id or "", {}).get("niche", {})
    node_plan = str(axes.get("_plan") or "")
    plan = pack.registry.plans.get(node_plan)
    medium = plan.medium if plan is not None else "land"
    lp = str(axes.get("leaf_persistence") or "evergreen")
    dt = str(axes.get("deciduous_trigger") or "none")
    height = float(axes.get("height_m") or 0.0)
    wood = float(axes.get("woodiness") or 0.0)
    return {
        "temp_opt_c": meta.get("temp_opt_c"),
        "temp_breadth_c": meta.get("temp_breadth_c"),
        "moisture_opt": meta.get("moisture_opt"),
        "moisture_breadth": meta.get("moisture_breadth"),
        "w_T": meta.get("w_T"),
        "w_P": meta.get("w_P"),
        "drought_tolerance": axes.get("drought_tolerance"),
        "waterlogging_tolerance": axes.get("waterlogging_tolerance"),
        "salinity_tolerance": axes.get("salinity_tolerance"),
        "ph_tolerance": axes.get("ph_tolerance"),
        "fertility_requirement": axes.get("fertility_requirement"),
        "growing_season_req": axes.get("growing_season_req"),
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
        # engine-side dispersal keys (K15 rounds; the stress strata
        # never read them) — mirrors FloraSim.derive.
        "dispersal_channels": axes.get("dispersal_channels"),
        "propagule_mass_mg": axes.get("propagule_mass_mg"),
        "propagule_count": axes.get("propagule_count"),
        "seed_bank": axes.get("seed_bank"),
        # per-capita space demand for the engine's density term
        "crown_spread_m": axes.get("crown_spread_m"),
    }


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


def _climate_suitability(view: dict, ctx: WorldContext) -> np.ndarray:
    """B5 §4.1: weighted saturating (T, P) distance from the [niche]
    baseline, phenology-gated, plus the growing-season and C4/CAM cold
    terms. Returns REQ_CLIMATE (12,H,W)."""
    H, W = ctx.H, ctx.W
    opt_t = _f(view.get("temp_opt_c"))
    b_t = _f(view.get("temp_breadth_c"))
    opt_p = _f(view.get("moisture_opt"))
    b_p = _f(view.get("moisture_breadth"))
    w_t = _f(view.get("w_T")) if view.get("w_T") is not None \
        else W_T_DEFAULT
    w_p = _f(view.get("w_P")) if view.get("w_P") is not None \
        else W_P_DEFAULT
    drought = _f(view.get("drought_tolerance"))
    if np.isnan(drought):
        drought = 0.0
    winter_dec = int(view.get("winter_deciduous") or 0)
    leafout = view.get("leafout_month")
    drought_dec = int(view.get("drought_deciduous") or 0)
    photo = str(view.get("photosynthesis") or "C3")

    cost = np.zeros((12, H, W), dtype=np.float32)
    if not np.isnan(opt_t) and b_t > 0:
        # submerged (benthic water) plans read the ANNUAL bottom
        # temperature, not the surface monthly field — B4: the deep
        # bottom has no seasons, shelf bottoms are damped.
        t_field = ctx.bottom_temp[None] if int(view.get("submerged")
                                               or 0) else ctx.t_c
        c = sat(np.abs(t_field - np.float32(opt_t)) / np.float32(b_t))
        if winter_dec and isinstance(leafout, (int, float)):
            leaf_on = (_MONTH1 >= int(leafout))[:, None, None]
            c = np.where(leaf_on, c, 0.0)      # dormant months: no cold
        cost += np.float32(w_t) * c
    # the moisture (P) half is meaningless for a plan that lives IN
    # water — its moisture niche is the water itself, carried by the
    # habitat/medium terms (an aquatic plant is not niche-limited by
    # precipitation over the ocean). Land and dual plans pay it.
    if view.get("medium") != "water" and not np.isnan(opt_p) and b_p > 0:
        b_dry = np.float32(max(b_p + DROUGHT_DRY_WIDEN * drought, 1e-6))
        b_wet = np.float32(max(b_p, 1e-6))
        dP = np.abs(ctx.p_norm - np.float32(opt_p))
        dry_side = ctx.p_norm < np.float32(opt_p)
        c = np.where(dry_side, sat(dP / b_dry), sat(dP / b_wet))
        if drought_dec:
            c = np.where(dry_side, c * np.float32(1.0 - DROUGHT_DECID_RELAX),
                         c)
        cost += np.float32(w_p) * c
    f = sat(1.0 - cost)

    # growing season (annual, saturating shortfall)
    gs_req = _f(view.get("growing_season_req"))
    if not np.isnan(gs_req):
        f_gs = shortfall_suit(ctx.growing_season, np.float32(gs_req),
                              np.float32(GS_REF_MONTHS))
        f = f * f_gs[None]

    # C4/CAM cold penalty (C3/none/chemosymbiosis carry none)
    if photo in ("C4", "CAM"):
        cold = sat((np.float32(COLD_PEN_T_C) - ctx.t_c)
                   / np.float32(COLD_PEN_SPAN_C))
        f = f * (1.0 - np.float32(COLD_PEN_W) * cold)
    return f.astype(np.float32)


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


def _ground_terms(view: dict, ctx: WorldContext) -> dict[str, np.ndarray]:
    """B5 §4.2 for LAND (and dual) plans: water availability, water-
    logging (with the inversion), fertility, pH, salinity — REQ_WATER
    and REQ_WATERLOGGING monthly, the rest annual broadcast."""
    H, W = ctx.H, ctx.W
    opt_p = _f(view.get("moisture_opt"))
    drought = _f(view.get("drought_tolerance"))
    need = np.float32(np.clip(
        (0.0 if np.isnan(opt_p) else opt_p)
        * (1.0 if np.isnan(drought) else 1.0 - min(drought, 1.0)),
        0.0, 1.0))
    f_water = shortfall_suit(ctx.water_potential, need,
                             np.float32(WATER_REF))

    wlog = _f(view.get("waterlogging_tolerance"))
    if np.isnan(wlog):
        f_wlog = np.ones((12, H, W), dtype=np.float32)
    elif wlog >= WLOG_INVERT_T:
        f_wlog = invert(excess_suit(ctx.water_potential,
                                    np.float32(WLOG_WET_LIMIT),
                                    np.float32(WLOG_WET_REF)))
    else:
        f_wlog = excess_suit(ctx.water_potential,
                             np.float32(WLOG_DRY_LIMIT),
                             np.float32(WLOG_DRY_REF))

    fert = _f(view.get("fertility_requirement"))
    fert_req = np.float32(0.0 if np.isnan(fert) else min(max(fert, 0.0),
                                                         1.0))
    f_fert = shortfall_suit(ctx.eff_nutrient, fert_req,
                            np.float32(FERT_REF))

    ph_tol = _f(view.get("ph_tolerance"))
    if np.isnan(ph_tol):
        f_ph_lo = f_ph_hi = np.ones((H, W), dtype=np.float32)
    else:
        opt_ph = PH_LO + PH_SPAN * min(max(ph_tol, 0.0), 1.0)
        f_ph_lo, f_ph_hi = _ph_suit_split(ctx.ground_ph, opt_ph)
        if view.get("medium") == "dual":
            w_lo, w_hi = _ph_suit_split(ctx.water_ph, opt_ph)
            f_ph_lo = np.minimum(f_ph_lo, w_lo)
            f_ph_hi = np.minimum(f_ph_hi, w_hi)

    sal_tol = _f(view.get("salinity_tolerance"))
    if np.isnan(sal_tol):
        f_sal = np.ones((H, W), dtype=np.float32)
    else:
        if view.get("medium") == "dual":
            sal_env = np.maximum(ctx.eff_sal_add, ctx.sal_water)
        else:
            sal_env = ctx.eff_sal_add
        f_sal = excess_suit(sal_env, np.float32(min(max(sal_tol, 0.0), 1.0)),
                            np.float32(SAL_REF))

    out = {
        REQ_WATER: f_water.astype(np.float32),
        REQ_WATERLOGGING: f_wlog.astype(np.float32),
        REQ_FERTILITY: np.broadcast_to(f_fert.astype(np.float32),
                                       (12, H, W)).copy(),
        REQ_PH_LOW: np.broadcast_to(f_ph_lo, (12, H, W)).copy(),
        REQ_PH_HIGH: np.broadcast_to(f_ph_hi, (12, H, W)).copy(),
        REQ_SALINITY: np.broadcast_to(f_sal.astype(np.float32),
                                      (12, H, W)).copy(),
    }
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
        f_sal = excess_suit(ctx.sal_water,
                            np.float32(min(max(sal_tol, 0.0), 1.0)),
                            np.float32(SAL_REF))
    return {
        REQ_PH_LOW: np.broadcast_to(f_ph_lo, (12, H, W)).copy(),
        REQ_PH_HIGH: np.broadcast_to(f_ph_hi, (12, H, W)).copy(),
        REQ_SALINITY: np.broadcast_to(f_sal.astype(np.float32),
                                      (12, H, W)).copy(),
    }


def _tail_terms(view: dict, ctx: WorldContext,
                freshwater: bool) -> dict[str, np.ndarray]:
    """B5 §4.3 tail terms: rooting, anchoring, the medium boundary
    (replaced by the habitat term for freshwater plans), and submerged
    light. Annual (H,W), broadcast to months."""
    H, W = ctx.H, ctx.W
    out: dict[str, np.ndarray] = {}

    root = _f(view.get("root_depth_m"))
    if np.isnan(root) or view.get("medium") == "water":
        f_root = np.ones((H, W), dtype=np.float32)
    else:
        f_root = excess_suit(np.float32(root), ctx.eff_rooting_m,
                             np.float32(ROOT_REF_M))
    out[REQ_ROOTING] = np.broadcast_to(f_root, (12, H, W)).copy()

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


# ── evaluation ────────────────────────────────────────────────────────


def evaluate(view: dict, ctx: WorldContext) -> dict[str, np.ndarray]:
    """Per-requirement suitability arrays (12,H,W) float32 keyed by the
    req_flora names, plus "F" (the product) and "s_env" (1 - 2F).
    Terms that do not apply to a plan (missing/None view keys) are
    omitted entirely — an absent factor is 1 (B5: the empty product is
    1, maximal vigor). Pure and deterministic: no draws, no state."""
    medium = view.get("medium", "land")
    salinity = _f(view.get("salinity_tolerance"))
    freshwater = (medium == "water" and not np.isnan(salinity)
                  and salinity < FRESH_SAL_MAX)

    factors: dict[str, np.ndarray] = {}
    f = _climate_suitability(view, ctx)
    factors[REQ_CLIMATE] = f
    factors[REQ_BLOOM_FROST] = _bloom_frost(view, ctx)
    if medium != "water":
        factors.update(_ground_terms(view, ctx))
    else:
        factors.update(_water_chemistry(view, ctx))
    factors.update(_tail_terms(view, ctx, freshwater))

    F = np.ones((12, ctx.H, ctx.W), dtype=np.float32)
    for a in factors.values():
        F *= a
    s_env = 1.0 - 2.0 * F
    out = dict(factors)
    out["F"] = F
    out["s_env"] = s_env.astype(np.float32)
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
        if name in ("F", "s_env"):
            continue
        provenance[name] = float(arr[month, y, x])
    r = compose(provenance)
    return StressVerdict(s=float(r.s), provenance=r.factors)


# ── world utilities for acceptance / downstream consumers ─────────────


def annual_stress(factors: dict[str, np.ndarray]) -> np.ndarray:
    """Annual-mean signed stress (12 -> (H,W)) — what the rounds
    integrate over (B5 §1 rounds contract)."""
    return factors["s_env"].mean(axis=0)
