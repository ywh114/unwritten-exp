"""K15 — B5 flora stress adapter unit tests (per-stratum).

Small SYNTHETIC WorldContext arrays — no real world, no disk. Each
stratum is tested against the kernel.stress primitives' documented
shapes (dist_suit / shortfall_suit / excess_suit / invert / compose).

Run: PYTHONPATH=. uv run pytest -q exp/k15_simdiff
"""

from __future__ import annotations

import numpy as np
import pytest

from exp.k13_treegen.interface import StressVerdict
from exp.k14_worldprod.ground import GROUND_ID, PROP_TABLES
from exp.k15_simdiff.req_flora import (
    REQ_ANCHORING,
    REQ_BLOOM_FROST,
    REQ_COLD,
    REQ_FERTILITY,
    REQ_FRESH_HABITAT,
    REQ_HEAT,
    REQ_MEDIUM,
    REQ_PH_HIGH,
    REQ_PH_LOW,
    REQ_ROOTING,
    REQ_SALINITY,
    REQ_SUBMERGED_LIGHT,
    REQ_WATER,
    REQ_WATERLOGGING,
)
from exp.k15_simdiff.stress_adapter import (
    FRESH_SAL_MAX,
    MEDIUM_VIOLATION_F,
    WIND_REF_MS,
    WLOG_DRY_LIMIT,
    WLOG_INVERT_T,
    WorldContext,
    evaluate,
    verdict_at,
)
from kernel.stress import (
    compose,
    dist_suit,
    excess_suit,
    invert,
    sat,
    shortfall_suit,
)

H = W = 4
N = 12

# default uniform ground mix for the synthetic world (nutrient 0.65,
# rooting 3.0 m, pH 6.0, sal 0, non-hard)
DEFAULT_MIX_CLASS = "brown earth"


def mix_arrays(*weighted_classes) -> tuple[np.ndarray, np.ndarray]:
    """(mix_ids, mix_w) at (3,H,W) from ("class name", weight) pairs —
    the best-of-class semantics read these; weights renormalize over
    the used slots, remaining slots repeat the first id at weight 0."""
    ids = np.zeros((3, H, W), dtype=np.uint8)
    w = np.zeros((3, H, W), dtype=np.float32)
    first = GROUND_ID[weighted_classes[0][0]]
    ids[:] = first
    total = sum(float(wt) for _, wt in weighted_classes)
    for slot, (name, wt) in enumerate(weighted_classes[:3]):
        ids[slot] = GROUND_ID[name]
        w[slot] = float(wt) / total
    return ids, w


def make_ctx(**overrides) -> WorldContext:
    """A tiny synthetic world: everything constant unless overridden.
    The ground mix defaults to a uniform DEFAULT_MIX_CLASS patch; pass
    mix=mix_arrays(("class", w), ...) to override (eff_hard stays an
    independent override for the anchoring SHARE tests)."""
    mix = overrides.pop("mix", None)
    ctx = WorldContext()
    ctx.seed = 1
    ctx.H, ctx.W = H, W
    ctx.sea_level = 0.35
    ones = np.ones((H, W), dtype=np.float32)
    ctx.t_c = np.full((N, H, W), 15.0, dtype=np.float32)
    ctx.p_norm = np.full((N, H, W), 0.5, dtype=np.float32)
    ctx.water_potential = np.full((N, H, W), 0.9, dtype=np.float32)
    ctx.fresh_availability = np.full((N, H, W), 0.0, dtype=np.float32)
    ctx.growing_season = np.full((H, W), 12.0, dtype=np.float32)
    ctx.eff_nutrient = ones * 0.8
    ctx.eff_rooting_m = ones * 2.0
    ctx.eff_sal_add = np.zeros((H, W), dtype=np.float32)
    ctx.eff_hard = ones * 0.9
    ctx.eff_loose = np.zeros((H, W), dtype=np.float32)
    ctx.ground_ph = np.full((H, W), 7.0, dtype=np.float32)
    ctx.water_ph = np.full((H, W), 7.0, dtype=np.float32)
    ctx.bathy = np.zeros((H, W), dtype=np.float32)
    ctx.depth_fresh = np.zeros((H, W), dtype=np.float32)
    ctx.column_depth = np.zeros((H, W), dtype=np.float32)
    ctx.photic = np.zeros((H, W), dtype=np.float32)
    ctx.sal_water = np.zeros((H, W), dtype=np.float32)
    ctx.water_cell = np.zeros((H, W), dtype=bool)
    ctx.land_cell = np.ones((H, W), dtype=bool)
    ctx.hand_m = ones
    ctx.ground_class = np.zeros((H, W), dtype=np.uint8)
    ctx.wind_ms = np.full((H, W), WIND_REF_MS, dtype=np.float32)  # neutral
    ctx.bottom_temp = np.zeros((H, W), dtype=np.float32)
    ctx.mix_ids, ctx.mix_w = mix if mix is not None else \
        mix_arrays((DEFAULT_MIX_CLASS, 1.0))
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


