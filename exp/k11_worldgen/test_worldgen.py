"""K11 worldgen tests.

Small grids (<= 96^2) keep the suite fast; the 256^2 demo world is the
integration check (`python -m exp.k11_worldgen demo`). Areas: PNG writer,
deterministic noise, plates/elevation frame, hydrology invariants,
climate/biomes, complex derivation, full-pipeline smoke.
"""

import struct
import math
import zlib

import numpy as np
import pytest

from kernel.hashrng import Stream
from kernel.complex.audit import audit

from exp.k11_worldgen.biomes import BIOMES, classify_biomes, forest_cover
from exp.k11_worldgen.climate import build_climate
from exp.k11_worldgen.complexify import derive_complex
from exp.k11_worldgen.hydrology import (
    _D8,
    build_hydrology,
    flow_accumulation,
    flow_direction,
    priority_flood,
)
from exp.k11_worldgen.plates import Plates, build_elevation
from exp.k11_worldgen.raster import (
    fbm,
    normalize_u8,
    upsample_bicubic,
    value_noise,
    write_png_gray,
    write_png_palette,
    write_png_rgb,
)

SEED = 7


def _read_png(path):
    """Minimal decoder for our own writer output (filter type 0 only)."""
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, ihdr, plte = 8, b"", None, None
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif tag == b"PLTE":
            plte = body
        elif tag == b"IDAT":
            idat += body
        pos += 12 + length
    w, h, bitdepth, ctype = ihdr[0], ihdr[1], ihdr[2], ihdr[3]
    channels = {0: 1, 2: 3, 3: 1}[ctype]
    raw = zlib.decompress(idat)
    stride = w * channels
    img = np.zeros((h, w, channels), dtype=np.uint8)
    for y in range(h):
        assert raw[y * (stride + 1)] == 0  # filter type 0
        row = np.frombuffer(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)], dtype=np.uint8)
        img[y] = row.reshape(w, channels)
    return img, plte


# ---- PNG writer ---------------------------------------------------------------

def test_png_gray_roundtrip(tmp_path):
    img = np.arange(64, dtype=np.uint8).reshape(8, 8) * 3
    p = tmp_path / "g.png"
    write_png_gray(str(p), img)
    out, plte = _read_png(p)
    assert plte is None
    assert np.array_equal(out[:, :, 0], img)


def test_png_palette_roundtrip(tmp_path):
    idx = (np.arange(64) % 4).reshape(8, 8).astype(np.uint8)
    palette = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (9, 9, 9)]
    p = tmp_path / "p.png"
    write_png_palette(str(p), idx, palette)
    out, plte = _read_png(p)
    assert np.array_equal(out[:, :, 0], idx)
    assert plte == bytes(v for rgb in palette for v in rgb)


def test_png_rgb_roundtrip(tmp_path):
    img = np.zeros((8, 8, 3), dtype=np.uint8)
    img[..., 0], img[..., 1], img[..., 2] = 10, 20, 30
    p = tmp_path / "r.png"
    write_png_rgb(str(p), img)
    out, _ = _read_png(p)
    assert np.array_equal(out, img)


# ---- noise --------------------------------------------------------------------

def test_noise_deterministic_and_seed_sensitive():
    a = value_noise(Stream(SEED, "t"), (32, 32), 8)
    b = value_noise(Stream(SEED, "t"), (32, 32), 8)
    c = value_noise(Stream(SEED + 1, "t"), (32, 32), 8)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
    assert 0.0 <= a.min() and a.max() <= 1.0


def test_noise_resolution_independent_at_lattice_points():
    coarse = value_noise(Stream(SEED, "t"), (16, 16), 8)
    fine = value_noise(Stream(SEED, "t"), (32, 32), 8)
    # lattice points (multiples of cell_size) carry the same lattice values
    lat = coarse[::8, ::8]
    n = lat.shape[0]
    assert np.allclose(lat, fine[::8, ::8][:n, :n], atol=1e-9)


def test_fbm_bounds_and_determinism():
    a = fbm(Stream(SEED, "t"), (32, 32), base_cell=16, octaves=3)
    b = fbm(Stream(SEED, "t"), (32, 32), base_cell=16, octaves=3)
    assert np.array_equal(a, b)
    assert 0.0 <= a.min() and a.max() <= 1.0


# ---- plates / elevation -------------------------------------------------------

