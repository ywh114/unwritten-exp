"""K11 — PNG renderings of the generated world."""

from __future__ import annotations

import numpy as np

from exp.k11_worldgen.biomes import PALETTE
from exp.k11_worldgen.raster import (
    normalize_u8,
    write_png_gray,
    write_png_palette,
    write_png_rgb,
)


def render_plates(path: str, plates, sea_level_elev: np.ndarray, factor: int = 4) -> None:
    """Tectonic overview at delivered size: macro plates in qualitative
    colors (oceanic dark), white fault lines, over a dim elevation base."""
    mid = plates.macro_id
    H, W = mid.shape
    base = normalize_u8(sea_level_elev, 0.0, 1.0) // 3
    rgb = np.dstack([base] * 3).astype(np.uint8)
    sea = np.array([15, 25, 55], dtype=float)
    for m in range(plates.n):
        cells = mid == m
        if not cells.any():
            continue
        # deterministic qualitative color per plate
        col = np.array([(m * 97 % 156 + 60), (m * 57 % 136 + 60), (m * 167 % 116 + 60)])
        if m in plates.oceanic:
            col = col * 0.4 + np.array([10, 20, 50]) * 0.6
        rgb[cells] = (0.55 * rgb[cells] + 0.45 * col).astype(np.uint8)
    rgb[plates.is_ocean] = (0.5 * rgb[plates.is_ocean] + 0.5 * sea).astype(np.uint8)
    bounds = plate_boundary_mask(plates)
    rgb[bounds] = (240, 240, 240)
    if factor > 1:
        rgb = np.kron(rgb, np.ones((factor, factor, 1), dtype=np.uint8))
    write_png_rgb(path, rgb)


def plate_boundary_mask(plates) -> np.ndarray:
    """Anchor-grid mask of macro-plate boundaries (any pair, land or sea,
    excluding the reserved ocean ring)."""
    mid = plates.macro_id
    b = np.zeros(mid.shape, dtype=bool)
    b[:, :-1] |= (mid[:, :-1] != mid[:, 1:]) & ((mid[:, :-1] >= 0) | (mid[:, 1:] >= 0))
    b[:, 1:] |= (mid[:, :-1] != mid[:, 1:]) & ((mid[:, :-1] >= 0) | (mid[:, 1:] >= 0))
    b[:-1, :] |= (mid[:-1, :] != mid[1:, :]) & ((mid[:-1, :] >= 0) | (mid[1:, :] >= 0))
    b[1:, :] |= (mid[:-1, :] != mid[1:, :]) & ((mid[:-1, :] >= 0) | (mid[1:, :] >= 0))
    return b


