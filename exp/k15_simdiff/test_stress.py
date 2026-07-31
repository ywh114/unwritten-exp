"""K15 — kernel/stress contract tests (B5 §2/§4 shape).

Pure-math tests over synthetic scalars/arrays; the world adapter and
its integration tests land with the engine.

Run: uv run pytest -q exp/k15_simdiff
"""

from __future__ import annotations

import numpy as np

from kernel.stress import (
    climate_suit,
    compose,
    dist_suit,
    excess_suit,
    invert,
    sat,
    shortfall_suit,
)


# ──  primitives  ──────────────────────────────────────────────────────


def test_sat_clips():
    assert sat(-0.5) == 0.0 and sat(0.5) == 0.5 and sat(1.5) == 1.0
    a = sat(np.array([-1.0, 0.25, 2.0]))
    assert np.allclose(a, [0.0, 0.25, 1.0])


def test_dist_suit_shape():
    assert dist_suit(15.0, 15.0, 10.0) == 1.0          # at optimum
    assert dist_suit(25.0, 15.0, 10.0) == 0.0          # at breadth: full
    # weight-1 cost saturates exactly at |env - opt| = breadth
    assert dist_suit(5.0, 15.0, 10.0) == 0.0           # two-sided
    assert dist_suit(100.0, 15.0, 10.0) == 0.0         # saturated
    assert dist_suit(25.0, 15.0, 20.0) == 0.5          # wider breadth
    assert dist_suit(25.0, 15.0, 10.0, weight=0.2) == 0.8


def test_one_sided_suits():
    assert shortfall_suit(2.0, 1.0) == 1.0             # need met
    assert shortfall_suit(0.5, 1.0) == 0.5
    assert shortfall_suit(0.5, 1.0, ref=0.5) == 0.0    # ref scales cost
    assert excess_suit(0.5, 1.0) == 1.0                # under limit
    assert excess_suit(1.5, 1.0) == 0.5
    assert excess_suit(3.0, 1.0) == 0.0                # saturated


def test_invert():
    assert invert(0.25) == 0.75
    a = invert(np.array([0.0, 1.0]))
    assert np.allclose(a, [1.0, 0.0])


# ──  climate stratum  ─────────────────────────────────────────────────


def test_climate_suit_monthly():
    t = np.full((12, 2, 2), 15.0)
    p = np.full((12, 2, 2), 100.0)
    f = climate_suit(t, p, 15.0, 10.0, 100.0, 50.0)
    assert f.shape == (12, 2, 2)
    assert np.allclose(f, 1.0)                          # all optimal
    f2 = climate_suit(t + 10.0, p, 15.0, 10.0, 100.0, 50.0)
    assert np.allclose(f2, 0.5)                         # T at breadth: w_T off
    f3 = climate_suit(t + 100.0, p - 1000.0, 15.0, 10.0, 100.0, 50.0)
    assert np.allclose(f3, 0.0)                         # both maxed: clip


def test_climate_weights_override():
    f = climate_suit(25.0, 100.0, 15.0, 10.0, 100.0, 50.0,
                     w_t=0.2, w_p=0.2)
    assert np.allclose(f, 0.8)                          # per-plan pair


# ──  composition  ─────────────────────────────────────────────────────


def test_compose_product_and_sign():
    r = compose({"pressure:temperature": 0.5, "pressure:ph": 0.5})
    assert np.isclose(r.F, 0.25)
    assert np.isclose(r.s, 0.5)                         # 1 - 2F
    assert r.factors["pressure:ph"] == 0.5
    assert r.__dataclass_params__.frozen


def test_compose_extremes():
    assert compose({}).s == -1.0                        # nothing wrong
    assert compose({"pressure:x": 1.0}).s == -1.0       # perfect suit
    assert compose({"pressure:x": 0.0}).s == 1.0        # lethal
    # Liebig tail-dominance: one zero kills the product
    r = compose({"pressure:a": 1.0, "pressure:b": 1.0, "pressure:c": 0.0})
    assert r.s == 1.0


def test_compose_vigor_gradient():
    """The good end keeps its gradient: acceptable != ideal."""
    ok = compose({"pressure:a": 0.9, "pressure:b": 0.9})
    ideal = compose({"pressure:a": 1.0, "pressure:b": 1.0})
    assert ok.s < 0.0 and ideal.s < ok.s                # -0.62 < -0.19... 
    assert np.isclose(ok.s, 1 - 2 * 0.81)
