"""K15 engine — spec §10 genesis rain tests.

Fast pure-partition tests run by default. The world-dependent tests run
on seed 1 (stress_adapter.load_world(1) + the stat-pass capacity anchor,
lifted as genesis.load_capacity) — 35 adapter evaluations per genesis
call, so they are marked ``slow`` per the repo convention (pyproject:
``pytest -m slow``). Ticket 0020 (DESIGN PIVOT) adds the sparse
founders + partial coverage seeding (GENESIS_F0 · K_L demand, per-
component GENESIS_COVER keep/drop draws, NO density budget) — the
species rain is exercised by test_genesis_species_sparse_founders via
Engine(1).genesis().

Run all: PYTHONPATH=. uv run pytest -q exp/k15_simdiff/test_genesis.py
Run fast: PYTHONPATH=. uv run pytest -q -m "not slow" ...
Run slow: PYTHONPATH=. uv run pytest -q -m slow exp/k15_simdiff/test_genesis.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from exp.k13_treegen.flora.backbone import build as build_backbone
from exp.k13_treegen.flora.content import load_content
from exp.k13_treegen.flora.sim import FloraSim
from exp.k13_treegen.model import Rank
from exp.k15_simdiff import population as pop
from exp.k15_simdiff import stress_adapter as sa
from exp.k15_simdiff.genesis import (
    GENESIS_COVER,
    GENESIS_COVER_MIN_R,
    GENESIS_F,
    GENESIS_F0,
    GENESIS_PROX_R,
    CloneSeed,
    _clone_units,
    _covered_components,
    _covered_tiered,
    _partition,
    _partition_range,
    _rain_for_view,
    connected_components,
    coverage_keep,
    genesis_rain,
    partition_k,
    proximity_components,
    reduced,
    valid_mask,
)
from exp.k15_descent.descent import DESCENT_MIN_BLOB_CELLS
from kernel.hashrng import Stream

FLORA_CONTENT = Path("exp/k13_treegen/content/flora")


# ── world fixtures (only built when a slow test runs) ──────────────────


@pytest.fixture(scope="session")
def pack_sim():
    pack = load_content(FLORA_CONTENT)
    return pack, FloraSim(pack)


@pytest.fixture(scope="session")
def world(k15_world):
    return k15_world


@pytest.fixture(scope="session")
def capacity(k15_capacity):
    return k15_capacity


# ── spec §10 step 3: the partition knobs (fast) ────────────────────────


def test_partition_k_formula():
    """Spec §10 verbatim: K = clip(1 + floor(log2(range/200)), 1, 8)."""
    assert partition_k(0) == 0
    assert partition_k(1) == 1
    assert partition_k(200) == 1        # 1 + floor(log2(1)) = 1
    assert partition_k(399) == 1
    assert partition_k(400) == 2        # 1 + floor(log2(2)) = 2
    assert partition_k(799) == 2
    assert partition_k(25600) == 8      # 1 + floor(log2(128)) = 8
    assert partition_k(10**9) == 8      # capped at PART_K_MAX


def _block(h: int, w: int, canvas: int = 256) -> np.ndarray:
    m = np.zeros((canvas, canvas), dtype=bool)
    m[:h, :w] = True
    return m


def _assert_partition_valid(chunks: list[np.ndarray], seeded: np.ndarray,
                            expected_count: int) -> None:
    """Every chunk contiguous; chunks disjoint; union == seeded; count."""
    assert len(chunks) == expected_count
    union = np.logical_or.reduce(chunks)
    assert np.array_equal(union, seeded)
    assert sum(int(c.sum()) for c in chunks) == int(seeded.sum())
    for c in chunks:
        assert c.sum() >= 1
        assert len(connected_components(c)) == 1


def test_partition_synthetic_split_to_k():
    """One big component (>= PART_MIN_CELLS) split into exactly K
    contiguous chunks — the recursion path seed 1's fragmented ranges do
    not exercise."""
    seeded = _block(128, 128)                       # 16384 cells
    for K in (1, 2, 4, 8):
        chunks = _partition(seeded, K, Stream(1, "k15.genesis", "syn"))
        _assert_partition_valid(chunks, seeded, K)


def test_partition_synthetic_small_components_floor():
    """Components below PART_MIN_CELLS stay one clone each — the floor
    wins over the K target (spec §10)."""
    seeded = np.zeros((256, 256), dtype=bool)
    seeded[2:4, 2:6] = True                          # 8 cells
    seeded[20:24, 30:32] = True                      # 8 cells
    seeded[40:44, 40:42] = True                      # 8 cells
    chunks = _partition(seeded, 2, Stream(1, "k15.genesis", "syn"))
    assert len(chunks) == 3                          # floor: one per comp
    _assert_partition_valid(chunks, seeded, 3)
    assert all(c.sum() == 8 for c in chunks)


def test_partition_synthetic_determinism():
    """Same seed → byte-identical chunk masks (hashrng-only draws)."""
    seeded = _block(128, 128)
    a = _partition(seeded, 7, Stream(5, "k15.genesis", "syn"))
    b = _partition(seeded, 7, Stream(5, "k15.genesis", "syn"))
    assert len(a) == len(b) == 7
    for ca, cb in zip(a, b):
        assert ca.dtype == cb.dtype == bool
        assert ca.tobytes() == cb.tobytes()


# ── ticket 0033 §1: proximity grouping + clone-unit partition ───────────


def _islands(pts, canvas: int = 40) -> np.ndarray:
    m = np.zeros((canvas, canvas), dtype=bool)
    for y, x in pts:
        m[y, x] = True
    return m


def test_proximity_components():
    """Ticket 0033 §1: the blob-stage grouping — connected components of
    dilate(mask, r) intersected back with the mask, so pixels that are
    NOT 8-connected but still close to each other merge into ONE blob
    (the strip-habitat fix: mangrove coast edges, kelp, waterlily,
    willow, sedge). The Chebyshev ring dilation (reused from the §7
    kernel) merges two pixels at Chebyshev distance ≤ 2r + 1: r = 2
    (GENESIS_PROX_R) merges within distance 5, separates beyond."""
    # two 1-pixel islands within r of each other -> ONE blob, both cells
    assert len(proximity_components(_islands([(10, 10), (14, 14)]))) == 1
    assert len(proximity_components(_islands([(10, 10), (15, 15)]))) == 1
    merged = proximity_components(_islands([(10, 10), (15, 15)]))[0]
    assert int(merged.sum()) == 2
    # ...and the merged blob is NOT 8-connected (that's the whole point)
    assert len(connected_components(merged)) == 2
    # beyond r: islands stay separate blobs
    assert len(proximity_components(_islands([(10, 10), (16, 16)]))) == 2
    # union of blobs == the input mask, parts disjoint
    m = _islands([(10, 10), (13, 13), (30, 5)])
    blobs = proximity_components(m)
    assert [int(b.sum()) for b in blobs] == [2, 1]
    assert np.array_equal(np.logical_or.reduce(blobs), m)
    assert sum(int(b.sum()) for b in blobs) == int(m.sum())
    # a blob of a single isolated pixel is still a blob (r > 0 strips the
    # ring's center exclusion — the mask union in the helper)
    assert proximity_components(_islands([(10, 10)]))[0].sum() == 1
    # deterministic: same input -> byte-identical blob masks
    a = proximity_components(m)
    b = proximity_components(m)
    assert len(a) == len(b)
    for ba, bb in zip(a, b):
        assert ba.tobytes() == bb.tobytes()


def test_partition_range_disconnected_retained():
    """Ticket 0033 §1: the partition of a proximity-merged retained set
    splits over CLONE UNITS (_clone_units): fat 8-components (>= 32)
    split into contiguous pieces; STRIP units (sub-32 material regrouped
    by proximity — NO size floor since ticket 0039) are ONE clone each —
    the owner's merge-into-one-instance ruling — and may be
    DISCONNECTED; residual islands inside a kept blob are strips too
    (never dropped)."""
    # a strip blob whose 8-components are all sub-12: ONE disconnected
    # clone (the mangrove/kelp case)
    seeded = np.zeros((40, 40), dtype=bool)
    seeded[10, 10:18] = True                        # 8-cell chain
    seeded[14, 14:20] = True                        # 6-cell chain, Cheb 4 away
    assert [int(b.sum()) for b in proximity_components(seeded)] == [14]
    chunks = _partition_range(seeded, 1, Stream(1, "k15.genesis", "syn"))
    assert len(chunks) == 1
    assert np.array_equal(chunks[0], seeded)
    assert len(connected_components(chunks[0])) == 2   # disconnected clone
    # far-apart blobs: one clone per blob (never merged into one)
    seeded = np.zeros((40, 40), dtype=bool)
    seeded[10, 10:25] = True                        # 15 cells
    seeded[30, 5:20] = True                         # 15 cells, > 5 away
    chunks = _partition_range(seeded, 1, Stream(1, "k15.genesis", "syn"))
    assert len(chunks) == 2
    assert all(int(c.sum()) == 15 for c in chunks)
    _assert_partition_valid(chunks, seeded, 2)
    # fat + strip in one blob: the fat splits, the strip stays single;
    # count = max(K, #units) = 3 (K = partition_k(812) = 3, units 2)
    seeded = np.zeros((64, 64), dtype=bool)
    seeded[5:25, 5:45] = True                       # 20x40 = 800 fat
    seeded[28, 28:40] = True                        # 12-cell strip, Cheb 4 away
    assert int(proximity_components(seeded)[0].sum()) == 812
    chunks = _partition_range(seeded, 3, Stream(1, "k15.genesis", "syn"))
    assert len(chunks) == 3
    sizes = sorted(int(c.sum()) for c in chunks)
    assert sizes[0] == 12                           # the strip stays single
    assert sizes[1] + sizes[2] == 800               # the fat split in 2
    for c in chunks:
        assert c.sum() >= 1
    # a sub-12 island inside a kept blob is a STRIP unit too (ticket
    # 0039: the mint floor is gone — nothing is dropped; the island
    # mints as its own single-instance clone)
    seeded = np.zeros((64, 64), dtype=bool)
    seeded[5:25, 5:45] = True                       # 800 fat
    seeded[28, 28:36] = True                        # 8-cell island, Cheb 4 away
    assert int(proximity_components(seeded)[0].sum()) == 808
    chunks = _partition_range(seeded, 1, Stream(1, "k15.genesis", "syn"))
    assert len(chunks) == 2                         # fat + island strip
    sizes = sorted(int(c.sum()) for c in chunks)
    assert sizes == [8, 800]
    assert chunks[1][28, 28:36].any()               # the island is minted
    assert np.array_equal(np.logical_or.reduce(chunks), seeded)


# ── ticket 0037: tiered coverage ────────────────────────────────────────


def _synthetic_ctx(h: int = 40, w: int = 40):
    """A bare WorldContext carrying only H/W (the synthetic rain only
    reads them through valid_mask's dual branch)."""
    ctx = sa.WorldContext()
    ctx.H, ctx.W = h, w
    return ctx


def _synthetic_rain(mask: np.ndarray, key: str, seed: int = 1,
                    h: int = 40, w: int = 40):
    """A synthetic ``_rain_for_view`` over a handcrafted viability
    mask: two factor planes (F = 0.8 on the mask, 0 elsewhere — plus a
    dummy provenance requirement so the §5.1 reduction has a prov
    axis), U = 1 everywhere, K = 1 everywhere (K_L = 1), percap = 1
    (crown 5 m, no woodiness → D = max(F0, N_FLOOR) = 0.1, N = 0.1).
    Returns (clones, range_cells)."""
    factors = {
        "F": np.where(mask, 0.8, 0.0).reshape(1, h, w),
        "substrate_share": np.ones((h, w)),
        "pressure:heat": np.zeros((1, h, w)),
    }
    view = {"medium": "dual", "crown_spread_m": 5.0, "woodiness": 0.0}
    return _rain_for_view(view, _synthetic_ctx(h, w), seed, key, factors,
                          np.ones((h, w)))


def test_coverage_keep_ramp():
    """Ticket 0037: the keep probability as a function of the
    pre-coverage retained cell count R — R < 200 → 1.0 (the no-draw
    regime), 200-400 → linear 1.0 → GENESIS_COVER, R > 400 → the flat
    GENESIS_COVER = 0.5 (the pre-0037 behavior)."""
    assert coverage_keep(0) == 1.0
    assert coverage_keep(199) == 1.0
    assert coverage_keep(200) == 1.0
    assert coverage_keep(250) == pytest.approx(0.875)
    assert coverage_keep(300) == pytest.approx(0.75)
    assert coverage_keep(400) == pytest.approx(0.5)
    assert coverage_keep(401) == pytest.approx(0.5)
    assert coverage_keep(10**6) == pytest.approx(GENESIS_COVER)


class _Poison(Stream):
    """A Stream whose bernoulli draw must never fire (ticket 0037: the
    R < GENESIS_COVER_MIN_R regime does NO coverage draw at all)."""
    def bernoulli(self, p, clock, index=0):
        raise AssertionError(
            "a coverage draw fired below GENESIS_COVER_MIN_R")


def test_covered_tiered_no_draw_below_200():
    """Ticket 0037: a pre-coverage retained count R < 200 skips the
    coverage draw entirely — every floor-passing blob is kept (the
    species seeds its whole viable range) and the stream is never
    touched (the poison stream proves the draw does not happen)."""
    big = [c for c in proximity_components(_block(14, 10))]  # 140 cells
    covered = _covered_tiered(big, _Poison(1, "k15.genesis", "poison"))
    assert covered is big                     # returned unchanged, no draw
    assert int(covered[0].sum()) == 140


def test_covered_tiered_draw_regimes_address_pinned_streams():
    """Ticket 0037: in the draw regimes (R >= 200) the tiered draw uses
    the ramped probability coverage_keep(R) on the SAME pinned
    content-addressed child streams (``cover:{i}``) — the kept set
    equals an explicit recomputation of the draws, and above 400 the
    outcome is literally the pre-0037 flat GENESIS_COVER draw."""
    m = np.zeros((40, 40), dtype=bool)
    m[2:22, 2:8] = True                        # 120
    m[2:22, 30:36] = True                      # 120
    m[27:33, 10:20] = True                     # 60 — > 5 from the others
    big = proximity_components(m)
    assert [int(b.sum()) for b in big] == [120, 120, 60]
    R = 300
    assert coverage_keep(R) == pytest.approx(0.75)
    for seed in (1, 7, 99):
        rng = Stream(seed, "k15.genesis", "draw")
        kept = _covered_tiered(big, rng)
        # explicit recomputation: same child streams, ramped p
        rng2 = Stream(seed, "k15.genesis", "draw")
        expected = [c for i, c in enumerate(big)
                    if rng2.child(f"cover:{i}").bernoulli(0.75, 0)]
        if not expected:
            expected = [max(big, key=lambda c: int(c.sum()))]
        assert len(kept) == len(expected)
        for k, e in zip(kept, expected):
            assert np.array_equal(k, e)
    # large range: R > 400 → identical to the flat GENESIS_COVER
    m6 = np.zeros((40, 40), dtype=bool)
    m6[2:22, 2:8] = True
    m6[2:22, 30:36] = True
    m6[27:33, 10:20] = True
    m6[2:22, 18:24] = True                        # 120 more, > 5 away
    big6 = proximity_components(m6)
    R6 = sum(int(b.sum()) for b in big6)
    assert R6 >= 400 and coverage_keep(R6) == GENESIS_COVER
    for seed in (3, 42):
        tiered = _covered_tiered(big6, Stream(seed, "k15.genesis", "big"))
        flat = _covered_components(big6, Stream(seed, "k15.genesis", "big"),
                                   GENESIS_COVER)
        assert len(tiered) == len(flat)
        for t, f in zip(tiered, flat):
            assert np.array_equal(t, f)


def test_covered_tiered_midrange_keep_statistics():
    """Statistical (ticket 0037): a mid-range draw (R = 300, p_keep =
    0.75) keeps, over many seeds, a realized fraction of the retained
    cells that is a proper fraction between 0.5 and 1.0 — the ramp's
    whole point: narrow ranges are no longer downsized by the flat
    0.5 (the 78-cell mangrove lost its larger blob pre-0037)."""
    m = np.zeros((40, 40), dtype=bool)
    m[2:22, 2:8] = True
    m[2:22, 30:36] = True
    m[27:33, 10:20] = True
    big = proximity_components(m)
    fracs = []
    for seed in range(1, 301):
        kept = _covered_tiered(big, Stream(seed, "k15.genesis", "stat"))
        fracs.append(sum(int(k.sum()) for k in kept) / 300.0)
    fracs = np.asarray(fracs)
    assert 0.70 <= fracs.mean() <= 0.95, fracs.mean()


def test_rain_small_range_seeds_full_range():
    """Ticket 0037 done-means (small range): a synthetic species whose
    pre-coverage retained count R < 200 seeds its WHOLE viable range —
    no coverage draw — where the pre-0037 flat draw downsized narrow
    ranges (the ticket's mangrove lost its larger blob and minted 36
    of 78 viable cells)."""
    m = np.zeros((40, 40), dtype=bool)
    m[5:15, 5:15] = True                       # 100 cells
    m[20:22, 20:32] = True                     # 24 cells, > 5 away
    clones, range_cells = _synthetic_rain(m, "small")
    assert range_cells == 124
    union = np.logical_or.reduce([c.cells for c in clones])
    assert np.array_equal(union, m)            # the full viable range
    for clone in clones:
        assert clone.N.dtype == np.float32
        assert np.allclose(clone.N[clone.cells], 0.1)


def test_rain_midrange_matches_explicit_draws():
    """Ticket 0037: a mid-range synthetic rain (R = 300, p_keep =
    0.75) applies the coverage draw with the RAMPED probability on the
    pinned ``cover:{i}`` child streams — the minted union equals an
    explicit recomputation of the draws (the draw addressing is
    unchanged by the ramp)."""
    m = np.zeros((40, 40), dtype=bool)
    m[2:22, 2:8] = True
    m[2:22, 30:36] = True
    m[27:33, 10:20] = True
    clones, range_cells = _synthetic_rain(m, "mid", seed=3)
    big = proximity_components(m)
    rng = Stream(3, "k15.genesis", "mid")
    kept = [c for i, c in enumerate(big)
            if rng.child(f"cover:{i}").bernoulli(0.75, 0)]
    if not kept:
        kept = [max(big, key=lambda c: int(c.sum()))]
    expected = np.logical_or.reduce(kept)
    assert range_cells == int(expected.sum())
    union = np.logical_or.reduce([c.cells for c in clones])
    assert np.array_equal(union, expected)


def test_rain_tiered_determinism():
    """Ticket 0037: two identical synthetic rains (draw regime, R =
    300) → byte-identical cells and N fields (the ramp is draw-free
    except the pinned coverage streams; same seed → byte-identical)."""
    m = np.zeros((40, 40), dtype=bool)
    m[2:22, 2:8] = True
    m[2:22, 30:36] = True
    m[27:33, 10:20] = True
    a = _synthetic_rain(m, "det", seed=5)
    b = _synthetic_rain(m, "det", seed=5)
    assert a[1] == b[1]
    assert len(a[0]) == len(b[0])
    for ca, cb in zip(a[0], b[0]):
        assert ca.cells.tobytes() == cb.cells.tobytes()
        assert ca.N.tobytes() == cb.N.tobytes()


# ── world-dependent genesis (slow: 35 adapter evaluations per call) ────


def _seeded_range(pack, ctx, pid: str) -> np.ndarray:
    """The preset's genesis range, recomputed independently as ground
    truth: evaluate → worst-month reduction → F_worst ≥ GENESIS_F ∩
    medium-valid (spec §10 steps 1-2)."""
    view = sa.preset_view(pid, pack)
    factors = sa.evaluate(view, ctx)
    _names, _m_star, F_worst, _prov = reduced(factors)
    del factors
    return (F_worst >= GENESIS_F) & valid_mask(view, ctx)


def _expected_demand(view: dict, ctx, K: np.ndarray
                     ) -> tuple[np.ndarray, float]:
    """The ticket 0020 founder demand, recomputed independently as
    ground truth: D(c) = max(GENESIS_F0 · K_L(c), N_FLOOR · percap)
    with K_L = pop.lineage_capacity(K, U) (spec §6 v0.3 capacity
    split) — the same formula genesis uses, re-derived here."""
    factors = sa.evaluate(view, ctx)
    U = factors["substrate_share"]
    K_L = pop.lineage_capacity(K, U)
    percap = pop.percap_demand(view)
    D = np.maximum(GENESIS_F0 * K_L, pop.N_FLOOR * percap)
    del factors
    return D, percap


def _expected_retained(seeded: np.ndarray, key: str, seed: int = 1
                       ) -> tuple[np.ndarray | None, int]:
    """The ticket 0020 covered retained mask, recomputed independently:
    PROXIMITY blobs (ticket 0033 §1 — proximity_components, the blob
    stage's grouping unit; NO mint floor since ticket 0039) → the
    TIERED coverage keep/drop (ticket 0037: R = the pre-coverage retained
    cell count, computed BEFORE the draws; R < GENESIS_COVER_MIN_R ->
    no draw at all — every blob kept; otherwise per-blob draws
    ``rng.child(f"cover:{i}")``, pinned emission order, keep
    probability coverage_keep(R)) with the largest-blob retry (the
    coverage draw never causes extinction). Returns (covered mask,
    pre-coverage retained cell count)."""
    rng = Stream(seed, "k15.genesis", key)
    big = proximity_components(seeded)
    if not big:
        return None, 0
    n_ret = int(sum(int(c.sum()) for c in big))
    if n_ret < GENESIS_COVER_MIN_R:
        sel = big
    else:
        sel = [c for i, c in enumerate(big)
               if rng.child(f"cover:{i}").bernoulli(coverage_keep(n_ret), 0)]
        if not sel:
            sel = [max(big, key=lambda c: int(c.sum()))]
    return np.logical_or.reduce(sel), n_ret


def _check_clone_field(clone: CloneSeed, seeded: np.ndarray,
                       D: np.ndarray, percap: float) -> None:
    """N = D/percap exactly on the clone's cells (D = max(F0·K_L,
    N_FLOOR·percap) — ticket 0020's capacity-relative founder demand),
    0 elsewhere."""
    assert clone.cells.dtype == bool
    assert clone.N.dtype == np.float32
    assert np.allclose(clone.N[clone.cells], D[clone.cells] / percap,
                       rtol=1e-6, atol=1e-9)
    assert not clone.N[~clone.cells].any()


@pytest.mark.slow
def test_genesis_partition_structure(world, pack_sim, capacity):
    """Every preset: clone count, contiguity, disjointness, union and N
    fields against an independent recomputation of the seeded range.
    v1.1 re-pin (ticket 0020, DESIGN PIVOT): per-blob coverage draws
    (``_expected_retained``) keep ~GENESIS_COVER of the retained blobs
    (whole blobs, never speckle), and the partition's K targets the
    COVERED range. v1.5 re-pin (ticket 0033 §1, owner's strip-habitat
    ruling 2026-08-03): the blob stage groups by PROXIMITY
    (proximity_components — disconnected-but-close pixels merge into
    one blob) and the mint floor drops 32 → 12. The partition
    decomposes the covered set into CLONE UNITS (_clone_units): fat
    8-components (>= 32) — contiguous, splittable — and STRIP units
    (sub-32 material regrouped by proximity — no size floor) — ONE
    clone each, possibly DISCONNECTED (the contiguity invariant's
    documented exception, the owner's merge-into-one-instance ruling);
    the clone union IS the covered set (nothing is dropped). Count =
    max(K, #units) when the surplus is absorbable. v1.6 re-pin
    (ticket 0037): the coverage keep probability is TIERED by the
    pre-coverage retained count R (``_expected_retained`` mirrors
    coverage_keep: R < 200 no draw, 200-400 ramped, > 400 flat
    GENESIS_COVER). v1.7 (ticket 0039, owner ruling 2026-08-04): the
    mint floor is REMOVED ENTIRELY — every proximity blob is retained,
    however small, so retained/covered counts GROW and the R-ramp
    regime may shift species (the pinned values below are PRE-0039 and
    need re-pinning from an actual slow run). Re-pinned on seed 1 at
    the 0033 landing: fungus.agaric retained 2477 (partition_k 4) →
    covered 1884 (partition_k 4); runner_meadow.seagrass retained 2030
    (4) → covered 515 (2)."""
    pack, sim = pack_sim
    rain = genesis_rain(pack, sim, world, capacity, seed=1)
    assert set(rain) == set(pack.presets)
    retained: dict[str, int] = {}
    minted: dict[str, int] = {}
    k_gt1: list[str] = []
    for pid in sorted(pack.presets):
        seeded = _seeded_range(pack, world, pid)
        D, percap = _expected_demand(sa.preset_view(pid, pack), world,
                                     capacity)
        covered, n_ret = _expected_retained(seeded, pid)
        retained[pid] = n_ret
        clones = rain[pid]
        if covered is None:
            # no viable cells at all (zero range) — never minted
            assert clones == ()
            continue
        minted[pid] = int(covered.sum())
        K = partition_k(int(covered.sum()))
        if K > 1:
            k_gt1.append(pid)
        # units: fat 8-components + strip proximity blobs; the clone
        # count is max(K, #units) — one clone per unit minimum, the
        # surplus K - #units to the largest FAT units (absorbable: K ≥ 2
        # ⟺ range ≥ 400 cells ⟹ the top unit is fat with enough cells).
        fat, strips = _clone_units(covered)
        units = fat + strips
        assert len(clones) == max(K, len(units))
        # union == the units' union == covered (nothing dropped since
        # ticket 0039), disjoint
        cells = [c.cells for c in clones]
        unit_union = np.logical_or.reduce(units)
        assert np.array_equal(np.logical_or.reduce(cells), unit_union)
        assert sum(int(c.sum()) for c in cells) == int(unit_union.sum())
        for clone in clones:
            assert clone.cells.shape == seeded.shape
            # contiguity with the strip exception: every clone is ONE
            # 8-connected component OR a whole strip unit (disconnected
            # by design — the owner's merge-into-one-instance ruling)
            assert (len(connected_components(clone.cells)) == 1
                    or any(np.array_equal(clone.cells, s) for s in strips))
            _check_clone_field(clone, seeded, D, percap)
    # RE-PIN NEEDED (ticket 0039): the pins below are PRE-0039 — the
    # floor removal admits sub-12 blobs, so retained/covered counts grow
    # and partition_k may step up; re-pin from an actual slow run (the
    # fast tier cannot run this test). The >= bounds are monotone-safe;
    # the == partition_k asserts may move.
    # re-pinned empirically on seed 1 at the 0033 §1 landing (2026-08-03):
    # the proximity blob stage + 12-cell floor admit the strip-shaped
    # ranges, so fungus.agaric retained 2477 (pk 4) → covered 1884
    # (pk 4) and runner_meadow.seagrass retained 2030 (4) → covered 515
    # (2) — agaric's COVERED partition_k rose 3 → 4 (its covered range
    # grew from 948 to 1884 cells with the admitted strips).
    assert partition_k(retained["fungus.agaric"]) == 4
    assert retained["fungus.agaric"] >= 2400
    assert partition_k(retained["runner_meadow.seagrass"]) == 4
    assert retained["runner_meadow.seagrass"] >= 1900
    assert partition_k(minted["fungus.agaric"]) == 4
    assert minted["fungus.agaric"] >= 1800
    assert partition_k(minted["runner_meadow.seagrass"]) == 2
    assert 100 <= minted["runner_meadow.seagrass"] <= 1000
    assert k_gt1, "expected at least one preset with partition_k > 1 on seed 1"


@pytest.mark.slow
def test_genesis_determinism(world, pack_sim, capacity):
    """Two full genesis runs on seed 1: byte-identical masks and N
    fields (spec §2 determinism hard rule — hashrng streams only;
    the coverage draws are pinned child streams, so they are
    byte-identical too)."""
    pack, sim = pack_sim
    a = genesis_rain(pack, sim, world, capacity, seed=1)
    b = genesis_rain(pack, sim, world, capacity, seed=1)
    assert list(a) == list(b)
    for pid, clones_a in a.items():
        clones_b = b[pid]
        assert len(clones_a) == len(clones_b)
        for ca, cb in zip(clones_a, clones_b):
            assert ca.cells.dtype == cb.cells.dtype == bool
            assert ca.N.dtype == cb.N.dtype == np.float32
            assert ca.cells.tobytes() == cb.cells.tobytes()
            assert ca.N.tobytes() == cb.N.tobytes()


@pytest.mark.slow
def test_genesis_species_sparse_founders(pack_sim, world, k15_world):
    """Ticket 0020 (DESIGN PIVOT) done-means on seed 1 through the
    ENGINE (the species rain — sparse founders + partial coverage, NO
    density budget): every species with a mintable blob mints (the
    coverage draw's largest-blob retry means the draw never causes
    extinction — no occupancy lockout), each DESCENT-MINTED instance
    stays ≥ DESCENT_MIN_BLOB_CELLS // 2 cells (no speckle; the descent
    can shrink parents below the original mint floor; genesis-minted
    clones are UNBOUNDED BELOW since the ticket-0039 floor removal),
    the per-lineage
    partition is disjoint, and the realized coverage (minted/viable
    cells per species, median) is a proper fraction of the viable
    range — unseeded habitat stays empty for §7 colonization. The
    utilization u = D/K_L is REPORTED, not asserted: sparse founders
    deliberately leave density competition to the rounds (measured u
    p50 1.22 / frac u>1 0.58 at F0=0.1 — the old done-means u targets
    are unreachable without a density gate; see the v1.1 changelog).
    v1.3 re-pin (ticket 0018, pre-genesis descent): the no-speckle
    floor moves from the GENESIS_MIN_CELLS mint floor to
    DESCENT_MIN_BLOB_CELLS // 2 — the descent legitimately mints
    fringe instances at the 8-cell blob floor AND shrinks parents
    below the original mint floor when a marginal blob breaks off (a
    broken-off fringe is not speckle). v1.7 (ticket 0039, owner ruling
    2026-08-04): the genesis mint floor is REMOVED ENTIRELY — the
    ORIGINAL clone seeding is now unbounded below, so the no-speckle
    bound below is scoped to DESCENT-minted instances only
    (``_g_since_split > 0``). A true
    speckle instance (1-3 cells) still trips the bound for descent
    fragments (realized post-descent minimum on seed 1: 7). v1.4 re-pin (2026-08-03,
    ticket 0012 Task D slow tier): the curated census surfaced a
    1-cell seeded-part fragment (sid 382a2efdb06ea061 — a harsh blob
    whose seeded part was a single cell slipped past the
    ``seeded.any()`` check and minted a 1-cell adapted instance at
    birth_g 159.67). The engine now skips any break-off whose seeded
    part is below DESCENT_MIN_BLOB_CELLS // 2 (the ``skipped_speckle``
    counter: the seeded part of a broken-off blob must itself clear
    the speckle floor). RE-MEASURED realized post-descent minimum
    instance size on seed 1 after the fix: 8 cells. v1.5 (ticket 0033
    §1): the proximity blob stage admits the strip-habitat lineages —
    lineage survival re-measured at the 0033 landing: 101/123 seeded
    (pre-0033 the un-pruned 150-species tree seeded 102). v1.7
    (ticket 0039): the 12-cell floor is REMOVED — sub-12 ranges now
    mint, so survival only grows from 101 (re-measured by the 0039
    probe). v1.6 (ticket 0037): the coverage keep probability is
    TIERED by the pre-coverage retained count (R < 200 no draw,
    200-400 ramped, > 400 flat GENESIS_COVER) and the per-cell total
    demand cap (GENESIS_S = 0.5, proportional squeeze, floor-clamped
    cells kept at N_FLOOR) runs at the end of the mint — the u anatomy
    printed below is the POST-cap anatomy (re-measured at landing:
    u p50 0.955 / frac u>1 0.477 / stacking mean 5.04 / median coverage
    0.404 vs the v1.1 baseline 1.22 / 0.58 / 5.31 / 0.29;
    tmp/0037_probe.py) and stays REPORTED, not asserted — u_i =
    D/K_Li may exceed 1 for a low-U lineage under the cap (u_i ≤ S/U_i,
    the correct crowding signal; the bound is the cell total ΣD ≤ K·S)."""
    from exp.k15_simdiff.engine import Engine

    eng = Engine(1, pack=pack_sim[0], ctx=k15_world)
    eng.genesis()
    H, W = eng.ctx.H, eng.ctx.W
    live = [d for d in eng.instances.values() if d.mass > 0.0]
    assert live, "genesis minted nothing"
    D = np.zeros((H, W), dtype=np.float64)
    for d in live:
        D[d.world_slice()] += d.N * d.percap
    u_all: list[np.ndarray] = []
    minted_cells: dict[str, int] = {}
    by_lineage: dict[str, list[np.ndarray]] = {}
    for d in live:
        ws = d.world_slice()
        occ = d.cells
        # ticket 0039: the no-speckle bound applies to DESCENT-minted
        # instances only (they carry their earned g in _g_since_split);
        # genesis-minted clones are unbounded below by design (the
        # mint floor is gone)
        if eng._g_since_split[d.x.instance_id] > 0.0:
            assert int(occ.sum()) >= DESCENT_MIN_BLOB_CELLS // 2, \
                f"speckle clone of {d.x.species_id}: {int(occ.sum())} cells"
        minted_cells[d.x.species_id] = \
            minted_cells.get(d.x.species_id, 0) + int(occ.sum())
        K_L = pop.lineage_capacity(eng.K[ws], d.cache.U[ws])
        with np.errstate(divide="ignore", invalid="ignore"):
            u = np.where(K_L > pop.K_EPS,
                         D[ws] / np.maximum(K_L, pop.K_EPS), np.inf)
        u_all.append(u[occ])
        y0, y1, x0, x1 = d.box
        full = np.zeros((H, W), dtype=bool)
        full[y0:y1, x0:x1] = occ
        by_lineage.setdefault(d.x.species_id, []).append(full)
    u_all = np.concatenate(u_all)
    assert len(by_lineage) >= 100, \
        f"lineage survival {len(by_lineage)} < 100 (occupancy lockout?)"
    # per-lineage partition disjoint: union of a lineage's clones == sum
    for sid, masks in by_lineage.items():
        union = np.logical_or.reduce(masks)
        assert int(union.sum()) == sum(int(m.sum()) for m in masks), \
            f"overlapping clones within lineage {sid}"
    # realized coverage: minted/viable per species, median (report —
    # partial coverage is by design; the median is a proper fraction)
    tree = build_backbone(1, pack_sim[0])
    cov: list[float] = []
    for node in sorted((n for n in tree.nodes.values()
                        if n.rank is Rank.SPECIES), key=lambda n: n.sid):
        view = sa.species_view(node, pack_sim[0])
        factors = sa.evaluate(view, world)
        _n, _m, Fw, _p = reduced(factors)
        viable = int(((Fw >= GENESIS_F) & valid_mask(view, world)).sum())
        if viable > 0 and node.sid in minted_cells:
            cov.append(minted_cells[node.sid] / viable)
    cov = np.asarray(cov)
    assert 0.05 <= np.quantile(cov, 0.5) <= 0.95, \
        f"median coverage {np.quantile(cov, 0.5):.3f} outside (0.05, 0.95)"
    print(f"\nticket 0020 pivot anatomy: {len(live)} instances, "
          f"{len(by_lineage)} lineages, {u_all.size} pairs, "
          f"u p50={np.quantile(u_all, 0.5):.3f}, "
          f"frac u>1={(u_all > 1.0).mean():.3f}, "
          f"max u={u_all.max():.1f}, "
          f"median coverage={np.quantile(cov, 0.5):.3f}")
