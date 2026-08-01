"""K15 engine — spec §7 dispersal unit tests (pure math, synthetic
small grids only — no world loads, no disk).

Each kernel and the establishment gate is checked against a
hand-computed case on a tiny synthetic grid; determinism is asserted
by re-running identical inputs with identical seed streams. All
randomness comes from kernel.hashrng streams.

Run: PYTHONPATH=. uv run pytest -q exp/k15_simdiff/test_dispersal.py
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from exp.k15_simdiff.dispersal import (
    ANIMAL_RADIUS_CELLS,
    EMIT_K,
    EMIT_P,
    EST_F_MIN,
    EST_N0,
    JUMP_RADIUS_CELLS,
    LOCAL_BIG,
    RAIN_HALF,
    SEEDBANK_KEEP,
    WATER_LAMBDA,
    WATER_MAX_CELLS,
    WIND_K,
    _ANIMAL_DISK,
    _JUMP_DISK,
    decay_rain,
    deposit_animal,
    deposit_local,
    deposit_water,
    deposit_wind,
    emission,
    establish,
    maybe_jump,
    round_probability,
)
from kernel.hashrng import Stream


def _assert_deposits(dep, expected):
    """Exact key sets; values within rel 1e-12."""
    assert set(dep) == set(expected)
    for key in expected:
        assert dep[key] == pytest.approx(expected[key], rel=1e-12)


def _euclid_disk(cy: int, cx: int, r: int) -> set[tuple[int, int]]:
    """Independent recomputation of the Euclidean disk (center excluded)."""
    return {(y, x) for y in range(cy - r, cy + r + 1)
            for x in range(cx - r, cx + r + 1)
            if (y - cy) ** 2 + (x - cx) ** 2 <= r * r
            and (y, x) != (cy, cx)}


def _cheb_disk(cy: int, cx: int, r: int) -> set[tuple[int, int]]:
    """Independent recomputation of the Chebyshev disk (the 8-
    neighborhood rule: max(|dy|, |dx|) <= r, center excluded)."""
    return {(y, x) for y in range(cy - r, cy + r + 1)
            for x in range(cx - r, cx + r + 1)
            if max(abs(y - cy), abs(x - cx)) <= r
            and (y, x) != (cy, cx)}


# ── §7.1 emission ──────────────────────────────────────────────────────


def test_emission_zero_stress_baseline():
    """E = occupied_cells * (propagule_count / COUNT_REF) at s = 0."""
    assert emission(10, {"propagule_count": 1e4}, 0.0) == pytest.approx(10.0)
    assert emission(10, {"propagule_count": 2e4}, 0.0) == pytest.approx(20.0)
    assert emission(0, {"propagule_count": 1e4}, 0.0) == 0.0
    assert emission(10, {}, 0.0) == 0.0          # no count -> nothing


def test_emission_stress_gate():
    """Positive stress raises emission; negative (opportunity) stress
    leaves the baseline (max(mean_s_real, 0) — a gate, not a dial)."""
    base = emission(10, {"propagule_count": 1e4}, 0.0)
    assert emission(10, {"propagule_count": 1e4}, -0.5) == pytest.approx(base)
    s = 0.3
    assert emission(10, {"propagule_count": 1e4}, s) == pytest.approx(
        10.0 * (1.0 + EMIT_K * s) ** EMIT_P)


# ── §7.2 local ─────────────────────────────────────────────────────────


def test_local_radius_one_uniform():
    """Single cell: the 8 neighbors, share spread uniformly, own cell
    excluded."""
    mask = np.zeros((9, 9), dtype=bool)
    mask[4, 4] = True
    dep = deposit_local(mask, 4.0, 0.3)         # < LOCAL_BIG -> radius 1
    expected = {(y, x): 0.5 for y, x in _cheb_disk(4, 4, 1)}
    _assert_deposits(dep, expected)
    assert (4, 4) not in dep
    assert len(dep) == 8


def test_local_radius_two_at_local_big():
    """local_share >= LOCAL_BIG widens the spill to radius 2 (the 24
    cells at Chebyshev distance 1 or 2), still uniform, own cell out."""
    mask = np.zeros((9, 9), dtype=bool)
    mask[4, 4] = True
    dep = deposit_local(mask, 4.0, 0.6)         # >= LOCAL_BIG -> radius 2
    ring = {(y, x) for y in range(2, 7) for x in range(2, 7)} - {(4, 4)}
    _assert_deposits(dep, {c: 4.0 / 24.0 for c in ring})
    assert len(dep) == 24
    # boundary: exactly LOCAL_BIG also widens
    assert len(deposit_local(mask, 4.0, LOCAL_BIG)) == 24
    # the r=1 case differs (already covered) — the two neighborhoods
    assert len(deposit_local(mask, 4.0, 0.49)) == 8


def test_local_union_excludes_own_cells():
    """Two adjacent cells: the union 8-neighborhood minus ALL own cells,
    uniform over the union."""
    H = W = 5
    mask = np.zeros((H, W), dtype=bool)
    mask[2, 2] = mask[2, 3] = True
    dep = deposit_local(mask, 8.0, 0.2)
    own = {(2, 2), (2, 3)}
    expected = {}
    for y, x in own:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                c = (y + dy, x + dx)
                if 0 <= c[0] < H and 0 <= c[1] < W and c not in own:
                    expected[c] = 8.0 / 10.0
    _assert_deposits(dep, expected)
    assert len(dep) == 10
    assert deposit_local(np.zeros((H, W), dtype=bool), 1.0, 0.2) == {}


# ── §7.2 wind ──────────────────────────────────────────────────────────


def test_wind_uniform_field_downwind_decay():
    """A +x uniform wind: the ray marches downwind, d_k = share_E *
    exp(-k / lambda_w) with lambda_w = WIND_K * speed / sqrt(mass)."""
    H = W = 12
    wind_u = np.full((H, W), 1.0)
    wind_v = np.zeros((H, W))
    share = 2.0
    dep = deposit_wind([(1, 1)], share, wind_u, wind_v,
                       {"propagule_mass_mg": 1.0})
    lam = WIND_K * math.hypot(1.0, 0.0) / math.sqrt(1.0)
    _assert_deposits(dep, {(1, 1 + k): share * math.exp(-k / lam)
                           for k in range(1, 11)})   # edge at x = 11
    # signed projection (acceptance §12.7): every deposit downwind
    for (y, x) in dep:
        assert (y - 1) * 0.0 + (x - 1) * 1.0 > 0.0
    # exponential decay: adjacent ratio is exp(-1 / lambda_w)
    assert dep[(1, 2)] / dep[(1, 3)] == pytest.approx(math.exp(1.0 / lam))


def test_wind_diagonal_ray_integer_steps():
    """A (3, 1) wind: the Bresenham-style ray reaches (dy, dx) = (k//3,
    k) after k steps — the minor axis advances when the fraction
    crosses an integer; deposits stay strictly downwind."""
    H = W = 15
    wind_u = np.full((H, W), 3.0)
    wind_v = np.full((H, W), 1.0)
    share = 1.0
    dep = deposit_wind([(5, 5)], share, wind_u, wind_v,
                       {"propagule_mass_mg": 4.0})
    lam = WIND_K * math.hypot(3.0, 1.0) / math.sqrt(4.0)
    _assert_deposits(dep, {(5 + k // 3, 5 + k): share * math.exp(-k / lam)
                           for k in range(1, 10)})   # edge at x = 14
    for (y, x) in dep:
        assert (y - 5) * 1.0 + (x - 5) * 3.0 > 0.0   # downwind projection
    assert (6, 8) in dep     # k=3: rows advance 5 + floor(3/3) = 6


def test_wind_no_ray_when_still_or_massless():
    """Zero wind vector or no positive propagule mass -> no deposits."""
    H = W = 8
    still = deposit_wind([(4, 4)], 1.0, np.zeros((H, W)), np.zeros((H, W)),
                         {"propagule_mass_mg": 1.0})
    assert still == {}
    no_mass = deposit_wind([(4, 4)], 1.0, np.ones((H, W)), np.zeros((H, W)),
                           {})
    assert no_mass == {}


# ── §7.2 water ─────────────────────────────────────────────────────────


def test_water_d8_walk_decays():
    """Fresh mode: a synthetic D8 pointer chain 0 -> 6 -> 12 -> 18 -> 24
    (flat row-major on a 5x5 grid), d_k = share_E * exp(-k /
    WATER_LAMBDA), stopping at the outlet."""
    H = W = 5
    downstream = np.full((H, W), -1, dtype=np.int64)
    f = downstream.ravel()
    chain = [0, 6, 12, 18, 24]
    for a, b in zip(chain[:-1], chain[1:]):
        f[a] = b
    dep = deposit_water([(0, 0)], 3.0, downstream)
    expected = {(1, 1): 3.0 * math.exp(-1 / WATER_LAMBDA),
                (2, 2): 3.0 * math.exp(-2 / WATER_LAMBDA),
                (3, 3): 3.0 * math.exp(-3 / WATER_LAMBDA),
                (4, 4): 3.0 * math.exp(-4 / WATER_LAMBDA)}
    _assert_deposits(dep, expected)


def test_water_d8_outlet_and_cap():
    """An outlet mid-chain stops the walk; a chain longer than
    WATER_MAX_CELLS is capped; an out-of-range pointer stops too."""
    H = W = 3
    downstream = np.full((H, W), -1, dtype=np.int64)
    f = downstream.ravel()
    chain = [0, 1, 2, 5, 8]                       # flat: (0,0)->(1,1)->(2,2)
    for a, b in zip(chain, chain[1:]):
        f[a] = b
    dep = deposit_water([(0, 0)], 1.0, downstream)
    assert len(dep) == 4                          # 4 chain steps, then -1
    assert (0, 1) in dep and (2, 2) in dep
    # mid-chain outlet
    d2 = np.full((H, W), -1, dtype=np.int64)
    d2.ravel()[0] = 1
    _assert_deposits(deposit_water([(0, 0)], 1.0, d2),
                     {(0, 1): 1.0 * math.exp(-1 / WATER_LAMBDA)})
    # cap: WATER_MAX_CELLS + 5 chain, only WATER_MAX_CELLS deposits
    long = np.full((1, WATER_MAX_CELLS + 8), -1, dtype=np.int64)
    lf = long.ravel()
    for a, b in zip(range(WATER_MAX_CELLS + 7), range(1, WATER_MAX_CELLS + 8)):
        lf[a] = b
    dep_long = deposit_water([(0, 0)], 1.0, long)
    assert len(dep_long) == WATER_MAX_CELLS
    assert (0, WATER_MAX_CELLS) in dep_long
    assert (0, WATER_MAX_CELLS + 1) not in dep_long


def test_water_currents_uniform_field():
    """Marine mode: a uniform +x current walks down-current with the
    same exp decay; a zero field walks nowhere; neither mode given
    raises."""
    H = W = 8
    cu = np.ones((H, W))
    cv = np.zeros((H, W))
    dep = deposit_water([(3, 3)], 2.0, None, currents=(cu, cv))
    _assert_deposits(dep, {(3, 3 + k): 2.0 * math.exp(-k / WATER_LAMBDA)
                           for k in range(1, 5)})  # edge at x = 7
    still = deposit_water([(3, 3)], 2.0, None,
                          currents=(np.zeros((H, W)), np.zeros((H, W))))
    assert still == {}
    with pytest.raises(ValueError):
        deposit_water([(0, 0)], 1.0, None)


# ── §7.2 animal ────────────────────────────────────────────────────────


def test_animal_disk_uniform():
    """One source: the Euclidean disk of radius ANIMAL_RADIUS_CELLS
    (center excluded), share_E spread uniformly over the disk."""
    r = ANIMAL_RADIUS_CELLS
    dep = deposit_animal([(5, 5)], 8.0)
    expected = {c: 8.0 / len(_euclid_disk(5, 5, r)) for c in _euclid_disk(5, 5, r)}
    _assert_deposits(dep, expected)
    assert len(dep) == 80                          # 81 - center


def test_animal_disk_no_clip_at_edges():
    """The stub carries no grid (pinned signature): a corner source keys
    out-of-grid cells (negative coords possible) — the caller drops
    them when scattering into the rain field (documented contract)."""
    dep = deposit_animal([(0, 0)], 1.0)
    assert (-1, 0) in dep
    assert (0, -1) in dep
    assert (0, 0) not in dep                       # own cell excluded


def test_disk_offset_tables_exact():
    """The precomputed disks are exactly the sorted Euclidean disks
    (independent recomputation), center excluded, no duplicates."""
    for disk, r in ((_ANIMAL_DISK, ANIMAL_RADIUS_CELLS),
                    (_JUMP_DISK, JUMP_RADIUS_CELLS)):
        assert len(set(disk)) == len(disk)
        assert disk == tuple(sorted(disk))
        assert all(0 < dy * dy + dx * dx <= r * r for dy, dx in disk)
    assert _ANIMAL_DISK == tuple(sorted(_euclid_disk(0, 0, ANIMAL_RADIUS_CELLS)))
    assert len(_JUMP_DISK) == len(_euclid_disk(0, 0, JUMP_RADIUS_CELLS))


# ── §7.2 jump ──────────────────────────────────────────────────────────


def test_jump_failure_redistributes_to_local():
    """jump_rate = 0 -> P = 0 -> always None: the caller folds the jump
    share into the local channel (spec verbatim)."""
    view = {"jump_rate": 0.0}
    for i in range(20):
        assert maybe_jump(view, 5.0,
                          Stream(i, "k15.disperse", f"t:j0{i}")) is None
    assert maybe_jump({}, 5.0, Stream(1, "k15.disperse", "t:j0")) is None


def test_jump_success_inside_disk():
    """jump_rate at/above 1/yr -> P = 1: always jumps; the offset is a
    uniform cell of the Euclidean jump disk (never the source itself)."""
    for i in range(20):
        off = maybe_jump({"jump_rate": 1.0}, 100.0,
                         Stream(i, "k15.disperse", f"t:j1{i}"))
        assert off is not None
        dy, dx = off
        assert dy * dy + dx * dx <= JUMP_RADIUS_CELLS ** 2
        assert (dy, dx) != (0, 0)
    off2 = maybe_jump({"jump_rate": 2.0}, 100.0,
                      Stream(3, "k15.disperse", "t:j1x"))   # rate clipped
    assert off2 is not None


def test_jump_determinism():
    """Same seed stream -> identical rolls and offsets."""
    def run():
        return [maybe_jump({"jump_rate": 0.3}, 5.0,
                           Stream(9, "k15.disperse", f"t:jd{i}"))
                for i in range(10)]
    assert run() == run()
    assert all(off is None or
               0 < off[0] * off[0] + off[1] * off[1] <= JUMP_RADIUS_CELLS ** 2
               for off in run())


# ── §7.3 establishment gate ────────────────────────────────────────────


def test_round_probability_formula():
    """P = 1 - (1 - p_yr)^T, hand-computed; monotone in p and T."""
    assert round_probability(0.0, 100.0) == 0.0
    assert round_probability(1.0, 100.0) == 1.0
    assert round_probability(0.13, 5.0) == pytest.approx(1.0 - 0.87 ** 5)
    assert round_probability(-0.5, 5.0) == 0.0     # clipped
    assert round_probability(2.0, 5.0) == 1.0      # clipped
    assert round_probability(0.05, 100.0) < round_probability(0.1, 100.0)
    assert round_probability(0.1, 50.0) < round_probability(0.1, 100.0)


def test_establish_gate_below_never_converts():
    """A sink cell (f_hab < EST_F_MIN) never converts, even at
    saturated rain — the vanguard semantics: rain flows, N stays 0."""
    rain = np.full((3, 3), 1.0)
    f_hab = np.full((3, 3), EST_F_MIN - 0.1)
    occ = np.zeros((3, 3), dtype=bool)
    N, founded = establish(rain, f_hab, occ, 1.0, 100.0,
                           Stream(1, "k15.disperse", "t:gate"))
    assert not founded.any()
    assert not N.any()


def test_establish_boundary_converts():
    """The gate is >=: f_hab == EST_F_MIN with saturated rain and rate
    1 converts near-certainly over T = 100 (P = 1 - 0.8^100 ~ 1)."""
    f_hab = np.full((2, 2), EST_F_MIN)
    rain = np.full((2, 2), 1.0)
    occ = np.zeros((2, 2), dtype=bool)
    N, founded = establish(rain, f_hab, occ, 1.0, 100.0,
                           Stream(2, "k15.disperse", "t:edge"))
    assert founded.all()
    assert np.allclose(N[founded], EST_N0)


def test_establish_above_gate_saturated_certain():
    """Saturated rain above the gate with establish_rate 1: p_yr ~ 0.53,
    P = 1 - (0.47)^100 rounds to exactly 1 -> every candidate founds
    at N = EST_N0."""
    rain = np.full((4, 4), 1.0)
    f_hab = np.full((4, 4), 0.8)
    occ = np.zeros((4, 4), dtype=bool)
    N, founded = establish(rain, f_hab, occ, 1.0, 100.0,
                           Stream(1, "k15.disperse", "t:sat"))
    assert founded.all()
    assert np.allclose(N[founded], EST_N0)
    assert not N[~founded].any()


def test_establish_conversion_probability():
    """Above the gate, the conversion probability is exactly
    P = 1 - (1 - p_yr)^T with p_yr = establish_rate * f_hab *
    rain_frac — verified by the empirical frequency over independent
    streams (p_yr ~ 0.13, T = 5 -> P ~ 0.5)."""
    T = 5.0
    rain = np.array([[0.203]])
    f_hab = np.array([[0.9]])
    occ = np.zeros((1, 1), dtype=bool)
    est = 0.5
    p_yr = est * 0.9 * (0.203 / (0.203 + RAIN_HALF))
    P = round_probability(p_yr, T)
    assert P == pytest.approx(1.0 - 0.87 ** 5, rel=1e-3)   # p_yr ~ 0.13
    n = 300
    hits = sum(establish(rain, f_hab, occ, est, T,
                         Stream(5, "k15.disperse", f"t:prob{i}"))[1].sum()
               for i in range(n))
    frac = hits / n
    assert 0.35 < frac < 0.65


def test_establish_rain_frac_slope():
    """Sparse rain converts at low probability (the rain_frac slope):
    rain 0.001, f_hab 0.9, rate 1, T = 100 -> P ~ 0.16, empirically."""
    T = 100.0
    rain = np.array([[0.001]])
    f_hab = np.array([[0.9]])
    occ = np.zeros((1, 1), dtype=bool)
    est = 1.0
    p_yr = est * 0.9 * (0.001 / (0.001 + RAIN_HALF))
    P = round_probability(p_yr, T)
    assert 0.05 < P < 0.35
    n = 400
    hits = sum(establish(rain, f_hab, occ, est, T,
                         Stream(7, "k15.disperse", f"t:slope{i}"))[1].sum()
               for i in range(n))
    frac = hits / n
    assert 0.05 < frac < 0.35


def test_establish_occupancy_discount():
    """A cell already holding an instance of the lineage is never a
    candidate — (1 - occupancy) is 0 there by construction (§7.3 'and
    no occupying instance of L'), even at saturated rain above the
    gate."""
    rain = np.array([[1.0, 1.0]])
    f_hab = np.array([[0.8, 0.8]])
    occ = np.array([[True, False]])
    N, founded = establish(rain, f_hab, occ, 1.0, 100.0,
                           Stream(1, "k15.disperse", "t:occ"))
    assert not founded[0, 0]
    assert N[0, 0] == 0.0
    assert founded[0, 1]
    assert N[0, 1] == pytest.approx(EST_N0)


# ── §7.3 seed bank ─────────────────────────────────────────────────────


def test_seed_bank_persistent_carryover():
    """'persistent' rain carries over with the SEEDBANK_KEEP decay —
    geometric carryover across rounds."""
    rain = np.array([[0.8, 0.2], [0.5, 0.0]])
    r1 = decay_rain(rain, {"seed_bank": "persistent"})
    assert np.allclose(r1, SEEDBANK_KEEP * rain)
    r2 = decay_rain(r1, {"seed_bank": "persistent"})
    assert np.allclose(r2, SEEDBANK_KEEP ** 2 * rain)
    assert SEEDBANK_KEEP == pytest.approx(0.5)


def test_seed_bank_transient_expires():
    """Transient rain (or no seed_bank trait) expires every round — the
    field is replaced by the next round's fresh deposits."""
    rain = np.array([[0.8, 0.2], [0.5, 0.0]])
    assert not decay_rain(rain, {"seed_bank": "transient"}).any()
    assert not decay_rain(rain, {}).any()


# ── full determinism ───────────────────────────────────────────────────


def _pipeline(seed: int):
    """The whole §7 step on a synthetic 9x9 world: all four kernels plus
    the jump roll and the establishment gate under one seed."""
    H = W = 9
    mask = np.zeros((H, W), dtype=bool)
    mask[4, 4] = mask[2, 6] = True
    wind_u = np.full((H, W), 2.0)
    wind_v = np.ones((H, W))
    downstream = np.full((H, W), -1, dtype=np.int64)
    view = {"propagule_mass_mg": 1.0, "jump_rate": 0.4}
    rng = Stream(seed, "k15.disperse", "t:det")
    jump = rng.child("jump")          # the engine's per-channel children
    est = rng.child("establish")
    return (
        deposit_local(mask, 1.0, 0.6),
        deposit_wind(np.argwhere(mask), 1.0, wind_u, wind_v, view),
        deposit_water(np.argwhere(mask), 1.0, downstream),
        deposit_animal(np.argwhere(mask), 1.0),
        maybe_jump(view, 5.0, jump),
        establish(np.full((H, W), 0.5), np.full((H, W), 0.8),
                  np.zeros((H, W), dtype=bool), 0.5, 5.0, est),
    )


def test_full_determinism_same_seed():
    """Same inputs + same seed -> identical deposits, jump roll and
    establishment (spec §2 determinism hard rule)."""
    a = _pipeline(11)
    b = _pipeline(11)
    for x, y in zip(a, b):
        if isinstance(x, dict):
            assert x == y
        elif isinstance(x, tuple) and x and isinstance(x[0], int):
            assert x == y                    # (dy, dx) or None
        else:
            assert np.array_equal(x[0], y[0]) and np.array_equal(x[1], y[1])


def test_pipeline_deposits_accumulate_from_two_sources():
    """Two source cells: the wind rays and animal disks overlap and
    accumulate on shared cells (each kernel deposits the full share per
    source, documented)."""
    H = W = 9
    mask = np.zeros((H, W), dtype=bool)
    mask[4, 4] = mask[4, 5] = True                 # adjacent, +x wind
    wind_u = np.full((H, W), 1.0)
    wind_v = np.zeros((H, W))
    view = {"propagule_mass_mg": 1.0}
    dep = deposit_wind(np.argwhere(mask), 2.0, wind_u, wind_v, view)
    lam = WIND_K * math.hypot(1.0, 0.0) / math.sqrt(1.0)
    # (4, 4) -> x = 5..; (4, 5) -> x = 6..; shared cell (4, 6) sums both
    assert dep[(4, 6)] == pytest.approx(2.0 * math.exp(-2 / lam)
                                        + 2.0 * math.exp(-1 / lam))
    assert dep[(4, 7)] == pytest.approx(2.0 * math.exp(-3 / lam)
                                        + 2.0 * math.exp(-2 / lam))
