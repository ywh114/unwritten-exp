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
from exp.k11_worldgen.units import DEPTH_MAX_M, ELEV_MAX_M

FACTOR = 4  # 256² @ 4 km anchors -> 1024² @ 1 km delivered

GLACIER_HI_FRAC = 0.5  # delivered-resolution ice extent: interpolated
                       # mask above this fraction counts as glacier
GLACIER_HI_FULL_M = 25.0  # anchor ice thinner than this is partial
                          # sub-cell cover: the extent threshold rises,
                          # thinning the rendered tongue tip


def glacier_extent_hires(hydro: dict, factor: int) -> np.ndarray | None:
    """Glacier extent at the delivered resolution. The extent itself is
    an anchor-level decision (like the lake core), but kron-stamping
    the mask turns tongue edges and tips into 4x4 km blocks. Instead
    the mask is interpolated as a continuous field and re-thresholded:
    the boundary lands where the anchor cells said it was, rendered on
    the fine grid (diagonal edges) without inventing or losing area.
    Where the (tapered) anchor thickness is thin — the snout — the
    threshold rises toward 1, so thin tips shrink to partial sub-cell
    cover instead of ending as full blocks. Thickness interpolation is
    NOT the primary extent signal — full-thickness interpolation
    bleeds a whole anchor cell past the margin and fattens thin
    tongues; here it only modulates the thin fringe."""
    if "glacier_mask" not in hydro:
        return None
    m = upsample_bicubic(hydro["glacier_mask"].astype(np.float64), factor)
    thick = hydro.get("glacier_thick_m")
    if thick is None:
        return m > GLACIER_HI_FRAC
    t = np.clip(upsample_bicubic(thick.astype(np.float64), factor),
                0.0, None)
    frac = GLACIER_HI_FRAC + (1.0 - GLACIER_HI_FRAC) * np.clip(
        (GLACIER_HI_FULL_M - t) / GLACIER_HI_FULL_M, 0.0, 1.0)
    return m > frac


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
    (a grid-routing artifact); magnified to the delivered grid and
    stamped at width, they read as knots. Collapsing sub-`tol`
    deviations removes them; endpoints (shared node cells) are
    preserved by construction."""
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


def _smooth_centerline(pts: list[tuple[float, float]],
                       window: int) -> list[tuple[float, float]]:
    """Pinned-endpoint moving average (render cosmetic). A D8 path
    approximates the true flow bearing by alternating the two
    direction ticks bracketing it — a staircase whose bearing still
    reads as the grid's 45-degree lock. Averaging over a few cells
    turns the staircase into the true-bearing curve; endpoints (shared
    node cells) are preserved by construction."""
    if len(pts) <= 2 or window < 3:
        return pts
    k = window // 2
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        lo, hi = max(0, i - k), min(len(pts), i + k + 1)
        n = hi - lo
        out.append((sum(p[0] for p in pts[lo:hi]) / n,
                    sum(p[1] for p in pts[lo:hi]) / n))
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
                 quality_override: dict | None = None,
                 want_owner: bool = False) -> np.ndarray:
    """Stamp the river network (scaled, smoothed polylines) onto the
    delivered grid at width-class radius. Returns the width-class array.

    EVERY edge stamps — the network is the network; dropping short
    edges would hole the rendered network wherever sources and
    confluences sit close together (the "disconnected clusters"
    artifact).

    `quality_override` (edge id -> width class) drives the MONTHLY
    stamps: the stamp radius and taper follow the month's class and
    class-0 edges are skipped, while the PATH cosmetics (jitter,
    meander) always use the edge's natural quality — so a permanent
    reach renders pixel-identical every month, only its width moves.

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

    def q_of(eid: str, natural: float) -> float:
        if quality_override is None:
            return natural
        return quality_override.get(eid, natural)

    # max quality of the edges feeding each node — width TAPER: a
    # river widens ALONG its course, never jumps a class at an edge
    # boundary (a 1-cell width-3 segment reads as a ball, not a river)
    feed_q: dict[str, float] = {}
    for e0 in complex_.edges.values():
        feed_q[e0.node_b] = max(feed_q.get(e0.node_b, 0.0),
                                q_of(e0.id, e0.quality))

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
        q = q_of(e.id, e.quality)
        if q <= 0:
            continue                # dry this month / seasonal off-view
        base = [(x * factor, y * factor) for x, y in
                ((p[0], p[1]) for p in e.polyline)]
        # collapse 1-cell flat-routing detours BEFORE any cosmetic
        # wiggle — magnified and stamped at width, they read as knots
        base = _simplify(base, 1.25 * factor)
        # dequantize the D8 bearing: the staircase between the two
        # ticks bracketing the true flow angle averages to that angle
        base = _smooth_centerline(base, window=2 * factor + 1)
        # jitter scales DOWN with width class: creeks wiggle, wide
        # rivers are smooth (a fat stamp over tight jitter is a blob).
        # PATH cosmetics always use the NATURAL quality — a permanent
        # reach's path is identical every month, only the stamp
        # radius (from q, the month's class) moves.
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
        q_start = feed_q.get(e.node_a, q)

        def stamp(a: tuple[float, float], b: tuple[float, float],
                  step: int, r: int) -> None:
            def dot(x: int, y: int) -> None:
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

            # ceil, never truncate: with floor, a fractional span
            # (2.97 -> 2 steps of 1.485) rounds onto 81, 80, 78 and
            # SKIPS a pixel row — the 1-px holes along every reach
            steps = max(1, int(np.ceil(max(abs(b[0] - a[0]),
                                           abs(b[1] - a[1])))))
            px = py = None
            for s in range(steps + 1):
                x = int(round(a[0] + (b[0] - a[0]) * s / steps))
                y = int(round(a[1] + (b[1] - a[1]) * s / steps))
                # bridge diagonal steps: a corner-touching pixel pair
                # reads as a 1-px gap on thin (rr=0) reaches
                if px is not None and x != px and y != py:
                    dot(x, py)
                dot(x, y)
                px, py = x, y

        prev = (base[0] if base else pts[0])
        hold = 0   # clamp hysteresis: after a fallback, keep the
                   # reduced scale for a few points (no sawtooth)
        for i in range(1, n):
            join = i >= n - 4
            # radius tapers to the edge's CURRENT class (the month's
            # when stamped with an override), from the upstream feed
            r_i = max(0, int(round(q_start + (q - q_start)
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
    if want_owner:
        return width, owner
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
                  edge_monthly: dict | None = None,
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
    # physical depth in METERS: ocean bathymetry from terrain below sea
    # level (the old normalized field forced every ocean cell to 1.0 —
    # a water mask, useless in the viewer tooltip), lake fill depth from
    # the fill surface over the bed
    depth_m_hi = np.where(
        ocean_hi,
        np.maximum(sea_level - elev_hi, 0.0) / sea_level * DEPTH_MAX_M,
        depth_hi / (1.0 - sea_level) * ELEV_MAX_M)

    # rivers: vector network stamped at width class (pointwise derive).
    # Seasonal edges (kind "river_seasonal") carry no annual water —
    # the annual view skips them via the override.
    width_hi, river_owner = river_raster(
        complex_, (H, W), factor, w=hydro["w"],
        sea_level=sea_level,
        phantom=(hydro["w_route"] - hydro["w"]) > 1e-9,
        quality_override={
            e.id: (e.quality if e.kind == "river" else 0.0)
            for e in complex_.edges.values()},
        want_owner=True)
    # delivered-res river SPEED: per-edge reach average from the anchor
    # speed field (mean over the polyline's anchor cells), painted along
    # the SAME stamped path via the owner map. Upsampling the anchor
    # speed field instead left 82% of delivered river pixels at 0 — the
    # meandering delivered line does not follow the anchor 4x4 blocks.
    spd_a = hydro.get("river_speed")
    if spd_a is None:
        # not persisted on this hydro (unit-test worlds skip refine) —
        # K11 owns the physics, so compute it on the spot
        from exp.k11_worldgen.hydrology import river_speed
        spd_a = river_speed(hydro["discharge"], hydro["river_mask"],
                            hydro["w_route"], hydro["flow_dir"], sea_level)
    ha, wa = spd_a.shape
    edge_speed = np.zeros(len(complex_.edges), dtype=np.float32)
    for ei, e in enumerate(complex_.edges.values()):
        vals = [float(spd_a[min(max(int(py), 0), ha - 1),
                            min(max(int(px), 0), wa - 1)])
                for px, py in e.polyline]
        edge_speed[ei] = float(np.mean(vals)) if vals else 0.0
    speed_hi = np.where(river_owner >= 0,
                        edge_speed[np.maximum(river_owner, 0)], 0.0)
    # rivers are an overlay; standing water wins where they coincide
    # (lake-outlet polylines start inside the interpolated lake extent)
    river_hi = (width_hi > 0) & ~ocean_hi & ~lake_hi
    speed_hi = np.where(river_hi, speed_hi, 0.0).astype(np.float32)

    # monthly river state: the SAME complex stamped once per month with
    # that month's per-edge width class — permanent reaches render
    # pixel-identical to the annual stamp (same path, same cosmetics),
    # only the radius moves; seasonal edges appear in their wet months
    river_width_monthly_hi = None
    river_speed_monthly_hi = None
    if edge_monthly:
        stamps = [
            river_raster(complex_, (H, W), factor, w=hydro["w"],
                         sea_level=sea_level,
                         phantom=(hydro["w_route"] - hydro["w"]) > 1e-9,
                         quality_override={eid: cls[m] for eid, cls in
                                           edge_monthly.items()},
                         want_owner=True)
            for m in range(12)]
        river_width_monthly_hi = np.stack([s[0] for s in stamps]) \
            .astype(np.int8)
        # monthly delivered speed, same convention as the annual one:
        # per-edge reach speed (mean anchor monthly speed along the
        # polyline) painted via the month's owner map — seasonal edges
        # carry their wet-month speeds along the stamped path
        spd_m = hydro.get("river_speed_monthly")
        if spd_m is not None:
            ha2, wa2 = spd_m.shape[1:]
            edge_speed_m = np.zeros((12, len(complex_.edges)),
                                    dtype=np.float32)
            for ei, e in enumerate(complex_.edges.values()):
                ys = np.clip([int(py) for px, py in e.polyline], 0, ha2 - 1)
                xs = np.clip([int(px) for px, py in e.polyline], 0, wa2 - 1)
                if len(ys):
                    edge_speed_m[:, ei] = spd_m[:, ys, xs].mean(axis=1)
            river_speed_monthly_hi = np.stack([
                np.where(stamps[m][1] >= 0,
                         edge_speed_m[m, np.maximum(stamps[m][1], 0)],
                         0.0)
                for m in range(12)]).astype(np.float32)
        standing = ocean_hi | lake_hi
        river_width_monthly_hi[:, standing] = 0
        if river_speed_monthly_hi is not None:
            river_speed_monthly_hi[:, standing] = 0

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
    glacier_hi = glacier_extent_hires(hydro, factor)
    biome_hi, T_hi, P_hi, p_grow_hi, t_cold_hi = classify_streaming(
        elev_hi, ocean_hi, lake_hi, river_hi, hand_hi,
        climate, sea_level, factor, width_hi=width_hi,
        glacier_hi=glacier_hi)

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
    if river_width_monthly_hi is not None:
        river_width_monthly_hi[:, rim] = 0
    depth_hi[rim] = 0.0
    depth_m_hi[rim] = 0.0
    sal_hi[rim] = 0.0
    biome_hi[rim] = BIOME_ID["rock"]
    cover_hi[rim] = 0.0

    out = {
        "shape": (H, W),
        "elev": elev_hi,
        "w": w_hi,
        "depth": depth_m_hi,
        "ocean_mask": ocean_hi,
        "lake_mask": lake_hi,
        "river_mask": river_hi,
        "river_speed": speed_hi,
        "width": width_hi,
        "salinity": sal_hi,
        "sea_mask": sea_hi,
        "hand": hand_hi,
        "aquatic": aq_hi,
        "T": T_hi,
        "P": P_hi,
        "biome_map": biome_hi,
        # d_cover (this "cover" entry): produced, no L0 consumer yet
        # (fauna-pending)
        "cover": cover_hi,
    }
    if glacier_hi is not None:
        # first-class glacier data at the delivered resolution: the
        # extent mask (smooth-edged, see glacier_extent_hires) and the
        # per-cell ice thickness in meters (interpolated from the
        # tapered anchor field, 0 off the glacier)
        glacier_hi = glacier_hi.copy()
        glacier_hi[rim] = False
        out["glacier_mask"] = glacier_hi
        thick_src = hydro.get("glacier_thick_m")
        if thick_src is not None:
            thick_hi = np.clip(
                upsample_bicubic(thick_src.astype(np.float64), factor),
                0.0, None).astype(np.float32)
            thick_hi[~glacier_hi] = 0.0
        else:
            thick_hi = np.zeros((H, W), dtype=np.float32)
        out["glacier_m"] = thick_hi
    if river_width_monthly_hi is not None:
        out["river_width_monthly"] = river_width_monthly_hi
    if river_speed_monthly_hi is not None:
        out["river_speed_monthly"] = river_speed_monthly_hi
    return out
