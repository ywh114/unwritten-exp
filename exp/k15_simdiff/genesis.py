"""K15 engine — spec §10 genesis rain (round 0).

Seeds every authored flora preset at N = GENESIS_N0 where the worst-
month suitability F_worst ≥ GENESIS_F, then partitions each preset's
seeded range into K = partition_k(range) contiguous clones by recursive
rng-chosen axis cuts — the headstart speciation (clones are sibling
lineages from round 0, merge-exempt for MERGE_GRACE rounds, free to
diverge independently).

Determinism (hard rule): every draw comes from kernel.hashrng —
``Stream(seed, "k15.genesis", preset_id)`` (spec §10), with child
streams per connected component in a pinned order (sorted by top-left
cell, row-major). Same seed → byte-identical masks and N fields.

Reduction and the medium mask are lifted from the stat-pass harness
(formulas, not the module — statpass.py is a calibration harness and is
never imported here): ``reduced`` is statpass.reduced verbatim, the
medium mask the statpass.valid_mask rule. For freshwater plans the
habitat term is part of the factor product, so it is automatically
inside F_worst — no special casing (spec §10 step 2).

Instance IDs are NOT minted here: a CloneSeed is plain spatial state
(cells mask + N field); the engine/authority mints instance ids and
dresses the clone when it becomes an Instance.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from exp.k15_simdiff import stress_adapter as sa
from kernel.hashrng import Stream

K14_OUT = Path(__file__).resolve().parent.parent / "k14_worldprod" / "out"

# ── spec §13 knobs (v0.3, settled values) ──────────────────────────────
GENESIS_F = 0.5         # settled 2026-08-01 (stat pass seeds 1-3)
GENESIS_N0 = 0.2        # founder density at seeded cells
PART_AREA_REF = 200     # partition: reference range area (cells)
PART_K_MAX = 8          # partition: clone-count cap per preset
PART_MIN_CELLS = 20     # partition: components below this stay single
# freshwater habitat mask floor for the medium mask (stat-pass value)
FRESH_MASK_MIN = 0.01

# re-draw cap per axis cut before a fragmented cut is accepted (the cut
# is rejected only when it fragments a half into > 1 piece — see _cut)
_CUT_REJECT_MAX = 32


@dataclass(frozen=True)
class CloneSeed:
    """One genesis clone: the contiguous range and its density field.

    ``cells``: (H,W) bool — the clone's 8-connected seeded range.
    ``N``:     (H,W) float32 — GENESIS_N0 on the cells, 0 elsewhere.

    Instance IDs are NOT minted here — the engine/authority mints them
    and dresses the clone (vital rates, cached stress fields) when it
    becomes an Instance (spec §3/§9)."""

    cells: np.ndarray
    N: np.ndarray


# ── world capacity (test/driver loader; the engine re-derives exactly) ─


def load_capacity(seed: int, ctx: sa.WorldContext) -> np.ndarray:
    """K(c) at anchor from the K14 annual productivity products,
    mean-pooled 1024 → 256 (calibration-grade; the same anchor the
    stat-pass uses — the engine will re-derive exactly, spec §5.0).
    Land reads terrestrial, ocean marine, lakes/rivers freshwater.
    Pure function of (seed, world); deterministic."""
    with np.load(K14_OUT / f"seed_{seed:08d}" / "derived.npz") as d:
        def pool(key):
            a = np.nan_to_num(d[key].astype(np.float64))
            return a.reshape(ctx.H, 4, ctx.W, 4).mean(axis=(1, 3))
        terr, marine, fresh = (pool("terrestrial_productivity"),
                               pool("marine_productivity_ann"),
                               pool("freshwater_productivity_ann"))
    ocean = ctx.water_cell & (ctx.bathy > 0)
    lake = ctx.water_cell & ~ocean
    K = np.where(ctx.land_cell, terr, np.where(ocean, marine, fresh))
    return np.nan_to_num(K).astype(np.float32)


# ── §5.1 reduction + medium mask (lifted from the stat-pass harness) ──


def reduced(factors: dict[str, np.ndarray]):
    """Worst-month reduction (spec §5.1): m*(c), F_worst(c), and
    per-requirement provenance at m*(c) — one aggregation for both
    selection and demography. Same formula as the stat-pass harness
    (statpass.reduced); lifted here because statpass is a calibration
    harness and must not be imported by the engine."""
    F = factors["F"]
    m_star = F.argmin(axis=0)                                   # (H,W)
    F_worst = np.take_along_axis(F, m_star[None], axis=0)[0]
    names = [k for k in factors if k not in ("F", "s_env",
                                             "substrate_share")]
    prov = np.stack([
        np.take_along_axis(factors[r], m_star[None], axis=0)[0]
        for r in names
    ])                                                          # (R,H,W)
    return names, m_star, F_worst, prov


def valid_mask(view: dict, ctx: sa.WorldContext) -> np.ndarray:
    """Cells where the plan's medium is possible (used to intersect the
    seeded range; the F product already carries the medium/habitat
    factors — for freshwater plans the habitat term replaces the medium
    boundary, so the mask is just the freshwater-availability floor)."""
    medium = view.get("medium", "land")
    if medium == "dual":
        return np.ones((ctx.H, ctx.W), dtype=bool)
    if medium == "water":
        sal = view.get("salinity_tolerance")
        freshwater = isinstance(sal, (int, float)) \
            and sal < sa.FRESH_SAL_MAX
        if freshwater:
            return ctx.fresh_availability.mean(axis=0) > FRESH_MASK_MIN
        return ctx.water_cell
    return ctx.land_cell


# ── spec §10 step 3: the initial partition (headstart speciation) ──────


def partition_k(range_cells: int) -> int:
    """Spec §10 verbatim: K = clip(1 + floor(log2(range / REF)), 1, 8).
    A preset with no range gets 0 clones."""
    if range_cells <= 0:
        return 0
    return int(min(PART_K_MAX,
                   max(1, 1 + math.floor(
                       math.log2(range_cells / PART_AREA_REF)))))


def connected_components(mask: np.ndarray) -> list[np.ndarray]:
    """8-connectivity connected components of a bool (H,W) mask, each
    returned as a (H,W) bool mask. Deterministic: emitted in sorted
    top-left (row-major) order of each component's first cell. Row-run
    extraction + union-find over runs — no scipy dependency.

    (Also the primitive the engine's §8 dressing reuses: per-instance
    components over the instance's own N > 0 cells.)"""
    mask = np.asarray(mask, dtype=bool)
    H, W = mask.shape
    runs: list[tuple[int, int, int]] = []      # (row, c0, c1) inclusive
    by_row: list[list[int]] = []               # row -> run ids
    for r in range(H):
        row = mask[r]
        if not row.any():
            by_row.append([])
            continue
        d = np.diff(row.astype(np.int8))
        starts = np.flatnonzero(d == 1) + 1
        ends = np.flatnonzero(d == -1)
        if row[0]:
            starts = np.concatenate(([0], starts))
        if row[-1]:
            ends = np.concatenate((ends, [W - 1]))
        ids = list(range(len(runs), len(runs) + len(starts)))
        for s, e in zip(starts, ends):
            runs.append((r, int(s), int(e)))
        by_row.append(ids)

    parent = list(range(len(runs)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    # 8-connectivity across adjacent rows: a run in row r links to runs
    # in row r+1 whose column interval intersects [c0-1, c1+1].
    for r in range(H - 1):
        if not by_row[r] or not by_row[r + 1]:
            continue
        next_runs = np.array([(runs[j][1], runs[j][2])
                              for j in by_row[r + 1]])
        starts_n = next_runs[:, 0]
        for j in by_row[r]:
            _r, c0, c1 = runs[j]
            lo, hi = c0 - 1, c1 + 1
            k = int(np.searchsorted(starts_n, lo, side="left"))
            while k < len(starts_n) and starts_n[k] <= hi:
                union(j, by_row[r + 1][k])
                k += 1

    comp_id: dict[int, int] = {}
    label = np.full((H, W), -1, dtype=np.int32)   # -1 = not in any run
    for i, (r, c0, c1) in enumerate(runs):
        root = find(i)
        if root not in comp_id:
            comp_id[root] = len(comp_id)       # first occurrence order
        label[r, c0:c1 + 1] = comp_id[root]
    return [label == k for k in range(len(comp_id))]


def _cut(chunk: np.ndarray, rng: Stream, cut: int) -> list[np.ndarray] | None:
    """One rng axis cut of a contiguous chunk: draw (axis, position)
    from *rng*, split the chunk by the half-plane, and return the pieces
    — the connected components of the two halves, contiguous by
    construction (≥ 2 pieces). Cuts that fragment a half into more than
    one piece are re-drawn up to _CUT_REJECT_MAX times, so the common
    result is exactly two pieces. Draw addressing (pinned): per cut
    number *cut*, attempt a draws (axis, position) from (clock=cut,
    index=2a) and (clock=cut, index=2a+1); the position is drawn at the
    same index whether the drawn axis was valid or fell back. A chunk
    with < 2 cells is unsplittable → None."""
    cells = np.argwhere(chunk)
    if len(cells) < 2:
        return None
    min_r, min_c = cells.min(axis=0)
    max_r, max_c = cells.max(axis=0)
    n_row, n_col = int(max_r - min_r), int(max_c - min_c)
    rows, cols = np.indices(chunk.shape)
    for a in range(_CUT_REJECT_MAX + 1):
        axis = rng.randrange(2, cut, 2 * a)
        if (axis == 0 and n_row == 0) or (axis == 1 and n_col == 0):
            axis = 1 - axis
        if axis == 0:
            pos = min_r + rng.randrange(n_row, cut, 2 * a + 1)
            lo = chunk & (rows <= pos)
            hi = chunk & (rows > pos)
        else:
            pos = min_c + rng.randrange(n_col, cut, 2 * a + 1)
            lo = chunk & (cols <= pos)
            hi = chunk & (cols > pos)
        pieces = connected_components(lo) + connected_components(hi)
        if len(pieces) == 2 or a == _CUT_REJECT_MAX:
            return pieces
    return None                                # unreachable


def _partition(seeded: np.ndarray, K: int, rng: Stream) -> list[np.ndarray]:
    """Spec §10 step 3: partition the seeded range into K clones TOTAL.

    Connected components (8-connectivity) of the range; components
    below PART_MIN_CELLS stay one clone each (never split); components
    ≥ PART_MIN_CELLS are split by recursive rng-chosen axis cuts until
    the preset's K is reached. Output chunks are contiguous, pairwise
    disjoint, and their union is the seeded range.

    Draws: child streams of *rng* per INITIAL component, in pinned
    order (sorted by top-left cell — connected_components' emission
    order); within a component the recursion cuts its largest piece
    first, ties by pinned order (lower component id, then earlier
    split). Component i draws from ``rng.child("comp:{i}")``.

    Count semantics: exactly K clones when K > component count (every
    cut adds one clone; a fragmented cut past the re-draw cap can add
    more — documented rarity); when K ≤ component count the one-clone-
    per-component floor wins and the count exceeds K."""
    comps = connected_components(seeded)
    if not comps:
        return []
    if K <= len(comps):
        return comps
    streams = [rng.child(f"comp:{i}") for i in range(len(comps))]
    # pieces: (chunk, component_id, splittable_flag) — the flag is
    # False for initial components below PART_MIN_CELLS, True forever
    # for pieces of big components (the floor governs initial
    # components only; the recursion splits down to single cells).
    pieces: list[tuple[np.ndarray, int, bool]] = [
        (c, i, c.sum() >= PART_MIN_CELLS) for i, c in enumerate(comps)]
    cut = 0
    while len(pieces) < K:
        best = None
        for i, (chunk, cid, can) in enumerate(pieces):
            if not can or chunk.sum() < 2:
                continue
            if best is None or chunk.sum() > best[1].sum():
                best = (i, chunk, cid)
        if best is None:
            break
        i, chunk, cid = best
        pieces2 = _cut(chunk, streams[cid], cut)
        cut += 1
        if pieces2 is None:
            break
        pieces[i:i + 1] = [(p, cid, True) for p in pieces2]
    return [chunk for chunk, _cid, _can in pieces]


def _n_field(cells: np.ndarray) -> np.ndarray:
    """The clone's density field: GENESIS_N0 on the cells, 0 elsewhere."""
    N = np.zeros(cells.shape, dtype=np.float32)
    N[cells] = np.float32(GENESIS_N0)
    return N


# ── the genesis rain ───────────────────────────────────────────────────


def genesis_preset(pack, sim, ctx: sa.WorldContext, seed: int,
                   preset_id: str) -> tuple[CloneSeed, ...]:
    """Spec §10 for ONE authored preset: evaluate its DerivedView over
    the world, seed cells with F_worst ≥ GENESIS_F at N = GENESIS_N0
    (the full factor product — for freshwater plans that includes the
    habitat term, B5 §4.5), then partition the seeded range into
    K = partition_k(range) clones. A preset with no seeded cells → ().

    *sim* is unused here (reserved: the engine dresses the clones with
    vital rates when minting instances). Draws from
    ``Stream(seed, "k15.genesis", preset_id)`` — deterministic."""
    view = sa.preset_view(preset_id, pack)
    factors = sa.evaluate(view, ctx)
    _names, _m_star, F_worst, _prov = reduced(factors)
    del factors
    valid = valid_mask(view, ctx)
    seeded = (F_worst >= GENESIS_F) & valid
    K = partition_k(int(seeded.sum()))
    if K == 0:
        return ()
    rng = Stream(seed, "k15.genesis", preset_id)
    chunks = _partition(seeded, K, rng)
    return tuple(CloneSeed(cells=ch, N=_n_field(ch)) for ch in chunks)


def genesis_rain(pack, sim, ctx: sa.WorldContext, K, seed: int,
                 ) -> dict[str, tuple[CloneSeed, ...]]:
    """Spec §10 for every authored preset, processed in sorted id order
    (determinism: presets, components, cuts all pinned). Returns
    {preset_id: clones}; a preset with no F_worst ≥ GENESIS_F range maps
    to (). Clones are (cells mask, N field) — see CloneSeed.

    *K* (the anchor capacity raster) and *sim* are reserved for the
    engine's dressing step and not read here. Same seed → byte-identical
    masks and N fields."""
    return {pid: genesis_preset(pack, sim, ctx, seed, pid)
            for pid in sorted(pack.presets)}