def base_view(**kw) -> dict:
    """A mesic, C3, evergreen land plan; individual keys overridable."""
    view = {
        "temp_opt_c": 15.0, "temp_breadth_c": 10.0,
        "moisture_opt": 0.5, "moisture_breadth": 0.3,
        "drought_tolerance": 0.2, "waterlogging_tolerance": 0.1,
        "salinity_tolerance": 0.1, "ph_tolerance": 0.5,
        "fertility_requirement": 0.4, "growing_season_req": 3.0,
        "root_depth_m": 1.0, "height_m": 10.0, "woodiness": 1.0,
        "photosynthesis": "C3",
        "winter_deciduous": 0, "leafout_month": 3,
        "drought_deciduous": 0,
        "bloom_start_month": 4, "bloom_length_months": 2.0,
        "medium": "land",
        "anchoring_need": 0.4, "holdfast": 0, "submerged": 0,
    }
    view.update(kw)
    return view


# ── climate stratum (B5 §4.1) ─────────────────────────────────────────


def test_climate_split_matches_kernel_distance():
    """The T requirement is SPLIT one-sided like pH (req_flora ruling
    2026-08-01): cold = shortfall of T below the optimum, heat = excess
    past it — cold x heat is exactly the symmetric dist_suit at unit
    weight, so the composed F is unchanged by the split. The moisture
    (P) half is gone from climate (the derived envelope feeds
    pressure:water/waterlogging instead)."""
    ctx = make_ctx()
    view = base_view()
    r = evaluate(view, ctx)
    cold, heat = r[REQ_COLD][0], r[REQ_HEAT][0]
    expect = dist_suit(ctx.t_c[0], 15.0, 10.0)
    assert np.allclose(cold * heat, expect)
    # at the optimum everything is 1
    assert np.allclose(cold, 1.0) and np.allclose(heat, 1.0)
    # cold side: T below opt docks cold, heat stays 1
    ctxc = make_ctx(t_c=np.full((N, H, W), 5.0, dtype=np.float32))
    rc = evaluate(base_view(), ctxc)
    assert np.allclose(rc[REQ_COLD][0], 0.0)        # |5-15|/10 saturated
    assert np.allclose(rc[REQ_HEAT][0], 1.0)
    # heat side: T above opt docks heat, cold stays 1
    ctxh = make_ctx(t_c=np.full((N, H, W), 25.0, dtype=np.float32))
    rh = evaluate(base_view(), ctxh)
    assert np.allclose(rh[REQ_COLD][0], 1.0)
    assert np.allclose(rh[REQ_HEAT][0], 0.0)
    # both sides saturated -> product clipped to 0
    ctx3 = make_ctx(t_c=np.full((N, H, W), 55.0, dtype=np.float32))
    r3 = evaluate(base_view(), ctx3)
    assert np.allclose(r3[REQ_COLD], 1.0)
    assert np.allclose(r3[REQ_HEAT], 0.0)
    assert np.allclose(r3[REQ_COLD] * r3[REQ_HEAT], 0.0)


