"""K15 engine — spec §10 genesis rain (round 0).

Seeds SPARSE founders at a capacity-relative demand D = GENESIS_F0 ·
K_L(c, L) wherever the worst-month suitability F_worst ≥ GENESIS_F
(the full factor product — for freshwater plans that includes the
habitat term, B5 §4.5). K_L is the §6 v0.3 capacity split (K_L = K x
U, reused from population.lineage_capacity — never duplicated), so a
lineage alone on a cell is born at utilization u = D/K_L = GENESIS_F0.
Founder abundance is N = D/percap, floored at N_FLOOR (a species
whose per-capita demand is so large that F0·K_L would seed below the
extinction floor is clamped to it — nothing mints below the §6 floor).
The old flat GENESIS_N0 = 0.2 founder density ignored per-cell
capacity and measured u p50 ≈ 14 (9.13 stacked lineages per populated
cell).

Ticket 0020 (DESIGN PIVOT, owner 2026-08-01): SPARSE founders,
PARTIAL range coverage, NO cross-lineage budget. The first
implementation (a world-level density budget with streaming admission,
an erosion sweep and relocation) met its done-means but at an
unrealistic cost: viable cells were claimed first-come-first-served in
sorted sid order, so ~2 lineages filled a cell and late-sid species
found their niche "already occupied" — occupancy decided by name hash,
not fitness. Owner rulings: (1) genesis seeds sparse founders and lets
competition happen inside the sim (where it can become niche/fitness-
aware), not at mint; (2) there is NO need to seed full viable ranges —
partial coverage leaves unseeded habitat for §7 colonization. So the
rain now seeds the whole viable range at the SMALL F0 (utilization
u ≈ F0 · n_stack stays under the density cap even with heavy
stacking) and then draws a per-component KEEP/DROP from the pinned
genesis stream (whole blobs — never speckled cells) with keep
probability GENESIS_COVER; a species whose every drawn component is
dropped keeps its single largest component unconditionally, so the
coverage draw can never cause extinction (only the ticket-0004/0009
paths do: zero range and all-sub-floor ranges).

Blobs below GENESIS_MIN_CELLS are dropped (ticket 0009: the genesis
mint floor — no speckle instances). Each retained range is partitioned
into K = partition_k(range) contiguous clones by recursive rng-chosen
axis cuts — the headstart speciation (clones are sibling lineages from
round 0, merge-exempt for MERGE_GRACE rounds, free to diverge
independently).

Two entry points share one seed+partition core (``_rain_for_view``):
``genesis_preset`` (an AUTHORED preset's record view — the pre-ticket-
0004 unit, still the tests' partition ground truth; single-lineage)
and ``genesis_rain_species`` (the radiated SPECIES nodes in ONE batch,
engine's pinned sorted sid order — the engine's round-0 seeding since
ticket 0004: the world is "completely written at L0", so the 35 ORDER
nodes are ancestors, never seeded). ``genesis_rain_species`` also
returns the compact §5.1 reduced bundle (names, F_worst, prov, U) per
species so the engine builds its cache from the SAME evaluation — one
adapter evaluation per species at genesis, not two.

Determinism (hard rule): every draw comes from kernel.hashrng —
``Stream(seed, "k15.genesis", key)`` where key is the preset id or the
species sid (spec §10), with child streams per connected component in a
pinned order (sorted by top-left cell, row-major): component i draws
``rng.child("cover:{i}")`` for the coverage keep/drop and the
partition's ``rng.child("comp:{i}")`` — both content-addressed, so the
draw order never matters. Same seed → byte-identical masks and N
fields.

Reduction and the medium mask are lifted from the stat-pass harness
(formulas, not the module — statpass.py is a calibration harness and is
never imported here): ``reduced`` is statpass.reduced verbatim, the
medium mask the statpass.valid_mask rule. For freshwater plans the
habitat term is part of the factor product, so it is automatically
inside F_worst — no special casing (spec §10 step 2).

Instance IDs are NOT minted here: a CloneSeed is plain spatial state
(cells mask + N field); the engine/authority mints instance ids and
dresses the clone when it becomes an Instance. A species (or preset)
with no seeded cells gets () — the caller's extinction path (ticket
0004: zero-range species are never minted and go extinct at genesis).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from exp.k15_simdiff import population as pop
from exp.k15_simdiff import stress_adapter as sa
from kernel.hashrng import Stream

K14_OUT = Path(__file__).resolve().parent.parent / "k14_worldprod" / "out"

# ── spec §13 knobs (v0.3, settled values) ──────────────────────────────
GENESIS_F = 0.5         # settled 2026-08-01 (stat pass seeds 1-3)
# ticket 0020 (DESIGN PIVOT): the per-(cell,lineage) founder demand as
# a fraction of the lineage's own carrying capacity K_L = K x U. SMALL
# by design — sparse founders: u = F0 · n_stack stays under the density
# cap even with heavy stacking, so competition happens inside the sim,
# not at mint. Settled 0.1 on seed 1 (allowed 0.05-0.15; measured
# anatomy: u p50 1.22 / frac u>1 0.58 at 0.1 — the done-means u target
# is NOT reachable at any setting in the allowed range without a
# density gate, see the v1.1 changelog).
GENESIS_F0 = 0.1
# ticket 0020 (DESIGN PIVOT): partial range coverage — per connected
# component (post-mint-floor), an independent keep/drop draw from the
# pinned genesis stream (rng.child(f"cover:{i}")) with this keep
# probability. Whole blobs kept or dropped (never speckled cells);
# a species whose every drawn component is dropped keeps its single
# largest component unconditionally (the coverage draw never causes
# extinction). Settled 0.5 on seed 1 (realized coverage ~55% of the
# viable range by cells); unseeded viable cells stay empty for §7
# colonization.
GENESIS_COVER = 0.5
PART_AREA_REF = 200     # partition: reference range area (cells)
PART_K_MAX = 8          # partition: clone-count cap per preset
PART_MIN_CELLS = 20     # partition: components below this stay single
# genesis mint floor (ticket 0009): connected components of a seeded
# range below this are DROPPED at genesis — never minted as established
# instances (option (a): §7 dispersal can re-find those cells later).
# 32 = the existing DIFF_MIN_CELLS sliver-suppression scale; measured
# seed-1 anatomy (ticket 0009): 91% of 14,751 components are < 32 cells
# (median 3), so the floor cuts genesis to the ~9% fat blobs the owner's
# fat-blobs ruling wants (1-10 instances per lineage).
GENESIS_MIN_CELLS = 32
# ticket 0018 (spec §10.1): the eligibility gate — seed a cell only
# where K_L >= N_FLOOR * percap, i.e. where the N_FLOOR clamp does NOT
# bind (a clamp-bound cell is born at u = N_FLOOR·percap/K_L > 1 —
# guaranteed round-1 density death + stress noise, the measured u≈1e5
# freak-tail artifact). The descent is seeded-only, so gate-excluded
# clamp cells are never descent candidates — the gate IS the whole
# freak-tail handling (no substrate-fit lever exists; the v3 "lifted
# 0" was structural, not a tuning miss). One line, toggleable
# (False → the pre-0018 seeding; P_ADAPT=0 + gate off ⇒ genesis
# byte-identical to HEAD).
GENESIS_K_L_GATE = True
# freshwater habitat mask floor for the medium mask (stat-pass value)
FRESH_MASK_MIN = 0.01

# re-draw cap per axis cut before a fragmented cut is accepted (the cut
# is rejected only when it fragments a half into > 1 piece — see _cut)
_CUT_REJECT_MAX = 32


@dataclass(frozen=True)
class CloneSeed:
    """One genesis clone: the contiguous range and its density field.

    ``cells``: (H,W) bool — the clone's 8-connected seeded range.
    ``N``:     (H,W) float32 — the founder abundance field: N = D/percap
    with D = max(GENESIS_F0 · K_L(c), N_FLOOR · percap) on the cells,
    0 elsewhere (ticket 0020: capacity-relative sparse founders, never
    below the §6 extinction floor).

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


