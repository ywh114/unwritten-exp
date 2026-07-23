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
                      flat_depth: np.ndarray | None = None,
                      weight: np.ndarray | None = None) -> np.ndarray:
    """Upstream totals, processing downstream-last. Sort key is
    descending (w, flat_depth): on flat surfaces the BFS depth orders
    cells strictly upstream-first, so donations always carry the full
    upstream subtree (plain descending-w order corrupts totals on flats).

    Each cell donates `weight` (default 1.0 — plain upstream cell count;
    pass monthly-mean precipitation for discharge).
    """
    H, W = w.shape
    if flat_depth is None:
        flat_depth = np.zeros((H, W), dtype=np.int32)
    acc = np.ones((H, W)) if weight is None else np.array(weight, dtype=float)
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


def _cap_inland_seas(w: np.ndarray, h: np.ndarray, ocean_mask: np.ndarray,
                     sea_level: float) -> np.ndarray:
    """Inland seas never stand above sea level. A filled basin whose
    floor dips below sea level floods (priority fill) to its rim sill —
    a phantom surface potentially hundreds of meters up — but a real
    enclosed basin fills to ~sea level at most (Caspian −28 m, Death
    Valley dry). Cap each whole filled component whose floor goes below
    sea level at sea level — per component, so lake surfaces stay
    equipotential. Mountain tarns (floor above sea level) are untouched.
    """
    cand = (w > h) & ~ocean_mask
    H, W = cand.shape
    seen = np.zeros_like(cand)
    for sy in range(H):
        for sx in range(W):
            if cand[sy, sx] and not seen[sy, sx]:
                comp, stack = [], [(sy, sx)]
                while stack:
                    y, x = stack.pop()
                    if seen[y, x] or not cand[y, x]:
                        continue
                    seen[y, x] = True
                    comp.append((y, x))
                    for dy, dx in _D8:
                        ny, nx_ = y + dy, x + dx
                        if (0 <= ny < H and 0 <= nx_ < W and not seen[ny, nx_]
                                and cand[ny, nx_]):
                            stack.append((ny, nx_))
                if min(float(h[y, x]) for y, x in comp) < sea_level:
                    for y, x in comp:
                        w[y, x] = max(float(h[y, x]), sea_level)
    return w