def test_climate_t_factors_ignore_drought_tolerance():
    """The moisture (P) half is REMOVED from climate (owner ruling
    2026-08-01): drought_tolerance no longer widens a P-breadth inside
    the climate term — it acts through the derived moisture envelope
    into pressure:water (test_water_dry_end_shortfall) — so the T
    factors are identical for a dry-adapted and a wet-adapted plan."""
    ctx = make_ctx()
    a = evaluate(base_view(drought_tolerance=0.1), ctx)
    b = evaluate(base_view(drought_tolerance=0.9), ctx)
    assert np.allclose(a[REQ_COLD], b[REQ_COLD])
    assert np.allclose(a[REQ_HEAT], b[REQ_HEAT])
    # the derived moisture envelope does feed pressure:water: a drier
    # optimum raises the need on the same water field -> lower f_water
    ctxdry = make_ctx(water_potential=np.full((N, H, W), 0.3,
                                              dtype=np.float32))
    wet_opt = evaluate(base_view(moisture_opt=0.5), ctxdry)[REQ_WATER]
    dry_opt = evaluate(base_view(moisture_opt=0.2), ctxdry)[REQ_WATER]
    assert (wet_opt < dry_opt).all()


def test_phenology_gates_cold_months():
    """winter_deciduous: the COLD cost is dropped in dormant months
    (m < leafout_month); an evergreen pays it year-round — but only in
    the GROWING season: months below GROW_T_C are dormant for every
    surface plan (owner ruling 2026-08-01). The HEAT side is ungated."""
    # 7 C: inside the growing band — evergreen pays, deciduous gated
    ctx = make_ctx(t_c=np.full((N, H, W), 7.0, dtype=np.float32),
                   p_norm=np.full((N, H, W), 0.5, dtype=np.float32))
    dec = evaluate(base_view(winter_deciduous=1, leafout_month=4),
                   ctx)[REQ_COLD]
    evg = evaluate(base_view(winter_deciduous=0), ctx)[REQ_COLD]
    assert np.allclose(dec[:3], 1.0)            # pre-leafout: no cost
    assert np.allclose(dec[3:], evg[3:])        # leaf-on: same as evergreen
    assert np.allclose(evg, 0.2)                # |7-15|/10 -> sat 0.8 cost
    # -10 C: dormant for everyone, deciduous or not
    cold = make_ctx(t_c=np.full((N, H, W), -10.0, dtype=np.float32),
                    p_norm=np.full((N, H, W), 0.5, dtype=np.float32))
    assert np.allclose(evaluate(base_view(winter_deciduous=0),
                                cold)[REQ_COLD], 1.0)
    assert np.allclose(evaluate(base_view(winter_deciduous=1),
                                cold)[REQ_COLD], 1.0)
    # heat is ungated: a warm month costs the same for deciduous plans
    ctxw = make_ctx(t_c=np.full((N, H, W), 25.0, dtype=np.float32))
    assert np.allclose(
        evaluate(base_view(winter_deciduous=1, leafout_month=4),
                 ctxw)[REQ_HEAT], 0.0)          # |25-15|/10 saturated


def test_c4_cam_cold_penalty():
    """C4/CAM carry a cold penalty term (C3 none) in the COOL GROWING
    band, folded into the COLD side; below GROW_T_C every plan is
    dormant and the penalty lifts. The HEAT side carries no penalty."""
    ctx = make_ctx(t_c=np.full((N, H, W), 7.0, dtype=np.float32),
                   p_norm=np.full((N, H, W), 0.5, dtype=np.float32))
    c3 = evaluate(base_view(photosynthesis="C3"), ctx)[REQ_COLD][0]
    c4 = evaluate(base_view(photosynthesis="C4"), ctx)[REQ_COLD][0]
    cam = evaluate(base_view(photosynthesis="CAM"), ctx)[REQ_COLD][0]
    assert (c4 < c3).all() and (cam < c3).all()
    # at 7 C: plain distance |7-15|/10 -> 0.2; the cold penalty
    # sat((10-7)/5)=0.6 docks 40% x 0.6 of that -> x 0.76
    assert np.allclose(c3, 0.2)
    assert np.allclose(c4, 0.2 * 0.76) and np.allclose(cam, 0.2 * 0.76)
    # dormant months (below GROW_T_C): no distance cost, no penalty
    cold = make_ctx(t_c=np.full((N, H, W), 0.0, dtype=np.float32),
                    p_norm=np.full((N, H, W), 0.5, dtype=np.float32))
    assert np.allclose(evaluate(base_view(photosynthesis="C4"),
                                cold)[REQ_COLD], 1.0)
    # the penalty never touches the heat side
    warm = make_ctx(t_c=np.full((N, H, W), 25.0, dtype=np.float32))
    c4w = evaluate(base_view(photosynthesis="C4"), warm)[REQ_HEAT]
    assert np.allclose(c4w, 0.0)                # pure T-distance sat


