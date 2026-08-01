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
    GENESIS_F,
    GENESIS_F0,
    GENESIS_MIN_CELLS,
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
    pre-floor components → mint floor (ticket 0009) → per-component
    keep/drop draws (``rng.child(f"cover:{i}")``, pinned emission
    order, keep probability GENESIS_COVER) with the largest-component
    retry (the coverage draw never causes extinction). Returns
    (covered mask, pre-coverage retained cell count)."""
    rng = Stream(seed, "k15.genesis", key)
    big = [c for c in connected_components(seeded)
           if int(c.sum()) >= GENESIS_MIN_CELLS]
    if not big:
        return None, 0
    n_ret = int(sum(int(c.sum()) for c in big))
    sel = [c for i, c in enumerate(big)
           if rng.child(f"cover:{i}").bernoulli(GENESIS_COVER, 0)]
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
    v0.9 re-pin (ticket 0009, the genesis mint floor): seeded
    components below GENESIS_MIN_CELLS are DROPPED — a preset whose
    every component is sub-floor yields () (never minted), and the
    partition's K targets the RETAINED range. v1.1 re-pin (ticket
    0020, DESIGN PIVOT): per-component coverage draws
    (``_expected_retained``) keep ~GENESIS_COVER of the retained blobs
    (whole blobs, never speckle), and the partition's K targets the
    COVERED range — the clone union equals the covered mask, not the
    full retained range. Re-pinned on seed 1 (2026-08-01): yarrow
    retained 3267 cells (partition_k 5) → covered 2736 (partition_k
    4, 7 clones); seagrass retained 1722 (4) → covered 466 (2, 6
    clones)."""
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
            # every component below the floor — dropped entirely
            # (ticket 0009 option (a); §7 dispersal re-finds the cells)
            assert clones == ()
            continue
        minted[pid] = int(covered.sum())
        K = partition_k(int(covered.sum()))
        if K > 1:
            k_gt1.append(pid)
        # count: K clones TOTAL over the covered components, unless the
        # one-clone-per-component floor wins — K ≤ component count keeps
        # one clone per covered component (spec §10; every covered
        # component is ≥ GENESIS_MIN_CELLS ≥ PART_MIN_CELLS, so all may
        # split — the synthetic tests cover the count == K path).
        assert len(clones) == max(K, len(connected_components(covered)))
        cells = [c.cells for c in clones]
        assert np.array_equal(np.logical_or.reduce(cells), covered)
        assert sum(int(c.sum()) for c in cells) == int(covered.sum())
        for clone in clones:
            assert clone.cells.shape == seeded.shape
            assert len(connected_components(clone.cells)) == 1
            _check_clone_field(clone, seeded, D, percap)
    # re-pinned empirically on seed 1 (2026-08-01): the PRE-coverage
    # retained ranges (3267 yarrow / 1722 seagrass ≥ floor — unchanged
    # by coverage, they were pinned in v0.9) and the COVERED ranges the
    # partition actually targets (2736 / 466 cells — ticket 0020).
    assert partition_k(retained["herb_forb.yarrow"]) == 5
    assert retained["herb_forb.yarrow"] >= 3200
    assert partition_k(retained["runner_meadow.seagrass"]) == 4
    assert retained["runner_meadow.seagrass"] >= 1600
    assert partition_k(minted["herb_forb.yarrow"]) == 4
    assert minted["herb_forb.yarrow"] >= 2000
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
def test_genesis_species_sparse_founders(pack_sim, world):
    """Ticket 0020 (DESIGN PIVOT) done-means on seed 1 through the
    ENGINE (the species rain — sparse founders + partial coverage, NO
    density budget): every species with a mintable blob mints (the
    coverage draw's largest-component retry means the draw never causes
    extinction — no occupancy lockout), each minted clone stays ≥
    GENESIS_MIN_CELLS (no speckle), the per-lineage partition is
    disjoint, and the realized coverage (minted/viable cells per
    species, median) is a proper fraction of the viable range —
    unseeded habitat stays empty for §7 colonization. The utilization
    u = D/K_L is REPORTED, not asserted: sparse founders deliberately
    leave density competition to the rounds (measured u p50 1.22 /
    frac u>1 0.58 at F0=0.1 — the old done-means u targets are
    unreachable without a density gate; see the v1.1 changelog)."""
    from exp.k15_simdiff.engine import Engine

    eng = Engine(1, pack=pack_sim[0])
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
        assert int(occ.sum()) >= GENESIS_MIN_CELLS, \
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
