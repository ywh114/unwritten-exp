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
    connected_ocean,
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
    direction, depth = flow_direction(w, h)
    acc = flow_accumulation(w, direction, depth)
    assert acc[1, 16] < acc[30, 16]
    assert acc.max() >= 32  # a full column drains through the outlet row


def test_flats_route_around_micro_ridge():
    """Priority-flood flats route on the RAW bed's micro-relief, not on
    fewest-hops beelines to the outlet: a micro-ridge on the straight
    line must force a detour around its end."""
    h = 0.50 + 0.01 * (15 - np.arange(16))[:, None] / 15.0 * np.ones((16, 16))
    ocean = np.zeros((16, 16), bool)
    ocean[-1, :] = True
    h[3:13, 3:13] = 0.42           # basin: floods flat at the rim spill
    h[9, 5:12] = 0.45              # micro-ridge across the beeline
    w = priority_flood(h, ocean)
    assert w[6, 8] > h[6, 8]       # the basin really is flooded flat
    direction, cost = flow_direction(w, h)
    # walk downstream from a cell north of the ridge: the path must go
    # AROUND the ridge (climbing it costs 0.03 * penalty = 30 hops)
    y, x, path = 5, 8, [(5, 8)]
    for _ in range(256):
        d = direction[y, x]
        if d < 0:
            break
        y, x = y + _D8[d][0], x + _D8[d][1]
        path.append((y, x))
        if w[y, x] <= h[y, x] + 1e-9:
            break                 # off the flat: directed terrain
    assert not any(py == 9 and 5 <= px < 12 for py, px in path)
    # and every flat cell still reached an outlet (no orphan pockets)
    assert (direction[(w > h) & ~ocean] >= 0).all()


def test_salinity_endorheic_vs_exorheic():    # plateau with an ocean column on the left, an open bowl (drains to
    # the sea -> fresh lake) and a below-sea enclosed bowl (terminal ->
    # salt lake)
    h = np.full((32, 32), 0.6)
    h[:, 0] = 0.2
    ocean = connected_ocean(h, 0.35)
    h[4:7, 4:7] = 0.55      # open bowl: fills to its sill, drains out
    h[24:27, 24:27] = 0.30  # enclosed below-sea bowl: endorheic terminal
    hy = build_hydrology(h, ocean, sea_level=0.35)
    sal = hy["salinity"]
    assert (sal[hy["ocean_mask"]] == 35.0).all()
    fresh = sal[4:7, 4:7][hy["lake_mask"][4:7, 4:7]]
    salt = sal[24:27, 24:27][hy["lake_mask"][24:27, 24:27]]
    assert fresh.size > 0 and (fresh == 0.5).all()       # exorheic
    assert salt.size > 0 and (salt > 35.0).all()
    # endorheic terminals run SALTIER than the sea (no cap at ocean)


def test_carve_gorges_notches_sill():
    from exp.k11_worldgen.hydrology import carve_gorges
    # westward tilt + a channel along row 16 that runs a river straight
    # into a wall across rows 8..24. The river's momentum points INTO
    # the wall; the flow bends around the wall's ends.
    h = 0.6 + 0.01 * (np.arange(32)[None, :] / 31)
    h = np.broadcast_to(h, (32, 32)).copy()
    h[:, 0] = 0.2
    h[16, 1:] = 0.55                    # the channel
    h[8:25, 8] = 0.75                   # the sill wall
    ocean = connected_ocean(h, 0.35)
    out = carve_gorges(h, ocean, passes=4, carve_threshold=10.0)
    assert out[16, 8] < 0.65            # the wall is notched through
    assert out[12, 8] == 0.75           # ...but only where the river points
    assert out[5, 20] == h[5, 20]       # open plain untouched
    assert out[16, 20] == h[16, 20]     # the channel bed itself untouched
    # threshold gates: with an unreachable threshold nothing changes
    same = carve_gorges(h, ocean, passes=3, carve_threshold=1e9)
    assert (same == h).all()


# ---- climate / biomes ---------------------------------------------------------

@pytest.mark.slow
def test_currents_and_sst():
    from exp.k11_worldgen.currents import advect_sst, build_currents, \
        velocity_field
    h = np.full((64, 64), 0.6)
    h[0:56, 8:56] = 0.2        # deep pool touching the border
    ocean = connected_ocean(h, 0.35)
    c1 = build_currents(h, ocean, 0.35, seed=SEED)
    c2 = build_currents(h, ocean, 0.35, seed=SEED)
    assert np.array_equal(c1["u"], c2["u"])            # deterministic
    assert c1["n_gyres"] >= 1
    assert "ramp" in c1                          # through-flow source
    assert len(c1["psi"]) == c1["n_gyres"] + 2   # gyres + ramp pair
    assert (c1["u"][~ocean] == 0).all()                # ocean-only flow
    assert (c1["v"][~ocean] == 0).all()
    base = np.linspace(-5.0, 25.0, 64)[:, None] * np.ones((1, 64))
    z64 = np.zeros((64, 64))
    # zero flow: advection is the identity, SST stays the baseline
    # (border rows drift by one bilinear clip epsilon per step — the
    # interior is exact)
    assert np.allclose(advect_sst(base, z64, z64, z64,
                                  diffuse_passes=0)[1:-1, 1:-1],
                       base[1:-1, 1:-1])
    # a rising stream mixes deep cold water up: SST drops
    assert advect_sst(base, z64, z64, z64 + 0.5).mean() < base.mean()
    # seasonal wobble: the velocity field differs month to month but
    # keeps its mean sign structure
    u0, v0 = velocity_field(c1, 0)
    u6, v6 = velocity_field(c1, 6)
    assert not np.array_equal(u0, u6)
    # the stream function makes land a streamline BY CONSTRUCTION:
    # psi is constant (0) across every land cell. The magic rim is
    # water in the solve, so compare against the solver's own mask
    from exp.k11_worldgen.currents import _blend, _coarse_grids
    psi = _blend(c1["psi"], c1["weights"])
    water_c, _ = _coarse_grids(h, ocean, 0.35, c1["factor"])
    assert abs(psi[~water_c].max() - psi[~water_c].min()) < 1e-9
    # conditioning-pass refinement: the world's OWN wind curl joins the
    # sources — deterministic, changes the field, keeps it stream-driven
    from exp.k11_worldgen.currents import refine_currents
    cl = {"wind_u": np.zeros((12, 2, 64, 64), np.float32),
          "wind_v": np.zeros((12, 2, 64, 64), np.float32)}
    # shear in y: the wind curl is nonzero (x-only shear is curl-free)
    cl["wind_u"][:] = np.sin(np.linspace(0.0, 3.0, 64))[:, None]
    c3 = refine_currents(build_currents(h, ocean, 0.35, seed=SEED),
                         h, ocean, 0.35, cl)
    c3b = refine_currents(build_currents(h, ocean, 0.35, seed=SEED),
                          h, ocean, 0.35, cl)
    assert np.array_equal(c3["u"], c3b["u"])       # deterministic
    assert not np.array_equal(c3["u"], c1["u"])    # wind correlation
    assert len(c3["psi"]) == c1["n_gyres"] + 3   # ramps + one wind source


