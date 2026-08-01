"""K15 engine — spec §7 dispersal unit tests (pure math, synthetic
small grids only — no world loads, no disk).

Each packet-shape function and the establishment gate is checked against
a hand-computed case on a tiny synthetic grid; determinism is asserted
by re-running identical inputs with identical seed streams. All
randomness comes from kernel.hashrng streams.

The v0.5 per-source deposit kernels (deposit_local/wind/water/animal)
were DELETED with the per-cell deposit paths (spec v0.6 §7.2); their
tests went with them. The packet shapes replace them: filled spill
blobs, tapered rays, width-carrying walks, filled disks.

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
    JUMP_DISK_RADIUS,
    JUMP_RADIUS_CELLS,
    LOCAL_BIG,
    MEM_PENALTY,
    MEM_ROUNDS,
    PACKET_AREA_REF,
    PACKET_BASE,
    PACKET_MAX,
    RAIN_HALF,
    SEEDBANK_KEEP,
    WATER_MAX_CELLS,
    WIND_K,
    _ANIMAL_DISK,
    _FILLED_ANIMAL_DISK,
    _FILLED_JUMP_DISK,
    _JUMP_DISK,
    decay_rain,
    emission,
    establish,
    frontier_cells,
    maybe_jump,
    packet_animal_disk,
    packet_count,
    packet_jump_disk,
    packet_local_blob,
    packet_mean_f,
    packet_probability,
    packet_water_walk,
    packet_wind_ray,
    round_probability,
)
from kernel.hashrng import Stream


def _euclid_disk(cy: int, cx: int, r: int, include_center: bool = False
                 ) -> set[tuple[int, int]]:
    """Independent recomputation of the Euclidean disk (center included
    for the packet blobs, excluded for the draw tables)."""
    out = set()
    for y in range(cy - r, cy + r + 1):
        for x in range(cx - r, cx + r + 1):
            if (y - cy) ** 2 + (x - cx) ** 2 <= r * r \
                    and (include_center or (y, x) != (cy, cx)):
                out.add((y, x))
    return out


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


# ── §7.2 packet count and origins ──────────────────────────────────────


def test_packet_count_formula():
    """n_pk = clip(PACKET_BASE + floor(log2(max(1, n_occ)/REF)), 1, MAX):
    a small instance emits ONE packet per active channel, a huge range
    saturates at PACKET_MAX."""
    assert packet_count(1) == 1
    assert packet_count(16) == 1
    assert packet_count(31) == 1
    assert packet_count(32) == 2
    assert packet_count(64) == 3
    assert packet_count(128) == 4
    assert packet_count(256) == 5
    assert packet_count(512) == 6
    assert packet_count(2048) == PACKET_MAX
    assert packet_count(10 ** 6) == PACKET_MAX
    # the formula verbatim (PACKET_BASE=2, REF=32)
    assert packet_count(32) == PACKET_BASE \
        + math.floor(math.log2(32 / PACKET_AREA_REF))


def test_frontier_cells_single_and_edges():
    """An occupied cell with no occupied 8-neighbor is the only frontier
    cell; window-edge occupied cells qualify (the frame is padded)."""
    occ = np.zeros((9, 9), dtype=bool)
    occ[4, 4] = True
    assert frontier_cells(occ) == [(4, 4)]
    # two adjacent cells: both have an unoccupied neighbor
    occ[4, 5] = True
    f = frontier_cells(occ)
    assert (4, 4) in f and (4, 5) in f and len(f) == 2
    # window edge: the full 9x9 block — only the boundary is frontier
    occ2 = np.ones((9, 9), dtype=bool)
    f2 = frontier_cells(occ2)
    assert len(f2) == 32                    # 9x9 perimeter
    assert (0, 0) in f2 and (4, 4) not in f2


def test_frontier_cells_row_major():
    """Frontier cells come back row-major (the pinned origin-draw
    order)."""
    occ = np.zeros((6, 6), dtype=bool)
    occ[1, 1] = occ[3, 4] = True
    f = frontier_cells(occ)
    assert f == sorted(f)
    assert f == [(1, 1), (3, 4)]


# ── §7.2 local packet ──────────────────────────────────────────────────


def test_local_blob_radius_one_uniform():
    """The local packet is the filled Chebyshev spill around the origin
    frontier cell: radius 1 (8 cells) below LOCAL_BIG, own cells out."""
    occ = np.zeros((9, 9), dtype=bool)
    occ[4, 4] = True
    blob = packet_local_blob((4, 4), occ, 0, 0, 9, 9, 0.3)
    assert set(blob) == _cheb_disk(4, 4, 1)
    assert (4, 4) not in blob
    assert len(blob) == 8
    # exactly LOCAL_BIG also widens to radius 2 (24 cells)
    blob2 = packet_local_blob((4, 4), occ, 0, 0, 9, 9, LOCAL_BIG)
    assert set(blob2) == _cheb_disk(4, 4, 2)
    assert len(blob2) == 24
    assert len(packet_local_blob((4, 4), occ, 0, 0, 9, 9, 0.49)) == 8


def test_local_blob_excludes_own_cells():
    """The spill never lands on the instance's OWN cells (the v0.5
    local kernel's rule)."""
    occ = np.zeros((9, 9), dtype=bool)
    occ[4, 4] = occ[4, 5] = occ[4, 3] = True
    blob = packet_local_blob((4, 4), occ, 0, 0, 9, 9, 0.3)
    for own in ((4, 3), (4, 4), (4, 5)):
        assert own not in blob