# ── ticket 0020: capacity-relative founder demand + partial coverage ──


def lineage_capacity(K: np.ndarray, U: np.ndarray) -> np.ndarray:
    """K_L(c) = PROD_CAP_SCALE · K(c) · U(c) — the per-lineage carrying
    capacity at every cell (spec §6 v0.3 capacity split). REUSED from
    population.lineage_capacity (never duplicated) — the genesis demand
    and the engine's density term must read the SAME capacity."""
    return pop.lineage_capacity(K, U)


def demand_field(K_L: np.ndarray, percap: float, f0: float = GENESIS_F0,
                 ) -> np.ndarray:
    """The per-(cell,lineage) founder demand D(c) = max(F0 · K_L(c),
    N_FLOOR · percap) — capacity-relative sparse founders, floored so
    no cell mints below the §6 extinction floor (a high-percap organism
    would otherwise seed at N < N_FLOOR and be abandoned at the first
    round). N = D / percap; D is the demand the engine's
    D(c) = Σ N·percap accumulates, so u = D/K_L is exact."""
    return np.maximum(f0 * np.asarray(K_L, dtype=np.float64),
                      pop.N_FLOOR * percap)


def _n_field(cells: np.ndarray, K_L: np.ndarray, percap: float,
             f0: float = GENESIS_F0) -> np.ndarray:
    """The clone's abundance field: N = D/percap with D = max(F0·K_L,
    N_FLOOR·percap) on the cells, 0 elsewhere (float32 — ticket 0020
    replaces the flat GENESIS_N0 founder density)."""
    D = demand_field(K_L, percap, f0)
    N = np.zeros(cells.shape, dtype=np.float32)
    N[cells] = np.float32(D[cells] / percap)
    return N