def test_current_streamfunction_continuity():
    """The barotropic solve is real fluid dynamics: the Poisson
    residual converges, each landmass is a streamline, straits THREAD
    (pinning all land to one value would suppress net transport —
    that was the old bug) and ACCELERATE the flow (continuity
    squeeze). Divergence-freeness is by construction (the velocity is
    the curl of psi)."""
    from exp.k11_worldgen.currents import (
        _land_constants, _poisson_sor, _transport)
    water = np.ones((48, 48), bool)
    water[4:44, 20:24] = False          # land wall across the basin...
    water[22:26, 20:24] = True          # ...with a narrow strait

    # dipole forcing: flow between the poles must thread the gap
    zeta = np.zeros((48, 48))
    zeta[24, 8] = 1.0
    zeta[24, 40] = -1.0
    psi = _poisson_sor(zeta, water, pin=_land_constants(zeta, water))
    tu, tv = _transport(psi)
    sp = np.hypot(tu, tv)
    # the solve converged: 5-point Laplacian matches the source
    p = np.pad(psi, 1)
    lap = (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:]
           - 4.0 * psi)
    interior = water.copy()
    interior[0, :] = interior[-1, :] = False
    interior[:, 0] = interior[:, -1] = False
    assert np.abs((lap - zeta)[interior]).max() < 1e-3
    # every land cell is a streamline (constant psi per landmass; the
    # gap splits the wall into two bars with two constants)
    lo = psi[4:22, 20:24]
    hi = psi[26:44, 20:24]
    assert np.ptp(lo) < 1e-9 and np.ptp(hi) < 1e-9
    # the strait is THREADED: the right sub-basin is alive (pinned to
    # a single value it stagnates)
    right = sp[4:44, 30][water[4:44, 30]].mean()
    left = sp[4:44, 12][water[4:44, 12]].mean()
    assert right > 0.3 * left

    # channel-scale forcing: the same flux squeezed through the gap
    # accelerates (Venturi continuity), not blocked
    yy, _ = np.mgrid[0:48, 0:48]
    zeta_c = yy / 47.0 - 0.5
    psi_c = _poisson_sor(zeta_c, water,
                         pin=_land_constants(zeta_c, water))
    sp_c = np.hypot(*_transport(psi_c))
    gap = sp_c[22:26, 21:24].mean()
    approach = sp_c[4:44, 17][water[4:44, 17]].mean()
    assert gap > 2.0 * approach


def test_foehn_suppresses_lee_rain():
    """Same flow, same moisture: a downslope (descent, foehn) rains
    less than the mirror upslope (orographic lift)."""
    from exp.k11_worldgen.climate import _advect
    shape = (32, 64)
    u = np.full(shape, 1.0)                     # uniform eastward flow
    v = np.zeros(shape)
    water = np.zeros(shape, bool)
    lake = np.zeros(shape, bool)
    T = np.full(shape, 0.5)
    ramp = np.tanh((32 - np.arange(64)) / 4.0)  # steep x ramp, falls E
    # eastward flow: h rising eastward = upslope (lift), falling =
    # downslope (descent, foehn)
    up = _advect(u, v, (0.5 - 0.3 * ramp)[None, :] * np.ones(shape),
                 water, lake, T)
    down = _advect(u, v, (0.5 + 0.3 * ramp)[None, :] * np.ones(shape),
                   water, lake, T)
    assert up.mean() > down.mean()


def test_aquatic_classes():
    from exp.k11_worldgen.aquatic import AQUATIC_ID, classify_aquatic
    h = np.full((32, 32), 0.4)
    h[:, 0] = 0.349                   # very shallow warm shelf
    ocean = connected_ocean(h, 0.35)
    h[4:7, 4:7] = 0.35                # exorheic (fresh) lake
    h[24:27, 24:27] = 0.30            # endorheic (salt) lake
    hy = build_hydrology(h, ocean, sea_level=0.35)
    climate = {"T_monthly": np.full((12, 32, 32), 0.75),   # ~+19 degC
               "P_monthly": np.full((12, 32, 32), 0.5)}
    a = classify_aquatic(h, hy, climate, 0.35)
    t = lambda n: AQUATIC_ID[n]
    # warm, very shallow, clear of big-river sediment -> coral
    assert (a[:, 0] == t("coral reef")).all()
    # frost-free fresh bowl -> tropical lake
    assert (a[4:7, 4:7][hy["lake_mask"][4:7, 4:7]]
            == t("tropical lake")).all()
    # endorheic bowl -> salt lake
    assert (a[24:27, 24:27][hy["lake_mask"][24:27, 24:27]]
            == t("salt lake")).all()


def test_refine_climate_conditions_on_rain():
    from exp.k11_worldgen.climate import refine_climate
    shape = (16, 16)
    T_m = np.full((12, *shape), 0.5)   # ~2.5 degC all year
    P_m = np.zeros((12, *shape))
    P_m[6] = 0.8                        # wet july
    r1 = refine_climate(T_m, P_m)
    r2 = refine_climate(T_m, P_m)
    assert np.array_equal(r1, r2)       # deterministic
    assert (r1[6] < T_m[6]).all()       # wet month cools (evap + cloud)
    assert np.allclose(r1[0], T_m[0])   # dry month: nothing to condition on
    assert r1.min() >= 0.0 and r1.max() <= 1.0
    # uniform rain damps the seasonal swing
    swing = np.stack([np.full(shape, 0.5 + 0.2 * math.cos(2 * math.pi * (m - 6) / 12))
                      for m in range(12)])
    r3 = refine_climate(swing, np.ones((12, *shape)))
    assert (r3.max(axis=0) - r3.min(axis=0)).mean() < 0.39


def test_albedo_round_cools_under_cover():
    """Snow/ice albedo: covered cells cool in proportion to cover x
    insolation; bare cells are untouched; single damped round."""
    from exp.k11_worldgen.solar import ALBEDO_COOL_K, albedo_round
    shape = (4, 4)
    T_m = np.full((12, *shape), 0.5)
    pack = np.zeros((12, *shape))
    pack[:, :2] = 1000.0                # north half deep snow (full cover)
    zero = np.zeros((12, *shape))
    insol = np.full((12, 4), 1.0)
    land = np.ones(shape, bool)
    out = albedo_round(T_m, pack, zero, zero, insol, land)
    assert np.isclose(out[:, 2:].mean(), T_m[:, 2:].mean())   # bare: no change
    assert np.isclose(out[:, :2].mean(), 0.5 - ALBEDO_COOL_K)  # full cover: -K
    # no sun -> no cooling even under full cover
    dark = albedo_round(T_m, pack, zero, zero, np.zeros((12, 4)), land)
    assert np.array_equal(dark, T_m)


def test_thermal_lag_wraps_the_year():
    from exp.k11_worldgen.climate import _thermal_lag
    water = np.zeros((4, 4), bool)
    water[:, 2:] = True                       # west land, east ocean
    T = np.zeros((12, 4, 4))
    T[7] = 1.0                                # July spike only
    out = _thermal_lag(T, water)
    # deterministic, bounded, and the year is a loop: December feels
    # the July spike too (wrapping), more so over the ocean
    assert (out >= 0).all() and (out <= 1).all()
    assert out[0, 0, 0] > 0.0                 # Jan land remembers July
    # ocean lags more: peak response later and broader than land
    land_curve = out[:, 0, 0]
    ocean_curve = out[:, 0, 2]
    assert ocean_curve.argmax() >= land_curve.argmax()
    assert ocean_curve[0] > land_curve[0]     # more wrap into January
    # a constant year is untouched by the filter
    T1 = np.ones((12, 4, 4)) * 0.5
    assert np.allclose(_thermal_lag(T1, water), 0.5)


