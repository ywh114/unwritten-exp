"""K11 — hydrology: depression filling, flow accumulation, lakes, rivers.

Water is stored as terrain height h and water surface w per cell; depth
is derived, (w − h)+ (game-layer RFC §1). Standing water is equipotential
per connected basin — the priority-flood fill level IS the outlet-sill
height, so lakes are at equilibrium by construction (never simulated
toward; RFC §1). Flow direction is D8 to the lowest neighbor on the
filled surface; accumulation counts upstream cells.
"""

from __future__ import annotations

import heapq

import numpy as np

_D8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def connected_ocean(h: np.ndarray, sea_level: float) -> np.ndarray:
    """Ocean = below-sea-level cells connected (via below-sea paths) to
    the map border. Enclosed below-sea basins are NOT ocean: they are
    land that happens to sit below sea level —
    a lake bed if the water balance feeds it, a DRY depression
    (Death Valley) if it doesn't. A purely elevation-defined ocean
    makes below-sea land a contradiction by construction."""
    from collections import deque

    H, W = h.shape
    ocean = np.zeros((H, W), dtype=bool)
    q: deque[tuple[int, int]] = deque()
    for y in range(H):
        for x in range(W):
            if (y in (0, H - 1) or x in (0, W - 1)) and h[y, x] < sea_level:
                ocean[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in _D8:
            ny, nx_ = y + dy, x + dx
            if (0 <= ny < H and 0 <= nx_ < W and not ocean[ny, nx_]
                    and h[ny, nx_] < sea_level):
                ocean[ny, nx_] = True
                q.append((ny, nx_))
    return ocean


def priority_flood(h: np.ndarray, ocean_mask: np.ndarray) -> np.ndarray:
    """Fill depressions so every cell drains to the ocean.

    Returns the filled surface w (>= h everywhere). Cells in depressions
    rise to their outlet-sill height — the lake surface.
    """
    H, W = h.shape
    w = np.full(h.shape, np.inf)
    visited = np.zeros(h.shape, dtype=bool)
    heap: list[tuple[float, int, int]] = []

    for y in range(H):
        for x in range(W):
            if ocean_mask[y, x]:
                w[y, x] = h[y, x]
                visited[y, x] = True
                heapq.heappush(heap, (float(h[y, x]), y, x))

    while heap:
        z, y, x = heapq.heappop(heap)
        for dy, dx in _D8:
            ny, nx_ = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx_ < W and not visited[ny, nx_]:
                visited[ny, nx_] = True
                w[ny, nx_] = max(float(h[ny, nx_]), z)
                heapq.heappush(heap, (float(w[ny, nx_]), ny, nx_))
    return w


def flow_direction(w: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """D8 flow direction to the lowest filled-surface neighbor.

    Returns (direction, flat_depth): direction codes into _D8 (-1 where no
    lower neighbor exists — ocean terminals), and the BFS depth used by
    flow_accumulation to process flats strictly upstream-first.
    """
    H, W = w.shape
    direction = np.full((H, W), -1, dtype=np.int8)
    for y in range(H):
        for x in range(W):
            best, best_z = -1, w[y, x]
            for i, (dy, dx) in enumerate(_D8):
                ny, nx_ = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx_ < W and w[ny, nx_] < best_z:
                    best, best_z = i, w[ny, nx_]
            direction[y, x] = best
    return _resolve_flats(w, direction)


def _resolve_flats(w: np.ndarray, direction: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Give flat cells (lake surfaces / plateaus) a direction toward their
    outlet: BFS outward from already-directed cells over equal-height
    neighbors. Every flat region on a priority-flooded surface touches an
    outlet cell, so this assigns every non-terminal flat cell exactly once,
    in O(H*W). Also returns each cell's BFS depth (0 for cells directed on
    their own) — accumulation must process flats upstream-first, and depth
    is the tiebreak that makes it exact."""
    from collections import deque

    H, W = w.shape
    depth = np.zeros((H, W), dtype=np.int32)
    queue: deque[tuple[int, int]] = deque()
    for y in range(H):
        for x in range(W):
            if direction[y, x] != -1:
                queue.append((y, x))
    while queue:
        y, x = queue.popleft()
        for i, (dy, dx) in enumerate(_D8):
            ny, nx_ = y + dy, x + dx
            if (0 <= ny < H and 0 <= nx_ < W
                    and direction[ny, nx_] == -1
                    and w[ny, nx_] == w[y, x]):
                # (ny, nx_) drains to (y, x): reverse of the BFS step
                direction[ny, nx_] = _D8.index((-dy, -dx))
                depth[ny, nx_] = depth[y, x] + 1
                queue.append((ny, nx_))
    return direction, depth


def flow_accumulation(w: np.ndarray, direction: np.ndarray,
                      flat_depth: np.ndarray | None = None) -> np.ndarray:
    """Upstream cell counts, processing downstream-last. Sort key is
    descending (w, flat_depth): on flat surfaces the BFS depth orders
    cells strictly upstream-first, so donations always carry the full
    upstream subtree (plain descending-w order corrupts totals on flats).
    """
    H, W = w.shape
    if flat_depth is None:
        flat_depth = np.zeros((H, W), dtype=np.int32)
    acc = np.ones((H, W))
    order = sorted(((float(w[y, x]), int(flat_depth[y, x]), y, x)
                    for y in range(H) for x in range(W)), reverse=True)
    for _, _, y, x in order:
        d = direction[y, x]
        if d >= 0:
            dy, dx = _D8[d]
            acc[y + dy, x + dx] += acc[y, x]
    return acc


def _filter_small_components(mask: np.ndarray, min_cells: int) -> np.ndarray:
    """Keep only 4-connected components of at least min_cells cells."""
    H, W = mask.shape
    out = np.zeros_like(mask)
    seen = np.zeros_like(mask)
    for sy in range(H):
        for sx in range(W):
            if mask[sy, sx] and not seen[sy, sx]:
                comp, stack = [], [(sy, sx)]
                while stack:
                    y, x = stack.pop()
                    if seen[y, x] or not mask[y, x]:
                        continue
                    seen[y, x] = True
                    comp.append((y, x))
                    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                        ny, nx_ = y + dy, x + dx
                        if 0 <= ny < H and 0 <= nx_ < W and not seen[ny, nx_]:
                            stack.append((ny, nx_))
                if len(comp) >= min_cells:
                    for y, x in comp:
                        out[y, x] = True
    return out


def _water_balance_filter(lake: np.ndarray, acc: np.ndarray,
                          depth: np.ndarray, stream, alpha: float = 4.0) -> np.ndarray:
    """Keep a filled basin as a lake when (a) its inflow balances
    evaporation (max accumulation within the component >= alpha * area)
    and it fits its size CAP, drawn per basin from a skewed
    distribution (25 + 425·u⁴ cells, K1-seeded): most basins draw small
    caps, a rare draw allows a mega-lake — mega-lakes exist but are
    special, never routine. Bigger or underfed basins become wetland
    flats with the river running through — EXCEPT deep basins: a floor
    hundreds of meters down (oceanic trenches, deep rifts) can never be
    dry land, so those are lakes regardless of inflow (Baikal/Caspian
    style). Without this rule, underfed trench floors surfaced as dry
    depressions kilometers deep."""
    H, W = lake.shape
    out = np.zeros_like(lake)
    seen = np.zeros_like(lake)
    k = 0
    for sy in range(H):
        for sx in range(W):
            if lake[sy, sx] and not seen[sy, sx]:
                comp, stack = [], [(sy, sx)]
                while stack:
                    y, x = stack.pop()
                    if seen[y, x] or not lake[y, x]:
                        continue
                    seen[y, x] = True
                    comp.append((y, x))
                    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                        ny, nx_ = y + dy, x + dx
                        if 0 <= ny < H and 0 <= nx_ < W and not seen[ny, nx_]:
                            stack.append((ny, nx_))
                u = stream.uniform(900 + k, 0)
                cap = 25 + int(425 * u ** 4)
                k += 1
                inflow = max(float(acc[y, x]) for y, x in comp)
                mean_depth = float(np.mean([depth[y, x] for y, x in comp]))
                fed = inflow >= alpha * len(comp) and len(comp) <= cap
                if fed or mean_depth > 0.03:
                    for y, x in comp:
                        out[y, x] = True
    return out


def _absorb_coastal_lakes(lake: np.ndarray, ocean: np.ndarray) -> np.ndarray:
    """Lakes 8-connected to the ocean are absorbed into it: a lake with
    an open connection to the sea is a bay or lagoon, not a lake.
    Returns the mask of absorbed cells."""
    H, W = lake.shape
    absorbed = np.zeros_like(lake)
    seen = np.zeros_like(lake)
    for sy in range(H):
        for sx in range(W):
            if lake[sy, sx] and not seen[sy, sx]:
                comp, stack = [], [(sy, sx)]
                touches = False
                while stack:
                    y, x = stack.pop()
                    if seen[y, x] or not lake[y, x]:
                        continue
                    seen[y, x] = True
                    comp.append((y, x))
                    for dy, dx in _D8:
                        ny, nx_ = y + dy, x + dx
                        if 0 <= ny < H and 0 <= nx_ < W:
                            if ocean[ny, nx_]:
                                touches = True
                            elif not seen[ny, nx_]:
                                stack.append((ny, nx_))
                if touches:
                    for y, x in comp:
                        absorbed[y, x] = True
    return absorbed


def strahler_order(direction: np.ndarray, river: np.ndarray,
                   acc: np.ndarray) -> np.ndarray:
    """Strahler stream order over river cells, processed upstream-first
    (ascending accumulation). Headwaters are order 1; a confluence of two
    equal-order k streams yields k+1, otherwise the max continues."""
    H, W = river.shape
    order = np.zeros((H, W), dtype=np.int16)
    order[river] = 1
    ys, xs = np.where(river)
    for y, x in sorted(zip(ys.tolist(), xs.tolist()), key=lambda c: acc[c]):
        ups = []
        for dy, dx in _D8:
            ny, nx_ = y + dy, x + dx
            if (0 <= ny < H and 0 <= nx_ < W and river[ny, nx_]):
                d = direction[ny, nx_]
                if d >= 0 and (ny + _D8[d][0], nx_ + _D8[d][1]) == (y, x):
                    ups.append(int(order[ny, nx_]))
        if ups:
            top = max(ups)
            order[y, x] = top + 1 if ups.count(top) >= 2 else top
    return order


def build_hydrology(h: np.ndarray, ocean_mask: np.ndarray,
                    sea_level: float = 0.35, river_threshold: float = 40.0,
                    seed: int = 0) -> dict:
    """Full water model for the L0 sketch.

    Lakes first: depressions fill to their outlet sills, then rivers are
    accumulation above threshold OUTSIDE lakes (rivers enter lakes at
    inlets and re-emerge at outlets carrying the lake's inflow — the
    accumulation passes through the filled lake surface). The threshold
    rises in the lowlands so rivers tend to start in high ground.

    Returns dict with: w (water surface), depth ((w-h)+), flow_dir,
    accumulation (= discharge), river_mask, order (Strahler), width
    (render width class 1-3 by discharge), lake_mask, ocean_mask.
    """
    from kernel.hashrng import Stream

    w = priority_flood(h, ocean_mask)
    depth = np.maximum(w - h, 0.0)
    depth[ocean_mask] = 1.0  # ocean is water by definition
    direction, flat_depth = flow_direction(w)
    acc = flow_accumulation(w, direction, flat_depth)

    lake = (depth > 1e-9) & ~ocean_mask
    # drop only 1-cell puddles; small ponds are the small-lake
    # smattering, not speckle
    lake = _filter_small_components(lake, min_cells=2)
    # water balance + per-basin size cap (K1-drawn, skewed small)
    lake = _water_balance_filter(lake, acc, depth, Stream(seed, "k11.hydro"), alpha=4.0)
    # lakes bordering the ocean are absorbed into it (bays/lagoons)
    absorbed = _absorb_coastal_lakes(lake, ocean_mask)
    if absorbed.any():
        ocean_mask = ocean_mask | absorbed
        lake = lake & ~absorbed
        w[absorbed] = np.maximum(h[absorbed], sea_level)
        depth = np.maximum(w - h, 0.0)
        depth[ocean_mask] = 1.0
    # elevation-biased threshold: lowlands need ~1.8x the upstream area
    span = max(float(h.max() - h.min()), 1e-9)
    h_norm = (h - h.min()) / span
    thr_eff = river_threshold * (1.0 + 0.8 * (1.0 - h_norm))
    river = (acc >= thr_eff) & ~ocean_mask & ~lake

    order = strahler_order(direction, river, acc)
    width = np.zeros((h.shape), dtype=np.int16)
    width[river] = 1
    width[river & (acc >= river_threshold * 6)] = 2
    width[river & (acc >= river_threshold * 30)] = 3
    return {
        "w": w,
        "depth": depth,
        "flow_dir": direction,
        "accumulation": acc,
        "discharge": acc,
        "order": order,
        "width": width,
        "river_mask": river,
        "lake_mask": lake,
        "ocean_mask": ocean_mask,
    }
