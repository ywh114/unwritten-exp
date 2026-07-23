"""K11 — landmarks for the world sheet.

Computes the interesting points/areas of a delivered world: the N
highest peaks (spaced regional maxima, meters via the units layer),
the 2 deepest ocean points, the M largest lakes (km²), the saltiest
lake (g/kg — the salinity layer), the L lowest terrestrial points,
and the biggest river mouths (by discharge — precipitation-weighted
accumulation, km³/yr).
Each mark is (kind, y, x, legend_text) in DELIVERED coordinates;
render_world draws the markers and the legend rows.
"""

from __future__ import annotations

import numpy as np

from exp.k11_worldgen.units import ELEV_MAX_M

KIND_COLOR = {
    "peak": (245, 245, 245),
    "deep": (120, 180, 255),
    "lake": (80, 220, 230),
    "sea": (110, 150, 230),
    "salt": (240, 170, 190),
    "low": (230, 120, 230),
    "mouth": (250, 220, 120),
}


def _m_above(elev: float, sea_level: float) -> int:
    return int(round((elev - sea_level) / (1.0 - sea_level) * ELEV_MAX_M))


def _greedy_spaced(cands: list[tuple[float, int, int]], min_sep: int,
                   limit: int) -> list[tuple[float, int, int]]:
    """Pick highest-value candidates first, rejecting any within
    min_sep cells of an already-picked one."""
    picked: list[tuple[float, int, int]] = []
    for v, y, x in cands:
        if all((y - py) ** 2 + (x - px) ** 2 >= min_sep ** 2
               for _, py, px in picked):
            picked.append((v, y, x))
            if len(picked) >= limit:
                break
    return picked


def _find_summits(elev: np.ndarray, sea_level: float, min_above: float,
                  neighborhood: int, min_sep: int,
                  cap: int) -> list[tuple[float, int, int]]:
    """All regional maxima above sea_level + min_above, highest first.

    Spaced and capped so the ridge graph stays a graph of SUMMITS, not
    of noise bumps (every peak above a threshold, but
    not a tangled web)."""
    r = neighborhood // 2
    is_max = np.ones(elev.shape, dtype=bool)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy or dx:
                is_max &= elev >= np.roll(np.roll(elev, dy, 0), dx, 1)
    cand = sorted(
        ((float(elev[y, x]), int(y), int(x))
         for y, x in np.argwhere(is_max & (elev > sea_level + min_above))),
        reverse=True)
    return _greedy_spaced(cand, min_sep, cap)


def _ridge_path(elev: np.ndarray, a: tuple[int, int], b: tuple[int, int],
                thr: float, margin: int = 32) -> tuple[list[tuple[int, int]], float] | None:
    """Ridge path between two summits, or None if none stays >= thr.

    BFS (4-conn, inside the pair's bounding box + margin — reachability,
    killed when no high-enough path), then the walk back always steps to
    the highest reached neighbor: the ridge crest. Returns (path,
    saddle) where saddle is the path's minimum elevation."""
    from collections import deque

    (ya, xa), (yb, xb) = a, b
    y0 = max(0, min(ya, yb) - margin)
    y1 = min(elev.shape[0], max(ya, yb) + margin + 1)
    x0 = max(0, min(xa, xb) - margin)
    x1 = min(elev.shape[1], max(xa, xb) + margin + 1)
    sub = elev[y0:y1, x0:x1]
    H, W = sub.shape
    sa, sb = (ya - y0, xa - x0), (yb - y0, xb - x0)
    dist = np.full((H, W), -1, dtype=np.int32)
    dist[sa] = 0
    q: deque[tuple[int, int]] = deque([sa])
    found = False
    while q and not found:
        y, x = q.popleft()
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            ny, nx_ = y + dy, x + dx
            if (0 <= ny < H and 0 <= nx_ < W and dist[ny, nx_] < 0
                    and sub[ny, nx_] >= thr):
                dist[ny, nx_] = dist[y, x] + 1
                if (ny, nx_) == sb:
                    found = True
                    break
                q.append((ny, nx_))
    if not found:
        return None
    path = [sb]
    y, x = sb
    while (y, x) != sa:
        best, best_e = None, -1.0
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1),
                       (-1, -1), (-1, 1), (1, -1), (1, 1)):
            ny, nx_ = y + dy, x + dx
            if (0 <= ny < H and 0 <= nx_ < W
                    and dist[ny, nx_] == dist[y, x] - 1
                    and sub[ny, nx_] > best_e):
                best, best_e = (ny, nx_), float(sub[ny, nx_])
        if best is None:
            return None
        path.append(best)
        y, x = best
    saddle = min(float(sub[y, x]) for y, x in path)
    return ([(y + y0, x + x0) for y, x in path], saddle)