def test_soil_schedule_memory():
    from exp.k11_worldgen.climate import _soil_schedule
    P = np.full((12, 3, 3), 0.02)             # dry year
    P[3] = 0.8                                # one wet April
    T = np.full((12, 3, 3), 0.6)              # warm
    S = _soil_schedule(P, T)
    assert (S >= 0).all()
    # the bucket remembers: May carries April's rain, and December's
    # bucket feeds January (no cold start)
    assert S[4].mean() > S[2].mean()
    assert S[0].mean() > 0.0
    # a wetter year keeps a wetter bucket
    S_wet = _soil_schedule(np.full((12, 3, 3), 0.4), T)
    assert S_wet.mean() > S.mean()


@pytest.mark.slow
def test_climate_and_biome_overrides():
    elev, ocean = _tiny_world()
    hy = build_hydrology(elev, ocean)
    cl = build_climate(elev, hy, 0.35, seed=SEED)
    cl2 = build_climate(elev, hy, 0.35, seed=SEED)
    assert np.array_equal(cl["P"], cl2["P"])  # deterministic from seed
    assert cl["T_monthly"].shape == (12, *elev.shape)
    assert cl["P_monthly"].shape == (12, *elev.shape)
    # the weather pattern is delivered with the climate: N surface-wind
    # snapshots per month at the coarse grid (96 < 128, so uncoarsened
    # here), deterministic from the seed
    assert cl["wind_u"].shape == (12, 8, *elev.shape)
    assert cl["wind_v"].shape == (12, 8, *elev.shape)
    assert np.array_equal(cl["wind_u"], cl2["wind_u"])
    assert np.array_equal(cl["wind_v"], cl2["wind_v"])
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
    bm, _sim = classify_biomes(elev, hy, cl, 0.35)
    names = [b["name"] for b in BIOMES]
    # only standing water is a water biome — except mangrove, which
    # legitimately stands on shallow SEA (tidal flats) by override;
    # river cells keep their land biome
    water = hy["ocean_mask"] | hy["lake_mask"]
    assert {names[i] for i in np.unique(bm[water])} <= {"ocean", "lake", "mangrove"}
    assert {names[i] for i in np.unique(bm[hy["river_mask"]])} - {"ocean", "lake"} != set()
    cover = forest_cover(bm, cl["P"])
    assert cover.min() >= 0.0 and cover.max() <= 1.0


# ---- realistic (earth-patch) temperature mode ----------------------------

def test_resolve_center_lat():
    from exp.k11_worldgen.climate import resolve_center_lat
    assert resolve_center_lat(1, 52.0) == 52.0      # explicit passthrough
    assert resolve_center_lat(7, None) == resolve_center_lat(7, None)
    vals = {resolve_center_lat(s, None) for s in range(20)}
    assert len(vals) > 10                            # seed-varying
    for v in vals:
        assert abs(v - 45.0) < 7.5                   # leaky cap ~ +-7
    # user calibration: mean abs deviation ~3 deg
    devs = [abs(resolve_center_lat(s, None) - 45.0) for s in range(200)]
    assert 2.5 < sum(devs) / len(devs) < 3.5

def test_lat_profile_realistic():
    from exp.k11_worldgen.climate import _lat_profile
    from exp.k11_worldgen.units import T_MAX_C, T_MIN_C, temp_c
    lat = np.linspace(0.0, 1.0, 128)[:, None] * np.ones((1, 128))
    T_lat, T_amp = _lat_profile(lat, 1024.0, 0, 0, 0, 0,
                                realistic=True, center_lat=53.5,
                                shrink=4.0)
    ann_c = temp_c(T_lat)          # annual mean, degC
    amp_c = T_amp * (T_MAX_C - T_MIN_C)
    # north rim colder than south rim, monotone-ish gradient
    assert ann_c[0, 0] < ann_c[-1, 0] - 20.0
    assert (np.diff(ann_c[:, 0]) > -1e-9).all()
    # default center/shrink: 1024 km * 4 / 111.19 ~ 36.9 deg of latitude,
    # spanning ~35 degN (subtropical) to ~72 degN (arctic)
    assert abs(ann_c[0, 0] - (-11.0)) < 4.0     # ~72 degN ~ -11 degC
    assert abs(ann_c[-1, 0] - 18.0) < 4.0       # ~35 degN ~ +18 degC
    # seasonal swing grows poleward (continental north, aseasonal tropics)
    assert amp_c[-1, 0] < 10.0 < amp_c[0, 0]
    # shrink halves -> half the latitude span (milder gradient)
    T_lat2, _ = _lat_profile(lat, 1024.0, 0, 0, 0, 0,
                             realistic=True, center_lat=53.5, shrink=2.0)
    assert abs(temp_c(T_lat2)[-1, 0] - temp_c(T_lat2)[0, 0]) < \
        abs(ann_c[-1, 0] - ann_c[0, 0]) - 5.0
    # invented mode untouched: default knobs reproduce the legacy shape
    Ti, Ai = _lat_profile(lat, 512.0, 0.12, 0.93, 0.40, 0.12)
    assert abs(Ti[0, 0] - 0.12) < 1e-9
    assert Ti[-1, 0] > 0.8
    assert Ai.max() <= 0.03 + 0.12 + 1e-9


@pytest.mark.slow
def test_climate_realistic_mode():
    from exp.k11_worldgen.units import temp_c
    elev, ocean = _tiny_world()
    hy = build_hydrology(elev, ocean)
    cl = build_climate(elev, hy, 0.35, seed=SEED, realistic=True,
                       center_lat=50.0, shrink=4.0)
    cl2 = build_climate(elev, hy, 0.35, seed=SEED, realistic=True,
                        center_lat=50.0, shrink=4.0)
    assert np.array_equal(cl["T_monthly"], cl2["T_monthly"])
    ann = temp_c(cl["T"]).mean(axis=1)   # per-row annual mean, degC
    # the 96x96 tiny map is 384 km ~ 14 deg of latitude at shrink 4;
    # center 50 -> 57 degN north rim (~+2 degC), 43 degN south rim (~+13)
    assert ann[0] < 4.0
    assert ann[-1] > 8.0
    assert ann[-1] - ann[0] > 6.0
    # July above freezing even near the north rim (tundra, not ice sheet)
    jul = temp_c(cl["T_monthly"][6]).mean(axis=1)
    assert jul[0] > 0.0


# ---- complex derivation + full pipeline ---------------------------------------