def test_bloom_frost_only_in_bloom_window():
    """REQ_BLOOM_FROST is 1 outside the bloom window and drops inside
    it when the month freezes."""
    ctx = make_ctx(t_c=np.full((N, H, W), -5.0, dtype=np.float32))
    r = evaluate(base_view(bloom_start_month=4, bloom_length_months=2.0),
                 ctx)
    f = r[REQ_BLOOM_FROST]
    assert np.allclose(f[3], f[3][0])           # April (m=3): frost cost
    assert (f[3] < 1.0).all()
    assert np.allclose(f[0], 1.0)               # January: no bloom
    assert np.allclose(f[5], 1.0)               # June: no bloom
    # warm bloom month: no cost even in the window
    ctxw = make_ctx(t_c=np.full((N, H, W), 10.0, dtype=np.float32))
    assert np.allclose(evaluate(base_view(), ctxw)[REQ_BLOOM_FROST], 1.0)


# ── ground stratum (B5 §4.2) ──────────────────────────────────────────


def test_water_dry_end_shortfall():
    """REQ_WATER = shortfall of water_potential below the moisture need
    (moisture_opt x (1 - drought_tolerance))."""
    ctx = make_ctx(water_potential=np.full((N, H, W), 1.0,
                                           dtype=np.float32))
    wet = evaluate(base_view(), ctx)[REQ_WATER][0]
    assert np.allclose(wet, 1.0)                # saturated: need met
    ctxdry = make_ctx(water_potential=np.zeros((N, H, W),
                                               dtype=np.float32))
    dry = evaluate(base_view(moisture_opt=0.5, drought_tolerance=0.0),
                   ctxdry)[REQ_WATER][0]
    assert np.allclose(dry, 0.0)                # bone dry, no tolerance
    # drought tolerance lowers the need: same dry cell, higher f
    tol = evaluate(base_view(moisture_opt=0.5, drought_tolerance=1.0),
                   ctxdry)[REQ_WATER][0]
    assert (tol > dry).all()


def test_waterlogging_inversion():
    """High waterlogging_tolerance INVERTS the term — and reads
    fresh_availability (the unwritten-wetland field, owner ruling
    2026-08-01): the marsh is the habitat, dry ground the cost. Dry
    plans keep the excess shape against water_potential."""
    ctx_marsh = make_ctx(fresh_availability=np.full((N, H, W), 1.0,
                                                    dtype=np.float32))
    ctx_dry = make_ctx()                        # fresh_availability = 0
    wet_plan = base_view(waterlogging_tolerance=1.0)
    f_wet = evaluate(wet_plan, ctx_marsh)[REQ_WATERLOGGING][0]
    assert np.allclose(f_wet, 1.0)
    bad_wet = evaluate(wet_plan, ctx_dry)[REQ_WATERLOGGING][0]
    assert np.allclose(bad_wet, 0.0)
    # the water-availability term reads the marsh too
    assert np.allclose(
        evaluate(wet_plan, ctx_marsh)[REQ_WATER][0], 1.0)
    # dry plan: water_potential drives the excess cost as before
    wp_wet = make_ctx(water_potential=np.full((N, H, W), 1.0,
                                              dtype=np.float32))
    wp_dry = make_ctx(water_potential=np.zeros((N, H, W),
                                               dtype=np.float32))
    dry_plan = base_view(waterlogging_tolerance=0.0)
    assert np.allclose(evaluate(dry_plan, wp_dry)[REQ_WATERLOGGING][0],
                       1.0)
    assert np.allclose(evaluate(dry_plan, wp_wet)[REQ_WATERLOGGING][0],
                       0.0)


def test_fertility_shortfall():
    """REQ_FERTILITY = shortfall of the BEST mix class's nutrient below
    the requirement (best-of-class; low requirement on rich soil is not
    penalized)."""
    ctx = make_ctx(mix=mix_arrays(("mollisol", 1.0)))      # nutrient .95
    rich = evaluate(base_view(fertility_requirement=0.3), ctx)
    assert np.allclose(rich[REQ_FERTILITY], 1.0)
    ctxpoor = make_ctx(mix=mix_arrays(("scree", 1.0)))     # nutrient .05
    poor = evaluate(base_view(fertility_requirement=0.5), ctxpoor)
    assert np.allclose(poor[REQ_FERTILITY],
                       1.0 - sat((0.5 - 0.05) / 0.5))
    # a 50/50 scree+mollisol cell: the plan reads the mollisol patch
    ctxmix = make_ctx(mix=mix_arrays(("scree", 1.0), ("mollisol", 1.0)))
    best = evaluate(base_view(fertility_requirement=0.3), ctxmix)
    assert np.allclose(best[REQ_FERTILITY], 1.0)


