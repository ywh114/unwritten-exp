"""K14 moisture tests — water_potential + fresh_availability (pure
functions, synthetic decoded fields; no k11 dump needed).

Run: uv run pytest -q exp/k14_worldprod/test_moisture.py
"""

from __future__ import annotations

import numpy as np

from exp.k14_worldprod import moisture
from exp.k14_worldprod.ground import GROUND_CLASSES, eff_props


def _monthly(v: float, shape=(1, 4)) -> np.ndarray:
    return np.full((12, *shape), v, dtype=float)


# ── eff_props (B5 shared precompute) ─────────────────────────────────


def test_eff_props_mix_weighted():
    i0, i1 = 0, 1
    mix_ids = np.array([[[i0]], [[i1]], [[i1]]])          # (3,1,1)
    mix_w = np.array([[[0.5]], [[0.0]], [[0.5]]])         # 50/50 over i0,i1
    eff = eff_props(mix_ids, mix_w)
    c0, c1 = GROUND_CLASSES[i0], GROUND_CLASSES[i1]
    expect = 0.5 * c0["retention"] + 0.5 * c1["retention"]
    assert np.isclose(eff["retention"][0, 0], expect)
    sal_expect = 0.5 * (c0["sal_add"] or 0.0) + 0.5 * (c1["sal_add"] or 0.0)
    assert np.isclose(eff["sal_add"][0, 0], sal_expect)
    assert set(eff) == {"retention", "nutrient", "rooting_m",
                        "sal_add", "hard", "loose"}


# ── water_potential ──────────────────────────────────────────────────


def test_water_potential_wet_beats_arid():
    hand = np.full((1, 2), 50.0)       # well-drained
    accum = np.zeros((1, 2))
    ret = np.full((1, 2), 0.6)
    sal = np.zeros((1, 2))
    p = _monthly(200.0, (1, 2))
    p[:, 0, 1] = 5.0                   # arid cell
    t = _monthly(15.0, (1, 2))
    t[:, 0, 1] = 32.0
    psi = moisture.water_potential(p, t, hand, accum, ret, sal)
    assert (psi[:, 0, 0] > 0.4).all()
    assert (psi[:, 0, 1] < 0.2).all()
    assert (psi[:, 0, 0] > psi[:, 0, 1]).all()


def test_water_potential_salinity_osmotic_penalty():
    hand = np.full((1, 1), 50.0)
    accum = np.zeros((1, 1))
    ret = np.full((1, 1), 0.6)
    p, t = _monthly(200.0, (1, 1)), _monthly(15.0, (1, 1))
    fresh = moisture.water_potential(p, t, hand, accum, ret,
                                     np.zeros((1, 1)))
    salty = moisture.water_potential(p, t, hand, accum, ret,
                                     np.ones((1, 1)))
    assert np.isclose((fresh - salty)[0, 0, 0], moisture.SAL_PEN,
                      atol=1e-6)


def test_water_potential_frozen_months_lock_water():
    hand = np.full((1, 1), 50.0)
    accum = np.zeros((1, 1))
    ret = np.full((1, 1), 0.6)
    sal = np.zeros((1, 1))
    p = _monthly(200.0, (1, 1))
    t = _monthly(15.0, (1, 1))
    t[:6] = -10.0                      # frozen half-year
    psi = moisture.water_potential(p, t, hand, accum, ret, sal)
    assert (psi[:6] == 0.0).all()      # ice holds the water
    assert (psi[6:] > 0.4).all()


def test_water_potential_waterlogged_saturation_end():
    """Low HAND + full retention + catchment feed saturates even at
    moderate local rainfall."""
    hand = np.zeros((1, 1))            # at the water table
    accum = np.full((1, 1), 300.0)
    ret = np.ones((1, 1))
    sal = np.zeros((1, 1))
    p, t = _monthly(60.0, (1, 1)), _monthly(15.0, (1, 1))
    psi = moisture.water_potential(p, t, hand, accum, ret, sal)
    assert (psi > 0.9).all()


