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
        ay, ax = p["y"] // factor, p["x"] // factor   # delivery -> anchor
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
        ay, ax = p["y"] // factor, p["x"] // factor
        assert not z["h_lake_mask"][ay, ax]


# ── productivity ───────────────────────────────────────────────────────


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


def test_soil_fertility_peaks(result, inputs):
    z, _ = inputs
    sf = result["products"]["soil_fertility"]
    factor = 4
    sf_a = sf[::factor, ::factor]      # back to anchor for the check
    land = ~z["h_ocean_mask"] & ~z["h_sea_mask"] & ~z["h_lake_mask"]
    acc_rank = derived._rank01(z["h_accumulation"])
    hand_rank = derived._rank01(z["h_hand"])
    hi = sf_a > np.percentile(sf_a[land], 95)
    assert acc_rank[hi].mean() > 0.7
    assert hand_rank[hi].mean() < 0.3


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
    # binary section length matches declared arrays
    expected = 8 + hlen
    dt_size = {"u1": 1, "<u2": 2}
    for layer in header["layers"]:
        if layer.get("field"):
            n = int(np.prod(layer["shape"]))
            expected += n * dt_size[layer["dtype"]]
    assert len(raw) == expected
    # points layers carry inline data; continuous layers declare ramps
    kinds = {l["id"]: l["kind"] for l in header["layers"]}
    assert kinds["waterfalls"] == "points"
    assert kinds["marine_prod"] == "continuous"
    marine = next(l for l in header["layers"] if l["id"] == "marine_prod")
    assert marine["month_dim"] == 12
    assert marine["shape"] == [12, 1024, 1024]


def test_river_fields_guard():
    """The persisted speed/ice fields are REQUIRED — a stale dump fails
    loudly with the regen hint instead of silently re-deriving."""
    import pytest
    with pytest.raises(KeyError, match="h_river_speed"):
        derived._river_fields({})
    with pytest.raises(KeyError, match="c_riverice_monthly"):
        derived._river_fields({"h_river_speed": np.zeros((2, 2))})
