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
)
from exp.k15_simdiff.stress_adapter import (
    FRESH_SAL_MAX,
    MEDIUM_VIOLATION_F,
    WLOG_DRY_LIMIT,
    WLOG_INVERT_T,
    WorldContext,
    evaluate,
    verdict_at,
)
from kernel.stress import (
    climate_suit,
    compose,
    dist_suit,
    excess_suit,
    invert,
    sat,
    shortfall_suit,
)

H = W = 4
N = 12


def make_ctx(**overrides) -> WorldContext:
    """A tiny synthetic world: everything constant unless overridden."""
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
    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


def base_view(**kw) -> dict:
    """A mesic, C3, evergreen land plan; individual keys overridable."""
    view = {
        "temp_opt_c": 15.0, "temp_breadth_c": 10.0,
        "moisture_opt": 0.5, "moisture_breadth": 0.3,
        "w_T": None, "w_P": None,
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


def test_climate_distance_matches_kernel():
    """REQ_CLIMATE equals the kernel climate_suit composition at the
    niche baseline (T/P at optimum -> 1; at breadth -> 1 - w)."""
    ctx = make_ctx()
    view = base_view()
    r = evaluate(view, ctx)
    f = r[REQ_CLIMATE][0]
    expect = climate_suit(ctx.t_c[0], ctx.p_norm[0], 15.0, 10.0,
                          0.5, 0.3)
    assert np.allclose(f, expect)
    # at optimum everything is 1
    assert np.allclose(f, 1.0)
    # T at breadth with w_T=0.5: f = 1 - 0.5
    ctx2 = make_ctx(t_c=np.full((N, H, W), 25.0, dtype=np.float32))
    f2 = evaluate(base_view(), ctx2)[REQ_CLIMATE][0]
    assert np.allclose(f2, 0.5)
    # both saturated -> clipped 0
    ctx3 = make_ctx(t_c=np.full((N, H, W), 55.0, dtype=np.float32),
                    p_norm=np.full((N, H, W), 1.0, dtype=np.float32))
    assert np.allclose(evaluate(base_view(), ctx3)[REQ_CLIMATE], 0.0)


def test_drought_widens_dry_side_asymmetric():
    """drought_tolerance widens the moisture breadth on the DRY side
    only: a dry cell costs less for a drought-tolerant plan, a wet cell
    costs the same."""
    ctx = make_ctx(p_norm=np.full((N, H, W), 0.1, dtype=np.float32))
    dry_low = evaluate(base_view(drought_tolerance=0.1), ctx)[REQ_CLIMATE][0]
    dry_high = evaluate(base_view(drought_tolerance=0.9), ctx)[REQ_CLIMATE][0]
    assert (dry_high > dry_low).all()          # dry side slackened
    ctxw = make_ctx(p_norm=np.full((N, H, W), 0.9, dtype=np.float32))
    wet_low = evaluate(base_view(drought_tolerance=0.1), ctxw)[REQ_CLIMATE][0]
    wet_high = evaluate(base_view(drought_tolerance=0.9), ctxw)[REQ_CLIMATE][0]
    assert np.allclose(wet_low, wet_high)      # wet side untouched


def test_phenology_gates_cold_months():
    """winter_deciduous: the T cost is dropped in dormant months
    (m < leafout_month); an evergreen pays it year-round."""
    ctx = make_ctx(t_c=np.full((N, H, W), -10.0, dtype=np.float32),
                   p_norm=np.full((N, H, W), 0.5, dtype=np.float32))
    dec = evaluate(base_view(winter_deciduous=1, leafout_month=4),
                   ctx)[REQ_CLIMATE]
    evg = evaluate(base_view(winter_deciduous=0), ctx)[REQ_CLIMATE]
    assert np.allclose(dec[:3], 1.0)            # dormant months: no cost
    assert np.allclose(dec[3:], evg[3:])        # leaf-on: same as evergreen
    assert (dec[3:] < 1.0).any()                # leaf-on cold cost bites


def test_drought_deciduous_relaxes_dry_season():
    """drought_deciduous discounts the dry-side P cost."""
    ctx = make_ctx(p_norm=np.full((N, H, W), 0.05, dtype=np.float32))
    base = evaluate(base_view(drought_deciduous=0), ctx)[REQ_CLIMATE]
    rel = evaluate(base_view(drought_deciduous=1), ctx)[REQ_CLIMATE]
    assert (rel > base).all()


def test_c4_cam_cold_penalty():
    """C4/CAM carry a cold penalty term (C3 none): on a cold cell the
    climate factor drops below the plain distance."""
    ctx = make_ctx(t_c=np.full((N, H, W), 0.0, dtype=np.float32),
                   p_norm=np.full((N, H, W), 0.5, dtype=np.float32))
    c3 = evaluate(base_view(photosynthesis="C3"), ctx)[REQ_CLIMATE][0]
    c4 = evaluate(base_view(photosynthesis="C4"), ctx)[REQ_CLIMATE][0]
    cam = evaluate(base_view(photosynthesis="CAM"), ctx)[REQ_CLIMATE][0]
    assert (c4 < c3).all() and (cam < c3).all()
    # the penalty is bounded ("costly, never lethal"): at T=0 the plain
    # distance factor is 0.5 (breadth cost) and the cold penalty docks
    # at most 40% of it -> floor 0.3, never 0.
    assert np.allclose(c3, 0.5)
    assert np.allclose(c4, 0.3) and np.allclose(cam, 0.3)


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
    """High waterlogging_tolerance INVERTS the term: the saturated end
    becomes the requirement (dry ground is the cost); dry plans keep
    the excess shape (saturated ground is the cost)."""
    ctx_wet = make_ctx(water_potential=np.full((N, H, W), 1.0,
                                               dtype=np.float32))
    ctx_dry = make_ctx(water_potential=np.zeros((N, H, W),
                                                dtype=np.float32))
    wet_plan = base_view(waterlogging_tolerance=1.0)
    dry_plan = base_view(waterlogging_tolerance=0.0)
    f_wet = evaluate(wet_plan, ctx_wet)[REQ_WATERLOGGING][0]
    f_dry = evaluate(dry_plan, ctx_dry)[REQ_WATERLOGGING][0]
    assert np.allclose(f_wet, 1.0) and np.allclose(f_dry, 1.0)
    bad_wet = evaluate(wet_plan, ctx_dry)[REQ_WATERLOGGING][0]
    bad_dry = evaluate(dry_plan, ctx_wet)[REQ_WATERLOGGING][0]
    assert np.allclose(bad_wet, 0.0) and np.allclose(bad_dry, 0.0)


def test_fertility_shortfall():
    """REQ_FERTILITY = shortfall of eff_nutrient below the requirement
    (low requirement on rich soil is not penalized)."""
    ctx = make_ctx(eff_nutrient=np.full((H, W), 0.9, dtype=np.float32))
    rich = evaluate(base_view(fertility_requirement=0.3), ctx)
    assert np.allclose(rich[REQ_FERTILITY], 1.0)
    ctxpoor = make_ctx(eff_nutrient=np.zeros((H, W), dtype=np.float32))
    poor = evaluate(base_view(fertility_requirement=0.5), ctxpoor)
    assert np.allclose(poor[REQ_FERTILITY], 0.0)


def test_ph_position_split():
    """ph_tolerance is a POSITION: opt = 4 + 5 x value, breadth ±1.
    The factor is emitted SPLIT one-sided (req_flora ruling): ph_low
    drops only when the cell is too acidic for the position, ph_high
    only when too alkaline; their product is the symmetric distance."""
    ctx = make_ctx(ground_ph=np.full((H, W), 4.0, dtype=np.float32))
    cf = evaluate(base_view(ph_tolerance=0.0), ctx)
    cc = evaluate(base_view(ph_tolerance=1.0), ctx)
    assert np.allclose(cf[REQ_PH_LOW][0], 1.0)
    assert np.allclose(cf[REQ_PH_HIGH][0], 1.0)
    assert np.allclose(cc[REQ_PH_LOW][0], 0.0)    # opt 9.0 vs 4.0: too acid
    assert np.allclose(cc[REQ_PH_HIGH][0], 1.0)   # not too alkaline
    ctxalk = make_ctx(ground_ph=np.full((H, W), 9.0, dtype=np.float32))
    cc2 = evaluate(base_view(ph_tolerance=1.0), ctxalk)
    assert np.allclose(cc2[REQ_PH_LOW][0], 1.0)
    assert np.allclose(cc2[REQ_PH_HIGH][0], 1.0)
    cf2 = evaluate(base_view(ph_tolerance=0.0), ctxalk)
    assert np.allclose(cf2[REQ_PH_LOW][0], 1.0)
    assert np.allclose(cf2[REQ_PH_HIGH][0], 0.0)  # too alkaline
    # water plans read water_ph instead
    ctxw = make_ctx(water_ph=np.full((H, W), 9.0, dtype=np.float32))
    r = evaluate(base_view(medium="water", ph_tolerance=1.0,
                           salinity_tolerance=0.9), ctxw)
    assert np.allclose(r[REQ_PH_LOW][0], 1.0)
    assert np.allclose(r[REQ_PH_HIGH][0], 1.0)


def test_salinity_ionic_excess():
    """REQ_SALINITY = one-sided excess: land plans read eff_sal_add,
    water plans read the normalized h_salinity."""
    ctx = make_ctx(eff_sal_add=np.full((H, W), 0.9, dtype=np.float32))
    low = evaluate(base_view(salinity_tolerance=0.1), ctx)[REQ_SALINITY][0]
    high = evaluate(base_view(salinity_tolerance=0.95), ctx)[REQ_SALINITY][0]
    assert (high > low).all()
    assert np.allclose(low, 1.0 - sat((0.9 - 0.1) / 1.0))


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
    """rooting = saturating excess of root_depth over eff_rooting;
    anchoring = hard substrate for holdfasts, (1 - eff_hard) for woody
    land plants; absent for non-woody non-holdfast plans."""
    ctx = make_ctx(eff_rooting_m=np.full((H, W), 0.5, dtype=np.float32))
    deep = evaluate(base_view(root_depth_m=2.0), ctx)[REQ_ROOTING][0]
    shallow = evaluate(base_view(root_depth_m=0.2), ctx)[REQ_ROOTING][0]
    assert (shallow > deep).all()
    assert np.allclose(deep, 1.0 - sat((2.0 - 0.5) / 1.0))
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
    tail-dominance and the signed scale), wired through the kernel."""
    ctx = make_ctx(t_c=np.full((N, H, W), 15.0, dtype=np.float32),
                   p_norm=np.full((N, H, W), 0.5, dtype=np.float32))
    r = evaluate(base_view(), ctx)
    F = np.ones((N, H, W), dtype=np.float32)
    for k, a in r.items():
        if k in ("F", "s_env"):
            continue
        F *= a
    assert np.allclose(r["F"], F, atol=1e-6)
    assert np.allclose(r["s_env"], 1.0 - 2.0 * F, atol=1e-6)
    # a genuinely every-axis-optimal view reads s = -1 (vigor); the
    # base mesic view on a neutral cell sits below 0 too
    opt = make_ctx(water_potential=np.ones((N, H, W), dtype=np.float32),
                   ground_ph=np.full((H, W), 6.5, dtype=np.float32))
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
    # provenance is the per-requirement scalars at that cell-month
    for k, a in r.items():
        if k in ("F", "s_env"):
            continue
        assert k in v.provenance
        assert v.provenance[k] == pytest.approx(float(a[5, 2, 3]))
    # s/F wiring goes through the kernel compose (same math, same shape)
    expect = compose(v.provenance)
    assert v.s == pytest.approx(expect.s)
    assert v.s == pytest.approx(1.0 - 2.0 * float(r["F"][5, 2, 3]))
    assert -1.0 <= v.s <= 1.0