def test_ph_position_split():
    """ph_tolerance is a POSITION: opt = 4 + 5 x value, breadth ±1,
    read against the BEST mix class (bog pH 4.0, solonetz pH 9.0).
    The factor is emitted SPLIT one-sided (req_flora ruling): ph_low
    drops only when the cell is too acidic for the position, ph_high
    only when too alkaline; their product is the symmetric distance."""
    ctx = make_ctx(mix=mix_arrays(("bog", 1.0)))           # pH 4.0
    cf = evaluate(base_view(ph_tolerance=0.0), ctx)
    cc = evaluate(base_view(ph_tolerance=1.0), ctx)
    assert np.allclose(cf[REQ_PH_LOW][0], 1.0)
    assert np.allclose(cf[REQ_PH_HIGH][0], 1.0)
    assert np.allclose(cc[REQ_PH_LOW][0], 0.0)    # opt 9.0 vs 4.0: too acid
    assert np.allclose(cc[REQ_PH_HIGH][0], 1.0)   # not too alkaline
    ctxalk = make_ctx(mix=mix_arrays(("solonetz", 1.0)))   # pH 9.0
    cc2 = evaluate(base_view(ph_tolerance=1.0), ctxalk)
    assert np.allclose(cc2[REQ_PH_LOW][0], 1.0)
    assert np.allclose(cc2[REQ_PH_HIGH][0], 1.0)
    cf2 = evaluate(base_view(ph_tolerance=0.0), ctxalk)
    assert np.allclose(cf2[REQ_PH_LOW][0], 1.0)
    assert np.allclose(cf2[REQ_PH_HIGH][0], 0.0)  # too alkaline
    # a mixed bog+solonetz cell serves BOTH the acidophile and the
    # basiphile (each finds its patch) — the mean would serve neither
    ctxmix = make_ctx(mix=mix_arrays(("bog", 1.0), ("solonetz", 1.0)))
    assert np.allclose(
        evaluate(base_view(ph_tolerance=0.0), ctxmix)[REQ_PH_LOW][0], 1.0)
    assert np.allclose(
        evaluate(base_view(ph_tolerance=1.0), ctxmix)[REQ_PH_LOW][0], 1.0)
    # water plans read water_ph instead
    ctxw = make_ctx(water_ph=np.full((H, W), 9.0, dtype=np.float32))
    r = evaluate(base_view(medium="water", ph_tolerance=1.0,
                           salinity_tolerance=0.9), ctxw)
    assert np.allclose(r[REQ_PH_LOW][0], 1.0)
    assert np.allclose(r[REQ_PH_HIGH][0], 1.0)


def test_salinity_ionic_excess():
    """REQ_SALINITY = one-sided excess over the best mix class's
    sal_add (solonchak sal_add 1.0); water plans read the normalized
    h_salinity."""
    ctx = make_ctx(mix=mix_arrays(("solonchak", 1.0)))
    low = evaluate(base_view(salinity_tolerance=0.1), ctx)[REQ_SALINITY][0]
    high = evaluate(base_view(salinity_tolerance=0.95), ctx)[REQ_SALINITY][0]
    assert (high > low).all()
    assert np.allclose(low, 1.0 - sat((1.0 - 0.1) / 1.0))
    # a fresh patch rescues the intolerant plan (best-of-class)
    ctxmix = make_ctx(mix=mix_arrays(("solonchak", 1.0), ("bog", 1.0)))
    rescued = evaluate(base_view(salinity_tolerance=0.1),
                       ctxmix)[REQ_SALINITY][0]
    assert np.allclose(rescued, 1.0)


# ── tail terms (B5 §4.3) ──────────────────────────────────────────────