def _covered_components(comps: list[np.ndarray], rng: Stream,
                        cover: float = GENESIS_COVER) -> list[np.ndarray]:
    """Ticket 0020 partial coverage: per connected component (in the
    pinned emission order — connected_components' sorted top-left), an
    independent keep/drop draw from ``rng.child("cover:{i}")`` with keep
    probability *cover*. WHOLE blobs are kept or dropped (never
    speckled cells); a run where every draw drops is RETRIED by keeping
    the single largest component unconditionally (ties → first emission
    order), so the coverage draw can never wipe out a lineage that has
    a mintable blob. Deterministic: child streams are content-addressed
    by the component index."""
    if not comps:
        return []
    sel = [c for i, c in enumerate(comps)
           if rng.child(f"cover:{i}").bernoulli(cover, 0)]
    if not sel:
        sel = [max(comps, key=lambda c: int(c.sum()))]
    return sel


# ── the genesis rain (single-lineage core: preset/tests) ───────────────


def _rain_for_view(view: dict, ctx: sa.WorldContext, seed: int,
                   key: str, factors: dict, K: np.ndarray
                   ) -> tuple[tuple[CloneSeed, ...], int]:
    """Spec §10 steps 2-3 for an ALREADY-EVALUATED DerivedView *view*
    (factors = ``sa.evaluate`` output): seed the cells with F_worst ≥
    GENESIS_F at the capacity-relative founder demand D = GENESIS_F0 ·
    K_L(c, L) (ticket 0020; the full factor product — for freshwater
    plans that includes the habitat term, B5 §4.5), then partition the
    seeded range into K = partition_k(range) clones. Returns
    (clones, range_cells). No mintable cells -> ((), 0) — the caller's
    extinction path (ticket 0004). Ticket 0009: connected components of
    the seeded range below GENESIS_MIN_CELLS are DROPPED (never
    minted; §7 dispersal can re-find those cells), and the partition's
    K (spec §10 step 3) targets the RETAINED range — the range_cells
    returned is the minted extent. Ticket 0020: partial coverage — a
    per-component keep/drop draw (``_covered_components``) then keeps
    ~GENESIS_COVER of the retained blobs (whole blobs, never speckle),
    leaving the drawn-away viable cells unseeded for §7 colonization;
    a lineage whose every component is drawn away keeps its largest
    blob, so the draw never causes extinction. Draws from
    ``Stream(seed, "k15.genesis", key)`` (key = preset id or species
    sid — content-addressed, so draw order never matters)."""
    _names, _m_star, F_worst, _prov = reduced(factors)
    valid = valid_mask(view, ctx)
    seeded = (F_worst >= GENESIS_F) & valid
    kept = [c for c in connected_components(seeded)
            if int(c.sum()) >= GENESIS_MIN_CELLS]
    if not kept:
        return (), 0
    rng = Stream(seed, "k15.genesis", key)
    kept = _covered_components(kept, rng)
    retained = np.logical_or.reduce(kept)
    range_cells = int(retained.sum())
    K_n = partition_k(range_cells)
    if K_n == 0:
        return (), 0
    U = factors["substrate_share"]
    K_L = lineage_capacity(K, U)
    percap = pop.percap_demand(view)
    chunks = _partition(retained, K_n, rng)
    return tuple(CloneSeed(cells=ch, N=_n_field(ch, K_L, percap))
                 for ch in chunks), range_cells