def test_local_blob_world_shift_and_clip():
    """The origin and occ are in window coords offset by (y0, x0); the
    blob is world coords and clipped to the grid."""
    # origin at the world corner: the spill clips to the grid edge and
    # never includes the ORIGIN (a frontier cell is an own cell — the
    # spill lands off the parent body)
    occ = np.zeros((9, 9), dtype=bool)
    occ[1, 1] = True
    blob = packet_local_blob((0, 0), occ, 20, 30, 26, 34, 0.3)
    assert set(blob) == {(0, 1), (1, 0), (1, 1)}
    # windowed occ is shifted into world coordinates for the own-cell
    # check: the own cell (21, 31) is never a target
    blob2 = packet_local_blob((21, 31), occ, 20, 30, 26, 34, 0.3)
    assert (21, 31) not in blob2
    assert all(0 <= y < 26 and 0 <= x < 34 for y, x in blob2)


# ── §7.2 wind packet ───────────────────────────────────────────────────


def test_wind_ray_length_and_taper():
    """The wind packet is a tapered tentacle of length L = ceil(lambda),
    lambda = WIND_K * speed / sqrt(mass): L = 1 for lambda = 1, with
    width 2 (ray cell + one perpendicular neighbor) for the first
    floor(len/2) cells."""
    H = W = 64
    wu = np.ones((H, W))
    wv = np.zeros((H, W))
    ray = packet_wind_ray((32, 8), wu, wv, {"propagule_mass_mg": 1.0})
    assert ray == [(32, 9)]                # L = ceil(1.0), width 1
    # speed 2, mass 1 -> L = 2; the first floor(2/2) = 1 cell is width 2
    ray2 = packet_wind_ray((32, 8), 2 * wu, wv, {"propagule_mass_mg": 1.0})
    assert set(ray2) == {(32, 9), (33, 9), (32, 10)}
    # mass 0.001, speed 5 -> L capped at WIND_MAX_CELLS: 40 ray cells +
    # 20 width cells (first half), all distinct (dedupe)
    ray3 = packet_wind_ray((32, 8), 5 * wu, wv,
                           {"propagule_mass_mg": 0.001})
    assert len(ray3) == 40 + 20
    assert len(set(ray3)) == len(ray3)
    # downwind projection (acceptance §12.7): every cell has positive
    # column offset from the origin
    assert all(x > 8 for _y, x in ray3)


def test_wind_ray_diagonal_direction():
    """A (3, 1) wind: the Bresenham-style ray marches downwind; the
    perpendicular neighbor is on the row axis (column-major ray)."""
    H = W = 64
    wu = np.full((H, W), 3.0)
    wv = np.full((H, W), 1.0)
    ray = packet_wind_ray((32, 8), wu, wv, {"propagule_mass_mg": 4.0})
    assert (32, 9) in ray and (33, 9) in ray   # first step + width
    for (y, x) in ray:
        assert (y - 32) * 1.0 + (x - 8) * 3.0 > 0.0    # downwind


def test_wind_ray_empty_when_still_or_massless():
    """Zero wind at the origin or no positive propagule mass -> no
    cells."""
    H = W = 8
    still = packet_wind_ray((4, 4), np.zeros((H, W)), np.zeros((H, W)),
                            {"propagule_mass_mg": 1.0})
    assert still == []
    no_mass = packet_wind_ray((4, 4), np.ones((H, W)), np.zeros((H, W)),
                              {})
    assert no_mass == []


# ── §7.2 water packet ──────────────────────────────────────────────────