def compute_range_lines(delivered: dict, sea_level: float,
                        drop: float = 0.06, min_above: float = 0.22,
                        k_near: int = 3, max_dist: int = 220,
                        peak_cap: int = 40) -> list[list[tuple[int, int]]]:
    """Mountain ranges as ridge polylines between summits. Every summit
    above sea_level + min_above offers edges to its k nearest neighbors;
    a pair is connected iff a ridge path exists that never dips below
    min(summit elevations) − drop — a TIGHT window (~360 m), so paths
    must stay on genuinely high crests rather than wandering open
    plateau. To avoid a tangled web, edges feed a MAXIMUM SPANNING
    FOREST over saddle heights — when two peaks are already connected,
    only the highest path is kept."""
    elev = delivered["elev"]
    peaks = _find_summits(elev, sea_level, min_above, neighborhood=9,
                          min_sep=32, cap=peak_cap)
    # candidate edges with their saddles
    edges: dict[tuple[int, int], tuple[float, list[tuple[int, int]]]] = {}
    for i, (ei, yi, xi) in enumerate(peaks):
        dists = sorted(((yi - yj) ** 2 + (xi - xj) ** 2, j)
                       for j, (_, yj, xj) in enumerate(peaks) if j != i)
        for d2, j in dists[:k_near]:
            if d2 > max_dist ** 2:
                continue
            key = (min(i, j), max(i, j))
            if key in edges:
                continue
            ej = peaks[j][0]
            thr = max(min(ei, ej) - drop, sea_level + 0.12)
            got = _ridge_path(elev, (yi, xi), (peaks[j][1], peaks[j][2]), thr)
            if got is not None:
                path, saddle = got
                edges[key] = (saddle, path)
    # Kruskal maximum spanning forest over saddle heights
    parent = list(range(len(peaks)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    lines: list[list[tuple[int, int]]] = []
    for (i, j), (saddle, path) in sorted(edges.items(),
                                         key=lambda kv: -kv[1][0]):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj
            lines.append(path)
    return lines


def compute_marks(delivered: dict, hydro: dict, sea_level: float,
                  factor: int, n_peaks: int = 5, n_lakes: int = 2,
                  n_lows: int = 2, n_mouths: int = 3) -> list[tuple[str, int, int, str]]:
    elev = delivered["elev"]
    ocean = delivered["ocean_mask"]
    lake = delivered["lake_mask"]
    land = ~ocean & ~lake
    marks: list[tuple[str, int, int, str]] = []

    # peaks: 5x5 regional maxima, highest first, >= 48 km apart
    is_max = np.ones(elev.shape, dtype=bool)
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            if dy or dx:
                is_max &= elev >= np.roll(np.roll(elev, dy, 0), dx, 1)
    cand = sorted(
        ((float(elev[y, x]), int(y), int(x))
         for y, x in np.argwhere(is_max & land & (elev > sea_level + 0.1))),
        reverse=True)
    for i, (v, y, x) in enumerate(_greedy_spaced(cand, 48, n_peaks)):
        marks.append(("peak", y, x, f"P{i + 1} {_m_above(v, sea_level)}M"))

    # largest lakes: 4-connected components, area in km^2 (1 km cells);
    # per-component salinity (g/kg) and the inland-sea flag come along
    # for the saltiest-lake / sea marks
    sal = delivered.get("salinity")
    sea_m = delivered.get("sea_mask")
    H, W = lake.shape
    seen = np.zeros_like(lake)
    comps: list[tuple[float, float, float, float, bool]] = []
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
                cy = float(np.mean([c[0] for c in comp]))
                cx = float(np.mean([c[1] for c in comp]))
                cys = tuple(c[0] for c in comp)
                cxs = tuple(c[1] for c in comp)
                sv = (float(sal[cys, cxs].mean())
                      if sal is not None else 0.0)
                is_sea = (bool((sea_m[cys, cxs].mean()) > 0.5)
                          if sea_m is not None else False)
                comps.append((float(len(comp)), cy, cx, sv, is_sea))
    comps.sort(reverse=True)
    n_sea = 0
    for i, (area, cy, cx, sv, is_sea) in enumerate(comps[:n_lakes]):
        if is_sea:
            n_sea += 1
            marks.append(("sea", int(round(cy)), int(round(cx)),
                          f"SE{n_sea} {int(area)}KM2 {int(round(sv))} G/KG"))
        else:
            marks.append(("lake", int(round(cy)), int(round(cx)),
                          f"LK{i + 1 - n_sea} {int(area)}KM2"))

    # saltiest lake (endorheic brine is a place, not a size class) —
    # only if some lake is genuinely salt (brackish-and-up). When the
    # saltiest IS one of the LK marks, fold the salinity into that
    # label instead of stacking two markers on one component; seas
    # already carry their salinity.
    if comps:
        area, cy, cx, sv, is_sea = max(comps, key=lambda c: c[3])
        if sv > 10.0 and not is_sea:
            sy, sx = int(round(cy)), int(round(cx))
            merged = False
            for j, (kind, y, x, text) in enumerate(marks):
                if kind == "lake" and (y, x) == (sy, sx):
                    marks[j] = (kind, y, x,
                                f"{text} {int(round(sv))} G/KG")
                    merged = True
                    break
            if not merged:
                marks.append(("salt", sy, sx,
                              f"SL1 {int(round(sv))} G/KG"))

    # deepest ocean points (reported negative, like LW), spaced
    if ocean.any():
        vals = elev[ocean]
        k = min(2000, vals.size)
        idx = np.argpartition(vals, k - 1)[:k]
        ys, xs = np.where(ocean)
        cand = sorted((float(vals[i]), int(ys[i]), int(xs[i]))
                      for i in idx.tolist())
        for i, (v, y, x) in enumerate(_greedy_spaced(cand, 48, 2)):
            depth = int(round((sea_level - v) / sea_level * 4000.0))
            marks.append(("deep", y, x, f"DP{i + 1} {-depth}M"))

    # lowest terrestrial points (below-sea depressions if any) — only
    # real depressions: a "lowest point" at sea level is no landmark
    if land.any():
        vals = elev[land]
        k = min(400, vals.size)
        thr = np.partition(vals, k - 1)[k - 1]
        ys, xs = np.where(land & (elev <= thr))
        cand = sorted((float(elev[y, x]), int(y), int(x)) for y, x in zip(ys, xs))
        for i, (v, y, x) in enumerate(_greedy_spaced(cand, 64, n_lows)):
            m = _m_above(v, sea_level)
            if m > -1:
                break  # sorted ascending: no deeper candidates follow
            marks.append(("low", y, x, f"LW{i + 1} {m}M"))

    # biggest river mouths by DISCHARGE: anchor river cells touching the
    # ocean, valued by precipitation-weighted accumulation (normalized
    # units: 1.0 = 400 mm/month over one 16 km^2 cell), reported as
    # km^3/yr (x 0.0768). Endorheic inflows (inland-sea terminals) are
    # not mouths — the cell must touch the connected ocean.
    discharge = hydro.get("discharge", hydro["accumulation"])
    river = hydro["river_mask"]
    oc = hydro["ocean_mask"]
    mouth = np.zeros_like(river)
    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)):
        mouth |= river & np.roll(np.roll(oc, dy, 0), dx, 1)
    cand = sorted(
        ((float(discharge[y, x]), int(y), int(x)) for y, x in np.argwhere(mouth)),
        reverse=True)
    for i, (v, y, x) in enumerate(_greedy_spaced(cand, 12, n_mouths)):
        # 1.0 norm-P = 400 mm/month over 16 km^2 -> 0.0768 km^3/yr
        km3y = int(round(v * 0.0768))
        marks.append(("mouth", y * factor + factor // 2,
                      x * factor + factor // 2, f"RV{i + 1} {km3y}KM3/Y"))

    return marks