def test_plates_glued_contiguous_with_ocean_ring():
    p = Plates(Stream(SEED, "t"), (96, 96), n_dots=30, n_plates=5)
    # border ring reserved for ocean (elevation reservation, not plate
    # membership — rim cells glue into macro plates like any other)
    assert p.is_ocean[0, :].all() and p.is_ocean[-1, :].all()
    assert p.is_ocean[:, 0].all() and p.is_ocean[:, -1].all()
    # every cell belongs to a macro plate 0..n-1 (no unassigned -1)
    assert (p.macro_id >= 0).all()
    land_ids = set(np.unique(p.macro_id[~p.is_ocean]))
    assert land_ids <= set(range(p.n)) and land_ids
    # each macro plate is dominated by one 4-connected component; other
    # components must be islands (fully ringed by ocean — domain-warped
    # fine cells can split off pieces with no land neighbor to fold into)
    H, W = p.macro_id.shape
    mid = p.macro_id
    for m in land_ids:
        cells = mid == m
        comps = []
        seen = np.zeros((H, W), dtype=bool)
        for sy in range(H):
            for sx in range(W):
                if cells[sy, sx] and not seen[sy, sx]:
                    comp, stack = [], [(sy, sx)]
                    ringed = True
                    while stack:
                        y, x = stack.pop()
                        if seen[y, x] or not cells[y, x]:
                            continue
                        seen[y, x] = True
                        comp.append((y, x))
                        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                            ny, nx_ = y + dy, x + dx
                            if 0 <= ny < H and 0 <= nx_ < W:
                                if cells[ny, nx_]:
                                    if not seen[ny, nx_]:
                                        stack.append((ny, nx_))
                                elif mid[ny, nx_] >= 0:
                                    ringed = False
                    comps.append((len(comp), ringed))
        comps.sort(reverse=True)
        main = comps[0][0]
        rest_ok = all(r for _, r in comps[1:])
        assert main >= 0.9 * int(cells.sum()) or rest_ok, f"plate {m} fragmented"
    assert (p.boundary_dist >= 0).all()
    # faults carry signed convergence where land-land boundaries exist
    # (two guaranteed-continental plates may not touch on a small grid)
    if (p.boundary_dist == 0).any():
        assert np.abs(p.convergence).max() > 0


@pytest.mark.slow
def test_elevation_frame_and_determinism():
    shape = (96, 96)
    e1, p1 = build_elevation(Stream(SEED, "t"), shape, sea_level=0.35)
    e2, _ = build_elevation(Stream(SEED, "t"), shape, sea_level=0.35)
    assert np.array_equal(e1, e2)
    # guaranteed buffer: map border is deep ocean on every seed
    assert (e1[0, :] < 0.35).all() and (e1[-1, :] < 0.35).all()
    assert (e1[:, 0] < 0.35).all() and (e1[:, -1] < 0.35).all()
    # landmasses well inside; interior seas emerge on oceanic plates
    # (the old "interior is mostly land" assertion predates oceanic plates)
    interior = ~p1.is_ocean
    continental = interior & ~p1.is_sea_plate
    assert (e1[interior] >= 0.35).mean() > 0.2
    assert (e1[continental] >= 0.35).mean() > 0.4
    sea_plate = interior & p1.is_sea_plate
    if sea_plate.any():  # island arcs may rise; the bulk stays below
        assert (e1[sea_plate] >= 0.35).mean() < 0.35
    assert (e1 > 0.72).any()
    high = (e1 > 0.72) & interior
    assert p1.boundary_dist[high].mean() < p1.boundary_dist[interior].mean()


# ---- hydrology ----------------------------------------------------------------

def test_priority_flood_fills_bowl_equipotentially():
    h = np.full((16, 16), 0.5)
    h[4:12, 4:12] = 0.1            # bowl
    ocean = np.zeros_like(h, bool)
    ocean[0, :] = True             # top row is ocean
    h[0, :] = 0.0
    w = priority_flood(h, ocean)
    assert (w >= h - 1e-12).all()
    bowl = np.zeros_like(h, bool)
    bowl[4:12, 4:12] = True
    assert np.ptp(w[bowl]) < 1e-9  # one fill level across the bowl
    assert w[8, 8] > h[8, 8]       # filled


