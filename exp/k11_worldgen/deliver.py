"""K11 — delivery: the resolution ladder from anchor grid to final cells.

Systematic rule: an upscale step may only do MECHANICAL
work; anything relational must be finished before it.

- Relational/intensive (plates, faults, priority flood, accumulation,
  water balance, advection, Strahler): computed ONCE at the anchor grid
  (256², 4 km cells), never recomputed after upscaling.
- Continuous state fields (elevation, water surface): interpolated
  (bicubic), inventing no detail — sub-cell detail is L1's job.
- Derived/pointwise quantities (masks, biomes, cover): re-derived at the
  target resolution from the interpolated parents (classification is
  pointwise; interpolating a mask or a class map would be wrong).
  Exception: LAKE EXTENT is an anchor-level decision (water balance is
  relational): the lake interior is the carried fact (eroded anchor
  mask), only the boundary band re-derives from the interpolated
  fields for a smooth waterline.
- Vector geometry (river network with discharge/Strahler/width, complex
  nodes/edges): resolution-free — coordinates scale, polylines get
  seeded interior-vertex wiggle (against D8 diagonal lock) and Chaikin
  corner smoothing at rasterization, on demand.
"""

from __future__ import annotations

import numpy as np

from kernel.complex.cells import Complex

from exp.k11_worldgen.raster import upsample_bicubic

FACTOR = 4  # 256² @ 4 km anchors -> 1024² @ 1 km delivered


def chaikin(points: list[tuple[float, float]], rounds: int = 2) -> list[tuple[float, float]]:
    """Chaikin corner-cutting: smooths a polyline, preserving endpoints."""
    pts = list(points)
    for _ in range(rounds):
        if len(pts) < 3:
            break
        out = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            out.append((0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]))
            out.append((0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1]))
        out.append(pts[-1])
        pts = out
    return pts


def _jitter(points: list[tuple[float, float]], key: str,
            mag: float = 1.4) -> list[tuple[float, float]]:
    """Seeded sub-cell wiggle on INTERIOR vertices (render cosmetic).

    D8 flow paths run in straight diagonals with 90-degree turns — a
    raster artifact, not terrain. Chaikin softens corners but cannot
    un-straighten a long diagonal, so interior vertices get a small
    content-addressed offset (K1, keyed by the edge id + start point:
    same path -> same wiggle) before corner-cutting. Endpoints never
    move: they are node cells shared by several edges. This is a
    RENDER-layer de-gridding; the committed complex keeps grid-true
    polylines so the K9 audit's nodeless-intersection invariant holds.
    """
    import math

    from kernel.hashrng import Stream

    stream = Stream(0, key)
    out = [points[0]]
    for i, (px, py) in enumerate(points[1:-1], 1):
        ang = 2.0 * math.pi * stream.uniform(i, 0)
        r = mag * stream.uniform(i, 1)
        out.append((px + r * math.cos(ang), py + r * math.sin(ang)))
    out.append(points[-1])
    return out


