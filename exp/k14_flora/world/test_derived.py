"""K14 P6 tests — derived products (D0) over the K11 seed-1 dump.

Run: uv run pytest -q exp/k14_flora/world/
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np
import pytest

from exp.artifacts import find as artifact_find
from exp.k14_flora.world import derived

SEED = 1

pytestmark = pytest.mark.skipif(
    artifact_find("k11", SEED) is None, reason="no local k11 seed-1 dump")


@pytest.fixture(scope="module")
def result():
    return derived.build(SEED)


@pytest.fixture(scope="module")
def inputs():
    z, manifest, seed_dir = derived.load_inputs(SEED)
    return z, manifest


# ── determinism ────────────────────────────────────────────────────────


def test_deterministic(result):
    again = derived.build(SEED)
    for name, a in result["products"].items():
        assert np.array_equal(a, again["products"][name]), name
    assert result["points"] == again["points"]


# ── waterfalls ─────────────────────────────────────────────────────────


def test_waterfalls_on_river_with_real_drops(result, inputs):
    from exp.k11_worldgen.units import alt_m
    z, manifest = inputs
    sea = float(manifest["sea_level"])
    alt = alt_m(z["w_elev"], sea)
    factor = 4
    assert result["points"]["waterfalls"]
    for p in result["points"]["waterfalls"]:
        # provenance: the anchor cell the drop was measured on (the
        # delivered point is snapped to the river line, which can sit
        # in a neighboring block, so p//factor is not authoritative)
        ay, ax = p.get("ay", p["y"] // factor), p.get("ax", p["x"] // factor)
        assert z["h_river_mask"][ay, ax]
        d = z["h_flow_dir"][ay, ax]
        dy, dx = derived._D8[d]
        actual = alt[ay, ax] - alt[ay + dy, ax + dx]
        assert abs(actual - p["drop_m"]) < 0.2
        assert p["drop_m"] >= derived.RAPIDS_DROP_M
        if p["kind"] == "waterfall":
            assert p["drop_m"] >= derived.FALLS_DROP_M
        # basin is a terminal cell (no downstream) or the sea
        by, bx = divmod(p["basin"], alt.shape[1])
        assert z["h_flow_dir"][by, bx] == -1 or \
            z["h_ocean_mask"][by, bx] or z["h_sea_mask"][by, bx]


def test_waterfalls_not_on_flats(result, inputs):
    """No falls where the terrain is flat (lakes/plains)."""
    z, _ = inputs
    factor = 4
    for p in result["points"]["waterfalls"]:
        ay, ax = p.get("ay", p["y"] // factor), p.get("ax", p["x"] // factor)
        assert not z["h_lake_mask"][ay, ax]


def test_waterfalls_snapped_to_delivered_river(result, inputs):
    """Falls/rapids points sit ON the delivered river line (a 3-block
    radius snap), not beside the meandering stamped path. The rare
    residuals are drops on sub-L0 streams (isolated/2-cell anchor
    rivers that never become edges, so nothing is stamped near them)."""
    z, _ = inputs
    drm = z["d_river_mask"]
    pts = result["points"]["waterfalls"]
    assert pts
    on = sum(1 for p in pts if drm[p["y"], p["x"]])
    assert on / len(pts) > 0.98, f"{on}/{len(pts)} on the river line"


# ── productivity ───────────────────────────────────────────────────────


SEA = 0.35   # synthetic world sea level (matches the k11 dump's)


def _synthetic_z() -> dict:
    """A 4x4 toy world: land in columns 0-1, ocean in 2-3. Cell A [0,0]
    is tropical moist forest with desert as its second-nearest biome,
    cell B [0,1] the mirror image — all else equal, so the priors
    decide. Row 2 is the open-ocean sunlight row (July-lit, January-
    dark); row 0 carries two upwelling cells for the anti-normalization
    regression test."""
    H, W = 4, 4
    land_T, ocean_T = 20.0, 5.0                     # degC
    z: dict = {
        "h_ocean_mask": np.tile(np.arange(W) >= 2, (H, 1)),
        "h_sea_mask": np.zeros((H, W), bool),
        "h_lake_mask": np.zeros((H, W), bool),
        "h_river_mask": np.zeros((H, W), bool),
        "h_river_speed": np.zeros((H, W)),
        "h_flow_dir": np.full((H, W), -1, np.int8),
        "h_accumulation": np.full((H, W), 100.0),
        "h_hand": np.full((H, W), 2.0 * (1.0 - SEA) / 6000.0),  # 2 m
        "h_depth": np.zeros((H, W)),
        "h_discharge": np.zeros((H, W)),
        "r_u": np.zeros((H, W)),
        "r_v": np.zeros((H, W)),
    }
    biome = np.full((H, W), 3, np.uint8)        # temperate broadleaf
    biome[0, 0], biome[0, 1] = 0, 12            # rainforest / desert
    biome[:, 2:] = 17                           # ocean
    second = np.full((H, W), 3, np.uint8)
    second[0, 0], second[0, 1] = 12, 0          # mirror images
    d1 = np.full((H, W), 0.1, np.float32)
    d2 = np.full((H, W), 0.3, np.float32)
    d1[1, 0] = 0.0                              # exact match -> pure b1
    z.update(w_biome_map=biome, w_biome_second=second,
             w_biome_d2_1=d1, w_biome_d2_2=d2)
    aq = np.full((H, W), 16, np.uint8)          # floodplain river (land)
    aq[:, 2:] = 0                               # open ocean
    z["w_aquatic"] = aq
    t_norm = np.where(z["h_ocean_mask"],
                      (ocean_T + 30.0) / 65.0, (land_T + 30.0) / 65.0)
    z["c_T"] = t_norm
    z["c_T_monthly"] = np.broadcast_to(t_norm, (12, H, W)).copy()
    z["c_P_monthly"] = np.full((12, H, W), 0.3)     # 1440 mm/yr
    insol = np.full((12, H), 0.8, np.float32)
    insol[:, 2] = 0.5
    insol[6, 2], insol[0, 2] = 1.0, 0.0         # July-lit, January-dark
    z["c_insol_monthly"] = insol
    z["c_seaice_monthly"] = np.zeros((12, H, W), np.float32)
    z["c_lakeice_monthly"] = np.zeros((12, H, W), np.float32)
    z["c_riverice_monthly"] = np.zeros((12, H, W), np.float32)
    rise = np.zeros((12, H, W), np.float32)
    rise[:, 0, 2], rise[:, 0, 3] = 1.0, 0.5     # upwelling pair
    z["r_rise_m"] = rise
    z["c_wind_u"] = np.zeros((12, 1, 2, 2), np.float32)
    z["c_wind_v"] = np.zeros((12, 1, 2, 2), np.float32)
    return z


def test_terrestrial_prior_dominates():
    """Rainforest cell beats its desert mirror — all else equal, the
    prior mix decides (no climate term can flip the baseline)."""
    t = derived.terrestrial_productivity(_synthetic_z(), SEA)
    assert t[0, 0] > t[0, 1]
    # w1 = d2/(d1+d2) = 0.75; base difference is the prior swing
    rf = derived.PRIOR_BIOME[0]         # tropical moist forest
    ds = derived.PRIOR_BIOME[12]        # desert xeric (hot)
    assert np.isclose(t[0, 0] - t[0, 1],
                      0.75 * rf + 0.25 * ds - (0.75 * ds + 0.25 * rf))


def test_terrestrial_weights_exact_match():
    """d1 = 0 -> pure b1 prior (w1 = 1), plus the bounded bonuses."""
    z = _synthetic_z()
    t = derived.terrestrial_productivity(z, SEA)
    f_clim = (0.8 * derived.temp_response(np.array(20.0))
              * min(1440.0 / derived.P_REF_MMYR, 1.0))
    f_dep = (min(100.0 / derived.ACC_REF, 1.0)
             * np.exp(-2.0 / derived.HAND_REF_M))
    prior_b1 = derived.PRIOR_BIOME[3]           # temperate broadleaf
    assert np.isclose(t[1, 0],
                      prior_b1 + derived.G_TER * (f_clim + f_dep))


def test_flood_pulse_raises_floodplain_productivity():
    """A seasonal-swing channel fertilizes its low-HAND neighborhood:
    cells near a swingy river gain over the no-river baseline, cells
    beyond the pulse's reach do not move, and a STEADY river with the
    same annual volume pulses not at all (the bonus keys on the
    swing, not the volume)."""
    z = _synthetic_z()
    rwm = np.zeros((12, 4, 4), np.int8)
    rwm[:, 0, 0] = 1                            # channel at (0,0), all months
    dis = np.zeros((12, 4, 4))
    dis[:3, 0, 0] = 120.0                       # 3-month flood, else dry
    z["h_river_width_monthly"] = rwm
    z["h_discharge_monthly"] = dis
    base = derived.terrestrial_productivity(_synthetic_z(), SEA)
    pulsed = derived.terrestrial_productivity(z, SEA)
    # (1,1) is one ring from the channel: gains. (3,0) is three rings
    # out in this 4x4 toy: exactly unchanged.
    assert pulsed[1, 1] > base[1, 1]
    assert pulsed[3, 0] == base[3, 0]
    # steady river, same total water: no pulse anywhere
    z2 = _synthetic_z()
    z2["h_river_width_monthly"] = rwm
    dis2 = np.zeros((12, 4, 4))
    dis2[:, 0, 0] = 30.0                        # same annual volume, no swing
    z2["h_discharge_monthly"] = dis2
    steady = derived.terrestrial_productivity(z2, SEA)
    assert steady[1, 1] == base[1, 1]


def test_marine_no_renormalization():
    """Scaling the world's single best upwelling cell 10x changes NO
    cell — the 99th-percentile bound clips it, it does not re-anchor
    the rest (the old _norm01 marine field would fail this). The toy
    ocean is big enough that one cell is < 1% of it, as in a real
    world, so the bound itself cannot move."""
    H, W = 16, 16
    ocean = np.tile(np.arange(W) >= W // 2, (H, 1))
    z: dict = {
        "h_ocean_mask": ocean,
        "h_sea_mask": np.zeros((H, W), bool),
        "h_lake_mask": np.zeros((H, W), bool),
        "h_river_mask": np.zeros((H, W), bool),
        "h_flow_dir": np.full((H, W), -1, np.int8),
        "h_discharge": np.zeros((H, W)),
        "r_u": np.zeros((H, W)),
        "r_v": np.zeros((H, W)),
        "w_aquatic": np.zeros((H, W), np.uint8),      # all open ocean
        "c_T_monthly": np.full((12, H, W), (5.0 + 30.0) / 65.0),
        "c_insol_monthly": np.full((12, H), 0.8, np.float32),
        "c_seaice_monthly": np.zeros((12, H, W), np.float32),
        "c_lakeice_monthly": np.zeros((12, H, W), np.float32),
        "c_wind_u": np.zeros((12, 1, 8, 8), np.float32),
        "c_wind_v": np.zeros((12, 1, 8, 8), np.float32),
    }
    rise = np.full((12, H, W), 0.5, np.float32)
    rise[:, 0, W - 1] = 1.0                         # the world's best cell
    z["r_rise_m"] = rise
    before = derived.marine_productivity(z, None)
    z["r_rise_m"] = rise.copy()
    z["r_rise_m"][:, 0, W - 1] *= 10.0
    after = derived.marine_productivity(z, None)
    assert np.array_equal(before, after)


def test_marine_open_ocean_sunlight():
    """Ice-free open ocean at 5 C in high summer reads clearly positive
    (the addendum's 0.03 symptom); dark winter is zero."""
    m = derived.marine_productivity(_synthetic_z(), None)
    july = m[6, 2, 2]
    expected = (derived.INSOL_W * 1.0
                * float(derived.temp_response(np.array(5.0))))
    assert np.isclose(july, expected)
    assert july > 0.2
    assert m[0, 2, 2] == 0.0


def test_temp_response_curve():
    f = derived.temp_response
    assert float(f(np.array(25.0))) == 1.0
    assert float(f(np.array(10.0))) == 1.0
    # gentle roll-off: 5 C is ~0.84, not Eppley's quarter-speed
    assert float(f(np.array(5.0))) > 0.8
    assert float(f(np.array(0.0))) == pytest.approx(2.0 ** -0.5)
    assert float(f(np.array(-2.0))) == 0.0
    assert float(f(np.array(-10.0))) == 0.0


def test_marine_productivity_at_upwelling(result, inputs):
    z, _ = inputs
    ann = result["products"]["marine_productivity_ann"]
    factor = 4
    up = np.clip(z["r_rise_m"], 0, None).mean(axis=0)
    top = np.unravel_index(np.argsort(up, axis=None)[-3:], up.shape)
    for y, x in zip(*top):
        cell = ann[y * factor:(y + 1) * factor, x * factor:(x + 1) * factor]
        assert cell.max() > 0, f"no productivity at upwelling ({y},{x})"


def test_marine_productivity_ocean_only(result, inputs):
    z, _ = inputs
    ann = result["products"]["marine_productivity_ann"]
    d_ocean = z["d_ocean_mask"] | z["d_sea_mask"]
    assert (ann[~d_ocean] == 0).all()


# ── freshwater productivity (monthly, dual-domain mangrove) ─────────────


def test_freshwater_monthly_seasonal_river():
    """Freshwater productivity is monthly: a seasonal river cell carries
    water (and productivity) only in its wet months; dry months are 0
    (flow below L0 granularity), and never-river land stays dry."""
    z = _synthetic_z()
    rwm = np.zeros((12, 4, 4), bool)
    rwm[:6, 1, 1] = True                            # seasonal channel
    z["h_river_monthly"] = rwm
    f = derived.freshwater_productivity(z, SEA)
    assert f.shape == (12, 4, 4)
    assert (f[:6, 1, 1] > 0).all()
    assert (f[6:, 1, 1] == 0).all()
    assert (f[:, 3, 0] == 0).all()                  # never-river land


def test_freshwater_mangrove_dual_domain():
    """Mangrove biome cells are water AND land (owner ruling): both the
    terrestrial product and the monthly freshwater product are positive
    there, and the freshwater base never collapses to the adjacent
    marine sentinel class."""
    z = _synthetic_z()
    z["h_river_monthly"] = np.zeros((12, 4, 4), bool)
    z["w_biome_map"][2, 0] = derived.MANGROVE_ID
    z["w_aquatic"][2, 0] = 0        # open-ocean sentinel (worst case)
    f = derived.freshwater_productivity(z, SEA)
    t = derived.terrestrial_productivity(z, SEA)
    assert (f[:, 2, 0] > 0).all()
    assert t[2, 0] > 0


# ── water column (B4) ──────────────────────────────────────────────────


def test_water_column_products(result, inputs):
    z, _ = inputs
    p = result["products"]
    d_ocean = z["d_ocean_mask"] | z["d_sea_mask"]
    assert p["benthic_food"].shape == (12, 1024, 1024)
    assert p["marine_snow"].shape == (12, 1024, 1024)
    for name in ("benthic_food", "marine_snow", "bathymetry_m",
                 "photic_depth_m", "bottom_temp_c"):
        assert (p[name][..., ~d_ocean] == 0).all(), name
    zones = np.unique(p["depth_zone"])
    assert set(zones.tolist()) <= {0, 1, 2, 3, 4, 255}
    assert 255 in zones                          # land cells unclassified
    # bathymetry is real meters now (trench exaggeration): deep ocean
    # exists on every world, zone ids are ordered by depth
    assert p["bathymetry_m"].max() > 3000.0
    # shelf bottoms are lit, the deep is not (kron boolean vs bilinear
    # bathy can't be pixel-exact at delivery — check the semantics)
    lit = p["bottom_lit"] & d_ocean
    assert lit.sum() > 0
    assert p["bathymetry_m"][lit].mean() < 200.0
    assert p["bathymetry_m"][d_ocean & ~p["bottom_lit"]].mean() > 1000.0


def test_vents_annotated(result):
    for pt in result["points"]["vents"]:
        assert pt["kind"] == "vent"
        assert "depth_m" in pt and pt["depth_m"] > 0
        assert "depth_zone" in pt
    kinds = {pt["kind"] for pt in result["points"]["hot_springs"]}
    assert kinds <= {"terrestrial", "sublacustrine", "riverine"}


# ── vents ──────────────────────────────────────────────────────────────


def test_vents_extracted(result, inputs):
    z, _ = inputs
    factor = 4
    ocean = z["h_ocean_mask"] | z["h_sea_mask"]
    assert result["points"]["vents"], "no marine vents"
    assert result["points"]["hot_springs"], "no hot springs"
    for p in result["points"]["vents"]:
        assert ocean[p["y"] // factor, p["x"] // factor]
    for p in result["points"]["hot_springs"]:
        assert not ocean[p["y"] // factor, p["x"] // factor]


# ── datapack ───────────────────────────────────────────────────────────


def test_pack_roundtrip(result, tmp_path):
    from exp.k14_flora.world.datapack import build_pack
    path = build_pack(result, tmp_path / "derived.k11pack")
    raw = path.read_bytes()
    assert raw[:4] == b"K11P"
    hlen = struct.unpack("<I", raw[4:8])[0]
    header = json.loads(raw[8:8 + hlen])
    assert header["format"] == "k11pack/1"
    assert header["seed"] == SEED
    # binary section length matches declared arrays: every name in
    # header["order"] (main fields + any auxiliary mix planes)
    expected = 8 + hlen
    dt_size = {"u1": 1, "<u2": 2}
    shapes: dict[str, tuple] = {}
    for layer in header["layers"]:
        if layer.get("field"):
            shapes[layer["field"]] = (layer["shape"], layer["dtype"])
        for key in ("mix_ids", "mix_w"):
            if key in layer:
                shapes[layer[key]["field"]] = (layer[key]["shape"],
                                               layer[key]["dtype"])
    assert set(header["order"]) == set(shapes)   # every array is described
    for name in header["order"]:
        shape, dt = shapes[name]
        expected += int(np.prod(shape)) * dt_size[dt]
    assert len(raw) == expected
    # points layers carry inline data; continuous layers declare ramps
    kinds = {l["id"]: l["kind"] for l in header["layers"]}
    assert kinds["waterfalls"] == "points"
    assert kinds["marine_prod"] == "continuous"
    assert "fertility" not in kinds
    terr = next(l for l in header["layers"] if l["id"] == "terr_prod")
    assert terr["kind"] == "continuous"
    assert terr["shape"] == [1024, 1024]
    marine = next(l for l in header["layers"] if l["id"] == "marine_prod")
    assert marine["month_dim"] == 12
    assert marine["shape"] == [12, 1024, 1024]
    fresh = next(l for l in header["layers"] if l["id"] == "fresh_prod")
    assert fresh["month_dim"] == 12
    assert fresh["shape"] == [12, 1024, 1024]


def test_river_fields_guard():
    """The persisted speed/ice fields are REQUIRED — a stale dump fails
    loudly with the regen hint instead of silently re-deriving."""
    import pytest
    with pytest.raises(KeyError, match="h_river_speed"):
        derived._river_fields({})
    with pytest.raises(KeyError, match="c_riverice_monthly"):
        derived._river_fields({"h_river_speed": np.zeros((2, 2))})