def test_water_walk_d8_with_width():
    """Fresh mode: the D8 pointer chain is walked; the first
    floor(len/2) walked cells carry a width-2 neighbor (deduped when it
    coincides with a later walked cell)."""
    H = W = 9
    downstream = np.full((H, W), -1, dtype=np.int64)
    f = downstream.ravel()
    chain = [4 * 9 + 4, 4 * 9 + 5, 4 * 9 + 6]
    for a, b in zip(chain[:-1], chain[1:]):
        f[a] = b
    walk = packet_water_walk((4, 4), downstream)
    # walked (4,5) -> (4,6); the walk is column-major so the width
    # neighbor of (4,5) is the row +1 cell (5,5); dedupe keeps cells
    # distinct
    assert set(walk) == {(4, 5), (5, 5), (4, 6)}
    assert len(walk) == len(set(walk))
    # an outlet mid-chain stops the walk; a single walked cell carries
    # no width (floor(1/2) = 0)
    d2 = np.full((H, W), -1, dtype=np.int64)
    d2.ravel()[0] = 1
    assert packet_water_walk((0, 0), d2) == [(0, 1)]


def test_water_walk_cap():
    """A chain longer than WATER_MAX_CELLS is capped; an out-of-range
    pointer stops too."""
    long = np.full((1, WATER_MAX_CELLS + 8), -1, dtype=np.int64)
    lf = long.ravel()
    for a, b in zip(range(WATER_MAX_CELLS + 7), range(1, WATER_MAX_CELLS + 8)):
        lf[a] = b
    walk = packet_water_walk((0, 0), long)
    assert len(walk) >= WATER_MAX_CELLS
    assert all(x < WATER_MAX_CELLS + 1 for _y, x in walk)


def test_water_walk_currents_and_error():
    """Marine mode: a uniform +x current walks down-current with the
    same width; a zero field walks nowhere; neither mode given raises."""
    H = W = 8
    cu = np.ones((H, W))
    cv = np.zeros((H, W))
    walk = packet_water_walk((3, 3), None, currents=(cu, cv))
    assert (3, 4) in walk and (4, 4) in walk      # first step + width
    assert (3, 7) in walk                          # walk reaches the edge
    still = packet_water_walk((3, 3), None,
                              currents=(np.zeros((H, W)), np.zeros((H, W))))
    assert still == []
    with pytest.raises(ValueError):
        packet_water_walk((0, 0), None)


# ── §7.2 animal / jump packets ─────────────────────────────────────────


def test_animal_disk_filled_and_clipped():
    """The animal packet is the FILLED Euclidean disk (center included)
    of radius ANIMAL_RADIUS_CELLS, clipped to the grid."""
    H = W = 20
    disk = packet_animal_disk((10, 10), H, W)
    assert set(disk) == _euclid_disk(10, 10, ANIMAL_RADIUS_CELLS, True)
    assert (10, 10) in disk
    assert len(disk) == len(_FILLED_ANIMAL_DISK)
    # corner clipping
    corner = packet_animal_disk((0, 0), H, W)
    assert all(0 <= y < H and 0 <= x < W for y, x in corner)
    assert (0, 0) in corner


def test_jump_disk_filled_size():
    """The jump packet is the filled Euclidean disk of radius
    JUMP_DISK_RADIUS (~28 cells) around the landing."""
    H = W = 20
    disk = packet_jump_disk((10, 10), H, W)
    assert set(disk) == _euclid_disk(10, 10, JUMP_DISK_RADIUS, True)
    assert (10, 10) in disk
    assert len(disk) == len(_FILLED_JUMP_DISK) == 29


def test_disk_offset_tables_exact():
    """The precomputed disks are exactly the sorted Euclidean disks
    (independent recomputation), no duplicates."""
    for disk, r, center in ((_ANIMAL_DISK, ANIMAL_RADIUS_CELLS, False),
                            (_JUMP_DISK, JUMP_RADIUS_CELLS, False),
                            (_FILLED_ANIMAL_DISK, ANIMAL_RADIUS_CELLS, True),
                            (_FILLED_JUMP_DISK, JUMP_DISK_RADIUS, True)):
        assert len(set(disk)) == len(disk)
        assert disk == tuple(sorted(disk))
        assert all(dy * dy + dx * dx <= r * r for dy, dx in disk)
        if center:
            assert (0, 0) in disk
        else:
            assert (0, 0) not in disk
            assert all(0 < dy * dy + dx * dx <= r * r for dy, dx in disk)
    assert _ANIMAL_DISK == tuple(sorted(_euclid_disk(0, 0, ANIMAL_RADIUS_CELLS)))
    assert _FILLED_JUMP_DISK == tuple(sorted(
        _euclid_disk(0, 0, JUMP_DISK_RADIUS, True)))


# ── §7.2 jump roll ─────────────────────────────────────────────────────


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


# ── §7.3 packet establishment gate ─────────────────────────────────────


