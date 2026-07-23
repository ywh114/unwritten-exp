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


def _plates_rgb(plates, sea_level_elev: np.ndarray,
                factor: int = 4) -> np.ndarray:
    """Tectonic overview as an RGB array: macro plates in qualitative
    colors (oceanic dark), white fault lines, over a dim elevation
    base."""
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
    return rgb


def render_plates(path: str, plates, sea_level_elev: np.ndarray, factor: int = 4) -> None:
    """Tectonic overview at delivered size (see _plates_rgb)."""
    write_png_rgb(path, _plates_rgb(plates, sea_level_elev, factor))


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
    sea = delivered["sea_mask"]
    left[sea] = (deep + (shallow - deep) * depth_t[..., None])[sea]
    # aquatic biome layer: water recolored toward its class color over
    # the bathymetry (deep open ocean stays pure depth; coral and salt
    # lakes read strongest — they are places, not depths). Rivers draw
    # in their class color.
    aq = delivered["aquatic"]
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
        draw_text(right, 48 if c == 0 else 520, y + row * 22, ln,
                  (190, 190, 190), scale=2)
    y += 22 * rows
    # domain bases for the per-section shares: each section reports
    # percentages of its own domain, not of the whole map
    land_cells = int((~ocean & ~lake).sum())
    fresh_cells = int((lake | delivered["river_mask"]).sum())
    ocean_cells = int(ocean.sum())

    def _legend_label(name: str, count: int, denom: int) -> str:
        """`NAME 12.3%` of the section's domain, or `NAME 234` when the
        share would round to 0.0% — below display precision the cell
        count says more."""
        share = count / max(denom, 1) * 100
        if share < 0.05:
            return f"{name} {count}"
        return f"{name} {share:.1f}%"

    draw_text(right, 48, y + 10,
              f"TERRESTRIAL ({100 * land_cells / (H * W):.0f}% LAND)",
              (235, 235, 235), scale=3)
    y += 46
    # ocean/lake are water masks, not terrestrial classes — they live
    # in the MARINE/FRESHWATER sections, not here
    terr = [r for r in biome_hist if r[0] not in ("ocean", "lake")]
    rows = (len(terr) + 1) // 2
    for i, (name, count, color) in enumerate(terr):
        # column-major fill: read down the left column, then the right
        col, row = divmod(i, rows)
        x0 = 48 if col == 0 else 520
        yy = y + row * 24
        fill_rect(right, x0, yy, 40, 16, color)
        draw_text(right, x0 + 48, yy + 2,
                  _legend_label(name.replace('_', ' '), count, land_cells),
                  (200, 200, 200), scale=2)
    y += 24 * rows
    # aquatic layer: FRESHWATER / MARINE sections (compact rows;
    # sub-8-cell classes hidden — the legend must fit)
    if aquatic_hists is not None:
        for title, denom, rows_h in (
                (f"FRESHWATER ({100 * fresh_cells / (H * W):.1f}% INLAND WATER)",
                 fresh_cells, aquatic_hists[0]),
                (f"MARINE ({100 * ocean_cells / (H * W):.0f}% OCEAN)",
                 ocean_cells, aquatic_hists[1])):
            present = [r for r in rows_h if r[1] >= 8]
            if not present:
                continue
            draw_text(right, 48, y + 8, title, (235, 235, 235), scale=3)
            y += 40
            rows = (len(present) + 1) // 2
            for i, (name, count, color) in enumerate(present):
                col, row = divmod(i, rows)
                x0 = 48 if col == 0 else 520
                yy = y + row * 20
                fill_rect(right, x0, yy, 40, 14, color)
                draw_text(right, x0 + 48, yy + 1,
                          _legend_label(name, count, denom),
                          (200, 200, 200), scale=2)
            y += 20 * rows
    draw_text(right, 48, y + 10, "LANDMARKS", (235, 235, 235), scale=3)
    y += 46
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
        yy = y + row * 24
        fill_rect(right, x0, yy, 18, 18, col)
        draw_text(right, x0 + 28, yy + 2, text, (210, 210, 210), scale=2)

    sheet = np.concatenate([left, right], axis=1)
    write_png_rgb(path, sheet)


_LOAD_STAGE_NAMES = (
    "",                 # stages are 1-indexed
    "PLATES",           # ---- pass 1: honest dependency order ----
    "ELEVATION",
    "CARVE",
    "HYDROLOGY",
    "CURRENTS",
    "PRECIP 1",
    "TEMP 1",
    "BIOMES 1",
    "WETLANDS",         # ---- pass 2: coarse second-order rerun ----
    "PRECIP 2",
    "TEMP 2",
    "BIOMES 2",
    "AQUATIC",
    "DELIVERY ELEV",
    "DELIVERY BIOMES",
)


def _stamp_stage(rgb: np.ndarray, n: int) -> np.ndarray:
    """Stage name in the top-left corner (black shadow for legibility)."""
    from exp.k11_worldgen.legend import draw_text
    rgb = rgb.copy()
    draw_text(rgb, 10, 10, _LOAD_STAGE_NAMES[n], (0, 0, 0), scale=4)
    draw_text(rgb, 8, 8, _LOAD_STAGE_NAMES[n], (245, 245, 245), scale=4)
    return rgb


