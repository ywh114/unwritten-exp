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

# monthly river weight: the standing soil moisture leaks to streams at
# this rate per month (normalized-P units — the same units the bucket
# and the precip fields share). This is the baseflow that keeps trunk
# rivers running through rainless months.
SOIL_BASEFLOW = 0.25

# river speed (regime hydraulic geometry — literature values, MOVED
# from K14 derived.py: K11 owns the physics and persists the field;
# downstream reads it, never re-derives it)
CELL_M = 4000.0                 # anchor cell = 4 km
SECONDS_PER_MONTH = 30.4 * 24 * 3600.0
# one discharge unit = one upstream cell's P_norm contribution:
# P_MAX_MM over a 16 km2 cell per month, in m3/s
Q_M3S_PER_UNIT = (400.0 / 1000.0) * (CELL_M ** 2) / SECONDS_PER_MONTH
WIDTH_COEF = 8.0                # w = 8 Q^0.5  (m; wide-channel regime)
DEPTH_COEF = 0.3                # d = 0.3 Q^0.4 (m)
MANNING_N = 0.035               # gravel-bed roughness
MIN_SLOPE = 1e-5                # numerical floor, not a physical cap
V_RIVER_MAX = 6.0               # leaky sanity ceiling (m/s)
# momentum: Manning from the single-step drop understates velocity
# wherever the filled surface is locally flat (a reach crossing a
# filled depression has drop exactly 0 and collapses to the slope
# floor, ~0.06 m/s — a real river carries its velocity over the flat).
# Processed upstream->downstream over the river subgraph: a cell keeps
# max(manning, MOMENTUM_GAMMA * best upstream final speed). The gamma
# decays inherited speed over long flats (0.85^10 ~ 0.2 after 40 km).
# Propagation runs over RIVER cells only, so the graph breaks at lake
# cells — momentum is cut at lakes automatically (water slows entering
# standing water; an outflow reach starts from its own Manning).
MOMENTUM_GAMMA = 0.85
# reach jitter: the relief is 4 km cells, so Manning here yields a
# reach AVERAGE, not a local measurement — sub-grid velocity varies
# around it. One seeded lognormal-ish draw per cell (e^+-SPEED_JITTER,
# ~+-28%) stands in for that variance. Consumers must treat speed as
# approximate: smooth gates, never hard thresholds on it.
SPEED_JITTER = 0.25


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


# flats routing: penalty per unit of RAW elevation climbed (normalized
# h) — a 0.01 climb costs as much as a 10-cell detour, so drainage on
# priority-flood flats winds through the bed's micro-lows instead of
# crossing micro-ridges on the straight line to the outlet
_FLAT_CLIMB_PENALTY = 1000.0


def flow_direction(w: np.ndarray, h: np.ndarray
                   ) -> tuple[np.ndarray, np.ndarray]:
    """D8 flow direction to the lowest filled-surface neighbor.

    `h` is the RAW terrain under the fill: flat regions (where the
    priority-flood surface hides all relief) route on its
    micro-gradient — see _resolve_flats. Returns (direction, cost):
    direction codes into _D8 (-1 where no lower neighbor exists —
    ocean terminals), and the routing cost used by flow_accumulation
    to process flats strictly upstream-first.
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
    return _resolve_flats(w, h, direction)


def _resolve_flats(w: np.ndarray, h: np.ndarray,
                   direction: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Give flat cells (lake surfaces / plateaus) a direction toward
    their outlet: multi-source Dijkstra from already-directed cells
    over equal-w neighbors, edge cost 1 + penalty * raw-h climb. The
    fill hides it, but the raw terrain under a flat has real
    micro-relief — drainage WINDS through the subtle lows instead of
    following the BFS wavefront, whose fewest-hops paths are geometric
    beelines to the outlet (the straight-diagonal river bearings).
    Acyclic and outlet-connected by construction (cost strictly
    increases away from the outlets, and every flat region on a
    priority-flooded surface touches one). Returns (direction, cost) —
    accumulation orders flats upstream-first by DESCENDING cost."""
    import heapq

    H, W = w.shape
    cost = np.full((H, W), np.inf)
    pq: list[tuple[float, int, int]] = []
    for y in range(H):
        for x in range(W):
            if direction[y, x] != -1:
                cost[y, x] = 0.0
                pq.append((0.0, y, x))
    heapq.heapify(pq)
    while pq:
        c, y, x = heapq.heappop(pq)
        if c > cost[y, x]:
            continue
        for i, (dy, dx) in enumerate(_D8):
            ny, nx_ = y + dy, x + dx
            if (0 <= ny < H and 0 <= nx_ < W
                    and direction[ny, nx_] == -1
                    and w[ny, nx_] == w[y, x]):
                nc = c + 1.0 + _FLAT_CLIMB_PENALTY * max(
                    0.0, float(h[ny, nx_] - h[y, x]))
                if nc < cost[ny, nx_]:
                    cost[ny, nx_] = nc
                    direction[ny, nx_] = _D8.index((-dy, -dx))
                    heapq.heappush(pq, (nc, ny, nx_))
    return direction, cost