def genesis_preset(pack, sim, ctx: sa.WorldContext, seed: int,
                   preset_id: str, K: np.ndarray) -> tuple[CloneSeed, ...]:
    """Spec §10 for ONE authored preset: evaluate its DerivedView over
    the world, seed + partition (shared core ``_rain_for_view``). A
    preset with no seeded cells → (). (Pre-ticket-0004 seeding unit;
    the engine now seeds radiated SPECIES nodes via genesis_rain_species
    — the preset-level form remains the tests' partition ground truth.)

    *sim* is unused here (reserved: the engine dresses the clones with
    vital rates when minting instances). Draws from
    ``Stream(seed, "k15.genesis", preset_id)`` — deterministic."""
    view = sa.preset_view(preset_id, pack)
    factors = sa.evaluate(view, ctx)
    clones, _range = _rain_for_view(view, ctx, seed, preset_id, factors, K)
    return clones


def genesis_rain(pack, sim, ctx: sa.WorldContext, K, seed: int,
                 ) -> dict[str, tuple[CloneSeed, ...]]:
    """Spec §10 for every authored PRESET, processed in sorted id order
    (determinism: presets, components, coverage draws, cuts all pinned).
    Returns {preset_id: clones}; a preset with no F_worst ≥ GENESIS_F
    range maps to (). Clones are (cells mask, N field) — see CloneSeed.
    (The preset-level aggregate is single-lineage; the engine's round-0
    seeding has been the radiated SPECIES nodes since ticket 0004 — see
    genesis_rain_species.)

    *sim* is reserved for the engine's dressing step and not read here.
    Same seed → byte-identical masks and N fields."""
    return {pid: genesis_preset(pack, sim, ctx, seed, pid, K)
            for pid in sorted(pack.presets)}


# ── the species rain: sparse founders + partial coverage (ticket 0020) ─


def _reduced_bundle(factors: dict) -> dict:
    """The compact §5.1 reduced set (names, F_worst, prov, U) — what
    the engine's per-instance cache is built from. genesis_rain_species
    returns it per species so the engine builds its cache from the SAME
    evaluation (one adapter evaluation per species at genesis)."""
    names, _m_star, F_worst, prov = reduced(factors)
    return {
        "names": names,
        "F_worst": F_worst.astype(np.float32),
        "prov": prov.astype(np.float32),
        "U": factors["substrate_share"].astype(np.float32),
    }