@pytest.mark.slow
def test_flow_direction_walks_downhill_to_water():
    hy = build_hydrology(*_tiny_world())
    for sy, sx in zip(*np.where(hy["river_mask"])):
        y, x, seen = int(sy), int(sx), set()
        while not (hy["ocean_mask"][y, x] or hy["lake_mask"][y, x]):
            assert (y, x) not in seen
            seen.add((y, x))
            d = hy["flow_dir"][y, x]
            assert d >= 0
            y, x = y + _D8[d][0], x + _D8[d][1]


@pytest.mark.slow
def test_rivers_sized_and_lakes_first():
    hy = build_hydrology(*_tiny_world())
    # lakes first: rivers never inside lakes
    assert not (hy["river_mask"] & hy["lake_mask"]).any()
    river = hy["river_mask"]
    if river.sum() < 20:
        pytest.skip("tiny world too dry for river statistics")
    # discharge non-decreasing downstream (confluences merge, not split)
    for y, x in zip(*np.where(river)):
        d = hy["flow_dir"][y, x]
        if d >= 0:
            ny, nx_ = y + _D8[d][0], x + _D8[d][1]
            if river[ny, nx_]:
                assert hy["discharge"][ny, nx_] >= hy["discharge"][y, x]
    # Strahler orders sane, widths only on rivers
    assert hy["order"][river].min() >= 1
    assert hy["order"][river].max() <= 10
    assert (hy["width"][~river] == 0).all()
    # width classes track discharge thresholds (6x / 30x base)
    big = river & (hy["discharge"] >= 40 * 6)
    assert (hy["width"][big] >= 2).all()
    assert (hy["width"][river & (hy["discharge"] < 40 * 6)] == 1).all()


def _tiny_world():
    shape = (96, 96)
    elev, _ = build_elevation(Stream(SEED, "t"), shape, sea_level=0.35)
    ocean = elev < 0.35
    return elev, ocean


def test_accumulation_grows_downstream():
    # tilted plane: everything drains to the bottom row
    h = np.linspace(1.0, 0.0, 32)[:, None] * np.ones((32, 32))
    ocean = np.zeros((32, 32), bool)
    ocean[-1, :] = True
    w = priority_flood(h, ocean)
    direction, depth = flow_direction(w)
    acc = flow_accumulation(w, direction, depth)
    assert acc[1, 16] < acc[30, 16]
    assert acc.max() >= 32  # a full column drains through the outlet row


# ---- climate / biomes ---------------------------------------------------------

def test_refine_climate_conditions_on_snow_and_rain():
    from exp.k11_worldgen.climate import refine_climate
    shape = (16, 16)
    T_lat = np.linspace(0, 1, 16)[:, None] * np.ones(shape)
    T_m = np.full((12, *shape), 0.5)   # ~2.5 degC all year
    T_m[0] = 0.3                        # january below freezing
    P_m = np.zeros((12, *shape))
    P_m[6] = 0.8                        # wet july
    r1 = refine_climate(T_m, P_m, T_lat)
    r2 = refine_climate(T_m, P_m, T_lat)
    assert np.array_equal(r1, r2)       # deterministic
    assert (r1[0] < T_m[0]).all()       # snow-albedo cools the freezing month
    assert (r1[6] < T_m[6]).all()       # wet month cools (evap + cloud)
    assert r1.min() >= 0.0 and r1.max() <= 1.0
    # uniform rain damps the seasonal swing
    swing = np.stack([np.full(shape, 0.5 + 0.2 * math.cos(2 * math.pi * (m - 6) / 12))
                      for m in range(12)])
    r3 = refine_climate(swing, np.ones((12, *shape)), T_lat)
    assert (r3.max(axis=0) - r3.min(axis=0)).mean() < 0.39


def test_wind_library_terrain_blocking():
    from exp.k11_worldgen.climate import WindLibrary
    shape = (64, 64)
    land = np.ones(shape, bool)
    alt = np.zeros(shape)
    alt[:, 32:] = 0.8                   # high range over the east half
    lib0 = WindLibrary(Stream(SEED, "t"), shape, land, alt=np.zeros(shape))
    lib1 = WindLibrary(Stream(SEED, "t"), shape, land, alt=alt)
    u0, v0 = lib0.sample(Stream(SEED, "s"), 1000, 1.0)
    u1, v1 = lib1.sample(Stream(SEED, "s"), 1000, 1.0)
    # same seed -> same base wind; the range only removes momentum
    assert np.hypot(u1, v1)[:, 40:].mean() < np.hypot(u0, v0)[:, 40:].mean()
    # and cell-by-cell the blocked wind never exceeds the free wind
    assert (np.hypot(u1, v1) <= np.hypot(u0, v0) + 1e-9).all()