def flow_accumulation(w: np.ndarray, direction: np.ndarray,
                      flat_depth: np.ndarray | None = None,
                      weight: np.ndarray | None = None) -> np.ndarray:
    """Upstream totals, processing downstream-last. Sort key is
    descending (w, flat_depth): on flat surfaces the routing cost (see
    _resolve_flats) orders cells strictly upstream-first, so donations
    always carry the full upstream subtree (plain descending-w order
    corrupts totals on flats).

    Each cell donates `weight` (default 1.0 — plain upstream cell count;
    pass monthly-mean precipitation for discharge).
    """
    H, W = w.shape
    if flat_depth is None:
        flat_depth = np.zeros((H, W))
    acc = np.ones((H, W)) if weight is None else np.array(weight, dtype=float)
    order = sorted(((float(w[y, x]), float(flat_depth[y, x]), y, x)
                    for y in range(H) for x in range(W)), reverse=True)
    for _, _, y, x in order:
        d = direction[y, x]
        if d >= 0:
            dy, dx = _D8[d]
            acc[y + dy, x + dx] += acc[y, x]
    return acc


def glacier_flow(direction: np.ndarray, flat_depth: np.ndarray,
                 w_route: np.ndarray, land: np.ndarray,
                 snowfall_m: np.ndarray, meltpot_m: np.ndarray,
                 melt_m: np.ndarray,
                 persist: np.ndarray | None = None
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Glacier pass: net-growth zones export their ice downslope.

    Where annual snowfall beats annual melt the snow bucket grows
    without bound year over year — ice does not pile up forever, it
    FLOWS. Only the growth-zone cells and their downslope paths are
    touched:

    - local ice production = max(annual snow balance, 0) — but only
      cells the caller marks PERSISTENT contribute (regional firn rule,
      detect_glaciers); a marginal cell's token surplus melts out with
      the season instead of seeding a phantom glacier
    - ablation capacity = the year's UNUSED melt potential (heat that
      found no snow to melt) — it eats the ice below the equilibrium
      line
    - ice not consumed flows to the downstream cell; where nothing
      flows on the glacier ends (terminus — the melt front); ice
      routed into standing water or a pit calves there

    Returns (glacier_mask, ice_flux, ice_melt_monthly): the ICE-COVERED
    cells (year-round: own snowpack survives, or ice flows on through —
    melt-front cells whose year's ice entirely melts in place are NOT
    glacier, though their meltwater counts), the annual ice throughput
    per cell (mm WE/yr), and the meltwater released from ICE per month
    (mm WE) — the caller adds it to the snowmelt pulse feeding the
    monthly river discharge.
    """
    H, W = land.shape
    balance = snowfall_m.sum(axis=0) - melt_m.sum(axis=0)
    pot_unused = np.clip(meltpot_m - melt_m, 0.0, None)
    abl_cap = pot_unused.sum(axis=0)
    production = np.clip(balance, 0.0, None)
    if persist is not None:
        production = np.where(persist, production, 0.0)
    flux = np.zeros((H, W))
    glacier = np.zeros((H, W), dtype=bool)
    ice_melt = np.zeros((H, W))
    cells = sorted(((float(w_route[y, x]), float(flat_depth[y, x]), y, x)
                    for y in range(H) for x in range(W)), reverse=True)
    for _, _, y, x in cells:
        ice = flux[y, x] + production[y, x]
        if ice <= 0.0:
            continue
        melted = min(ice, abl_cap[y, x])
        ice_melt[y, x] = melted
        out = ice - melted
        # glacier = ice PRESENT year-round: the cell's own snowpack
        # never melts out (production > 0), or ice flows on through it
        # (out > 0 — the tongue). A cell whose year's ice entirely
        # melts in place is just the melt front passing through — its
        # meltwater still counts, but it is not ice-covered.
        if production[y, x] > 0.0 or out > 0.0:
            glacier[y, x] = True
        if out <= 0.0:
            continue                    # terminus: nothing flows on
        d = direction[y, x]
        if d < 0:
            continue                    # pit: calves in place
        dy, dx = _D8[d]
        ny, nx_ = y + dy, x + dx
        if land[ny, nx_]:
            flux[ny, nx_] += out
        # else: calves into standing water (lake/ocean) — flux ends
    # monthly ice melt, distributed by the unused melt potential
    denom = np.where(abl_cap > 1e-9, abl_cap, 1.0)
    ice_melt_m = (pot_unused / denom[None]) * ice_melt[None]
    return glacier, flux + production, ice_melt_m


# glacial terrain: the land's ONE-SHOT equilibrium response to its ice
# (detect once, respond once — no iteration loop; see __main__). The
# relations are order-of-magnitude glaciology keyed to the persisted
# ice flux (mm WE/yr throughput) — never tuned per world.
THICK_A = 10.0          # m of ice per (mm WE/yr)^1/3 of throughput
THICK_SOFT_M = 1500.0   # leaky soft cap (tanh) on equilibrium thickness
ERODE_A = 2.0           # bed erosion (m) per (mm WE/yr)^1/3 — quarrying
                        # and abrasion scale with throughput
DEPOSIT_DECAY = 0.5     # moraine/outwash spread: weight per ring out


def glacier_thickness(flux: np.ndarray) -> np.ndarray:
    """Equilibrium ice thickness (m) from throughput: thick ~ flux^1/3
    (flow-law flavor — outlet glaciers run 100s of m, ice-cap interiors
    ~1 km), leaky soft cap, 0 where there is no ice."""
    t = THICK_A * np.cbrt(np.maximum(flux, 0.0))
    return (THICK_SOFT_M * np.tanh(t / THICK_SOFT_M)).astype(np.float32)


# terminus taper: a glacier snout is THIN. The equilibrium (flux-keyed)
# thickness holds in the interior, but near the melt front the ice
# thins with the square root of the distance upstream (the perfect-
# plasticity profile). Without this the tongue ends at full thickness,
# which renders as a wall of ice at the front.
TAPER_CELLS = 4         # anchor cells over which the front ramps 0 -> full


def terminus_taper(glacier: np.ndarray, direction: np.ndarray
                   ) -> np.ndarray:
    """Front-taper scale in [0, 1] for the thickness field: 0 at the
    melt front, ramping to 1 over TAPER_CELLS upstream with the
    sqrt profile. A terminus is a glacier cell whose downstream is
    not glacier (the front, a calving margin, or a pit); distance is
    counted upstream along the reverse flow graph. Non-glacier and
    unreachable cells scale 1 (untouched)."""
    H, W = glacier.shape
    dist = np.full((H, W), -1, dtype=np.int32)
    rev: dict[tuple[int, int], list[tuple[int, int]]] = {}
    stack: list[tuple[int, int]] = []
    for y, x in zip(*np.nonzero(glacier)):
        d = int(direction[y, x])
        term = d < 0
        if not term:
            dy, dx = _D8[d]
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W and glacier[ny, nx]:
                rev.setdefault((ny, nx), []).append((y, x))
            else:
                term = True            # calves off the ice / off-grid
        if term:
            dist[y, x] = 0
            stack.append((y, x))
    while stack:                       # multi-source BFS upstream
        y, x = stack.pop()
        for py, px in rev.get((y, x), ()):
            if dist[py, px] < 0:
                dist[py, px] = dist[y, x] + 1
                stack.append((py, px))
    d = np.where(dist < 0, TAPER_CELLS, dist).astype(np.float64)
    scale = np.sqrt(np.clip(d / TAPER_CELLS, 0.0, 1.0))
    return np.where(glacier, scale, 1.0).astype(np.float32)


# persistence (firn) rule: a cell joins the growth zone only when the
# REGIONAL annual surplus is a substantial share of the year's
# snowfall. Per-cell ">0" is a knife-edge — the whole subpolar margin
# sits within weather-sampling noise of it, which lattices the mask.
PERSIST_FIRN = 0.5        # smoothed surplus > half the smoothed snowfall
PERSIST_SMOOTH = 2        # 3x3 mean passes regionalizing the balance


def _box3(a: np.ndarray, passes: int = PERSIST_SMOOTH) -> np.ndarray:
    """3x3 mean smoothing, edge-replicated — regionalizes a per-cell
    field (the biome modal filter's continuous cousin)."""
    out = a.astype(np.float64)
    for _ in range(passes):
        p = np.pad(out, 1, mode="edge")
        s = np.zeros_like(out)
        for dy in range(3):
            for dx in range(3):
                s += p[dy:dy + a.shape[0], dx:dx + a.shape[1]]
        out = s / 9.0
    return out


def detect_glaciers(hydro: dict, climate: dict) -> dict | None:
    """The glacier pass over the current routing: growth-zone ice
    routed downslope (glacier_flow) plus equilibrium thickness from the
    throughput. The growth zone is judged REGIONALLY (smoothed annual
    snow balance, firn-share threshold) — a per-cell rule lattices the
    subpolar margin with weather-sampling noise. Returns the glacier
    state dict, or None when the climate lacks the snow-partition
    fields (synthetic test climates).
    """
    if not ("snowfall_monthly" in climate and "meltpot_monthly" in climate
            and "snowmelt_monthly" in climate):
        return None
    land = ~hydro["ocean_mask"] & ~hydro["lake_mask"]
    sf = climate["snowfall_monthly"].astype(np.float64)
    melt = climate["snowmelt_monthly"].astype(np.float64)
    production = np.clip(sf.sum(axis=0) - melt.sum(axis=0), 0.0, None)
    persist = (_box3(production) > PERSIST_FIRN * _box3(sf.sum(axis=0))) \
        & land
    g_mask, g_flux, melt_m = glacier_flow(
        hydro["flow_dir"], hydro["flat_depth"], hydro["w_route"], land,
        sf, climate["meltpot_monthly"].astype(np.float64), melt,
        persist=persist)
    return {
        "glacier_mask": g_mask,
        "glacier_flux": g_flux.astype(np.float32),
        "glacier_melt_monthly": melt_m.astype(np.float32),
        "glacier_thick_m": np.where(
            g_mask,
            glacier_thickness(g_flux)
            * terminus_taper(g_mask, hydro["flow_dir"]),
            0.0).astype(np.float32),
    }


def _dilate8(mask: np.ndarray) -> np.ndarray:
    """8-neighbor dilation, no wraparound."""
    p = np.pad(mask, 1)
    out = np.zeros_like(mask)
    for dy in range(3):
        for dx in range(3):
            out |= p[dy:dy + mask.shape[0], dx:dx + mask.shape[1]]
    return out


def glacial_terrain(elev: np.ndarray, hydro: dict, sea_level: float
                    ) -> tuple[np.ndarray, bool]:
    """The land's one-shot response to its ice (detect-once/respond-once):

    - EROSION: glacier beds deepen ∝ flux^1/3 (quarrying/abrasion scale
      with throughput), dry land only — standing-water beds are never
      eroded (the carve_gorges rule). Overdeepened beds refill as tarns
      on the re-route — real glacial lakes.
    - DEPOSITION: the eroded volume is dumped around the termini
      (glacier cells whose downstream is not glacier) as a
      moraine/outwash bump, decaying ring by ring — mass conserved.
    - ICE RAISE: ice sits ON the land — glacier cells rise by the
      equilibrium thickness (the persisted glacier_thick_m).

    Pure function of the persisted glacier state — no K1 draws.
    Returns (elev2, changed).
    """
    g = hydro.get("glacier_mask")
    if g is None or not g.any():
        return elev, False
    from exp.k11_worldgen.units import ELEV_MAX_M
    flux = hydro["glacier_flux"].astype(np.float64)
    thick = hydro["glacier_thick_m"].astype(np.float64)
    water = hydro["lake_mask"] | hydro["ocean_mask"]
    scale = (1.0 - sea_level) / ELEV_MAX_M   # normalized units per meter
    h = elev.astype(np.float64).copy()

    erode_m = np.where(g & ~water, ERODE_A * np.cbrt(flux), 0.0)
    removed = float(erode_m.sum())
    h -= erode_m * scale

    # termini: glacier cells whose D8 downstream is not glacier (pits
    # and calving fronts included — their load dumps in place / at the
    # waterline)
    H, W = g.shape
    direction = hydro["flow_dir"]
    downstream_g = np.zeros_like(g)
    for i, (dy, dx) in enumerate(_D8):
        m = g & (direction == i)
        ny = np.clip(np.arange(H)[:, None] + dy, 0, H - 1)
        nx = np.clip(np.arange(W)[None, :] + dx, 0, W - 1)
        downstream_g |= m & g[ny, nx]
    term = g & ~downstream_g
    ring1 = _dilate8(term) & ~term
    ring2 = _dilate8(term | ring1) & ~term & ~ring1
    deposit_m = (term + DEPOSIT_DECAY * ring1
                 + DEPOSIT_DECAY ** 2 * ring2).astype(np.float64)
    deposit_m *= removed / max(float(deposit_m.sum()), 1e-9)
    h += deposit_m * scale

    h += np.where(g, thick, 0.0) * scale
    return h.astype(elev.dtype), True


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
                   acc: np.ndarray, lake: np.ndarray | None = None
                   ) -> np.ndarray:
    """Strahler stream order over river cells, processed upstream-first
    (ascending accumulation). Headwaters are order 1; a confluence of two
    equal-order k streams yields k+1, otherwise the max continues.

    When `lake` is given, lake cells act as order CONDUITS: they carry
    the max incoming order through to the outlet (no increment — the
    lake is one body). Without this, a river's order restarts at 1
    every time it crosses a lake, so a Strahler-3 river visibly
    "turns into 1" at the outlet."""
    H, W = river.shape
    order = np.zeros((H, W), dtype=np.int16)
    order[river] = 1
    path = river if lake is None else river | lake
    ys, xs = np.where(path)
    for y, x in sorted(zip(ys.tolist(), xs.tolist()), key=lambda c: acc[c]):
        ups = []
        for dy, dx in _D8:
            ny, nx_ = y + dy, x + dx
            if (0 <= ny < H and 0 <= nx_ < W and path[ny, nx_]):
                d = direction[ny, nx_]
                if d >= 0 and (ny + _D8[d][0], nx_ + _D8[d][1]) == (y, x):
                    ups.append(int(order[ny, nx_]))
        # order-0 upstreams are lakes with no river inflow — a stream
        # leaving such a lake is a headwater, not a continuation
        ups = [u for u in ups if u > 0]
        if not ups:
            continue
        top = max(ups)
        if lake is not None and lake[y, x]:
            order[y, x] = top
        else:
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
        direction, flat_depth = flow_direction(w, h)
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
                      cell_km2: float = 16.0,
                      evap: np.ndarray | None = None) -> np.ndarray:
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
      `evap` (the climate's Clausius-Clapeyron factor, pass 2 only)
      scales the flushing threshold DOWN in the cold: with little
      evaporation a modest inflow keeps the lake fresh (Titicaca),
      while a trickle-fed terminal still brines up even on a cold
      plateau (Uyuni)."""
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
                # evaporation opposes flushing: the effective flush is
                # inflow per unit evaporation, so a cold basin needs
                # far less inflow to stay fresh
                ev = (float(np.mean([evap[y, x] for y, x in comp]))
                      if evap is not None else 1.0)
                value = float(220.0 * np.exp(-ratio / (120.0 * ev)))
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
    (interim render class 1-3 by upstream AREA — the final, water-keyed
    classes are computed in refine_hydrology once climate exists),
    lake_mask, ocean_mask.
    """
    from kernel.hashrng import Stream

    w = priority_flood(h, ocean_mask)
    w_capped = _cap_inland_seas(w.copy(), h, ocean_mask, sea_level)
    # the water balance is judged on the CAPPED candidate surface: an
    # inland sea's true depth is to sea level, not to its rim sill
    depth_c = np.maximum(w_capped - h, 0.0)
    depth_c[ocean_mask] = 1.0  # ocean is water by definition
    direction, flat_depth = flow_direction(w, h)
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
    direction, flat_depth = flow_direction(w, h)
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

    order = strahler_order(direction, river, acc, lake=lake)
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


def speed_jitter(seed: int, shape: tuple[int, int]) -> np.ndarray:
    """Seeded multiplicative reach jitter (e^+-SPEED_JITTER), one draw
    per cell — the sub-grid variance around the Manning reach average.
    Shared by the annual and monthly speed fields, so a reach keeps its
    character year-round. K1-reproducible: same seed, same field."""
    from kernel.hashrng import Stream
    stream = Stream(seed, "k11.hydro.speed")
    H, W = shape
    u = np.array([[stream.uniform(y * W + x, 0) for x in range(W)]
                  for y in range(H)])
    return np.exp(SPEED_JITTER * (2.0 * u - 1.0)).astype(np.float32)


def _momentum_relax(v: np.ndarray, river_mask: np.ndarray,
                    direction: np.ndarray, gamma: float) -> np.ndarray:
    """Upstream->downstream momentum relaxation over the river subgraph.

    Kahn topological order (each cell has <=1 out-edge), so every cell's
    final value is settled before its downstream neighbor reads it; a
    cell with several upstreams takes the best inherited speed. A cycle
    (should not exist on a filled surface) would keep its Manning
    values — the queue just never reaches it."""
    H, W = v.shape
    ys, xs = np.nonzero(river_mask)
    n = len(ys)
    if n == 0:
        return v
    idx_of = np.full((H, W), -1, dtype=np.int64)
    idx_of[ys, xs] = np.arange(n)
    down = np.full(n, -1, dtype=np.int64)
    indeg = np.zeros(n, dtype=np.int64)
    for k in range(n):
        dy, dx = _D8[int(direction[ys[k], xs[k]])]
        ny, nx = ys[k] + dy, xs[k] + dx
        if 0 <= ny < H and 0 <= nx < W:
            j = idx_of[ny, nx]
            if j >= 0:
                down[k] = j
                indeg[j] += 1
    out = v[ys, xs].astype(np.float64).copy()
    queue = [k for k in range(n) if indeg[k] == 0]
    head = 0
    while head < len(queue):
        k = queue[head]
        head += 1
        j = down[k]
        if j < 0:
            continue
        if gamma * out[k] > out[j]:
            out[j] = gamma * out[k]
        indeg[j] -= 1
        if indeg[j] == 0:
            queue.append(j)
    vv = v.astype(np.float64).copy()
    vv[ys, xs] = out
    return vv


def river_speed(discharge: np.ndarray, river_mask: np.ndarray,
                w_route: np.ndarray, direction: np.ndarray,
                sea_level: float,
                jitter: np.ndarray | None = None,
                momentum: float = MOMENTUM_GAMMA) -> np.ndarray:
    """Manning velocity on river cells (m/s), 0 off-river.

    MOVED from K14 (derived.river_speed) — K11 owns the physics and
    PERSISTS the field; downstream reads, never re-derives. Regime
    geometry: width = 8 Q^0.5, depth = 0.3 Q^0.4, slope = filled-
    surface (w_route) drop along flow_dir. With 4 km relief this is a
    reach AVERAGE; pass `jitter` (speed_jitter) to stand in for the
    sub-grid variance around it.

    Order: Manning -> momentum relaxation (momentum=gamma; 0 disables)
    -> jitter, so the jitter stays a purely multiplicative reach
    character and the momentum graph sees un-jittered speeds.
    """
    from exp.k11_worldgen.units import alt_m
    dis = discharge * Q_M3S_PER_UNIT          # m3/s
    d = np.maximum(DEPTH_COEF * np.maximum(dis, 0.0) ** 0.4, 0.05)
    alt = alt_m(w_route, sea_level)
    H, W = dis.shape
    drop = np.zeros_like(dis)
    for i, (dy, dx) in enumerate(_D8):
        m = direction == i
        ny = np.clip(np.arange(H)[:, None] + dy, 0, H - 1)
        nx = np.clip(np.arange(W)[None, :] + dx, 0, W - 1)
        drop = np.where(m, alt - alt[ny, nx], drop)
    slope = np.maximum(drop / CELL_M, MIN_SLOPE)
    v = (1.0 / MANNING_N) * d ** (2.0 / 3.0) * np.sqrt(slope)
    v = V_RIVER_MAX * np.tanh(v / V_RIVER_MAX)   # leaky ceiling
    if momentum:
        v = _momentum_relax(v, river_mask, direction, momentum)
    if jitter is not None:
        v = v * jitter
    return np.where(river_mask, v, 0.0).astype(np.float32)


def refine_hydrology(hydro: dict, elev: np.ndarray, climate: dict,
                     sea_level: float, seed: int = 0,
                     river_threshold: float = 40.0,
                     alpha: float = 4.0,
                     glacier_state: dict | None = None) -> dict:
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
    - glaciers: where annual snowfall beats annual melt the snow
      bucket diverges; the surplus ice is routed downslope
      (glacier_flow), ablation eats it below the equilibrium line,
      and the terminus meltwater joins the monthly discharge.
    - monthly discharge: each month's water (rain + snowmelt +
      glacier melt + soil baseflow — the standing soil moisture keeps
      leaking to streams, so trunks survive rainless months) is routed
      and persisted with its monthly threshold. The monthly NETWORKS
      are the complex builder's job (complexify.derive_complex): one
      month-aware network, monthly width classes on its edges.

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

    order = strahler_order(direction, river, acc, lake=lake)
    # width classes are WATER-keyed, like the monthly classes and the
    # RV labels: class 2/3 at 6x/30x the stream threshold in discharge
    # terms — a big dry basin renders thin (Nile effect), a wet one
    # renders wide. (Pass 1's area-keyed classes are interim only.)
    width = np.zeros((h.shape), dtype=np.int16)
    width[river] = 1
    if p_mean > 1e-9:
        thr_w = river_threshold * p_mean
        width[river & (discharge >= thr_w * 6)] = 2
        width[river & (discharge >= thr_w * 30)] = 3

    # ---- glaciers: net-growth zones export ice downslope ----
    # Where annual snowfall beats annual melt the snowpack bucket
    # grows without bound year over year — ice does not pile up
    # forever, it FLOWS (glacier_flow); its meltwater joins the monthly
    # discharge below, so glacier-fed rivers swell in the melt season.
    # Detection normally runs ONCE, upstream of the glacial-terrain
    # response (__main__) — when the state is handed in, reuse it: the
    # terrain already responded, re-detecting would be a second
    # iteration.
    if glacier_state is None:
        glacier_state = detect_glaciers(hydro, climate)
    glacier_melt_m = None
    if glacier_state is not None:
        hydro.update(glacier_state)
        glacier_melt_m = glacier_state["glacier_melt_monthly"] \
            .astype(np.float64)

    # ---- monthly discharge: each month's actual water ----
    # rain + snowmelt + glacier melt + soil BASEFLOW (the standing
    # soil moisture keeps leaking to streams, so trunks survive
    # rainless months). The monthly NETWORKS are not decided here:
    # the month-aware complex builder (complexify.derive_complex)
    # reads these planes — monthly width classes hang on the ONE
    # network's edges, seasonal water joins or floats beside it.
    hydro.update({"w": w, "depth": depth, "river_mask": river,
                  "lake_mask": lake, "order": order, "width": width})
    # synthetic climates (unit tests) may not carry the monthly fields;
    # production climates always do
    if "P_monthly" in climate and "snowmelt_monthly" in climate:
        from exp.k11_worldgen.units import P_MAX_MM
        P_m = climate["P_monthly"]
        melt = climate["snowmelt_monthly"]
        if glacier_melt_m is not None:
            melt = melt + glacier_melt_m
        soil = climate.get("soil_monthly")
        dis_m = np.zeros((12, H, W), dtype=np.float32)
        w_bar = 0.0
        for m in range(12):
            w_m = P_m[m] + melt[m] / P_MAX_MM
            if soil is not None:
                w_m = w_m + SOIL_BASEFLOW * soil[m]
            dis_m[m] = flow_accumulation(w_route, direction, flat_depth,
                                         weight=w_m)
            w_bar += float(w_m[land].mean()) if land.any() else 0.0
        # ONE bar all year — the SAME scalar that drew the annual
        # network (river_threshold * p_mean). A per-month bar (global
        # land-mean wetness that month) inverted seasonality: basins
        # whose wet season is out of phase with the global mean lost
        # their river exactly in their wettest months; a melt/baseflow-
        # inflated constant bar would dry the annual network out most
        # of the year, contradicting the baseline. Monthly classes are
        # monthly discharge vs the annual bar — the annual network
        # changes class, never location. Fallback for rainless
        # (synthetic) climates: the total-wetness mean, so baseflow
        # worlds still classify.
        thr_base = river_threshold * (p_mean if p_mean > 1e-9
                                      else w_bar / 12.0)
        thr_m = np.full(12, thr_base)
        hydro["discharge_monthly"] = dis_m
        hydro["river_threshold_monthly"] = thr_m
    # ---- river speed: Manning reach-average, persisted first-class ----
    # K14 (and anything later) reads h_river_speed / h_river_speed_monthly;
    # it never re-derives velocity. The per-cell jitter stands in for
    # sub-grid variance around the 4 km reach average.
    jitter = speed_jitter(seed, river.shape)
    hydro["river_speed"] = river_speed(
        hydro["discharge"], river, w_route, direction, sea_level, jitter)
    if "discharge_monthly" in hydro:
        hydro["river_speed_monthly"] = np.stack([
            river_speed(hydro["discharge_monthly"][m], river, w_route,
                        direction, sea_level, jitter)
            for m in range(12)]).astype(np.float32)
    # pass 2 knows the climate: salt concentration now feels the
    # local evaporation (mean-annual temperature through the shared
    # Clausius-Clapeyron factor) as well as the flushing ratio
    from exp.k11_worldgen.climate import evap_factor
    t_ann = climate["T_monthly"].mean(axis=0)
    hydro["salinity"] = classify_salinity(hydro, evap=evap_factor(t_ann))
    hydro["hand"] = height_above_drainage(
        h, w_route, direction, ocean_mask | lake | river)
    return hydro