def _gray_rgb(a: np.ndarray) -> np.ndarray:
    return np.dstack([a] * 3).astype(np.uint8)


def _hydro_rgb(bag: dict, delta: bool = False) -> np.ndarray:
    """Anchor-grid hydrology composite: dim elevation, blue standing
    water, yellow rivers (the readable form — a raw depth map is not).
    With delta=True and the pass-1 masks in the bag, the pass-2
    additions are tinted (new ponds cyan, new streams orange)."""
    elev, hydro = bag["elev"], bag["hydro"]
    rgb = (np.dstack([normalize_u8(elev, 0.0, 1.0)] * 3) * 0.6).astype(float)
    water = hydro["ocean_mask"] | hydro["lake_mask"]
    rgb[water] = np.array([40, 90, 180])
    rgb[hydro["river_mask"]] = np.array([240, 200, 60])
    if delta and "hydro1_lake" in bag:
        rgb[hydro["lake_mask"] & ~bag["hydro1_lake"]] = np.array([80, 220, 230])
        rgb[hydro["river_mask"] & ~bag["hydro1_river"]] = np.array([250, 140, 40])
    return np.clip(rgb, 0, 255).astype(np.uint8)


def load_stage_draw(n: int, bag: dict):
    """Draw callable (path -> None) for loading stage n — the single
    source for what each stage shows, shared by the demo's live writes
    and the batch re-render. The stages are the computation DAG: pass 1
    (1-8) builds the scaffold in dependency order; pass 2 (9-13) is the
    coarse second-order rerun (hydrology conditioned on climate,
    climate conditioned on the real forest cover and new water, biomes
    re-derived); 14-15 deliver. bag keys: "plates", "elev", "elev_raw",
    "hydro", "currents", "climate", "biome_map", "aquatic",
    "delivered" (whichever the stage needs)."""
    def up4(a):
        return np.kron(a, np.ones((4, 4), dtype=a.dtype))

    def gray(a):
        return lambda p: write_png_rgb(p, _stamp_stage(_gray_rgb(up4(a)), n))

    if n == 1:
        return lambda p: write_png_rgb(
            p, _stamp_stage(_plates_rgb(bag["plates"], bag["elev"], 4), n))
    if n == 2:
        return gray(normalize_u8(bag["elev"], 0.0, 1.0))
    if n == 3:
        def draw_carve(p):
            # elevation with the carved notches tinted — a plain
            # elevation render hides the pass entirely (1-2 cell cuts)
            rgb = _gray_rgb(up4(normalize_u8(bag["elev"], 0.0, 1.0)))
            if "elev_raw" in bag:
                carved = up4(bag["elev_raw"] - bag["elev"] > 1e-9)
                rgb[carved] = (235, 90, 60)
            write_png_rgb(p, _stamp_stage(rgb, n))
        return draw_carve
    if n == 4:
        return lambda p: write_png_rgb(
            p, _stamp_stage(np.kron(_hydro_rgb(bag),
                                    np.ones((4, 4, 1))), n))
    if n == 5:
        def draw_currents(p):
            cur = bag["currents"]
            speed = np.hypot(cur["u"], cur["v"])
            g = normalize_u8(speed, 0.0, 1.0).astype(float)
            ocean = bag["hydro"]["ocean_mask"]
            # current speed as brightness over the ocean bathymetry;
            # land dark
            depth_t = np.clip(bag["elev"] / bag["sea_level"],
                              0.0, 1.0)
            rgb = np.full((*speed.shape, 3), (28, 30, 34), dtype=float)
            rgb[ocean, 0] = 15 + 30 * depth_t[ocean]
            rgb[ocean, 1] = 40 + 70 * depth_t[ocean]
            rgb[ocean, 2] = 90 + 130 * depth_t[ocean]
            fast = speed > 0.02
            rgb[fast] = (rgb[fast] * 0.35
                         + np.stack([g, g, g], axis=-1)[fast] * 0.65)
            write_png_rgb(p, _stamp_stage(
                np.kron(rgb.astype(np.uint8), np.ones((4, 4, 1))), n))
        return draw_currents
    if n in (6, 10):
        def draw_P(p, n=n):
            rgb = _gray_rgb(up4(normalize_u8(bag["climate"]["P"], 0.0, 1.0))).astype(float)
            if n == 10 and "climate1" in bag:
                # pass-2 delta: greener where conditioned rain rose,
                # redder where it fell (interception shadows)
                d = up4(bag["climate"]["P"] - bag["climate1"]["P"])
                rgb[d > 0.01] = 0.65 * rgb[d > 0.01] + 0.35 * np.array([80, 230, 120])
                rgb[d < -0.01] = 0.65 * rgb[d < -0.01] + 0.35 * np.array([235, 100, 90])
            write_png_rgb(p, _stamp_stage(np.clip(rgb, 0, 255).astype(np.uint8), n))
        return draw_P
    if n in (7, 11):
        def draw_T(p, n=n):
            rgb = _gray_rgb(up4(normalize_u8(bag["climate"]["T"], 0.0, 1.0))).astype(float)
            if n == 11 and "climate1" in bag:
                d = up4(bag["climate"]["T"] - bag["climate1"]["T"])
                rgb[d > 0.004] = 0.65 * rgb[d > 0.004] + 0.35 * np.array([80, 230, 120])
                rgb[d < -0.004] = 0.65 * rgb[d < -0.004] + 0.35 * np.array([235, 100, 90])
            write_png_rgb(p, _stamp_stage(np.clip(rgb, 0, 255).astype(np.uint8), n))
        return draw_T
    if n in (8, 12):
        def draw_biomes(p, n=n):
            rgb = np.array(PALETTE, dtype=np.uint8)[up4(bag["biome_map"])].astype(float)
            if n == 12 and "biome1" in bag:
                # pass-2 delta: cells whose class changed, brightened
                flip = up4(bag["biome_map"] != bag["biome1"])
                rgb[flip] = rgb[flip] * 0.45 + 140.0
            write_png_rgb(p, _stamp_stage(np.clip(rgb, 0, 255).astype(np.uint8), n))
        return draw_biomes
    if n == 9:
        return lambda p: write_png_rgb(
            p, _stamp_stage(np.kron(_hydro_rgb(bag, delta=True),
                                    np.ones((4, 4, 1))), n))
    if n == 13:
        def draw_aquatic(p):
            from exp.k11_worldgen.aquatic import AQUATIC_PALETTE
            aq = bag["aquatic"]
            water = (bag["hydro"]["ocean_mask"] | bag["hydro"]["lake_mask"]
                     | bag["hydro"]["river_mask"])
            rgb = np.full((*aq.shape, 3), (28, 30, 34), dtype=np.uint8)
            rgb[water] = AQUATIC_PALETTE[aq][water]
            write_png_rgb(p, _stamp_stage(
                np.kron(rgb, np.ones((4, 4, 1))), n))
        return draw_aquatic
    if n == 14:
        def draw_d_elev(p):
            write_png_rgb(p, _stamp_stage(
                _gray_rgb(normalize_u8(bag["delivered"]["elev"], 0.0, 1.0)), n))
        return draw_d_elev
    if n == 15:
        def draw_d_biomes(p):
            rgb = np.array(PALETTE, dtype=np.uint8)[bag["delivered"]["biome_map"]]
            write_png_rgb(p, _stamp_stage(rgb, n))
        return draw_d_biomes
    raise ValueError(n)