@pytest.mark.slow
def test_climate_and_biome_overrides():
    elev, ocean = _tiny_world()
    hy = build_hydrology(elev, ocean)
    cl = build_climate(elev, hy, 0.35, seed=SEED)
    cl2 = build_climate(elev, hy, 0.35, seed=SEED)
    assert np.array_equal(cl["P"], cl2["P"])  # deterministic from seed
    assert cl["T_monthly"].shape == (12, *elev.shape)
    assert cl["P_monthly"].shape == (12, *elev.shape)
    assert cl["T"].min() >= 0.0 and cl["T"].max() <= 1.0
    assert cl["P"].min() >= 0.0 and cl["P"].max() <= 1.0
    land = ~ocean
    # northern hemisphere: the top (north) edge is colder than the bottom
    assert cl["T"][0, :].mean() < cl["T"][-1, :].mean()
    # altitude cooling: high cells colder than low cells on average
    hi_q, lo_q = np.quantile(elev[land], 0.8), np.quantile(elev[land], 0.2)
    high, low = (elev >= hi_q) & land, (elev <= lo_q) & land
    assert cl["T"][high].mean() < cl["T"][low].mean()
    # seasonality exists, and interiors are not rain-shadow deserts
    # (0.12 normalized ~= 480 mm/yr)
    assert cl["P_monthly"][:, land].std(axis=0).mean() > 0.01
    assert cl["P"][land].mean() > 0.12
    bm = classify_biomes(elev, hy, cl, 0.35)
    names = [b["name"] for b in BIOMES]
    # only standing water is a water biome; river cells keep their land biome
    water = hy["ocean_mask"] | hy["lake_mask"]
    assert {names[i] for i in np.unique(bm[water])} <= {"ocean", "lake"}
    assert {names[i] for i in np.unique(bm[hy["river_mask"]])} - {"ocean", "lake"} != set()
    cover = forest_cover(bm, cl["P"])
    assert cover.min() >= 0.0 and cover.max() <= 1.0


# ---- complex derivation + full pipeline ---------------------------------------

@pytest.mark.slow
def test_derive_complex_clean_and_deterministic():
    elev, ocean = _tiny_world()
    hy = build_hydrology(elev, ocean)
    cl = build_climate(elev, hy, 0.35)
    bm = classify_biomes(elev, hy, cl, 0.35)
    names = [b["name"] for b in BIOMES]
    c1 = derive_complex(hy, bm, names)
    c2 = derive_complex(hy, bm, names)
    assert [n.id for n in c1.nodes.values()] == [n.id for n in c2.nodes.values()]
    fatal = [d for d in audit(c1)
             if d.split(":")[0] in ("dangling_edge", "nodeless_intersection", "isolated_patch")]
    assert fatal == []
    assert len(c1.nodes) > 2 and len(c1.edges) > 0 and len(c1.patches) > 0


def test_diagonal_crossings_expanded_through_corners():
    # two anti-diagonal rivers in one cell would cross without a node;
    # diagonal steps must be expanded through a corner cell instead
    shape = (5, 5)
    river = np.zeros(shape, bool)
    river[1, 1] = river[2, 2] = river[1, 2] = river[2, 1] = True
    direction = np.full(shape, -1, dtype=np.int8)
    direction[1, 1] = _D8.index((1, 1))    # A: (1,1) -> (2,2)
    direction[2, 2] = _D8.index((1, 0))    #    -> ocean
    direction[1, 2] = _D8.index((1, -1))   # B: (1,2) -> (2,1)
    direction[2, 1] = _D8.index((1, 0))    #    -> ocean
    ocean = np.zeros(shape, bool)
    ocean[3, :] = True
    w = np.full(shape, 0.5)
    w[3, :] = 0.0
    hydro = {"river_mask": river, "flow_dir": direction, "w": w,
             "ocean_mask": ocean, "lake_mask": np.zeros(shape, bool),
             "accumulation": np.ones(shape), "width": np.ones(shape, dtype=np.int16)}
    cx = derive_complex(hydro, np.zeros(shape, int), ["ocean"])
    defects = audit(cx)
    assert not [d for d in defects if d.startswith("nodeless_intersection")]