def test_medium_boundary_near_one():
    """A land plan on a water cell and a water plan on a land cell cost
    ≈ 1 always (f = MEDIUM_VIOLATION_F); dual-domain plans are exempt."""
    wmask = np.zeros((H, W), dtype=bool)
    wmask[0, 0] = True
    ctx = make_ctx(water_cell=wmask, land_cell=~wmask)
    land = evaluate(base_view(), ctx)[REQ_MEDIUM]
    assert land[0, 0, 0] == pytest.approx(MEDIUM_VIOLATION_F)
    assert np.allclose(land[:, 0, 1:], 1.0)     # land cells fine
    water = evaluate(base_view(medium="water", salinity_tolerance=0.9),
                     ctx)[REQ_MEDIUM]
    assert water[0, 0, 1] == pytest.approx(MEDIUM_VIOLATION_F)
    assert np.allclose(water[:, 0, 0], 1.0)     # water cell fine
    dual = evaluate(base_view(medium="dual"), ctx)
    assert np.allclose(dual[REQ_MEDIUM], 1.0)


def test_submerged_light():
    """A submerged plan reads photic depth vs column depth: below the
    photic zone costs ~1; above is fine. Non-submerged plans carry no
    light term."""
    ctx = make_ctx(photic=np.full((H, W), 50.0, dtype=np.float32),
                   column_depth=np.full((H, W), 200.0, dtype=np.float32))
    sub = evaluate(base_view(medium="water", submerged=1,
                             salinity_tolerance=0.9), ctx)
    assert REQ_SUBMERGED_LIGHT in sub
    assert np.allclose(sub[REQ_SUBMERGED_LIGHT][0], 0.0)   # too deep
    shallow = make_ctx(photic=np.full((H, W), 50.0, dtype=np.float32),
                       column_depth=np.full((H, W), 10.0, dtype=np.float32))
    assert np.allclose(evaluate(base_view(medium="water", submerged=1,
                                          salinity_tolerance=0.9),
                                shallow)[REQ_SUBMERGED_LIGHT][0], 1.0)
    surface = evaluate(base_view(medium="water", submerged=0,
                                 salinity_tolerance=0.9), ctx)
    assert REQ_SUBMERGED_LIGHT not in surface


def test_rooting_excess_and_anchoring():
    """rooting = saturating excess of root_depth over the BEST mix
    class's rooting_m (fen 1.0 m); anchoring = hard substrate SHARE for
    holdfasts, (1 - eff_hard) for woody land plants; absent for
    non-woody non-holdfast plans."""
    ctx = make_ctx(mix=mix_arrays(("fen", 1.0)))           # rooting 1.0 m
    deep = evaluate(base_view(root_depth_m=2.0), ctx)[REQ_ROOTING][0]
    shallow = evaluate(base_view(root_depth_m=0.2), ctx)[REQ_ROOTING][0]
    assert (shallow > deep).all()
    assert np.allclose(deep, 1.0 - sat((2.0 - 1.0) / 1.0))
    # best-of-class: a fen patch in a bedrock cell roots fine
    ctxmix = make_ctx(mix=mix_arrays(("bedrock outcrop", 1.0),
                                     ("fen", 1.0)))
    patched = evaluate(base_view(root_depth_m=0.2), ctxmix)[REQ_ROOTING][0]
    assert np.allclose(patched, 1.0)
    hf = make_ctx(eff_hard=np.zeros((H, W), dtype=np.float32))
    hold = evaluate(base_view(medium="water", holdfast=1, woodiness=0.0,
                              root_depth_m=None, salinity_tolerance=0.9,
                              submerged=1), hf)
    # soft mud: shortfall of eff_hard below HOLDFAST_NEED (0.6) — costly,
    # not a cutoff (f = 1 - sat(0.6/1) = 0.4).
    assert np.allclose(hold[REQ_ANCHORING][0], 0.4)
    hard = make_ctx(eff_hard=np.full((H, W), 1.0, dtype=np.float32))
    hold2 = evaluate(base_view(medium="water", holdfast=1, woodiness=0.0,
                               root_depth_m=None, salinity_tolerance=0.9,
                               submerged=1), hard)
    assert np.allclose(hold2[REQ_ANCHORING][0], 1.0)
    no_anchor = evaluate(base_view(woodiness=0.0, root_depth_m=None),
                         ctx)
    assert REQ_ANCHORING not in no_anchor