@pytest.mark.slow
def test_derive_complex_clean_and_deterministic():
    elev, ocean = _tiny_world()
    hy = build_hydrology(elev, ocean)
    cl = build_climate(elev, hy, 0.35)
    bm, _sim = classify_biomes(elev, hy, cl, 0.35)
    names = [b["name"] for b in BIOMES]
    c1 = derive_complex(hy, bm, names)[0]
    c2 = derive_complex(hy, bm, names)[0]
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
    cx = derive_complex(hydro, np.zeros(shape, int), ["ocean"])[0]
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
    from exp.k11_worldgen.aquatic import classify_aquatic
    from exp.k11_worldgen.deliver import upscale_world
    elev, ocean = _tiny_world()
    hy = build_hydrology(elev, ocean)
    cl = build_climate(elev, hy, 0.35, seed=SEED)
    names = [b["name"] for b in BIOMES]
    bm, _sim = classify_biomes(elev, hy, cl, 0.35)
    cx = derive_complex(hy, bm, names)[0]
    aq = classify_aquatic(elev, hy, cl, 0.35)
    d = upscale_world(elev, hy, cl, cx, 0.35, aq, factor=4)
    H, W = elev.shape
    assert d["elev"].shape == (H * 4, W * 4)
    assert d["biome_map"].shape == (H * 4, W * 4)
    assert d["ocean_mask"].any() and (d["elev"] >= 0.35).any()
    assert not (d["river_mask"] & d["lake_mask"]).any()
    # ocean is always sub-sea (connectivity is carried from the anchor)
    assert not (d["ocean_mask"] & (d["elev"] >= 0.35)).any()
    # the delivery rim is a 1 km rock border, never water
    from exp.k11_worldgen.biomes import BIOME_ID
    assert (d["biome_map"][0, :] == BIOME_ID["rock"]).all()
    assert (d["biome_map"][:, 0] == BIOME_ID["rock"]).all()
    assert not d["ocean_mask"][0, :].any() and not d["lake_mask"][:, -1].any()
    d2 = upscale_world(elev, hy, cl, cx, 0.35, aq, factor=4)
    assert np.array_equal(d["biome_map"], d2["biome_map"])  # deterministic
    # marine classes are recomputed pointwise at delivery: every
    # delivered open-water cell carries a MARINE class (not a stamped
    # anchor block), lakes and rivers keep their relational families
    from exp.k11_worldgen.aquatic import AQUATIC_ID
    marine_ids = {AQUATIC_ID[n] for n in (
        "open ocean", "polar shelf", "temperate shelf", "tropical shelf",
        "coral reef", "temperate upwelling", "tropical upwelling")}
    lake_ids = {AQUATIC_ID[n] for n in (
        "inland sea", "salt lake", "large lake", "polar lake",
        "montane lake", "tropical lake", "temperate lake")}
    river_ids = set(range(len(AQUATIC_ID))) - marine_ids - lake_ids
    open_water = d["ocean_mask"] & ~d["river_mask"]
    assert set(np.unique(d["aquatic"][open_water])) <= marine_ids
    assert set(np.unique(d["aquatic"][d["lake_mask"]])) <= lake_ids
    assert set(np.unique(d["aquatic"][d["river_mask"]])) <= river_ids


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
    bm, _sim = classify_biomes(elev, hy, cl, 0.35)
    names = [b["name"] for b in BIOMES]
    cx = derive_complex(hy, bm, names)[0]
    from exp.k11_worldgen.aquatic import classify_aquatic
    from exp.k11_worldgen.currents import build_currents
    aq = classify_aquatic(elev, hy, cl, 0.35)
    cur = build_currents(elev, ocean, 0.35, seed=SEED)
    world = {"elev": elev, "hydro": hy, "climate": cl, "biome_map": bm,
             "cover": forest_cover(bm, cl["P"]), "complex": cx,
             "plates": plates, "ocean_mask": ocean, "aquatic": aq,
             "currents": cur}
    delivered = upscale_world(elev, hy, cl, cx, 0.35, factor=4, aquatic=aq)
    marks = compute_marks(delivered, hy, 0.35, 4)
    save_world(str(tmp_path), world, delivered, SEED, 0.35, 4,
               {"plates": plates.n}, marks, {"determinism": True})
    assert (tmp_path / "world.json").exists() and (tmp_path / "world.npz").exists()
    data = load_world(str(tmp_path))
    assert np.array_equal(data["world"]["elev"], elev)
    assert np.array_equal(data["world"]["climate"]["T_monthly"], cl["T_monthly"])
    assert np.array_equal(data["world"]["climate"]["wind_u"], cl["wind_u"])
    assert np.array_equal(data["world"]["climate"]["wind_v"], cl["wind_v"])
    assert np.array_equal(data["delivered"]["biome_map"], delivered["biome_map"])
    assert np.array_equal(data["world"]["currents"]["u"], cur["u"])
    # the loaded currents are complete: monthly velocity fields work
    from exp.k11_worldgen.currents import rise_monthly, velocity_field
    ul, vl = velocity_field(data["world"]["currents"], 3)
    assert ul.shape == elev.shape and np.isfinite(ul).all()
    # the nutrient store round-trips: monthly upwelling, seasonal
    rm = data["world"]["currents"]["rise_monthly"]
    assert rm.shape == (12, *elev.shape)
    assert np.array_equal(rm, rise_monthly(cur))
    assert rm.std(axis=0).max() > 0          # it really breathes
    assert data["world"]["plates"].n == plates.n
    assert len(data["marks"]) == len(marks)
    cx2 = load_complex(str(tmp_path))
    assert cx == cx2  # Complex.__eq__ compares value-wise incl. DriftFields


def _bowl_terrain():
    """48x48 tilted plane draining north, border ocean ring, and a
    shallow 4x4 pit near the south edge: small catchment, <180 m deep,
    so pass 1's uniform water balance rejects it."""
    H, W = 48, 48
    h = 0.5 + 0.2 * (np.arange(H)[:, None] / (H - 1)) * np.ones((1, W))
    h[40:44, 20:24] = 0.65            # pit floor below its ~0.6625 sill
    h[0, :] = h[-1, :] = h[:, 0] = h[:, -1] = 0.2
    return h


def _flat_climate(shape, p_norm, t_c):
    from exp.k11_worldgen.units import T_MAX_C, T_MIN_C
    t_norm = (t_c - T_MIN_C) / (T_MAX_C - T_MIN_C)
    return {"P": np.full(shape, p_norm),
            "T_monthly": np.full((12,) + shape, t_norm)}


def test_refine_hydrology_lush_ponds():
    from exp.k11_worldgen.hydrology import (
        build_hydrology, connected_ocean, refine_hydrology)
    h = _bowl_terrain()
    bowl = np.zeros_like(h, bool)
    bowl[40:44, 20:24] = True
    ocean = connected_ocean(h, 0.35)
    hy = build_hydrology(h, ocean, sea_level=0.35, seed=SEED)
    assert not hy["lake_mask"][bowl].any()       # pass 1 rejects it
    # wet + cold: the P-weighted inflow beats weak evaporation — pond
    hy2 = refine_hydrology(hy, h, _flat_climate(h.shape, 0.8, 2.0), 0.35,
                           seed=SEED)
    assert hy2["lake_mask"][bowl].all()
    assert (hy2["w"][bowl] > h[bowl]).all()      # real water surface
    # hot + dry: nothing sprouts
    hy = build_hydrology(h, ocean, sea_level=0.35, seed=SEED)
    hy3 = refine_hydrology(hy, h, _flat_climate(h.shape, 0.05, 30.0), 0.35,
                           seed=SEED)
    assert not hy3["lake_mask"][bowl].any()
    # invariants: rivers never inside lakes, discharge persisted
    assert not (hy2["river_mask"] & hy2["lake_mask"]).any()
    assert hy2["discharge"].shape == h.shape