def test_packet_mean_f():
    """mean(f_hab^beta) over the packet's cells, row-major order; beta
    = 0 is the stress-blind fallback (mean of 1s = 1)."""
    f_hab = np.full((9, 9), 0.7)
    assert packet_mean_f(f_hab, [(4, 4), (5, 5)]) == 0.7
    f2 = f_hab.copy()
    f2[5, 5] = 0.1
    assert packet_mean_f(f2, [(4, 4), (5, 5)]) == pytest.approx(0.4)
    # order-independent value but deterministic accumulation: same cells
    # in any order give the same mean
    assert packet_mean_f(f2, [(5, 5), (4, 4)]) == pytest.approx(0.4)
    assert packet_mean_f(f_hab, [(4, 4)], beta=0.0) == 1.0
    assert packet_mean_f(f_hab, [(4, 4)], beta=2.0) == pytest.approx(0.49)
    assert packet_mean_f(f_hab, []) == 0.0


def test_packet_probability_formula_and_gate():
    """P = 1 - (1 - est x mean_f)^T (the §4 single-T policy) with the
    §7.3 gate: mean_f < EST_F_MIN -> 0 (vanguard semantics at the packet
    scale)."""
    assert packet_probability(0.2, 1.0, 100.0) == 0.0     # gate
    assert packet_probability(EST_F_MIN - 1e-9, 1.0, 100.0) == 0.0
    p = packet_probability(0.8, 1.0, 100.0)
    assert p == pytest.approx(1.0 - 0.2 ** 100)
    p2 = packet_probability(0.8, 0.5, 10.0)
    assert p2 == pytest.approx(1.0 - 0.6 ** 10)
    # monotone in mean_f and establish_rate (at non-saturating T)
    assert packet_probability(0.9, 0.5, 5.0) \
        > packet_probability(0.8, 0.5, 5.0)
    assert packet_probability(0.8, 0.55, 5.0) \
        > packet_probability(0.8, 0.5, 5.0)


def test_packet_probability_memory_penalty():
    """A packet whose candidate cells are remembered is down-weighted
    x MEM_PENALTY (colonization memory, spec §7.3)."""
    p = packet_probability(0.8, 1.0, 100.0)
    pm = packet_probability(0.8, 1.0, 100.0, in_memory=True)
    assert pm == pytest.approx(MEM_PENALTY * p)
    assert MEM_PENALTY == pytest.approx(0.25)
    # the gate is not rescued by the memory flag
    assert packet_probability(0.2, 1.0, 100.0, in_memory=True) == 0.0


def test_packet_probability_memory_constants():
    """The memory knobs exist with their settled values."""
    assert MEM_ROUNDS == 3


# ── §7.3 per-cell establishment gate (retained) ────────────────────────


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


def _packets(seed: int):
    """The whole §7 packet layer under one seed on a synthetic 9x9
    world: packet counts, origins, all four shapes, the jump roll and
    the packet probability (no engine)."""
    H = W = 9
    occ = np.zeros((H, W), dtype=bool)
    occ[4, 4] = occ[2, 6] = True
    wind_u = np.full((H, W), 2.0)
    wind_v = np.ones((H, W))
    downstream = np.full((H, W), -1, dtype=np.int64)
    f_hab = np.full((H, W), 0.8)
    view = {"propagule_mass_mg": 1.0, "jump_rate": 0.4}
    rng = Stream(seed, "k15.disperse", "t:det")
    n_pk = packet_count(2)
    return (
        n_pk,
        frontier_cells(occ),
        [packet_local_blob((4, 4), occ, 0, 0, H, W, 0.6)
         for _ in range(n_pk)],
        [packet_wind_ray((4, 4), wind_u, wind_v, view)
         for _ in range(n_pk)],
        [packet_water_walk((4, 4), downstream) for _ in range(n_pk)],
        [packet_animal_disk((4, 4), H, W) for _ in range(n_pk)],
        [packet_jump_disk((4, 4), H, W) for _ in range(n_pk)],
        maybe_jump(view, 5.0, rng.child("jump")),
        packet_probability(packet_mean_f(f_hab, [(4, 4), (2, 6)]), 0.5,
                           5.0, in_memory=True),
    )


def test_full_determinism_same_seed():
    """Same inputs + same seed -> identical shapes, jump roll and packet
    probability (spec §2 determinism hard rule)."""
    a = _packets(11)
    b = _packets(11)
    for x, y in zip(a, b):
        if isinstance(x, list):
            assert x == y
        elif isinstance(x, tuple) and x and isinstance(x[0], int):
            assert x == y                    # (dy, dx) or None
        else:
            assert x == y