# ── fresh_availability ───────────────────────────────────────────────

_FIELDS = dict(hand=np.full((1, 4), 50.0), accum=np.zeros((1, 4)),
               alt=np.zeros((1, 4)), ret=np.full((1, 4), 0.6),
               lake=np.zeros((1, 4), bool),
               river_m=np.zeros((12, 1, 4), bool),
               mangrove=np.zeros((1, 4), bool))


def _avail(p, t, **over):
    f = {k: (v.copy() if hasattr(v, "copy") else v)
         for k, v in _FIELDS.items()}
    f.update(over)
    return moisture.fresh_availability(p, t, f["hand"], f["accum"],
                                       f["alt"], f["ret"], f["lake"],
                                       f["river_m"], f["mangrove"])


def test_fresh_unwritten_stream_below_river_threshold():
    p, t = _monthly(100.0), _monthly(15.0)
    accum = np.zeros((1, 4))
    accum[0, 0] = 20.0                 # unwritten creek (< river thresh)
    a = _avail(p, t, accum=accum)
    assert (a[:, 0, 0] > 0.3).all()
    assert (a[:, 0, 1] < 1e-3).all()   # no accum, high HAND: ponding
    # term is nonzero but negligible at 50 m above the water table
    assert (a[:, 0, 0] <= moisture.FRESH_LAND_CAP + 1e-6).all()


def test_fresh_ponding_needs_flat_wet_retentive():
    p, t = _monthly(100.0), _monthly(15.0)
    pondy = _avail(p, t, hand=np.zeros((1, 4)),
                   accum=np.full((1, 4), 250.0), ret=np.ones((1, 4)))
    assert (pondy > 0.5).all()
    steep = _avail(p, t, hand=np.zeros((1, 4)),
                   accum=np.full((1, 4), 250.0), ret=np.ones((1, 4)),
                   alt=np.array([[0.0, 200.0, 0.0, 200.0]]))
    # relief only lowers the ponding term; stream/feed terms may remain
    assert (steep <= pondy + 1e-6).all()


def test_fresh_adjacency_capped():
    p, t = _monthly(100.0), _monthly(15.0)
    lake = np.zeros((1, 4), bool)
    lake[0, 0] = True
    a = _avail(p, t, lake=lake)
    assert (a[:, 0, 0] == 1.0).all()                       # the lake
    assert np.isclose(a[0, 0, 1], moisture.ADJ_W, atol=1e-6) or \
        a[0, 0, 1] <= moisture.ADJ_W + 1e-6
    assert a[0, 0, 1] > 0.0                                # neighbor
    assert a[0, 0, 3] < 1e-3                               # out of reach


def test_fresh_mapped_water_and_seasonality():
    p = _monthly(100.0)
    t = _monthly(15.0)
    river_m = np.zeros((12, 1, 4), bool)
    river_m[:6, 0, 0] = True             # seasonal river: wet months only
    a = _avail(p, t, river_m=river_m, accum=np.full((1, 4), 50.0))
    assert (a[:6, 0, 0] == 1.0).all()    # mapped in wet months
    assert (a[6:, 0, 0] > 0.0).all()     # implicit in dry months
    # seasonality: a rain-fed pocket (no catchment) swings with the
    # water balance
    p2 = _monthly(100.0)
    p2[6:] = 5.0                         # dry half-year
    t2 = _monthly(15.0)
    t2[6:] = 32.0
    b = _avail(p2, t2, accum=np.full((1, 4), 8.0))
    assert b[0, 0, 0] > b[-1, 0, 0]


def test_fresh_land_cap_below_mapped_water():
    """Implicit habitat NEVER reads as high as mapped water, even when
    every driver maxes out."""
    p, t = _monthly(300.0), _monthly(15.0)
    a = _avail(p, t, hand=np.zeros((1, 4)),
               accum=np.full((1, 4), 39.0),   # just under river mapping
               ret=np.ones((1, 4)))
    assert (a <= moisture.FRESH_LAND_CAP + 1e-6).all()
    assert (a > 0.0).all()
