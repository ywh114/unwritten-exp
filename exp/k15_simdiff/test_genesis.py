"""K15 engine — spec §10 genesis rain tests.

Fast pure-partition tests run by default. The world-dependent tests run
on seed 1 (stress_adapter.load_world(1) + the stat-pass capacity anchor,
lifted as genesis.load_capacity) — 35 adapter evaluations per genesis
call, so they are marked ``slow`` per the repo convention (pyproject:
``pytest -m slow``).

Run all: PYTHONPATH=. uv run pytest -q exp/k15_simdiff/test_genesis.py
Run fast: PYTHONPATH=. uv run pytest -q -m "not slow" ...
Run slow: PYTHONPATH=. uv run pytest -q -m slow exp/k15_simdiff/test_genesis.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from exp.k13_treegen.flora.content import load_content
from exp.k13_treegen.flora.sim import FloraSim
from exp.k15_simdiff import stress_adapter as sa
from exp.k15_simdiff.genesis import (
    GENESIS_F,
    GENESIS_N0,
    CloneSeed,
    _partition,
    connected_components,
    genesis_rain,
    load_capacity,
    partition_k,
    reduced,
    valid_mask,
)
from kernel.hashrng import Stream

FLORA_CONTENT = Path("exp/k13_treegen/content/flora")


# ── world fixtures (only built when a slow test runs) ──────────────────


@pytest.fixture(scope="session")
def pack_sim():
    pack = load_content(FLORA_CONTENT)
    return pack, FloraSim(pack)


@pytest.fixture(scope="session")
def world():
    return sa.load_world(1)


@pytest.fixture(scope="session")
def capacity(world):
    return load_capacity(1, world)


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


def _check_clone_field(clone: CloneSeed, seeded: np.ndarray) -> None:
    """N = GENESIS_N0 exactly on the clone's cells, 0 elsewhere."""
    assert clone.cells.dtype == bool
    assert clone.N.dtype == np.float32
    assert (clone.N[clone.cells] == np.float32(GENESIS_N0)).all()
    assert not clone.N[~clone.cells].any()


@pytest.mark.slow
def test_genesis_partition_structure(world, pack_sim, capacity):
    """Every preset: clone count, contiguity, disjointness, union and N
    fields against an independent recomputation of the seeded range."""
    pack, sim = pack_sim
    rain = genesis_rain(pack, sim, world, capacity, seed=1)
    assert set(rain) == set(pack.presets)
    ranges: dict[str, int] = {}
    k_gt1: list[str] = []
    for pid in sorted(pack.presets):
        seeded = _seeded_range(pack, world, pid)
        n_range = int(seeded.sum())
        ranges[pid] = n_range
        K = partition_k(n_range)
        if K > 1:
            k_gt1.append(pid)
        clones = rain[pid]
        if K == 0:
            assert clones == ()
            continue
        # count: K clones TOTAL, unless the one-clone-per-component
        # floor wins — components below PART_MIN_CELLS never split, so
        # when the component count already meets/exceeds K every
        # component stays one clone (spec §10; seed 1's ranges are
        # fragmented enough that the floor dominates — the synthetic
        # tests above cover the count == K path).
        n_comps = len(connected_components(seeded))
        assert len(clones) == max(K, n_comps)
        cells = [c.cells for c in clones]
        assert np.array_equal(np.logical_or.reduce(cells), seeded)
        assert sum(int(c.sum()) for c in cells) == n_range
        for clone in clones:
            assert clone.cells.shape == seeded.shape
            assert len(connected_components(clone.cells)) == 1
            _check_clone_field(clone, seeded)
    # pinned empirically on seed 1 (2026-08-01, re-pinned after the
    # derived-climate breadth widening + B6 re-authors moved the
    # landscape — T0001, biosphere-addendum-b6-flora-wiring.md §4:
    # every preset now seeds >= 50 cells; yarrow and seagrass carry the
    # large ranges): two presets whose range exceeds PART_AREA_REF, per
    # the task's suggestion
    assert partition_k(ranges["herb_forb.yarrow"]) == 5
    assert ranges["herb_forb.yarrow"] >= 3000
    assert partition_k(ranges["runner_meadow.seagrass"]) == 4
    assert ranges["runner_meadow.seagrass"] >= 2000
    assert k_gt1, "expected at least one preset with partition_k > 1 on seed 1"


@pytest.mark.slow
def test_genesis_determinism(world, pack_sim, capacity):
    """Two full genesis runs on seed 1: byte-identical masks and N
    fields (spec §2 determinism hard rule — hashrng streams only)."""
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