def test_anchoring_wind_modulation():
    """Wind exposure scales the land-tree anchoring need (storm proxy =
    max monthly-mean speed): the same tree is undocked at the calm
    floor, docked at the neutral reference, and heavily docked at the
    storm cap. need 0.6 x mod vs strength 1 - eff_hard = 0.5."""
    hard = np.full((H, W), 0.5, dtype=np.float32)
    kw = dict(anchoring_need=0.6, woodiness=1.0)
    calm = evaluate(base_view(**kw), make_ctx(
        eff_hard=hard, wind_ms=np.zeros((H, W), dtype=np.float32)))
    assert np.allclose(calm[REQ_ANCHORING][0], 1.0)      # need 0.3 < 0.5
    neut = evaluate(base_view(**kw), make_ctx(eff_hard=hard))
    assert np.allclose(neut[REQ_ANCHORING][0], 0.9)      # need 0.6 vs 0.5
    storm = evaluate(base_view(**kw), make_ctx(
        eff_hard=hard,
        wind_ms=np.full((H, W), 3.0 * WIND_REF_MS, dtype=np.float32)))
    assert np.allclose(storm[REQ_ANCHORING][0], 0.3)     # need 1.2 vs 0.5


def test_climate_submerged_reads_bottom_temp():
    """A submerged benthic plan reads the ANNUAL bottom temperature for
    the climate T term, not the surface monthly field — and carries NO
    dormancy gate (the deep sea has no winter): a -20 C bottom costs
    the full cold distance. A surface plan at -20 C is simply dormant."""
    ctx = make_ctx(t_c=np.full((N, H, W), -20.0, dtype=np.float32),
                   bottom_temp=np.full((H, W), -20.0, dtype=np.float32))
    surf = evaluate(base_view(medium="water", submerged=0,
                              salinity_tolerance=0.9), ctx)
    assert np.allclose(surf[REQ_COLD], 1.0)     # dormant: no T-distance
    assert np.allclose(surf[REQ_HEAT], 1.0)
    sub = evaluate(base_view(medium="water", submerged=1,
                             salinity_tolerance=0.9), ctx)
    assert np.allclose(sub[REQ_COLD], 0.0)      # |−20−15|/10 saturated
    assert np.allclose(sub[REQ_HEAT], 1.0)
    assert np.allclose(sub[REQ_COLD] * sub[REQ_HEAT], 0.0)
    warm = make_ctx(bottom_temp=np.full((H, W), 15.0, dtype=np.float32))
    sub_warm = evaluate(base_view(medium="water", submerged=1,
                                  salinity_tolerance=0.9), warm)
    assert np.allclose(sub_warm[REQ_COLD], 1.0)  # bottom 15 == opt 15
    assert np.allclose(sub_warm[REQ_HEAT], 1.0)


# ── freshwater habitat stratum (B5 §4.5) ──────────────────────────────


def test_fresh_habitat_replaces_medium_for_freshwater_plans():
    """A water plan below FRESH_SAL_MAX is a freshwater plan: the
    habitat term (fresh_availability) replaces the medium boundary; a
    marine obligate keeps the strict medium boundary."""
    fa = np.full((N, H, W), 0.5, dtype=np.float32)
    ctx = make_ctx(fresh_availability=fa, land_cell=np.ones((H, W), bool),
                   water_cell=np.zeros((H, W), bool))
    fresh = evaluate(base_view(medium="water", salinity_tolerance=0.1),
                     ctx)
    assert REQ_FRESH_HABITAT in fresh
    assert REQ_MEDIUM not in fresh
    assert np.allclose(fresh[REQ_FRESH_HABITAT], 0.5)   # graded land
    marine = evaluate(base_view(medium="water",
                                salinity_tolerance=FRESH_SAL_MAX + 0.2),
                      ctx)
    assert REQ_MEDIUM in marine
    assert REQ_FRESH_HABITAT not in marine
    assert np.allclose(marine[REQ_MEDIUM], MEDIUM_VIOLATION_F)  # dry land


# ── composition and the verdict materializer ──────────────────────────