# ---- delivery (resolution ladder) ---------------------------------------------

def test_upsample_bicubic():
    c = np.full((8, 8), 3.5)
    assert np.allclose(upsample_bicubic(c, 4), 3.5)  # constant stays constant
    yy, xx = np.mgrid[0:8, 0:8].astype(float)
    plane = 2 * xx + 3 * yy
    up = upsample_bicubic(plane, 4)
    assert up.shape == (32, 32)
    py, px = np.mgrid[0:32, 0:32].astype(float)
    expect = 2 * ((px + 0.5) / 4 - 0.5) + 3 * ((py + 0.5) / 4 - 0.5)
    # Catmull-Rom reproduces a plane exactly away from the clamped border
    assert np.allclose(up[6:-6, 6:-6], expect[6:-6, 6:-6], atol=1e-9)


@pytest.mark.slow
def test_deliver_smoke():
    from exp.k11_worldgen.deliver import upscale_world
    elev, ocean = _tiny_world()
    hy = build_hydrology(elev, ocean)
    cl = build_climate(elev, hy, 0.35, seed=SEED)
    names = [b["name"] for b in BIOMES]
    bm = classify_biomes(elev, hy, cl, 0.35)
    cx = derive_complex(hy, bm, names)
    d = upscale_world(elev, hy, cl, cx, 0.35, factor=4)
    H, W = elev.shape
    assert d["elev"].shape == (H * 4, W * 4)
    assert d["biome_map"].shape == (H * 4, W * 4)
    assert d["ocean_mask"].any() and (d["elev"] >= 0.35).any()
    assert not (d["river_mask"] & d["lake_mask"]).any()
    # ocean is always sub-sea (connectivity is carried from the anchor)
    assert not (d["ocean_mask"] & (d["elev"] >= 0.35)).any()
    # the delivery rim is a 1 km rock-and-ice border, never water
    from exp.k11_worldgen.biomes import BIOME_ID
    assert (d["biome_map"][0, :] == BIOME_ID["rock and ice"]).all()
    assert (d["biome_map"][:, 0] == BIOME_ID["rock and ice"]).all()
    assert not d["ocean_mask"][0, :].any() and not d["lake_mask"][:, -1].any()
    d2 = upscale_world(elev, hy, cl, cx, 0.35, factor=4)
    assert np.array_equal(d["biome_map"], d2["biome_map"])  # deterministic


@pytest.mark.slow
def test_demo_world_passes_all_checks():
    from exp.k11_worldgen.__main__ import run_demo
    report = run_demo(SEED)
    assert report["ok"], [k for k, v in report["checks"].items() if not v]


@pytest.mark.slow
def test_persist_roundtrip(tmp_path):
    from exp.k11_worldgen.deliver import upscale_world
    from exp.k11_worldgen.marks import compute_marks
    from exp.k11_worldgen.persist import load_complex, load_world, save_world
    elev, plates = build_elevation(Stream(SEED, "t"), (96, 96), sea_level=0.35)
    ocean = elev < 0.35
    hy = build_hydrology(elev, ocean)
    cl = build_climate(elev, hy, 0.35, seed=SEED)
    bm = classify_biomes(elev, hy, cl, 0.35)
    names = [b["name"] for b in BIOMES]
    cx = derive_complex(hy, bm, names)
    world = {"elev": elev, "hydro": hy, "climate": cl, "biome_map": bm,
             "cover": forest_cover(bm, cl["P"]), "complex": cx,
             "plates": plates, "ocean_mask": ocean}
    delivered = upscale_world(elev, hy, cl, cx, 0.35, factor=4)
    marks = compute_marks(delivered, hy, 0.35, 4)
    save_world(str(tmp_path), world, delivered, SEED, 0.35, 4,
               {"plates": plates.n}, marks, {"determinism": True})
    assert (tmp_path / "world.json").exists() and (tmp_path / "world.npz").exists()
    data = load_world(str(tmp_path))
    assert np.array_equal(data["world"]["elev"], elev)
    assert np.array_equal(data["world"]["climate"]["T_monthly"], cl["T_monthly"])
    assert np.array_equal(data["delivered"]["biome_map"], delivered["biome_map"])
    assert data["world"]["plates"].n == plates.n
    assert len(data["marks"]) == len(marks)
    cx2 = load_complex(str(tmp_path))
    assert cx == cx2  # Complex.__eq__ compares value-wise incl. DriftFields