def _submerge_islets(lake: np.ndarray, w: np.ndarray, h: np.ndarray,
                     ocean_mask: np.ndarray, sea_level: float,
                     max_cells: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """Tiny land components fully enclosed by a lake render as blocky
    one/few-cell artifacts at the anchor grid — and they ARE artifacts:
    capping an inland sea at sea level strands interior bumps that the
    rim-sill flood used to drown. Real seas hide such bumps (sandbars,
    reefs, guyots); submerge islets up to max_cells into the
    surrounding lake at its surface. Larger islands stay islands."""
    land = ~lake & ~ocean_mask
    H, W = lake.shape
    seen = np.zeros_like(land)
    for sy in range(H):
        for sx in range(W):
            if not (land[sy, sx] and not seen[sy, sx]):
                continue
            comp, stack = [], [(sy, sx)]
            while stack:
                y, x = stack.pop()
                if seen[y, x] or not land[y, x]:
                    continue
                seen[y, x] = True
                comp.append((y, x))
                for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    ny, nx_ = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx_ < W and not seen[ny, nx_]:
                        stack.append((ny, nx_))
            if len(comp) > max_cells:
                continue
            cells = set(comp)
            neighbor_ws: list[float] = []
            enclosed = True
            for y, x in comp:
                for dy, dx in _D8:
                    ny, nx_ = y + dy, x + dx
                    if not (0 <= ny < H and 0 <= nx_ < W):
                        enclosed = False
                    elif lake[ny, nx_]:
                        neighbor_ws.append(float(w[ny, nx_]))
                    elif (ny, nx_) not in cells:
                        enclosed = False  # touches other land or ocean
            if enclosed and neighbor_ws:
                surf = min(neighbor_ws)  # the enclosing lake's surface
                for y, x in comp:
                    lake[y, x] = True
                    w[y, x] = surf
    return lake, w


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


def carve_gorges(h: np.ndarray, ocean_mask: np.ndarray,
                 passes: int = 3, rate: float = 0.5,
                 carve_threshold: float = 240.0) -> np.ndarray:
    """Antecedent gorges: a big river whose momentum points into a
    sill cuts through instead of bending around.

    A river is a vector: it does not climb — when the terrain rises
    ahead, the flow bends. Multi-pass refinement (reflood -> notch ->
    reflood), no explicit path carving: for each river cell with
    accumulation >= carve_threshold (the width-2 discharge line),
    take the arrival direction of its largest inflow (the river's
    momentum) and look STRAIGHT AHEAD: if the cell there is HIGHER
    LAND and the actual flow bends away from it, that cell is a sill
    wall — erode it asymptotically toward the river's own level
    (h -= rate * (h - h_river); no clamp, never overshoots). Each
    pass lets the river run straighter and points it at the next wall
    cell, walking the gorge through the ridge. Erosion touches DRY
    LAND only — standing water and its beds are never eroded.
    """
    h = h.copy()
    H, W = h.shape
    for _ in range(passes):
        w = priority_flood(h, ocean_mask)
        direction, flat_depth = flow_direction(w)
        acc = flow_accumulation(w, direction, flat_depth)
        ponded = (w - h) > 1e-9          # standing water: never eroded
        ys, xs = np.where(acc >= carve_threshold)
        for y, x in zip(ys.tolist(), xs.tolist()):
            # momentum: arrival direction of the biggest inflow
            best, bq = None, -1.0
            for i, (dy, dx) in enumerate(_D8):
                uy, ux = y - dy, x - dx
                if not (0 <= uy < H and 0 <= ux < W):
                    continue
                ud = direction[uy, ux]
                if (ud >= 0
                        and (uy + _D8[ud][0], ux + _D8[ud][1]) == (y, x)
                        and acc[uy, ux] > bq):
                    bq, best = acc[uy, ux], i
            d = direction[y, x]
            if best is None or d < 0 or best == d:
                continue                 # source, sink, or no bend
            ay, ax = y + _D8[best][0], x + _D8[best][1]
            if not (0 <= ay < H and 0 <= ax < W):
                continue
            if ponded[ay, ax] or ocean_mask[ay, ax]:
                continue                 # never erode water bodies
            if h[ay, ax] > h[y, x] + 1e-9:
                h[ay, ax] -= rate * (h[ay, ax] - h[y, x])
    return h


def height_above_drainage(h: np.ndarray, w: np.ndarray,
                          direction: np.ndarray,
                          water: np.ndarray) -> np.ndarray:
    """HAND — Height Above Nearest Drainage, normalized units.

    For every land cell, the elevation drop to the water surface its
    flow path first reaches (river cell, lake surface, or sea); water
    cells are 0. Computed downstream-first (ascending w): each land
    cell inherits the base surface of its downstream neighbor.
    """
    H, W = h.shape
    base = np.where(water, w, np.inf)
    hand = np.zeros((H, W))
    order = sorted((float(w[y, x]), y, x) for y in range(H) for x in range(W))
    for _, y, x in order:
        if water[y, x]:
            continue
        d = direction[y, x]
        if d >= 0:
            dy, dx = _D8[d]
            base[y, x] = base[y + dy, x + dx]
            hand[y, x] = max(float(h[y, x]) - float(base[y, x]), 0.0)
    return hand


def classify_salinity(hydro: dict, sea_min_area_km2: float = 5000.0,
                      cell_km2: float = 16.0) -> np.ndarray:
    """Salinity per water cell in g/kg (see units.SALINITY_OCEAN_GKG),
    anchor grid. Also sets hydro["sea_mask"]: INLAND SEAS — saline
    (brackish-and-up) components big enough to be seas, not lakes
    (Caspian/Aral: large + endorheic + salt is exactly the real-world
    rule; sea_min_area_km2 is the class line, Aral-scale).

    Relational — decided once at the anchor grid, never after upscale.

    - ocean: 35 g/kg by definition
    - rivers: 0.0 (flowing water accumulates no salt), except the
      tidal estuary band 8-adjacent to the ocean: a sea/fresh mixing
      ratio on the river's own discharge — big rivers flush their
      estuary toward fresh, tidal creeks stay nearly seawater
    - lakes: trace the drainage downstream from each component's
      maximum-accumulation cell. Reaching the ocean means the lake is
      EXORHEIC — flushed, fresh (0.5). Terminating inside the basin
      means ENDORHEIC — evaporation concentrates salt, and the level
      decays exponentially with the flushing ratio (inflow
      accumulation per lake cell), no hard bounds: an underfed
      terminal approaches ~220 (Great Salt Lake / Dead Sea range), a
      Volga-scale inflow flushes it toward fresh (Caspian ~12).
    """
    from exp.k11_worldgen.units import SALINITY_OCEAN_GKG

    ocean = hydro["ocean_mask"]
    lake = hydro["lake_mask"]
    river = hydro["river_mask"]
    direction = hydro["flow_dir"]
    acc = hydro["accumulation"]
    H, W = lake.shape
    sal = np.zeros((H, W))
    sal[ocean] = SALINITY_OCEAN_GKG
    sea = np.zeros((H, W), dtype=bool)

    seen = np.zeros_like(lake)
    for sy in range(H):
        for sx in range(W):
            if not (lake[sy, sx] and not seen[sy, sx]):
                continue
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
            start = max(comp, key=lambda c: acc[c])
            # walk downstream: ocean -> exorheic; sink/cycle -> endorheic
            y, x = start
            path = set()
            exorheic = False
            while True:
                if ocean[y, x]:
                    exorheic = True
                    break
                if (y, x) in path:
                    break
                path.add((y, x))
                d = direction[y, x]
                if d < 0:
                    break
                y, x = y + _D8[d][0], x + _D8[d][1]
            if exorheic:
                value = 0.5
            else:
                inflow = max(float(acc[y, x]) for y, x in comp)
                ratio = inflow / max(len(comp), 1)
                value = float(220.0 * np.exp(-ratio / 120.0))
            for cy, cx in comp:
                sal[cy, cx] = value
            if value > 10.0 and len(comp) * cell_km2 >= sea_min_area_km2:
                for cy, cx in comp:
                    sea[cy, cx] = True

    # tidal estuaries: river cells directly on the sea mix seawater
    # with their own discharge — 35 * Q_half / (Q_half + Q), where
    # Q_half is the upstream-cell count at which the mix is half sea
    near_ocean = np.zeros_like(ocean)
    p = np.pad(ocean, 1, mode="edge")
    for dy in range(3):
        for dx in range(3):
            near_ocean |= p[dy:dy + H, dx:dx + W]
    estuary = river & near_ocean
    q_half = 50.0
    sal[estuary] = (SALINITY_OCEAN_GKG * q_half
                    / (q_half + acc[estuary]))
    hydro["sea_mask"] = sea
    return sal


def build_hydrology(h: np.ndarray, ocean_mask: np.ndarray,
                    sea_level: float = 0.35, river_threshold: float = 40.0,
                    seed: int = 0) -> dict:
    """Full water model for the L0 sketch.

    Lakes first: depressions fill to their outlet sills, then rivers are
    accumulation above threshold OUTSIDE lakes (rivers enter lakes at
    inlets and re-emerge at outlets carrying the lake's inflow — the
    accumulation passes through the filled lake surface). The threshold
    rises in the lowlands so rivers tend to start in high ground.

    Returns dict with: w (WET surface — lake cells at their lake level,
    dry cells at terrain; rejected basins are dry land), w_route (the
    surface flow routes on — rejected basins keep their flood surface
    so drainage can pass through), depth ((w-h)+), flow_dir,
    accumulation (= discharge), river_mask, order (Strahler), width
    (render width class 1-3 by discharge), lake_mask, ocean_mask.
    """
    from kernel.hashrng import Stream

    w = priority_flood(h, ocean_mask)
    w_capped = _cap_inland_seas(w.copy(), h, ocean_mask, sea_level)
    # the water balance is judged on the CAPPED candidate surface: an
    # inland sea's true depth is to sea level, not to its rim sill
    depth_c = np.maximum(w_capped - h, 0.0)
    depth_c[ocean_mask] = 1.0  # ocean is water by definition
    direction, flat_depth = flow_direction(w)
    acc = flow_accumulation(w, direction, flat_depth)

    lake = (depth_c > 1e-9) & ~ocean_mask
    # drop only 1-cell puddles; small ponds are the small-lake
    # smattering, not speckle
    lake = _filter_small_components(lake, min_cells=2)
    # water balance + per-basin size cap (K1-drawn, skewed small)
    lake = _water_balance_filter(lake, acc, depth_c, Stream(seed, "k11.hydro"), alpha=4.0)
    # lakes bordering the ocean are absorbed into it (bays/lagoons)
    absorbed = _absorb_coastal_lakes(lake, ocean_mask)
    if absorbed.any():
        ocean_mask = ocean_mask | absorbed
        lake = lake & ~absorbed
        w[absorbed] = np.maximum(h[absorbed], sea_level)
        w_capped[absorbed] = w[absorbed]
    # accepted inland seas keep the capped sea-level surface and become
    # ENDORHEIC terminals (rivers flow in, nothing flows out — Caspian);
    # rejected basins keep the flood surface so their wetland flats
    # still drain through to the ocean. Above-sea-level lakes keep
    # through-flow (inflow re-emerges at the outlet) as before.
    w = np.where(lake | ocean_mask, w_capped, w)
    # submerge speck islets (cap artifacts) before routing
    lake, w = _submerge_islets(lake, w, h, ocean_mask, sea_level)
    # re-route on the final surface (capped seas are terminals)
    direction, flat_depth = flow_direction(w)
    acc = flow_accumulation(w, direction, flat_depth)
    # routing surface vs wet surface: on REJECTED basins the flood
    # surface exists only so flow can drain through — it is a phantom
    # water body and must never be seen downstream (delivery re-derives
    # waterlines from w and would re-flood dry basins; the confinement
    # that prevented that is what made small lakes rectangular).
    # w = what is actually WET; w_route = what flow routes on.
    w_route = w
    w = np.where(lake | ocean_mask, w_route, h)
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
    hydro = {
        "w": w,
        "w_route": w_route,
        "depth": depth,
        "flow_dir": direction,
        "flat_depth": flat_depth,
        "accumulation": acc,
        "discharge": acc,
        "order": order,
        "width": width,
        "river_mask": river,
        "lake_mask": lake,
        "ocean_mask": ocean_mask,
    }
    hydro["salinity"] = classify_salinity(hydro)
    hydro["hand"] = height_above_drainage(
        h, w_route, direction, ocean_mask | lake | river)
    return hydro


def refine_hydrology(hydro: dict, elev: np.ndarray, climate: dict,
                     sea_level: float, seed: int = 0,
                     river_threshold: float = 40.0,
                     alpha: float = 4.0) -> dict:
    """Second hydrology pass, after climate: precipitation-conditioned
    small features, ADDITIVE only (nothing pass 1 made is removed).

    The first pass judges the water balance with a uniform assumed
    wetness, so lush regions and tundra hollows end up with the same
    drainage density as steppe — unreasonable. Here the actual monthly
    climate re-judges:

    - ponds: basins the uniform balance rejected (their phantom flood
      surface still lives in w_route) are accepted when the P-WEIGHTED
      inflow beats temperature-scaled evaporation (hot basins evaporate
      more, so the same rain feeds a pond in taiga hollows but not in
      the tropics' seasonal heat). Accepted ponds join the wet surface:
      above-sea floors keep their fill level (through-flow), floors
      below sea level cap AT sea level (the inland-sea rule).
    - streams: river cells wherever the P-weighted discharge clears the
      equivalent of the area threshold at mean land wetness — wet
      basins cross it further upstream, so drainage density follows
      the rain.

    Routing surfaces (w_route, flow_dir) are untouched — ponds sit on
    the flow paths they always drained through — so discharge is
    computed once, before the mask updates. Strahler order, width
    classes, salinity, and HAND are recomputed afterwards.
    """
    from exp.k11_worldgen.units import temp_c

    h = elev
    w_route = hydro["w_route"]
    direction, flat_depth = hydro["flow_dir"], hydro["flat_depth"]
    ocean_mask, lake = hydro["ocean_mask"], hydro["lake_mask"].copy()
    river = hydro["river_mask"].copy()
    w, depth = hydro["w"].copy(), hydro["depth"].copy()
    acc = hydro["accumulation"]
    P = climate["P"]                      # monthly-mean, normalized
    land = ~ocean_mask & ~lake
    discharge = flow_accumulation(w_route, direction, flat_depth, weight=P)
    hydro["discharge"] = discharge

    # ---- ponds: re-judge rejected basins on P-weighted inflow ----
    cand = (w_route - h > 1e-9) & ~ocean_mask & ~lake
    t_ann = temp_c(climate["T_monthly"]).mean(axis=0)
    H, W = lake.shape
    seen = np.zeros_like(lake)
    from exp.k11_worldgen.aquatic import _dilate
    lake_halo = _dilate(lake, 1)
    for sy in range(H):
        for sx in range(W):
            if not (cand[sy, sx] and not seen[sy, sx]):
                continue
            comp, stack = [], [(sy, sx)]
            while stack:
                y, x = stack.pop()
                if seen[y, x] or not cand[y, x]:
                    continue
                seen[y, x] = True
                comp.append((y, x))
                for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    ny, nx_ = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx_ < W and not seen[ny, nx_]:
                        stack.append((ny, nx_))
            cys = tuple(c[0] for c in comp)
            cxs = tuple(c[1] for c in comp)
            # a candidate touching an existing lake would merge with it
            # at a different surface level — skip (one basin, one lake)
            if lake_halo[cys, cxs].any():
                continue
            # evaluate each equipotential fill level SEPARATELY: a
            # candidate component can span several sub-basins at
            # different flood levels connected by wetland flats;
            # judging (or filling) them as one would drown the lower
            # sub-basins and their streams under the highest level
            for level in np.unique(w_route[cys, cxs]):
                sub = np.zeros_like(lake)
                sub[cys, cxs] = w_route[cys, cxs] == level
                if lake_halo[sub].any():
                    continue
                ys2, xs2 = np.where(sub)
                inflow_p = float(discharge[ys2, xs2].max())
                # evaporation scales with heat: ~1 m/yr at 25 degC, a
                # fraction of that in the cold, more in the hot seasonals
                evap = float(np.clip(t_ann[ys2, xs2].mean() / 25.0, 0.2, 1.4))
                if inflow_p < alpha * len(ys2) * evap:
                    continue
                surf = float(level)
                if (h[ys2, xs2] < sea_level).any():
                    # enclosed below-sea floor: fill to ~sea level at
                    # most, keep only cells that stay wet at that level
                    surf = min(surf, sea_level)
                wet = np.zeros_like(lake)
                wet[ys2, xs2] = h[ys2, xs2] < surf - 1e-9
                wet = _filter_small_components(wet, min_cells=2)
                if not wet.any():
                    continue
                lake |= wet
                w[wet] = surf
                depth[wet] = surf - h[wet]
                # new ponds also block neighbors: two adjacent basins
                # accepted at different levels would read as one lake
                # with two surfaces
                lake_halo |= _dilate(wet, 1)

    # ---- streams: P-weighted discharge threshold ----
    # a basin must gather river_threshold * mean-wetness worth of
    # precipitation — in lush country that is a fraction of the cells,
    # in dry country multiples of them
    p_mean = float(P[land].mean()) if land.any() else 0.0
    if p_mean > 1e-9:
        river |= (discharge >= river_threshold * p_mean) & ~ocean_mask & ~lake
    river &= ~lake                      # ponds swallow their through-river

    order = strahler_order(direction, river, acc)
    width = np.zeros((h.shape), dtype=np.int16)
    width[river] = 1
    width[river & (acc >= river_threshold * 6)] = 2
    width[river & (acc >= river_threshold * 30)] = 3
    hydro.update({"w": w, "depth": depth, "river_mask": river,
                  "lake_mask": lake, "order": order, "width": width})
    hydro["salinity"] = classify_salinity(hydro)
    hydro["hand"] = height_above_drainage(
        h, w_route, direction, ocean_mask | lake | river)
    return hydro