def test_F_product_and_signed_s():
    """F is the product of every factor and s = 1 - 2F (Liebig
    tail-dominance and the signed scale), wired through the kernel.
    substrate_share rides along as capacity metadata — never in F."""
    ctx = make_ctx(t_c=np.full((N, H, W), 15.0, dtype=np.float32),
                   p_norm=np.full((N, H, W), 0.5, dtype=np.float32))
    r = evaluate(base_view(), ctx)
    F = np.ones((N, H, W), dtype=np.float32)
    for k, a in r.items():
        if k in ("F", "s_env", "substrate_share"):
            continue
        F *= a
    assert np.allclose(r["F"], F, atol=1e-6)
    assert np.allclose(r["s_env"], 1.0 - 2.0 * F, atol=1e-6)
    # a genuinely every-axis-optimal view reads s = -1 (vigor); the
    # wet-obligate reads fresh_availability, so the marsh is optimal;
    # the clay patch (pH 6.5, nutrient 0.55) hits the view's optimum
    opt = make_ctx(water_potential=np.ones((N, H, W), dtype=np.float32),
                   fresh_availability=np.ones((N, H, W),
                                              dtype=np.float32),
                   mix=mix_arrays(("clay", 1.0)))
    r_opt = evaluate(base_view(waterlogging_tolerance=1.0,
                               woodiness=0.0, root_depth_m=None), opt)
    assert np.allclose(r_opt["s_env"], -1.0, atol=1e-5)
    # a fully-failed one reads s = 1
    lethal = make_ctx(water_potential=np.zeros((N, H, W),
                                               dtype=np.float32),
                      t_c=np.full((N, H, W), 55.0, dtype=np.float32),
                      p_norm=np.ones((N, H, W), dtype=np.float32))
    s = evaluate(base_view(moisture_opt=0.5, drought_tolerance=0.0),
                 lethal)["s_env"]
    assert np.allclose(s, 1.0, atol=1e-5)


def test_verdict_at_materialization():
    """verdict_at indexes one (month, y, x) into every factor and
    materializes the StressVerdict through kernel.stress.compose."""
    ctx = make_ctx()
    r = evaluate(base_view(), ctx)
    v = verdict_at(r, 2, 3, 5)
    assert isinstance(v, StressVerdict)
    # provenance is the per-requirement scalars at that cell-month;
    # capacity metadata (substrate_share) is NOT provenance
    for k, a in r.items():
        if k in ("F", "s_env", "substrate_share"):
            continue
        assert k in v.provenance
        assert v.provenance[k] == pytest.approx(float(a[5, 2, 3]))
    assert "substrate_share" not in v.provenance
    # s/F wiring goes through the kernel compose (same math, same shape)
    expect = compose(v.provenance)
    assert v.s == pytest.approx(expect.s)
    assert v.s == pytest.approx(1.0 - 2.0 * float(r["F"][5, 2, 3]))
    assert -1.0 <= v.s <= 1.0


def test_substrate_share_capacity_split():
    """substrate_share = sum w_i x prod f_i over the mix classes — the
    engine's capacity split (owner ruling 2026-08-01): a 50/50 cell of
    a perfect patch and a failed patch gives suitability 1.0 (the plan
    lives on the good patch) but share 0.5 (only half the cell carries
    it). Computed from the class property rows, self-consistent."""
    mix = mix_arrays(("scree", 1.0), ("mollisol", 1.0))
    ctx = make_ctx(mix=mix)
    view = base_view(fertility_requirement=0.5, ph_tolerance=None,
                     salinity_tolerance=None, root_depth_m=None)
    r = evaluate(view, ctx)
    nut = PROP_TABLES["nutrient"]
    f_scree = float(shortfall_suit(nut[GROUND_ID["scree"]], 0.5, 0.5))
    f_moll = float(shortfall_suit(nut[GROUND_ID["mollisol"]], 0.5, 0.5))
    assert f_scree < 1.0 and f_moll == 1.0
    # the cell factor reads the BEST patch
    assert np.allclose(r[REQ_FERTILITY][0], 1.0)
    # the share weights the patches (fertility is the only substrate
    # requirement this view carries)
    assert np.allclose(r["substrate_share"],
                       0.5 * f_scree + 0.5 * f_moll)
    assert r["substrate_share"].shape == (H, W)
    # water-medium plans carry no ground: share is 1.0 everywhere
    rw = evaluate(base_view(medium="water", salinity_tolerance=0.9), ctx)
    assert np.allclose(rw["substrate_share"], 1.0)
