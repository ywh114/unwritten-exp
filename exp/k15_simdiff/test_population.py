"""K15 engine — spec §6 population update unit tests (pure math, no
world, no disk). Each formula is checked against a hand-computed case.

Run: PYTHONPATH=. uv run pytest -q exp/k15_simdiff/test_population.py
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from exp.k15_simdiff.population import (
    BIOMASS_REF,
    DENS_CAP,
    K_EPS,
    ROUND_YEARS,
    VIG_K,
    bscale,
    cell_demand,
    density_half_life_rounds,
    density_stress,
    extinction_floor,
    lineage_capacity,
    percap_demand,
    update_instance,
    vital_update,
)


def test_percap_demand_formula():
    """crown²·(1+wood)/BIOMASS_REF, hand-computed; absent keys → 0."""
    assert percap_demand({"crown_spread_m": 1.0, "woodiness": 0.0}) \
        == pytest.approx(1.0 / BIOMASS_REF)
    assert percap_demand({"crown_spread_m": 2.0, "woodiness": 0.5}) \
        == pytest.approx(4.0 * 1.5 / BIOMASS_REF)
    assert percap_demand({}) == 0.0
    assert percap_demand({"crown_spread_m": None, "woodiness": 1.0}) == 0.0


def test_cell_demand_sums_instances():
    """D(c) = Σ_i N_i(c)·percap_i — the engine's per-instance N stack."""
    N_stack = np.array([
        [[0.5, 0.2], [0.0, 0.1]],      # instance 0
        [[0.1, 0.0], [0.4, 0.3]],      # instance 1
    ])
    percap = np.array([0.2, 0.4])
    D = cell_demand(N_stack, percap)
    expected = np.array([
        [0.5 * 0.2 + 0.1 * 0.4, 0.2 * 0.2 + 0.0 * 0.4],
        [0.0 * 0.2 + 0.4 * 0.4, 0.1 * 0.2 + 0.3 * 0.4],
    ])
    assert np.allclose(D, expected)


def test_capacity_split_two_lineages_same_cell():
    """K_L = PROD_CAP_SCALE·productivity·U_L: two lineages with
    different substrate shares on the same cell draw different K_L."""
    productivity = np.full((2, 2), 10.0)
    U_a = np.full((2, 2), 0.5)          # heath on its podzol patch
    U_b = np.full((2, 2), 0.25)         # calcicole on the rendzina patch
    K_a = lineage_capacity(productivity, U_a)
    K_b = lineage_capacity(productivity, U_b)
    assert np.array_equal(K_a, np.full((2, 2), 5.0))
    assert np.array_equal(K_b, np.full((2, 2), 2.5))
    assert K_a[0, 0] != K_b[0, 0]
    # water plans pass U = 1: the whole cell's capacity
    assert np.array_equal(lineage_capacity(productivity, 1.0),
                          np.full((2, 2), 10.0))


def test_density_stress_k_eps():
    """K_L ≤ K_EPS with D > 0 → DENS_CAP; D = 0 → 0 even at zero cap."""
    s = density_stress(np.array([1.0, 0.0]), np.array([1e-7, 1e-7]))
    assert s[0] == DENS_CAP
    assert s[1] == 0.0
    # normal denominator form: DENS_C·D/K
    assert density_stress(np.array([2.0]), np.array([1.0]))[0] \
        == pytest.approx(1.0)
    # clipped at DENS_CAP
    assert density_stress(np.array([10.0]), np.array([1.0]))[0] == DENS_CAP


def test_bscale_clipping_both_ends():
    """clip(1 − s_real, 0, 1 + VIG_K): floor at 0, cap at 1 + VIG_K."""
    assert bscale(np.array([2.0]))[0] == 0.0            # floor
    assert bscale(np.array([-0.8]))[0] == pytest.approx(1.0 + VIG_K)
    assert bscale(np.array([0.3]))[0] == pytest.approx(0.7)  # linear inside


def test_vital_update_exp_form_hand_computed():
    """Continuous compounding, hand-computed: D = 0 → s_dens = 0;
    s_env = 0.3, birth = 0.02, death = 0.01, T = 100:
        s_real = 0.3 → bscale = 0.7 → growth = 0.014
        mort = 0.01 + 0.002·0.3 = 0.0106
        N' = N·exp((0.014 − 0.0106)·100) = N·exp(0.34)"""
    N = np.array([0.5])
    N1 = vital_update(N, s_env=np.array([0.3]), D=np.array([0.0]),
                      K_L=np.array([1.0]), birth=0.02, death=0.01)
    assert N1[0] == pytest.approx(0.5 * math.exp(0.34), rel=1e-9)


def test_vital_update_negative_s_boosts_growth_only():
    """Negative s_real is opportunity, never immortality: mort never
    drops below the baseline death rate (spec §6)."""
    N = np.array([0.1])   # 0.1·e² ≈ 0.74 stays below the [0,1] clip
    N1 = vital_update(N, s_env=np.array([-0.5]), D=np.array([0.0]),
                      K_L=np.array([1.0]), birth=0.02, death=0.01)
    # bscale = 1.5 → growth = 0.03; mort = 0.01 (max(s_real,0) = 0)
    assert N1[0] == pytest.approx(0.1 * math.exp((0.03 - 0.01) * ROUND_YEARS),
                                  rel=1e-9)


def test_extinction_floor_retirement_mask():
    """N < N_FLOOR → abandoned (N = 0); the mask reports which cells."""
    N = np.array([[0.05, 0.009], [0.0, 0.5]])
    N1, abandoned = extinction_floor(N)
    assert np.array_equal(abandoned, [[False, True], [True, False]])
    assert N1[0, 1] == 0.0 and N1[1, 0] == 0.0
    assert N1[0, 0] == 0.05 and N1[1, 1] == 0.5
    # an instance whose cells all hit the floor: engine reads the mask
    _, ab = extinction_floor(np.array([[0.001], [0.005]]))
    assert ab.all()


def test_update_instance_density_cap_crushes_growth():
    """Zero usable capacity: s_dens = DENS_CAP → bscale = 0 → N decays
    at the stress-mortality-only rate (hand-computed)."""
    N = np.array([1.0])
    N1, abandoned = update_instance(N, s_env=np.array([0.0]),
                                    D=np.array([1.0]),
                                    K_L=np.array([1e-9]),
                                    birth=0.1, death=0.0)
    # s_real = 2.0 → bscale = 0 → growth = 0; mort = 0.002·2.0 = 0.004
    assert N1[0] == pytest.approx(math.exp(-0.004 * ROUND_YEARS), rel=1e-9)
    assert not abandoned[0]


def test_die_k_half_life_constraint():
    """Spec §6 design constraint: sustained s_real = 0.3 gives density
    half-life ≥ 5 rounds at DIE_K = 0.002, T = 100."""
    assert density_half_life_rounds(0.3) >= 5.0
    # and the numeric value: ln2 / (0.002·0.3·100) ≈ 11.6
    assert density_half_life_rounds(0.3) \
        == pytest.approx(math.log(2.0) / (0.002 * 0.3 * 100.0))