def render_world(path: str, delivered: dict, plates, factor: int,
                 seed: int, stats: dict, biome_hist: dict,
                 biome_colors: list[tuple[int, int, int]],
                 marks: list[tuple[str, int, int, str]]) -> None:
    """2048x1024 world sheet: shaded biome map + depth-rendered water +
    rivers + range lines + plate lines + landmarks on the left; legend
    panel on the right."""
    from exp.k11_worldgen.legend import draw_text, fill_rect
    from exp.k11_worldgen.marks import KIND_COLOR

    elev, biome = delivered["elev"], delivered["biome_map"]
    H, W = elev.shape
    sea_level = stats["sea_level"]

    # left: biome color x hillshade on LAND; water is drawn by DEPTH,
    # never hillshaded — hillshaded lakes read as rippling land
    gy, gx = np.gradient(elev)
    shade = np.clip(0.72 + 6.0 * (-(gx + gy) / 1.4142), 0.25, 1.2)
    pal = np.array(biome_colors, dtype=float)
    left = pal[biome] * shade[..., None]
    ocean = delivered["ocean_mask"]
    lake = delivered["lake_mask"]
    # ocean: bathymetric gradient from the interpolated elevation
    depth_t = np.clip(elev / sea_level, 0.0, 1.0)
    deep = np.array([8, 16, 44], dtype=float)
    shallow = np.array([46, 98, 175], dtype=float)
    left[ocean] = (deep + (shallow - deep) * depth_t[..., None])[ocean]
    # lakes: darken with true depth (w - elev)
    lake_t = np.clip(delivered["depth"] / 0.02, 0.0, 1.0)
    lake_shallow = np.array([70, 130, 195], dtype=float)
    lake_deep = np.array([12, 30, 80], dtype=float)
    left[lake] = (lake_shallow + (lake_deep - lake_shallow)
                  * lake_t[..., None])[lake]
    left[delivered["river_mask"]] = (235, 210, 90)
    # plate lines: 2 px at the delivered grid (the 4 px kron blocks were
    # too hard); convergent CC/OC segments = mountain
    # ranges, drawn thicker in the SAME white (orange was too noisy)
    mid_hi = np.kron(plates.macro_id,
                     np.ones((factor, factor), dtype=plates.macro_id.dtype))
    b_hi = np.zeros(mid_hi.shape, dtype=bool)
    b_hi[:, :-1] |= mid_hi[:, :-1] != mid_hi[:, 1:]
    b_hi[:, 1:] |= mid_hi[:, :-1] != mid_hi[:, 1:]
    b_hi[:-1, :] |= mid_hi[:-1, :] != mid_hi[1:, :]
    b_hi[1:, :] |= mid_hi[:-1, :] != mid_hi[1:, :]
    left[b_hi] = (245, 245, 245)
    left = np.clip(left, 0, 255).astype(np.uint8)

    # mountain ranges: ridge polylines connecting summits (maximum
    # spanning forest over saddle heights — no tangled web), 1 px black
    from exp.k11_worldgen.marks import compute_range_lines
    for ridge in compute_range_lines(delivered, sea_level):
        for y, x in ridge:
            left[y, x] = (10, 10, 10)

    # landmarks: diamond markers + labels (black shadow for legibility)
    for kind, y, x, text in marks:
        col = KIND_COLOR[kind]
        for dy, dx in ((0, 0), (-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1),
                       (1, -1), (1, 0), (1, 1), (-2, 0), (2, 0), (0, -2), (0, 2)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < H and 0 <= xx < W:
                left[yy, xx] = col
        tag = text.split(" ")[0]
        draw_text(left, x + 7, y - 5, tag, (0, 0, 0), scale=2)
        draw_text(left, x + 6, y - 6, tag, col, scale=2)

    # right: legend panel (two-column sections)
    right = np.full((H, W, 3), (16, 18, 26), dtype=np.uint8)
    draw_text(right, 48, 48, "K11 WORLDGEN", (235, 235, 235), scale=5)
    draw_text(right, 48, 108, f"SEED {seed}", (180, 200, 235), scale=3)
    lines = [
        f"PLATES {stats['plates']}",
        f"OCEAN {stats['ocean_fraction'] * 100:.1f}%",
        f"RIVERS {stats['river_cells']} CELLS",
        f"LAKES {stats['lake_cells']} CELLS",
        f"MAX STREAM ORDER {stats['max_stream_order']}",
        f"HIGH RELIEF {stats['high_relief_fraction'] * 100:.1f}%",
        "CELL 1 KM - MAP 1024 KM",
    ]
    y = 172
    for ln in lines:
        draw_text(right, 48, y, ln, (190, 190, 190), scale=2)
        y += 26
    draw_text(right, 48, y + 14, "BIOMES", (235, 235, 235), scale=3)
    y += 56
    for i, (name, count, color) in enumerate(biome_hist):
        share = count / (H * W) * 100
        x0 = 48 if i % 2 == 0 else 520
        yy = y + (i // 2) * 27
        fill_rect(right, x0, yy, 44, 18, color)
        draw_text(right, x0 + 54, yy + 2, f"{name.replace('_', ' ')} {share:.1f}%",
                  (200, 200, 200), scale=2)
    y += 27 * ((len(biome_hist) + 1) // 2)
    draw_text(right, 48, y + 14, "LANDMARKS", (235, 235, 235), scale=3)
    y += 56
    for i, (kind, _, _, text) in enumerate(marks):
        col = KIND_COLOR[kind]
        x0 = 48 if i % 2 == 0 else 520
        yy = y + (i // 2) * 26
        fill_rect(right, x0, yy, 18, 18, col)
        draw_text(right, x0 + 28, yy + 2, text, (210, 210, 210), scale=2)

    sheet = np.concatenate([left, right], axis=1)
    write_png_rgb(path, sheet)


def render_loading(out_dir: str, world: dict, delivered: dict,
                   plates, sea_level: float) -> list[str]:
    """One PNG per pipeline stage, `out/loading/load_NN.png` (zero-
    padded), all at the delivered 1024² (anchor stages naively upscaled
    by nearest 4x). Also maintains `out/load.png` -> the newest stage."""
    import os

    load_dir = f"{out_dir}/loading"
    os.makedirs(load_dir, exist_ok=True)
    for stale in os.listdir(load_dir):
        if stale.startswith("load_") and stale.endswith(".png"):
            os.remove(f"{load_dir}/{stale}")
    paths: list[str] = []

    def _w(n, fn, *args):
        p = f"{load_dir}/load_{n:02d}.png"
        fn(p, *args)
        paths.append(p)

    def up4(a):
        return np.kron(a, np.ones((4, 4), dtype=a.dtype))

    _w(1, lambda p: render_plates(p, plates, world["elev"], factor=4))
    _w(2, write_png_gray, up4(normalize_u8(world["elev"], 0.0, 1.0)))
    _w(3, write_png_gray, up4(normalize_u8(np.log1p(world["hydro"]["depth"] * 20), 0.0, 2.0)))
    _w(4, write_png_gray, up4(normalize_u8(world["climate"]["P_pass1"], 0.0, 1.0)))
    _w(5, write_png_gray, up4(normalize_u8(world["climate"]["green"], 0.0, 1.0)))
    _w(6, write_png_gray, up4(normalize_u8(world["climate"]["P"], 0.0, 1.0)))
    _w(7, write_png_gray, up4(normalize_u8(world["climate"]["T"], 0.0, 1.0)))
    _w(8, write_png_palette, up4(world["biome_map"]), PALETTE)
    _w(9, write_png_gray, normalize_u8(delivered["elev"], 0.0, 1.0))
    _w(10, write_png_palette, delivered["biome_map"], PALETTE)

    link = f"{out_dir}/load.png"
    if os.path.lexists(link):
        os.remove(link)
    os.symlink(os.path.relpath(paths[-1], out_dir), link)
    return paths


def render_monthly(out_dir: str, climate: dict) -> list[str]:
    """Write the UNAVERAGED monthly (T, P) curves — the canonical climate
    store — as grayscale PNGs into `<out_dir>/monthly/` (anchor grid)."""
    import os

    os.makedirs(f"{out_dir}/monthly", exist_ok=True)
    paths: list[str] = []
    for m in range(12):
        for key, tag in (("T_monthly", "T"), ("P_monthly", "P")):
            p = f"{out_dir}/monthly/m{m + 1:02d}_{tag}.png"
            write_png_gray(p, normalize_u8(climate[key][m], 0.0, 1.0))
            paths.append(p)
    return paths


def render_all(out_dir: str, delivered: dict, complex_, factor: int = 4) -> list[str]:
    """Write the demo PNG set at the DELIVERED resolution (1024²);
    returns the list of paths."""
    paths: list[str] = []
    elev = delivered["elev"]

    def _w(name, fn, *args):
        p = f"{out_dir}/{name}.png"
        fn(p, *args)
        paths.append(p)

    _w("elevation", write_png_gray, normalize_u8(elev, 0.0, 1.0))
    _w("depth", write_png_gray, normalize_u8(np.log1p(delivered["depth"] * 20), 0.0, 2.0))
    _w("temperature", write_png_gray, normalize_u8(delivered["T"], 0.0, 1.0))
    _w("precipitation", write_png_gray, normalize_u8(delivered["P"], 0.0, 1.0))
    _w("biomes", write_png_palette, delivered["biome_map"], PALETTE)
    _w("forest_cover", write_png_gray, normalize_u8(delivered["cover"], 0.0, 1.0))

    # hydrology.png: elevation hillshade-ish + standing water + river
    # raster (width-class stamped) + node dots. Rivers are NOT filled as
    # water: at L0 a river is drainage crossing the cell, an overlay.
    rgb = np.dstack([normalize_u8(elev, 0.0, 1.0)] * 3).astype(float)
    water = delivered["ocean_mask"] | delivered["lake_mask"]
    rgb[water] = np.array([40, 90, 180])
    river = delivered["river_mask"]
    rgb[river] = np.array([240, 200, 60])
    for n in complex_.nodes.values():
        x = int(round(n.pos[0] * factor))
        y = int(round(n.pos[1] * factor))
        r = 2
        if 0 <= y < rgb.shape[0] and 0 <= x < rgb.shape[1]:
            rgb[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1] = np.array([230, 60, 40])
    _w("hydrology", write_png_rgb, np.clip(rgb, 0, 255).astype(np.uint8))

    return paths