def test_refine_hydrology_stream_density_follows_rain():
    from exp.k11_worldgen.hydrology import (
        build_hydrology, connected_ocean, refine_hydrology)
    h = _bowl_terrain()
    ocean = connected_ocean(h, 0.35)
    # rain only in the southern (high) half: streams sprout there
    P = np.full(h.shape, 0.02)
    P[h.shape[0] // 2:, :] = 0.8
    cl = _flat_climate(h.shape, 0.0, 15.0)
    cl["P"] = P
    wet = refine_hydrology(build_hydrology(h, ocean, sea_level=0.35,
                                           seed=SEED),
                           h, cl, 0.35, seed=SEED)
    dry = refine_hydrology(build_hydrology(h, ocean, sea_level=0.35,
                                           seed=SEED),
                           h, _flat_climate(h.shape, 0.02, 15.0), 0.35,
                           seed=SEED)
    assert wet["river_mask"].sum() > dry["river_mask"].sum()
    extra = wet["river_mask"] & ~dry["river_mask"]
    # new headwater streams sprout in the wet south; the dry north can
    # only gain trunk cells carrying southern water (Nile effect)
    assert extra[h.shape[0] // 2:, :].any()
    north_extra = np.zeros_like(extra)
    north_extra[:h.shape[0] // 2, :] = extra[:h.shape[0] // 2, :]
    if north_extra.any():
        q, acc = wet["discharge"], wet["accumulation"]
        # discharge far above what the dry northern catchment could
        # supply on its own — the water is imported from the south
        assert (q[north_extra] > 2.5 * 0.02 * acc[north_extra]).all()


def _refine_monthly(h, p=0.3, melt_spec=None, soil=None):
    """Bowl-terrain hydro with monthly climate fields. melt_spec:
    (month, amount, southern_half_only)."""
    from exp.k11_worldgen.hydrology import (
        build_hydrology, connected_ocean, refine_hydrology)
    ocean = connected_ocean(h, 0.35)
    cl = _flat_climate(h.shape, p, 15.0)
    cl["P_monthly"] = np.full((12,) + h.shape, p)
    melt = np.zeros((12,) + h.shape)
    if melt_spec is not None:
        m, amt, south = melt_spec
        if south:
            melt[m, h.shape[0] // 2:, :] = amt
        else:
            melt[m] = amt
    cl["snowmelt_monthly"] = melt
    if soil is not None:
        cl["soil_monthly"] = np.full((12,) + h.shape, soil)
    return refine_hydrology(build_hydrology(h, ocean, sea_level=0.35,
                                            seed=SEED),
                            h, cl, 0.35, seed=SEED)


def test_month_aware_complex_one_network():
    """ONE network: base edges carry monthly width classes (location
    never changes), seasonal edges join or float beside them, and the
    monthly per-cell products derive from the edge state."""
    from exp.k11_worldgen.complexify import derive_complex
    h = _bowl_terrain()
    hy = _refine_monthly(h, p=0.2, melt_spec=(4, 400.0, True))
    cx, em = derive_complex(hy, np.zeros(h.shape, np.uint8), ["x"])
    assert em                                       # month-aware
    base = {eid: c for eid, c in em.items()
            if cx.edges[eid].kind == "river"}
    seas = {eid: c for eid, c in em.items()
            if cx.edges[eid].kind == "river_seasonal"}
    # some base edge is wet all year (emergent permanence)
    assert any(min(c) >= 1 for c in base.values())
    # seasonal edges exist and run in the melt month
    assert seas and any(c[4] >= 1 for c in seas.values())
    # monthly per-cell products come FROM the edge state
    assert hy["river_width_monthly"].shape == (12,) + h.shape
    assert (hy["river_monthly"] == (hy["river_width_monthly"] > 0)).all()
    assert (hy["river_perm"] == hy["river_monthly"].all(axis=0)).all()
    # every seasonal edge terminates at a node of the same complex
    for eid in seas:
        assert cx.edges[eid].node_b in cx.nodes


def test_monthly_rivers_soil_baseflow_keeps_trunks():
    """No rain, no melt: without the soil term every edge is dry all
    year; with standing soil moisture the trunk keeps running
    (baseflow)."""
    from exp.k11_worldgen.complexify import derive_complex
    h = _bowl_terrain()
    hy_dry = _refine_monthly(h, p=0.0)
    _, em_dry = derive_complex(hy_dry, np.zeros(h.shape, np.uint8), ["x"])
    assert not hy_dry["river_monthly"].any()        # no water: all dry
    assert all(max(c) == 0 for c in em_dry.values())
    hy_wet = _refine_monthly(h, p=0.0, soil=2.0)
    _, em_wet = derive_complex(hy_wet, np.zeros(h.shape, np.uint8), ["x"])
    assert hy_wet["river_monthly"].any()            # baseflow runs
    assert any(min(c) >= 1 for c in em_wet.values())  # ...all year


def test_unified_complex_audit_clean():
    """The month-aware complex (base + seasonal joins/floats) has no
    mechanical defects: seasonal joins are real nodes, nothing
    crosses the base network nodelessly."""
    from exp.k11_worldgen.complexify import derive_complex
    from kernel.complex.audit import audit
    h = _bowl_terrain()
    hy = _refine_monthly(h, p=0.2, melt_spec=(4, 400.0, True))
    cx, _ = derive_complex(hy, np.zeros(h.shape, np.uint8), ["x"])
    defects = audit(cx)
    fatal = [d for d in defects
             if d.split(":")[0] in (
                 "dangling_edge", "nodeless_intersection", "isolated_patch")]
    assert not fatal
    # every edge's polyline truly connects its OWN nodes — an id
    # collision leaves a polyline ending far from its node (the
    # shredded-stamp defect). Mouth edges may extend past node_b into
    # the receiving water cell, possibly via a diagonal corner (the
    # waterline render rule), so node_b must appear in the last points.
    for e in cx.edges.values():
        assert e.polyline[0] == cx.nodes[e.node_a].pos
        assert cx.nodes[e.node_b].pos in e.polyline[-3:]


def test_glacier_flow_routes_ice_downslope():
    """Glacier pass: net-growth rows export ice downslope; ablation
    (unused melt potential) eats it below the equilibrium line; the
    flux ends at the terminus — or calves at a pit."""
    from exp.k11_worldgen.hydrology import _D8, glacier_flow
    H, W = 10, 1
    direction = np.full((H, W), -1, dtype=int)
    direction[:9, 0] = _D8.index((1, 0))     # all flow south to a pit
    flat = np.zeros((H, W))
    w_route = np.linspace(1.0, 0.0, H)[:, None]
    land = np.ones((H, W), bool)
    meltpot = np.zeros((12, H, W))
    meltpot[6, 4:] = 300.0                   # july heat below row 4
    melt = np.zeros((12, H, W))

    # big accumulation: the tongue reaches the pit and calves there
    snowfall = np.zeros((12, H, W))
    snowfall[:, :4] = 100.0                  # 1200 mm/yr on rows 0-3
    glacier, flux, ice_melt_m = glacier_flow(
        direction, flat, w_route, land, snowfall, meltpot, melt)
    assert glacier[:4].all()                 # the growth zone itself
    assert glacier.sum() > 4                 # tongue extends below it
    assert ice_melt_m.sum() <= 4 * 1200.0 + 1e-9
    assert ice_melt_m[6].sum() > 0           # melts only with potential
    assert ice_melt_m[:6].sum() == 0 and ice_melt_m[7:].sum() == 0

    # small accumulation: ablation consumes the flux — the cell where
    # the last ice melts is the melt front, NOT ice-covered year-round
    snowfall_small = np.zeros((12, H, W))
    snowfall_small[:, :4] = 50.0 / 12        # 50 mm/yr on rows 0-3
    g2, f2, im2 = glacier_flow(
        direction, flat, w_route, land, snowfall_small, meltpot, melt)
    assert g2[:4].all()                      # the year-round snowfield
    assert not g2[4:].any()                  # melt front is not glacier
    assert abs(im2.sum() - 200.0) < 1e-6     # all the ice still melts

    # deterministic
    g3 = glacier_flow(direction, flat, w_route, land, snowfall,
                      meltpot, melt)
    assert np.array_equal(glacier, g3[0]) and np.array_equal(flux, g3[1])


def test_river_raster_continuous():
    """Every base edge renders as a CONTINUOUS stamped path from its
    start cell to its end cell (8-connected flood). The step-count
    truncation bug (floor of a fractional span) skipped pixel rows
    along the walk — 1-px holes along every reach."""
    from exp.k11_worldgen.complexify import derive_complex
    from exp.k11_worldgen.deliver import river_raster
    h = _bowl_terrain()
    hy = _refine_monthly(h, p=0.2, melt_spec=(4, 400.0, True))
    cx, _ = derive_complex(hy, np.zeros(h.shape, np.uint8), ["x"])
    Hh, Wh = h.shape
    f = 4
    phantom = (hy["w_route"] - hy["w"]) > 1e-9
    ov = {e.id: (e.quality if e.kind == "river" else 0.0)
          for e in cx.edges.values()}
    width = river_raster(cx, (Hh * f, Wh * f), f, w=hy["w"],
                         sea_level=0.35, phantom=phantom,
                         quality_override=ov)
    mask = width > 0
    H, W = mask.shape
    broken = []
    for e in cx.edges.values():
        if e.kind != "river":
            continue
        sy, sx = int(e.polyline[0][1]), int(e.polyline[0][0])
        ey, ex = int(e.polyline[-1][1]), int(e.polyline[-1][0])
        start = [(y, x) for y in range(sy * f, sy * f + f)
                 for x in range(sx * f, sx * f + f)
                 if 0 <= y < H and 0 <= x < W and mask[y, x]]
        seen, stack = set(start), list(start)
        reached = False
        while stack and not reached:
            y, x = stack.pop()
            if ey * f <= y < ey * f + f and ex * f <= x < ex * f + f:
                reached = True
                break
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    ny, nx_ = y + dy, x + dx
                    if (0 <= ny < H and 0 <= nx_ < W and mask[ny, nx_]
                            and (ny, nx_) not in seen):
                        seen.add((ny, nx_))
                        stack.append((ny, nx_))
        if not reached:
            broken.append(e.id)
    assert not broken


def test_strahler_carries_through_lakes():
    from exp.k11_worldgen.hydrology import strahler_order
    # two order-1 headwaters join into order 2, cross a lake, and must
    # emerge as order 2 — not restart at 1
    direction = np.full((5, 5), -1, dtype=int)
    river = np.zeros((5, 5), dtype=bool)
    lake = np.zeros((5, 5), dtype=bool)
    # headwaters at (0,1) and (0,3) join at (1,2), flow to lake at
    # (2,2)-(3,2), outlet at (4,2)
    path = [(0, 1), (1, 2), (2, 2), (3, 2), (4, 2)]
    path2 = [(0, 3), (1, 2)]
    river[path[0]] = river[path[1]] = river[path2[0]] = river[path[4]] = True
    lake[2, 2] = lake[3, 2] = True
    direction[0, 1] = direction[0, 3] = 7  # down-left/down-right... set below
    from exp.k11_worldgen.hydrology import _D8
    down = _D8.index((1, 0))
    dl = _D8.index((1, -1))
    dr = _D8.index((1, 1))
    direction[0, 1] = dr          # (0,1) -> (1,2)
    direction[0, 3] = dl          # (0,3) -> (1,2)
    direction[1, 2] = down        # (1,2) -> (2,2)
    direction[2, 2] = down        # (2,2) -> (3,2)
    direction[3, 2] = down        # (3,2) -> (4,2)
    acc = np.zeros((5, 5))
    for i, (y, x) in enumerate([(0, 1), (0, 3), (1, 2), (2, 2), (3, 2), (4, 2)]):
        acc[y, x] = i + 1
    order = strahler_order(direction, river, acc, lake=lake)
    assert order[1, 2] == 2       # confluence of two 1s
    assert order[4, 2] == 2       # the outlet keeps order 2 past the lake


def test_volcanoes():
    """Volcanic cones: seeded on convergent faults, deterministic,
    elevation raised at the summit with a crater dip, metadata sane."""
    from exp.k11_worldgen.plates import build_elevation, build_volcanoes
    from kernel.hashrng import Stream
    stream = Stream(SEED, "t.volc")
    elev, plates = build_elevation(stream, (128, 128), sea_level=0.35)
    e1, v1 = build_volcanoes(Stream(SEED, "t.volc").child("volcanoes"),
                             plates, elev, 0.35)
    e2, v2 = build_volcanoes(Stream(SEED, "t.volc").child("volcanoes"),
                             plates, elev, 0.35)
    assert v1 == v2 and np.array_equal(e1, e2)        # deterministic
    if not v1:
        return                                        # fault-poor world
    for y, x, h_m in v1:
        assert 200.0 <= h_m <= 5000.0
        # near a convergent fault by construction
        assert plates.fault_dist[y, x] <= 2
        assert plates.fault_conv[y, x] > 0
        # the cone raised the terrain, and the crater dips the summit
        assert e1[y, x] > elev[y, x] - 0.01
        ring = e1[max(0, y - 3):y + 4, max(0, x - 3):x + 4]
        assert ring.max() > e1[y, x]
    # spacing respected
    for i, (y1, x1, *_a) in enumerate(v1):
        for y2, x2, *_b in v1[i + 1:]:
            assert (y1 - y2) ** 2 + (x1 - x2) ** 2 >= 12 ** 2


def test_river_speed_manning_and_jitter():
    """Manning reach speed: positive on-river, zero off-river, monotone
    in discharge and slope, leaky-capped; jitter deterministic and
    multiplicative (the sub-grid variance around the reach average)."""
    from exp.k11_worldgen.hydrology import (
        SPEED_JITTER, V_RIVER_MAX, river_speed, speed_jitter)
    H, W = 16, 16
    sea = 0.35
    # tilted filled surface falling SOUTH so D8 index 6 = (+1, 0) is
    # downhill: row 0 high, bottom row low
    tilt = np.arange(H)[:, None] / (H - 1) * np.ones((1, W))
    w_route = 0.8 - 0.2 * tilt
    direction = np.full((H, W), 6, dtype=np.int8)
    river = np.ones((H, W), bool)
    dis_low = np.full((H, W), 50.0)
    dis_high = np.full((H, W), 500.0)
    v_low = river_speed(dis_low, river, w_route, direction, sea)
    v_high = river_speed(dis_high, river, w_route, direction, sea)
    assert (v_low > 0).all() and (v_low <= V_RIVER_MAX).all()
    assert (v_high > v_low).all()          # more water: deeper, faster
    steep = 0.8 - 0.4 * tilt
    v_steep = river_speed(dis_low, river, steep, direction, sea)
    # steeper: faster, same water (last row self-clips to zero drop —
    # both sit at the slope floor there)
    assert (v_steep >= v_low).all() and (v_steep[:-1] > v_low[:-1]).all()
    assert river_speed(dis_low, np.zeros((H, W), bool), w_route,
                       direction, sea).max() == 0.0
    j1 = speed_jitter(7, (H, W))
    assert np.array_equal(j1, speed_jitter(7, (H, W)))
    assert not np.array_equal(j1, speed_jitter(8, (H, W)))
    lo, hi = np.exp(-SPEED_JITTER), np.exp(SPEED_JITTER)
    assert j1.min() >= lo and j1.max() <= hi
    assert np.allclose(
        river_speed(dis_low, river, w_route, direction, sea, j1),
        v_low * j1)


def test_refine_persists_river_speed():
    """refine_hydrology persists the first-class speed fields: annual
    (H,W) + monthly (12,H,W), zero off-river, positive on it."""
    hy = _refine_monthly(_bowl_terrain())
    rm = hy["river_mask"]
    assert rm.any()
    assert hy["river_speed"].shape == rm.shape
    assert hy["river_speed_monthly"].shape == (12,) + rm.shape
    assert (hy["river_speed"][rm] > 0).all()
    assert hy["river_speed"][~rm].max() == 0.0
    assert hy["river_speed_monthly"][:, ~rm].max() == 0.0


def test_glacier_thickness_flux_keyed():
    """Equilibrium thickness: 0 with no ice, monotone in throughput,
    leaky-capped at the soft ceiling (never a hard clamp)."""
    from exp.k11_worldgen.hydrology import THICK_SOFT_M, glacier_thickness
    assert glacier_thickness(np.zeros((2, 2))).max() == 0.0
    f = np.array([[1e2, 1e4], [1e6, 1e8]])
    t = glacier_thickness(f)
    assert t[0, 0] < t[0, 1] < t[1, 0] < t[1, 1]
    # above the soft cap tanh leaks slowly, never clips flat: still
    # (barely) monotone, and bounded well under 2x the cap
    assert t.max() < 2.0 * THICK_SOFT_M


def test_terminus_taper_thins_snout():
    """The front taper: 0 at the melt front, sqrt ramp to full
    thickness TAPER_CELLS upstream, 1 off the glacier."""
    from exp.k11_worldgen.hydrology import TAPER_CELLS, terminus_taper
    H, W = 24, 24
    g = np.zeros((H, W), bool)
    g[2:H - 4, 10:12] = True                  # the strip, flowing south
    direction = np.full((H, W), 6, dtype=np.int8)   # 6 = south (_D8)
    scale = terminus_taper(g, direction)
    term_r = H - 5                            # strip's bottom row
    assert scale.shape == g.shape
    assert (scale[~g] == 1.0).all()           # off-glacier untouched
    assert (scale[term_r, 10:12] == 0.0).all()      # the melt front
    # sqrt ramp upstream
    for d in range(1, TAPER_CELLS):
        want = np.sqrt(d / TAPER_CELLS)
        assert np.allclose(scale[term_r - d, 10:12], want, atol=1e-6)
    # far interior: full thickness
    assert (scale[2:term_r - TAPER_CELLS, 10:12] == 1.0).all()
    # monotone upstream
    col = scale[2:term_r + 1, 10]
    assert (np.diff(col) <= 1e-6).all()
    # deterministic
    assert np.array_equal(scale, terminus_taper(g, direction))
    # a calving margin (downstream not glacier) is a terminus too:
    # an isolated glacier cell is its own front
    g2 = np.zeros((H, W), bool)
    g2[5, 5] = True
    s2 = terminus_taper(g2, direction)
    assert s2[5, 5] == 0.0


def _glacier_hydro(h, strip_cols=(10, 12), lake_cell=None):
    """Synthetic glacier state on a south-draining tilt: a flux strip
    growing downstream, terminus at the strip's bottom end."""
    from exp.k11_worldgen.hydrology import glacier_thickness
    H, W = h.shape
    g = np.zeros((H, W), bool)
    g[2:H - 4, strip_cols[0]:strip_cols[1]] = True
    flux = np.zeros((H, W))
    rows = np.broadcast_to(np.arange(H)[:, None] + 1, (H, W))
    flux[g] = 1e4 * rows[g]                        # grows downstream
    lake = np.zeros((H, W), bool)
    if lake_cell is not None:
        lake[lake_cell] = True
    return {
        "glacier_mask": g,
        "glacier_flux": flux.astype(np.float32),
        "glacier_thick_m": glacier_thickness(flux),
        "flow_dir": np.full((H, W), 6, dtype=np.int8),   # all south
        "lake_mask": lake,
        "ocean_mask": np.zeros((H, W), bool),
    }


def test_glacial_terrain_responds_once():
    """Erosion under ice, deposition at termini (mass-conserving), ice
    raise by thickness; standing-water beds never eroded; deterministic.
    """
    from exp.k11_worldgen.hydrology import glacial_terrain
    from exp.k11_worldgen.units import ELEV_MAX_M
    sea = 0.35
    scale = (1.0 - sea) / ELEV_MAX_M
    H, W = 24, 24
    h = 0.6 + 0.1 * (np.arange(H)[:, None] / (H - 1)) * np.ones((1, W))
    lake_cell = (5, 11)                    # inside the strip
    hydro = _glacier_hydro(h, lake_cell=lake_cell)
    g = hydro["glacier_mask"]
    h2, changed = glacial_terrain(h, hydro, sea)
    assert changed
    # ice raise is exactly thickness (minus erosion, plus deposit share)
    ice_raise = np.where(g, hydro["glacier_thick_m"], 0.0) * scale
    bed = (h2 - h) - ice_raise             # erosion + deposition only
    assert bed[g].max() < 0.0 or bed[~g].max() > 0.0
    # mass conserved: eroded volume == deposited volume (float64
    # roundoff from the normalization is negligible)
    assert abs(bed.sum()) < 1e-6 * abs(bed).sum()
    # the strip's interior erodes (bed drops), the terminus zone gains
    interior = np.s_[3:H - 8, 10:12]
    assert bed[interior].mean() < 0.0
    term_zone = np.s_[H - 6:H - 1, 8:14]
    assert bed[term_zone].max() > 0.0
    # the lake bed is never eroded: its change is pure ice raise
    # (tolerance covers float64 cancellation in h+delta-h, ~1e-4 mm)
    assert abs(bed[lake_cell]) < 1e-8
    # deterministic: same inputs, byte-identical output
    h3, _ = glacial_terrain(h, hydro, sea)
    assert np.array_equal(h2, h3)
    # no glacier state: untouched
    h4, changed4 = glacial_terrain(h, {"glacier_mask": np.zeros_like(g)},
                                   sea)
    assert not changed4 and np.array_equal(h4, h)


def test_glacier_biome_override():
    """Cells under flowing ice classify as ice biome even when the
    month's curves say something warmer."""
    from exp.k11_worldgen.biomes import BIOME_ID, _apply_overrides
    H, W = 6, 6
    b = np.full((H, W), BIOME_ID["temperate grassland"], dtype=np.uint8)
    gm = np.zeros((H, W), bool)
    gm[2, 2] = True
    st = {
        "ocean_m": np.zeros((H, W), bool),
        "lake_m": np.zeros((H, W), bool),
        "river_m": np.zeros((H, W), bool),
        "alt_m": np.full((H, W), 500.0),
        "hand_m": np.full((H, W), 50.0),
        "width": np.zeros((H, W), dtype=np.int16),
        "T_warm": np.full((H, W), 20.0),
        "T_cold": np.full((H, W), 5.0),
        "P_wet": np.full((H, W), 50.0),
        "glacier_m": gm,
    }
    out = _apply_overrides(b, st)
    assert out[2, 2] == BIOME_ID["ice"]
    assert (out[gm] == BIOME_ID["ice"]).all()
    assert (out[~gm] == BIOME_ID["temperate grassland"]).all()


def test_glacier_extent_hires_tapers_edges():
    """Delivered-resolution glacier extent: the interpolated mask
    re-thresholded at 0.5 — edges and tongue tips render at the fine
    grid (diagonal, not 4x4 km blocks) while the anchor-level extent
    decision (area) is preserved."""
    from exp.k11_worldgen.deliver import glacier_extent_hires
    factor = 4
    H, W = 24, 24
    # a diagonal tongue: 2-cell-wide band along the main diagonal
    g = np.zeros((H, W), bool)
    for i in range(4, H - 4):
        g[i, i] = g[i, i + 1] = True
    hydro = {"glacier_mask": g}
    hi = glacier_extent_hires(hydro, factor)
    assert hi.shape == (H * factor, W * factor)
    kron = np.kron(g, np.ones((factor, factor), bool))
    # area preserved (the extent is an anchor-level decision): fine
    # boundary rounding only, no fattening of a thin tongue
    assert abs(hi.sum() - kron.sum()) < 0.15 * kron.sum()
    # not block-aligned: some row's glacier run starts or ends at a
    # column that is not a multiple of the factor (a kron stamp can
    # never do that)
    ragged = 0
    for row in hi:
        cols = np.flatnonzero(row)
        if len(cols) and (cols[0] % factor or (cols[-1] + 1) % factor):
            ragged += 1
    assert ragged > 0
    # deterministic
    assert np.array_equal(hi, glacier_extent_hires(hydro, factor))
    # no glacier state -> None
    assert glacier_extent_hires({}, factor) is None


def test_glacier_extent_hires_thins_tapered_tips():
    """A thin (tapered) snout renders as partial sub-cell cover: the
    same mask with a thin tip cell extends less far than with a
    full-thickness tip, while thick margins are unaffected."""
    from exp.k11_worldgen.deliver import glacier_extent_hires
    factor = 4
    H, W = 24, 24
    g = np.zeros((H, W), bool)
    g[4:H - 4, 10:12] = True                  # south-flowing strip
    thick_full = np.where(g, 300.0, 0.0)
    thick_thin = thick_full.copy()
    thick_thin[H - 5, 10:12] = 5.0            # tapered snout row
    hi_full = glacier_extent_hires(
        {"glacier_mask": g, "glacier_thick_m": thick_full}, factor)
    hi_thin = glacier_extent_hires(
        {"glacier_mask": g, "glacier_thick_m": thick_thin}, factor)
    assert hi_thin.sum() < hi_full.sum()      # the tip shrank
    # the difference is at the snout, not along the thick margins
    diff = hi_full & ~hi_thin
    rows = np.flatnonzero(diff.any(axis=1))
    assert rows.min() >= (H - 6) * factor
    # margins unaffected
    assert np.array_equal(hi_thin[:(H - 7) * factor],
                          hi_full[:(H - 7) * factor])


def test_refine_reuses_glacier_state():
    """A handed-in glacier state travels into hydro unchanged (the
    detect-once rule) instead of being re-derived."""
    from exp.k11_worldgen.hydrology import (
        build_hydrology, connected_ocean, refine_hydrology)
    h = _bowl_terrain()
    H, W = h.shape
    g = np.zeros((H, W), bool)
    g[3:5, 3:5] = True
    state = {
        "glacier_mask": g,
        "glacier_flux": np.ones((H, W), dtype=np.float32),
        "glacier_melt_monthly": np.zeros((12, H, W), dtype=np.float32),
        "glacier_thick_m": np.ones((H, W), dtype=np.float32) * 100.0,
    }
    ocean = connected_ocean(h, 0.35)
    cl = {"P": np.full(h.shape, 0.3),
          "T_monthly": np.full((12,) + h.shape, 0.7),
          "P_monthly": np.full((12,) + h.shape, 0.3),
          "snowmelt_monthly": np.zeros((12,) + h.shape)}
    hy2 = refine_hydrology(build_hydrology(h, ocean, sea_level=0.35,
                                           seed=SEED),
                           h, cl, 0.35, seed=SEED, glacier_state=state)
    assert np.array_equal(hy2["glacier_mask"], g)
    assert np.array_equal(hy2["glacier_thick_m"], state["glacier_thick_m"])


def test_detect_glaciers_regional_firn_rule():
    """The growth zone is REGIONAL: a coherent block of year-round snow
    forms ice, an isolated marginal speck with the same local surplus
    does not, and a token-surplus background (most of the year's snow
    melts) never seeds phantom glaciers."""
    from exp.k11_worldgen.hydrology import detect_glaciers
    H, W = 9, 9
    flow = np.full((H, W), 6, dtype=np.int8)   # all south
    flow[-1, :] = -1                           # bottom row: pits
    hydro = {
        "flow_dir": flow,
        "flat_depth": np.zeros((H, W)),
        "w_route": (1.0 - np.arange(H)[:, None] / H) * np.ones((1, W)),
        "ocean_mask": np.zeros((H, W), bool),
        "lake_mask": np.zeros((H, W), bool),
    }
    sf = np.full((12, H, W), 50.0)         # 600 mm/yr everywhere
    melt = np.full((12, H, W), 45.0)       # background: 540 melts,
                                           # token 60 surplus (10%)
    block = np.s_[2:5, 2:5]
    melt[:, block[0], block[1]] = 0.0      # coherent firn block
    melt[:, 7, 7] = 0.0                    # isolated speck, same surplus
    climate = {
        "snowfall_monthly": sf.astype(np.float32),
        "snowmelt_monthly": melt.astype(np.float32),
        "meltpot_monthly": melt.astype(np.float32),   # no extra ablation
    }
    g = detect_glaciers(hydro, climate)
    gm = g["glacier_mask"]
    # the block forms ice (corners round off — they are regionally
    # marginal, that IS the smoothing's job)
    assert gm[3, 3] and gm[block].sum() >= 7
    assert not gm[7, 7]                    # the isolated speck is not
    assert not gm[0, 0]                    # token-surplus background: no
    assert gm[0, 0] == gm[1, 1] == gm[0, 8] == False
    # tongue: block ice flows south through background cells
    assert gm[6, 3] or gm[8, 3]            # downstream of the block
