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
                 marks: list[tuple[str, int, int, str]],
                 aquatic_hists: tuple[list, list] | None = None) -> None:
    """2048x1024 world sheet: shaded biome map + depth-rendered water +
    rivers + range lines + plate lines + landmarks on the left; legend
    panel on the right (TERRESTRIAL / FRESHWATER / MARINE sections when
    the aquatic layer is present)."""
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
    # lakes: same bathymetric scale as the ocean (bed elevation, not
    # w - elev — an inland sea bed IS seabed), fresher tint; lakes above
    # sea level clip to the bright end like tarns should
    lake_shallow = np.array([70, 130, 195], dtype=float)
    lake_deep = np.array([12, 30, 80], dtype=float)
    left[lake] = (lake_deep + (lake_shallow - lake_deep)
                  * depth_t[..., None])[lake]
    # inland seas are drawn on the OCEAN bathymetric ramp, not the lake
    # one — a Caspian is a piece of ocean that lost its outlet, not a
    # big pond
    sea = delivered.get("sea_mask")
    if sea is not None:
        left[sea] = (deep + (shallow - deep) * depth_t[..., None])[sea]
    # aquatic biome layer: water recolored toward its class color over
    # the bathymetry (deep open ocean stays pure depth; coral and salt
    # lakes read strongest — they are places, not depths). Rivers draw
    # in their class color.
    aq = delivered.get("aquatic")
    if aq is not None:
        from exp.k11_worldgen.aquatic import AQUATIC_ID, AQUATIC_PALETTE
        pal_aq = AQUATIC_PALETTE.astype(float)
        water = ocean | lake
        blend = np.full((H, W), 0.45)
        blend[aq == AQUATIC_ID["open ocean"]] = 0.0
        blend[aq == AQUATIC_ID["coral reef"]] = 0.75
        blend[aq == AQUATIC_ID["salt lake"]] = 0.75
        b3 = blend[..., None]
        left[water] = (left * (1.0 - b3) + pal_aq[aq] * b3)[water]
        left[delivered["river_mask"]] = pal_aq[aq][delivered["river_mask"]]
    else:
        left[delivered["river_mask"]] = (235, 210, 90)
    # mangrove stands can sit on very shallow SEA (tidal flats) — repaint
    # them over the bathymetry so they stay visible
    from exp.k11_worldgen.biomes import BIOME_ID
    left[biome == BIOME_ID["mangrove"]] = pal[BIOME_ID["mangrove"]]
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
    draw_text(right, 48, 108, f"SEED {seed:08d}", (180, 200, 235), scale=3)
    # world type, prominent, right under the seed
    cm = stats.get("climate_mode")
    if cm is not None:
        if cm.get("realistic"):
            span = 1024 * cm["shrink"] / 111.19
            lo = cm["center_lat"] - span / 2
            hi = cm["center_lat"] + span / 2
            wtype = (f"EARTH-PATCH {cm['center_lat']:.0f}N "
                     f"X{cm['shrink']:.0f} SPAN {lo:.0f}-{hi:.0f}N")
        else:
            wtype = "INVENTED CLIMATE"
        draw_text(right, 48, 142, wtype, (150, 220, 180), scale=2)
    # grouped stats, two columns column-major: geography left,
    # measures + climate trivia right (headroom for aquatic classes)
    lines = [
        f"PLATES {stats['plates']}",
        f"OCEAN {stats['ocean_fraction'] * 100:.1f}%",
        f"RIVERS {stats['river_cells']} CELLS",
        f"LAKES {stats['lake_cells']} CELLS",
        f"HIGH RELIEF {stats['high_relief_fraction'] * 100:.1f}%",
        "CELL 1 KM - MAP 1024 KM",
    ]
    tw = stats.get("climate_trivia")
    if tw is not None:
        lines.append(f"LAND T {tw['t_min']:.0f}..{tw['t_max']:.0f}C "
                     f"AVG {tw['t_mean']:.0f}C")
        lines.append(f"LAND P AVG {tw['p_mm_yr']:.0f} MM/YR")
    y = 178
    # two-column stats (column-major) — headroom for the aquatic
    # biome classes when they land
    rows = (len(lines) + 1) // 2
    for i, ln in enumerate(lines):
        c, row = divmod(i, rows)
        draw_text(right, 48 if c == 0 else 520, y + row * 26, ln,
                  (190, 190, 190), scale=2)
    y += 26 * rows
    draw_text(right, 48, y + 14, "TERRESTRIAL", (235, 235, 235), scale=3)
    y += 56
    rows = (len(biome_hist) + 1) // 2
    for i, (name, count, color) in enumerate(biome_hist):
        share = count / (H * W) * 100
        # column-major fill: read down the left column, then the right
        col, row = divmod(i, rows)
        x0 = 48 if col == 0 else 520
        yy = y + row * 27
        fill_rect(right, x0, yy, 44, 18, color)
        draw_text(right, x0 + 54, yy + 2, f"{name.replace('_', ' ')} {share:.1f}%",
                  (200, 200, 200), scale=2)
    y += 27 * rows
    # aquatic layer: FRESHWATER / MARINE sections (compact rows;
    # sub-8-cell classes hidden — the legend must fit)
    if aquatic_hists is not None:
        for title, rows_h in (("FRESHWATER", aquatic_hists[0]),
                              ("MARINE", aquatic_hists[1])):
            present = [r for r in rows_h if r[1] >= 8]
            if not present:
                continue
            draw_text(right, 48, y + 10, title, (235, 235, 235), scale=3)
            y += 46
            rows = (len(present) + 1) // 2
            for i, (name, count, color) in enumerate(present):
                share = count / (H * W) * 100
                col, row = divmod(i, rows)
                x0 = 48 if col == 0 else 520
                yy = y + row * 24
                fill_rect(right, x0, yy, 44, 16, color)
                draw_text(right, x0 + 54, yy + 1,
                          f"{name} {share:.1f}%", (200, 200, 200), scale=2)
            y += 24 * rows
    draw_text(right, 48, y + 14, "LANDMARKS", (235, 235, 235), scale=3)
    y += 56
    # one representative per kind (the map keeps every marker)
    key = []
    seen_kinds: set[str] = set()
    for mk in marks:
        if mk[0] not in seen_kinds:
            seen_kinds.add(mk[0])
            key.append(mk)
    for i, (kind, _, _, text) in enumerate(key):
        col = KIND_COLOR[kind]
        rows = (len(key) + 1) // 2
        c, row = divmod(i, rows)
        x0 = 48 if c == 0 else 520
        yy = y + row * 26
        fill_rect(right, x0, yy, 18, 18, col)
        draw_text(right, x0 + 28, yy + 2, text, (210, 210, 210), scale=2)

    sheet = np.concatenate([left, right], axis=1)
    write_png_rgb(path, sheet)