def _simplify(pts: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Ramer–Douglas–Peucker polyline simplification (render cosmetic).

    The anchor flow path makes 1-cell out-and-back detours on flats
    (a BFS artifact); magnified to the delivered grid and stamped at
    width, they read as knots. Collapsing sub-`tol` deviations removes
    them; endpoints (shared node cells) are preserved by construction."""
    import math
    if len(pts) < 3:
        return pts
    (ax, ay), (bx, by) = pts[0], pts[-1]
    dx, dy = bx - ax, by - ay
    n = math.hypot(dx, dy) + 1e-9
    dmax, idx = -1.0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        d = abs(dy * px - dx * py + bx * ay - by * ax) / n
        if d > dmax:
            dmax, idx = d, i
    if dmax <= tol:
        return [pts[0], pts[-1]]
    return _simplify(pts[:idx + 1], tol)[:-1] + _simplify(pts[idx:], tol)


def _meander(pts: list[tuple[float, float]], wavelength: float,
             amplitude: float, phase: float) -> list[tuple[float, float]]:
    """Sine meander along a smoothed polyline (render cosmetic).
    Real meanders run a wavelength of ~10-14 channel widths on low
    gradients; the caller supplies wavelength/amplitude in cells."""
    if len(pts) < 3 or wavelength <= 0 or amplitude <= 0:
        return pts
    import math
    out = [pts[0]]
    s = 0.0
    for i in range(1, len(pts) - 1):
        ax, ay = pts[i - 1]
        bx, by = pts[i]
        cx, cy = pts[i + 1]
        s += math.hypot(bx - ax, by - ay)
        dx, dy = cx - ax, cy - ay
        n = math.hypot(dx, dy) + 1e-9
        off = amplitude * math.sin(2 * math.pi * (s + phase) / wavelength)
        out.append((bx + (-dy / n) * off, by + (dx / n) * off))
    out.append(pts[-1])
    return out


def _resample(pts: list[tuple[float, float]], step: float) -> list[tuple[float, float]]:
    """Subdivide segments longer than `step` — an RDP-collapsed straight
    run is two points, and no downstream wobble can curve two points."""
    import math
    if len(pts) < 2:
        return pts
    out = [pts[0]]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        n = max(1, int(math.hypot(bx - ax, by - ay) / step))
        for s in range(1, n + 1):
            out.append((ax + (bx - ax) * s / n, ay + (by - ay) * s / n))
    return out


def river_raster(complex_: Complex, shape: tuple[int, int], factor: int,
                 w: np.ndarray | None = None,
                 sea_level: float | None = None,
                 phantom: np.ndarray | None = None,
                 min_edge_cells: int = 6) -> np.ndarray:
    """Stamp the river network (scaled, smoothed polylines) onto the
    delivered grid at width-class radius. Returns (width_class, mask).

    Edges shorter than `min_edge_cells` anchor cells are NOT stamped:
    at 1 km delivery a 2-4 cell D8 path can only render as a straight
    diagonal — these are sub-L0 creeks whose actual formation is the
    refinement layer's job (they still exist in the hydro fields for
    discharge and HAND).

    With the anchor water surface `w` passed, low-gradient edges
    MEANDER (real meanders form below ~2 m/km valley slope, at a
    wavelength of ~10 channel widths and a belt a few widths wide);
    steep reaches keep their jittered-straight mountain look.

    Rivers through PHANTOM-FLOOD cells (rejected-lake wetland flats:
    the routing surface stands above the wet one) stamp one width
    class THINNER — in a marsh the discharge spreads over the flat
    and the channels anastomose (Okavango/Biebrza), they do not run
    at the nominal river width.

    SELF-AVOIDANCE by design: cells are stamped with an owner (edge
    id); every candidate center point is collision-checked against
    already-stamped river — its OWN old path (fold-back) and OTHER
    edges (braid/spaghetti) are both rejected, and the point falls
    back toward the un-meandered base path (full, half, quarter, zero
    offset) until it is free. The final points before an edge's end
    node are a join zone: they MAY touch another river — that is what
    a confluence is."""
    H, W = shape
    width = np.zeros((H, W), dtype=np.int16)
    owner = np.full((H, W), -1, dtype=np.int32)
    own_step = np.full((H, W), -1, dtype=np.int32)

    # max quality of the edges feeding each node — width TAPER: a
    # river widens ALONG its course, never jumps a class at an edge
    # boundary (a 1-cell width-3 segment reads as a ball, not a river)
    feed_q: dict[str, float] = {}
    for e0 in complex_.edges.values():
        feed_q[e0.node_b] = max(feed_q.get(e0.node_b, 0.0), e0.quality)

    def free(y: int, x: int, ei: int, step: int, r: int,
             join: bool) -> bool:
        y0, y1 = max(0, y - r - 1), min(H, y + r + 2)
        x0, x1 = max(0, x - r - 1), min(W, x + r + 2)
        ow = owner[y0:y1, x0:x1]
        if not (ow >= 0).any():
            return True
        if join:
            return True
        st = own_step[y0:y1, x0:x1]
        # blocked by another edge, or by our own path from >8 steps back
        other = (ow >= 0) & (ow != ei)
        folded = (ow == ei) & (st >= 0) & (step - st > 8)
        return not (other | folded).any()

    for ei, e in sorted(enumerate(complex_.edges.values()),
                        key=lambda kv: -kv[1].quality):
        if len(e.polyline) < min_edge_cells:
            continue
        base = [(x * factor, y * factor) for x, y in
                ((p[0], p[1]) for p in e.polyline)]
        # collapse 1-cell flat-routing detours BEFORE any cosmetic
        # wiggle — magnified and stamped at width, they read as knots
        base = _simplify(base, 1.25 * factor)
        # jitter scales DOWN with width class: creeks wiggle, wide
        # rivers are smooth (a fat stamp over tight jitter is a blob)
        wc0 = max(1, int(round(e.quality)))
        base = _jitter(base, f"k11.river|{e.id}|{e.polyline[0]}",
                       mag=1.4 / wc0)
        base = chaikin(base, rounds=2)
        # subdivide long segments so the wobble has interior points —
        # an RDP-collapsed straight D8 run is two endpoints, and
        # nothing downstream can curve two endpoints (the long
        # exact-45-degree diagonal artifact)
        base = _resample(base, 6.0)
        # every edge gets a gentle long-wave wobble — D8 centerlines
        # are axis/diagonal-locked even in steep terrain; low-gradient
        # reaches then get the real valley meander on top
        from kernel.hashrng import Stream
        phase0 = 24.0 * Stream(0, f"k11.meander|{e.id}").uniform(0, 1)
        pts = _meander(base, max(24.0, 8.0 * wc0), 2.0 * wc0, phase0)
        if w is not None and sea_level is not None:
            ha, wa = w.shape
            ws = [float(w[min(max(int(py), 0), ha - 1),
                          min(max(int(px), 0), wa - 1)])
                  for px, py in e.polyline]
            # valley slope from the path's total drop (endpoint
            # rounding straddles flats and reads spurious negatives)
            drop_m = (max(ws) - min(ws)) / (1.0 - sea_level) * 6000.0
            slope = drop_m / max(e.length * 4.0, 1e-9)   # m per km
            # marsh edges (mostly phantom-flood cells) do NOT meander:
            # a wetland flat has no valley for a 10-30 km sine to fit
            # into — there it reads as a knot, not a meander
            marsh = False
            if phantom is not None and e.polyline:
                ph, pw = phantom.shape
                marsh = (sum(bool(phantom[min(max(int(py), 0), ph - 1),
                                          min(max(int(px), 0), pw - 1)])
                             for px, py in e.polyline)
                         / len(e.polyline)) > 0.5
            if not marsh and 0.0 <= slope < 2.0:
                wc = max(1, int(round(e.quality)))       # width class ~ km
                # ~10 channel widths, but never more than half the
                # edge's own length — a sub-wavelength edge cannot
                # meander, it can only knot
                lam = min(10.0 * wc, 0.5 * e.length * factor)
                amp = min(0.25 * lam, 2.0 * wc)          # belt ~ a few widths
                phase = lam * Stream(0, f"k11.meander|{e.id}").uniform(0, 0)
                pts = _meander(pts, lam, amp, phase)
        # collision-resolved center path, stamped as it grows so each
        # new point sees the path so far (self fold-back included);
        # the stamp radius TAPERs from the upstream course's width
        n = len(pts)
        q_start = feed_q.get(e.node_a, e.quality)

        def stamp(a: tuple[float, float], b: tuple[float, float],
                  step: int, r: int) -> None:
            steps = max(1, int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))))
            for s in range(steps + 1):
                x = int(round(a[0] + (b[0] - a[0]) * s / steps))
                y = int(round(a[1] + (b[1] - a[1]) * s / steps))
                rr = r
                if phantom is not None and phantom[
                        min(y // factor, phantom.shape[0] - 1),
                        min(x // factor, phantom.shape[1] - 1)]:
                    rr = 0   # wetland: anastomosing channels are thin
                             # whatever the nominal class
                y0, y1 = max(0, y - rr), min(H, y + rr + 1)
                x0, x1 = max(0, x - rr), min(W, x + rr + 1)
                width[y0:y1, x0:x1] = np.maximum(width[y0:y1, x0:x1], rr + 1)
                owner[y0:y1, x0:x1] = ei
                own_step[y0:y1, x0:x1] = step

        prev = (base[0] if base else pts[0])
        hold = 0   # clamp hysteresis: after a fallback, keep the
                   # reduced scale for a few points (no sawtooth)
        for i in range(1, n):
            join = i >= n - 4
            r_i = max(0, int(round(q_start + (e.quality - q_start)
                                   * (i / max(n - 1, 1)))) - 1)
            bx, by = base[i]
            mx, my = pts[i]
            cur = (bx, by)
            if hold > 0:
                hold -= 1
                for scale in (0.0,):
                    cand = (bx + (mx - bx) * scale, by + (my - by) * scale)
                    cur = cand
            else:
                for scale in (1.0, 0.5, 0.25, 0.0):
                    cand = (bx + (mx - bx) * scale, by + (my - by) * scale)
                    xi = int(round(cand[0]))
                    yi = int(round(cand[1]))
                    if free(yi, xi, ei, i, r_i, join):
                        cur = cand
                        if scale < 1.0:
                            hold = 4
                        break
            stamp(prev, cur, i, r_i)
            prev = cur
    return width


def _fill_lake_holes(lake: np.ndarray, ocean: np.ndarray,
                     near_lake: np.ndarray, max_cells: int = 64) -> np.ndarray:
    """Fill small enclosed land specks inside delivered lakes.

    The delivered waterline is re-derived from interpolated fields,
    which speckles: shallow bed bumps inside a lake dip below the
    depth threshold between anchor samples and read as blocky land
    holes — the same artifact the anchor's islet submersion drowned,
    reborn at delivery. Same submersion rule: enclosed specks up to
    max_cells are filled back in (their depth stays 0 — sandbar-
    shallow)."""
    land_band = ~lake & ~ocean & near_lake
    H, W = lake.shape
    seen = np.zeros(lake.shape, dtype=bool)
    for sy in range(H):
        for sx in range(W):
            if not (land_band[sy, sx] and not seen[sy, sx]):
                continue
            comp, stack = [], [(sy, sx)]
            while stack:
                y, x = stack.pop()
                if seen[y, x] or not land_band[y, x]:
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
            if all(lake[ny, nx_] or (ny, nx_) in cells
                   for y, x in comp
                   for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                   if 0 <= (ny := y + dy) < H and 0 <= (nx_ := x + dx) < W):
                for y, x in comp:
                    lake[y, x] = True
    return lake


def upscale_world(elev: np.ndarray, hydro: dict, climate: dict,
                  complex_: Complex, sea_level: float,
                  aquatic: np.ndarray,
                  currents: dict | None = None,
                  factor: int = FACTOR) -> dict:
    """Deliver the anchor world at factor x resolution (1024² @ 1 km)."""
    from exp.k11_worldgen.biomes import classify_streaming

    elev_hi = upsample_bicubic(elev, factor)
    w_hi = upsample_bicubic(hydro["w"], factor)
    H, W = elev_hi.shape

    # masks: ocean CONNECTIVITY is relational (border-connected basins),
    # so like lake extent it is CARRIED from the anchor — re-derived as
    # below-sea cells within the (dilated) anchor ocean region, which
    # covers interpolation wiggle at coasts.
    from exp.k11_worldgen.biomes import _dilate
    ocean_anchor_hi = _dilate(
        upsample_bicubic(hydro["ocean_mask"].astype(float), factor) > 0.5,
        factor)
    ocean_hi = (elev_hi < sea_level) & ocean_anchor_hi
    # lake extent is an anchor-level DECISION (water balance is
    # relational), but its boundary is re-derived from the interpolated
    # FIELDS — w and elev are both bicubic-smooth, so the waterline is a
    # smooth contour that hugs the terrain — confined to anchor-lake
    # neighborhoods so no interpolation wiggle spawns new ponds. The
    # anchor-decided INTERIOR must not flip back to land: between anchor
    # samples, bed bumps would otherwise resurrect islets the anchor
    # already drowned (submerge_islets), as blocky land holes.
    lake_anchor_hi = upsample_bicubic(hydro["lake_mask"].astype(float), factor) > 0.5
    near_lake = _dilate(lake_anchor_hi, 2 * factor)
    lake_core_hi = ~_dilate(~lake_anchor_hi, factor)
    lake_hi = ((w_hi - elev_hi > 0.004) | lake_core_hi) & ~ocean_hi & near_lake
    lake_hi = _fill_lake_holes(lake_hi, ocean_hi, near_lake)
    depth_hi = np.maximum(w_hi - elev_hi, 0.0)
    depth_hi[ocean_hi] = 1.0

    # rivers: vector network stamped at width class (pointwise derive)
    width_hi = river_raster(complex_, (H, W), factor, w=hydro["w"],
                            sea_level=sea_level,
                            phantom=(hydro["w_route"] - hydro["w"]) > 1e-9)
    # rivers are an overlay; standing water wins where they coincide
    # (lake-outlet polylines start inside the interpolated lake extent)
    river_hi = (width_hi > 0) & ~ocean_hi & ~lake_hi

    # salinity is relational (per water body — see classify_salinity):
    # CARRY the anchor field, re-mask to the delivered water
    sal_hi = upsample_bicubic(hydro["salinity"], factor)
    sal_hi = np.where(ocean_hi | lake_hi | river_hi, sal_hi, 0.0)

    # inland seas (relational, anchor-decided): carried with the lake
    # extent; HAND is a continuous field, interpolated like elevation
    sea_hi = (upsample_bicubic(hydro["sea_mask"].astype(float), factor)
              > 0.5) & lake_hi
    hand_hi = upsample_bicubic(hydro["hand"], factor)

    # aquatic biome layer: the RELATIONAL classes are carried per
    # channel — lakes/seas (per-component decisions) and rivers (anchor
    # order/width fields) each spread nearest-value across their own
    # ~2-cell boundary band (covers the re-derived waterline and river
    # jitter), then nearest upsample. Per-channel because the delivered
    # lake extent can reach over anchor RIVER cells at inflow sills —
    # a shared map would class those lake cells as river. The spread is
    # distance-ordered: a cell takes the mode of its already-filled
    # neighbors (ties to the lowest id), so no class leaks outward —
    # the previous max-value spread systematically painted high ids
    # (upwelling, tropical) past their real extent. The marine classes
    # are POINTWISE — recomputed below, not carried.
    aq_anchor = aquatic.astype(np.int16) + 1

    def _spread(seed: np.ndarray) -> np.ndarray:
        fill = seed
        for _ in range(2):
            m = fill == 0
            if not m.any():
                break
            neigh = np.stack([np.roll(np.roll(fill, dy, 0), dx, 1)
                              for dy in (-1, 0, 1) for dx in (-1, 0, 1)
                              if (dy, dx) != (0, 0)])
            best = np.zeros_like(fill)
            score = np.zeros(fill.shape, dtype=np.int16)
            for v in [v for v in np.unique(neigh) if v > 0]:
                c = (neigh == v).sum(axis=0)
                upd = c > score        # ascending v: lowest id wins ties
                score = np.where(upd, c, score)
                best = np.where(upd, v, best)
            fill = np.where(m, best, fill)
        return np.kron(fill, np.ones((factor, factor), dtype=np.int16)) - 1

    kron_lake = _spread(np.where(hydro["lake_mask"], aq_anchor, 0))
    kron_river = _spread(
        np.where(hydro["river_mask"] & ~hydro["lake_mask"], aq_anchor, 0))
    aq_hi = np.zeros((H, W), dtype=np.uint8)
    aq_hi[lake_hi] = np.clip(kron_lake, 0, None)[lake_hi]
    aq_hi[river_hi] = np.clip(kron_river, 0, None)[river_hi]

    # biomes: streaming similarity classify at the delivered resolution
    biome_hi, T_hi, P_hi, p_grow_hi, t_cold_hi = classify_streaming(
        elev_hi, ocean_hi, lake_hi, river_hi, hand_hi,
        climate, sea_level, factor, width_hi=width_hi)

    # marine classes are POINTWISE (depth / temperature / rise), so per
    # the delivery rule they are recomputed on the smooth delivered
    # fields — the kron path is for the relational classes only, and
    # stamping it up turned threshold speckle into visible squares
    from exp.k11_worldgen.aquatic import classify_marine
    from exp.k11_worldgen.units import elev_m, temp_c
    marine_hi = classify_marine(
        ocean_hi, river_hi, width_hi, -elev_m(elev_hi, sea_level),
        temp_c(T_hi), t_cold_hi,
        rise=(upsample_bicubic(currents["rise"], factor)
              if currents is not None else None),
        mouth_band=factor, clear_band=3 * factor)
    open_water = ocean_hi & ~river_hi
    aq_hi[open_water] = marine_hi[open_water]

    from exp.k11_worldgen.biomes import forest_cover
    cover_hi = forest_cover(biome_hi, p_grow_hi)

    # world-edge rim (rfc-game-layer §1: "ocean margins, rim mountain
    # barrier, then void" — the rim is a boundary plate margin all
    # around): the outermost 1 km ring is smooth
    # "rock" a few meters above sea level — land may approach
    # the border but never gets cut off by it; the map edge is a rock
    # wall to the void. (Minimal form: a real rim RANGE from the plate
    # pass is a later refinement; the guarantee is what matters — no
    # landmass touches the void.)
    from exp.k11_worldgen.biomes import BIOME_ID
    rim = np.zeros((H, W), dtype=bool)
    rim[0, :] = rim[-1, :] = rim[:, 0] = rim[:, -1] = True
    elev_hi[rim] = sea_level + 0.002  # ~12 m of smooth rock
    ocean_hi[rim] = False
    lake_hi[rim] = False
    sea_hi[rim] = False
    river_hi[rim] = False
    depth_hi[rim] = 0.0
    sal_hi[rim] = 0.0
    biome_hi[rim] = BIOME_ID["rock"]
    cover_hi[rim] = 0.0

    return {
        "shape": (H, W),
        "elev": elev_hi,
        "w": w_hi,
        "depth": depth_hi,
        "ocean_mask": ocean_hi,
        "lake_mask": lake_hi,
        "river_mask": river_hi,
        "width": width_hi,
        "salinity": sal_hi,
        "sea_mask": sea_hi,
        "hand": hand_hi,
        "aquatic": aq_hi,
        "T": T_hi,
        "P": P_hi,
        "biome_map": biome_hi,
        "cover": cover_hi,
    }
