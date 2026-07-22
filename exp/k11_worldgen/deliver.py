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
  relational), so the lake mask is the carried fact and is interpolated
  as a float field, not re-derived.
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


def river_raster(complex_: Complex, shape: tuple[int, int], factor: int) -> np.ndarray:
    """Stamp the river network (scaled, smoothed polylines) onto the
    delivered grid at width-class radius. Returns (width_class, mask)."""
    H, W = shape
    width = np.zeros((H, W), dtype=np.int16)
    for e in complex_.edges.values():
        pts = [(x * factor, y * factor) for x, y in
               ((p[0], p[1]) for p in e.polyline)]
        pts = _jitter(pts, f"k11.river|{e.id}|{e.polyline[0]}")
        pts = chaikin(pts, rounds=2)
        r = max(0, int(round(e.quality)) - 1)
        for a, b in zip(pts, pts[1:]):
            steps = max(1, int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))))
            for s in range(steps + 1):
                x = int(round(a[0] + (b[0] - a[0]) * s / steps))
                y = int(round(a[1] + (b[1] - a[1]) * s / steps))
                y0, y1 = max(0, y - r), min(H, y + r + 1)
                x0, x1 = max(0, x - r), min(W, x + r + 1)
                width[y0:y1, x0:x1] = np.maximum(width[y0:y1, x0:x1], r + 1)
    return width


def upscale_world(elev: np.ndarray, hydro: dict, climate: dict,
                  complex_: Complex, sea_level: float,
                  factor: int = FACTOR, seed: int = 0) -> dict:
    """Deliver the anchor world at factor x resolution (1024² @ 1 km)."""
    from exp.k11_worldgen.biomes import classify_streaming

    elev_hi = upsample_bicubic(elev, factor)
    # gentle fine detail at the delivered grid: bicubic patches are only
    # C1, and their 4x4 block seams read as a grid in flat areas and in
    # the hillshade. A low-amplitude rotated fbm (K1-seeded, so renders
    # replay identically) breaks the regularity; masks/biomes re-derive
    # from the noised field, so coasts and lake edges get organic
    # sub-cell wiggle too. Sub-cell terrain FORM is still refinement's
    # job — this is anti-aliasing, not geology (+-30 m).
    from kernel.hashrng import Stream
    from exp.k11_worldgen.raster import fbm
    fine = fbm(Stream(seed, "k11.deliver"), elev_hi.shape, base_cell=12,
               octaves=3, persistence=0.55)
    elev_hi = elev_hi + (fine - 0.5) * 0.006
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
    # neighborhoods so no interpolation wiggle spawns new ponds.
    lake_anchor_hi = upsample_bicubic(hydro["lake_mask"].astype(float), factor) > 0.5
    near_lake = _dilate(lake_anchor_hi, 2 * factor)
    lake_hi = (w_hi - elev_hi > 0.004) & ~ocean_hi & near_lake
    depth_hi = np.maximum(w_hi - elev_hi, 0.0)
    depth_hi[ocean_hi] = 1.0

    # rivers: vector network stamped at width class (pointwise derive)
    width_hi = river_raster(complex_, (H, W), factor)
    # rivers are an overlay; standing water wins where they coincide
    # (lake-outlet polylines start inside the interpolated lake extent)
    river_hi = (width_hi > 0) & ~ocean_hi & ~lake_hi

    # biomes: streaming similarity classify at the delivered resolution
    biome_hi, T_hi, P_hi, p_grow_hi = classify_streaming(
        elev_hi, ocean_hi, lake_hi, river_hi, climate, sea_level, factor)

    from exp.k11_worldgen.biomes import forest_cover
    cover_hi = forest_cover(biome_hi, p_grow_hi)

    # world-edge rim (rfc-game-layer §1: "ocean margins, rim mountain
    # barrier, then void" — the rim is a boundary plate margin all
    # around): the outermost 1 km ring is smooth
    # "rock and ice" a few meters above sea level — land may approach
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
    river_hi[rim] = False
    depth_hi[rim] = 0.0
    biome_hi[rim] = BIOME_ID["rock and ice"]
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
        "T": T_hi,
        "P": P_hi,
        "biome_map": biome_hi,
        "cover": cover_hi,
    }