class LoadingSink:
    """Live loading-screen writer: writes `loading/load_NN.png` for one
    pipeline stage and copies it to `out/load.png` (a real file, not a
    symlink — image viewers that can't follow symlink swaps still
    refresh). The demo passes a sink down the build, so each stage's
    screen lands as the stage completes — a watcher sees the world
    assemble in real time."""

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
        import shutil
        p = f"{self.out_dir}/loading/load_{n:02d}.png"
        draw(p)
        self.paths.append(p)
        dst = f"{self.out_dir}/load.png"
        if self._os.path.lexists(dst):
            # may be a symlink left by an older build — copying onto a
            # symlink target can name the very file being copied
            self._os.remove(dst)
        shutil.copyfile(p, dst)
        return p


def render_loading(out_dir: str, world: dict, delivered: dict,
                   plates, sea_level: float) -> list[str]:
    """Batch path: re-write the loading stages from a built world (used
    by the re-render subcommand; the demo writes them live via
    LoadingSink as the build progresses). The dump holds the FINAL
    (pass-2) world, so the pass-1 scaffold screens (6-8) are not
    re-rendered here. All images at the delivered 1024² (anchor stages
    naively upscaled by nearest 4x)."""
    sink = LoadingSink(out_dir)
    bag = {"plates": plates, "elev": world["elev"], "hydro": world["hydro"],
           "climate": world["climate"], "biome_map": world["biome_map"],
           "aquatic": world["aquatic"],
           "currents": world["currents"],
           "sea_level": sea_level,
           "delivered": delivered}
    stages = [1, 2, 3, 4, 5, 9, 10, 11, 12, 13, 14, 15]
    return [sink.write(n, load_stage_draw(n, bag)) for n in stages]


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

    # aquabiomes.png: the aquatic class layer at delivered resolution —
    # water cells in their class colors over a dim elevation base
    if "aquatic" in delivered:
        from exp.k11_worldgen.aquatic import AQUATIC_PALETTE
        aq = delivered["aquatic"]
        water = (delivered["ocean_mask"] | delivered["lake_mask"]
                 | delivered["river_mask"])
        base = np.dstack([normalize_u8(elev, 0.0, 1.0) // 3] * 3)
        rgb = base.astype(np.uint8).copy()
        rgb[water] = AQUATIC_PALETTE[aq][water]
        _w("aquabiomes", write_png_rgb, rgb)

    return paths