def genesis_rain_species(pack, ctx: sa.WorldContext, seed: int,
                         K: np.ndarray, nodes
                         ) -> dict[str, tuple[tuple[CloneSeed, ...], int,
                                              dict]]:
    """Spec §10 for every radiated SPECIES node in ONE batch (ticket
    0020, DESIGN PIVOT): the radiated species share nothing at mint —
    each is seeded independently at the capacity-relative sparse
    founder demand (D = GENESIS_F0 · K_L, F0 small) with PARTIAL
    coverage of its viable range; there is NO cross-lineage density
    budget, NO erosion sweep, NO relocation (the first implementation's
    budget gate claimed viable cells first-come-first-served in sorted
    sid order and budget-dropped 51/150 species — occupancy decided by
    name hash instead of fitness; rejected by the owner). Pipeline:

    1. Evaluate each species' OWN record view (``sa.species_view`` —
       radiated axes, not the authored preset record) → the §5.1
       reduced fields; ONE evaluation per species (the engine builds
       its cache from the returned bundle).
    2. **Seed the viable range** (F_worst ≥ GENESIS_F ∩ medium-valid ∩
       K_L > K_EPS) at D = max(GENESIS_F0·K_L, N_FLOOR·percap) — sparse
       founders: a lineage alone on a cell is born at u = GENESIS_F0
       and the whole stacked population at u ≈ F0 · n_stack, so even
       heavy stacking stays near (and the density term stays inside)
       the cap WITHOUT any mint-time budget — competition is left to
       the rounds.
    3. **Mint floor** (ticket 0009): connected components below
       GENESIS_MIN_CELLS are dropped (never minted; §7 dispersal can
       re-find those cells).
    4. **Partial coverage** (ticket 0020): per retained component, a
       keep/drop draw from ``Stream(seed, "k15.genesis", sid)``
       (``rng.child("cover:{i}")``, pinned emission order) with keep
       probability GENESIS_COVER — whole blobs kept or dropped, never
       speckled cells; a species whose every drawn component is dropped
       keeps its single largest component unconditionally (the draw
       never causes extinction). Unseeded viable cells stay empty for
       §7 colonization.
    5. **Partition** (spec §10 step 3): per species, K =
       partition_k(range_cells) clones TOTAL over the retained
       components by recursive rng-chosen axis cuts — the headstart
       speciation. Draws from ``rng.child("comp:{i}")`` — content-
       addressed, so the coverage draws' order never matters for the
       partition draws.

    Returns {sid: (clones, range_cells, bundle)} — *bundle* is the
    compact §5.1 reduced set (``_reduced_bundle``) the engine's
    per-instance cache is built from. A species with no mintable cells
    (zero range, or every component below the floor) maps to ((), 0,
    bundle): it is never minted and goes extinct at genesis (the
    authority's normal extinction path — ticket 0004; measured on seed
    1: 4 zero-range + 41 all-sub-floor + 3 all-below-K_EPS = 48
    unseeded, 102 minted). Same seed → byte-identical masks and N
    fields."""
    order = sorted(nodes, key=lambda n: n.sid)
    evals: dict[str, dict] = {}
    for node in order:
        view = sa.species_view(node, pack)
        factors = sa.evaluate(view, ctx)
        U = factors["substrate_share"].astype(np.float64)
        names, _m_star, F_worst, prov = reduced(factors)
        percap = pop.percap_demand(view)
        K_L = lineage_capacity(K, U)
        ok = ((F_worst >= GENESIS_F) & valid_mask(view, ctx)
              & (K_L > pop.K_EPS))
        if GENESIS_K_L_GATE:
            ok &= K_L >= pop.N_FLOOR * percap
        evals[node.sid] = {
            "U": U, "K_L": K_L, "ok": ok, "percap": percap,
            "D": demand_field(K_L, percap),
            "bundle": {"names": names,
                       "F_worst": F_worst.astype(np.float32),
                       "prov": prov.astype(np.float32),
                       "U": U.astype(np.float32)},
        }

    # ── 2-5: seed, floor, coverage, partition — per species ─────────
    out: dict[str, tuple[tuple[CloneSeed, ...], int, dict]] = {}
    for sid, ev in evals.items():
        big = [c for c in connected_components(ev["ok"])
               if int(c.sum()) >= GENESIS_MIN_CELLS]
        if not big:
            out[sid] = ((), 0, ev["bundle"])
            continue
        rng = Stream(seed, "k15.genesis", sid)
        big = _covered_components(big, rng)
        retained = np.logical_or.reduce(big)
        range_cells = int(retained.sum())
        K_n = partition_k(range_cells)
        if K_n == 0:
            out[sid] = ((), 0, ev["bundle"])
            continue
        chunks = _partition(retained, K_n, rng)
        clones = tuple(CloneSeed(cells=ch,
                                 N=_n_field(ch, ev["K_L"], ev["percap"]))
                       for ch in chunks)
        out[sid] = (clones, range_cells, ev["bundle"])
    return out