def load_stage_draw(n: int, bag: dict):
    """Draw callable (path -> None) for loading stage n — the single
    source for what each stage shows, shared by the demo's live writes
    and the batch re-render. bag keys: "plates", "elev", "hydro",
    "climate", "biome_map", "delivered" (whichever the stage needs)."""
    def up4(a):
        return np.kron(a, np.ones((4, 4), dtype=a.dtype))

    if n == 1:
        return lambda p: render_plates(p, bag["plates"], bag["elev"], factor=4)
    if n == 2:
        return lambda p: write_png_gray(p, up4(normalize_u8(bag["elev"], 0.0, 1.0)))
    if n == 3:
        return lambda p: write_png_gray(p, up4(normalize_u8(np.log1p(bag["hydro"]["depth"] * 20), 0.0, 2.0)))
    if n == 4:
        return lambda p: write_png_gray(p, up4(normalize_u8(bag["climate"]["P_pass1"], 0.0, 1.0)))
    if n == 5:
        return lambda p: write_png_gray(p, up4(normalize_u8(bag["climate"]["green"], 0.0, 1.0)))
    if n == 6:
        return lambda p: write_png_gray(p, up4(normalize_u8(bag["climate"]["P"], 0.0, 1.0)))
    if n == 7:
        return lambda p: write_png_gray(p, up4(normalize_u8(bag["climate"]["T"], 0.0, 1.0)))
    if n == 8:
        return lambda p: write_png_palette(p, up4(bag["biome_map"]), PALETTE)
    if n == 9:
        return lambda p: write_png_gray(p, normalize_u8(bag["delivered"]["elev"], 0.0, 1.0))
    if n == 10:
        return lambda p: write_png_palette(p, bag["delivered"]["biome_map"], PALETTE)
    raise ValueError(n)


class LoadingSink:
    """Live loading-screen writer: writes `loading/load_NN.png` for one
    pipeline stage and repoints `out/load.png` at it. The demo passes a
    sink down the build, so each stage's screen lands as the stage
    completes — a watcher sees the world assemble in real time."""

    def __init__(self, out_dir: str) -> None:
        import os
        self._os = os
        self.out_dir = out_dir
        self.paths: list[str] = []
        load_dir = f"{out_dir}/loading"
        os.makedirs(load_dir, exist_ok=True)
        for stale in os.listdir(load_dir):
            if stale.startswith("load_") and stale.endswith(".png"):
                os.remove(f"{load_dir}/{stale}")

    def write(self, n: int, draw) -> str:
        os = self._os
        p = f"{self.out_dir}/loading/load_{n:02d}.png"
        draw(p)
        self.paths.append(p)
        link = f"{self.out_dir}/load.png"
        if os.path.lexists(link):
            os.remove(link)
        os.symlink(os.path.relpath(p, self.out_dir), link)
        return p


def render_loading(out_dir: str, world: dict, delivered: dict,
                   plates, sea_level: float) -> list[str]:
    """Batch path: re-write all loading stages from a built world (used
    by the re-render subcommand; the demo writes them live via
    LoadingSink as the build progresses). All images at the delivered
    1024² (anchor stages naively upscaled by nearest 4x)."""
    sink = LoadingSink(out_dir)
    bag = {"plates": plates, "elev": world["elev"], "hydro": world["hydro"],
           "climate": world["climate"], "biome_map": world["biome_map"],
           "delivered": delivered}
    return [sink.write(n, load_stage_draw(n, bag)) for n in range(1, 11)]


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
    # raster (width-class stamped) + node dots colored by role:
    # source (start) green, confluence (converge) orange, outlet (end)
    # violet. Rivers are NOT filled as
    # water: at L0 a river is drainage crossing the cell, an overlay.
    rgb = np.dstack([normalize_u8(elev, 0.0, 1.0)] * 3).astype(float)
    water = delivered["ocean_mask"] | delivered["lake_mask"]
    rgb[water] = np.array([40, 90, 180])
    river = delivered["river_mask"]
    rgb[river] = np.array([240, 200, 60])
    node_colors = {"source": np.array([80, 210, 100]),
                   "confluence": np.array([250, 170, 50]),
                   "outlet": np.array([150, 110, 235])}
    for n in complex_.nodes.values():
        x = int(round(n.pos[0] * factor))
        y = int(round(n.pos[1] * factor))
        r = 2
        col = node_colors.get(n.id.split(":")[0], np.array([230, 60, 40]))
        if 0 <= y < rgb.shape[0] and 0 <= x < rgb.shape[1]:
            rgb[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1] = col
    _w("hydrology", write_png_rgb, np.clip(rgb, 0, 255).astype(np.uint8))

    return paths
