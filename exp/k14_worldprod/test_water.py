"""K14 B4 tests — water-column attributes (pure functions, synthetic
fields; no k11 dump needed). Real-data integration assertions live in
test_derived.py (shared build fixture).

Run: uv run pytest -q exp/k14_worldprod/test_water.py
"""

from __future__ import annotations

import numpy as np
import pytest

from exp.k14_worldprod import water


def _bathy(field_m: np.ndarray) -> np.ndarray:
    """Helper: depth field (positive = ocean) straight in meters."""
    return np.asarray(field_m, dtype=float)


# ── zones ──────────────────────────────────────────────────────────────


def test_depth_zone_boundaries():
    bathy = _bathy([[0.0, 100.0, 200.0, 500.0, 2000.0, 5000.0, 7000.0]])
    zone = water.depth_zone(bathy)
    assert zone[0, 0] == 255                     # land
    names = [z_["name"] for z_ in water.ZONES]
    assert [names[zone[0, i]] for i in range(1, 7)] == [
        "epipelagic bottom", "epipelagic bottom", "mesopelagic bottom",
        "bathypelagic bottom", "abyssal bottom", "hadal"]


# ── marine snow ────────────────────────────────────────────────────────


def test_snow_attenuates_with_depth():
    """Two UNIFORM seafloors (no drops -> no routing): the deeper world
    gets exponentially less snow everywhere."""
    mprod = np.ones((12, 1, 4))
    shallow = water.marine_snow(_bathy([[100.0] * 4]), mprod).sum(axis=0)
    deep = water.marine_snow(_bathy([[4000.0] * 4]), mprod).sum(axis=0)
    assert (shallow > 0).all() and (deep > 0).all()
    assert (shallow > deep).all()
    assert np.isclose((deep / shallow)[0, 0],
                      np.exp(-(4000.0 - 100.0) / water.SNOW_REF_M),
                      rtol=1e-6)


def test_snow_zero_on_land_and_monthly_shape():
    bathy = _bathy([[0.0, 500.0]])
    mprod = np.ones((12, 1, 2))
    mprod[:6] = 0.0                          # productive only Jul-Dec
    snow = water.marine_snow(bathy, mprod)
    assert (snow[:, 0, 0] == 0).all()        # land cell
    assert (snow[:6, 0, 1] == 0).all()       # unproductive months
    assert (snow[6:, 0, 1] > 0).all()


def test_downslope_concentrates_at_base():
    """A 1x5 transect: shelf (50 m) -> slope (2000, 3900) -> abyss
    (4000, 4000 flat). Snow slides downhill and ponds where the
    gradient BREAKS (base-of-slope fan); the flat abyss keeps only
    what arrives over the gentle last step."""
    bathy = _bathy([[50.0, 2000.0, 3900.0, 4000.0, 4000.0]])
    mprod = np.ones((12, 1, 5))
    snow = water.marine_snow(bathy, mprod).sum(axis=0)[0]
    fan = int(np.argmax(snow))
    assert fan in (2, 3)                     # the gradient-break cells
    assert snow[fan] > snow[0] and snow[fan] > snow[1]
    # mass is conserved by the routing (export moves, never destroys);
    # `snow` is already the 12-month sum
    pre = (mprod[0] * np.exp(-bathy / water.SNOW_REF_M)).sum() * 12
    assert np.isclose(snow.sum(), pre, rtol=1e-6)


def test_downslope_pits_are_traps():
    """A trench between two ridges: sediment routes INTO the pit and
    does not escape — no fill, no spillover."""
    bathy = _bathy([[100.0, 3000.0, 8000.0, 3000.0, 100.0]])
    mprod = np.ones((12, 1, 5))
    snow = water.marine_snow(bathy, mprod).sum(axis=0)[0]
    assert snow[2] > snow[1] and snow[2] > snow[3]


# ── deep-return inventory ──────────────────────────────────────────────


def test_inventory_rich_pole_beats_poor_pole():
    """Same rise field, same bathymetry: the upwelling whose deep
    catchment holds the rich polar snow out-modifies the one fed by
    barren water. (Two exits — the 99th-percentile bound needs a
    distribution; a single-exit world is degenerate BY CONVENTION:
    its one exit is trivially the world's best-fed, modifier 1.5.)"""
    H, W = 8, 16
    bathy = np.full((H, W), 3000.0)
    bathy[0, :8] = 200.0                     # west polar shelf
    bathy[0, 8:] = 3000.0                    # east stays deep
    rise = np.zeros((H, W))
    rise[6, 3] = 1.0                         # exit near the rich shelf
    rise[6, 12] = 1.0                        # exit far from it
    snow = np.full((H, W), 0.01)
    snow[0, :8] = 1.0
    mod = water.deep_return_inventory(bathy, snow, rise)
    assert mod[6, 3] > mod[6, 12]
    assert water.INV_LO - 1e-9 <= mod.min()
    assert mod.max() <= water.INV_HI + 1e-9
    # off-upwelling cells are neutral
    assert mod[3, 8] == 1.0


def test_inventory_no_exits_is_neutral():
    bathy = np.full((4, 4), 3000.0)
    mod = water.deep_return_inventory(bathy, np.ones((4, 4)),
                                      np.zeros((4, 4)))
    assert (mod == 1.0).all()


# ── vent benthos ───────────────────────────────────────────────────────


def test_vent_halo_active_only_and_decays():
    pts = [{"y": 5, "x": 5}, {"y": 5, "x": 20}]
    halo = water.vent_benthos(pts, [True, False], (11, 31))
    assert halo[5, 5] == pytest.approx(water.VENT_OASIS)
    assert halo[5, 8] < halo[5, 5]           # decays away
    assert halo[5, 20] == 0.0                # dormant casts nothing


# ── photic depth ───────────────────────────────────────────────────────


def test_photic_turbidity_shading_and_bounds():
    bathy = _bathy([[1000.0, 1000.0, 1000.0]])
    plume = np.array([[0.0, 0.6, 0.0]])      # 0.6 = PLUME_WEIGHT
    prod = np.array([[0.0, 0.0, 0.6]])       # full bloom
    d = water.photic_depth_m(bathy, plume, prod, 0.6)
    assert d[0, 0] == water.PHOTIC_OPEN_M    # clear water
    assert d[0, 1] < d[0, 0]                 # plume shades
    assert d[0, 2] < d[0, 0]                 # bloom shades
    assert water.PHOTIC_MIN_M <= d.min() and d.max() <= water.PHOTIC_MAX_M


# ── bottom temperature ─────────────────────────────────────────────────


def test_bottom_temp_deep_approaches_floor():
    from exp.k11_worldgen.units import T_MAX_C, T_MIN_C
    # monthly T constant 20 C everywhere
    t_norm = (20.0 - T_MIN_C) / (T_MAX_C - T_MIN_C)
    z = {"c_T_monthly": np.full((12, 1, 3), t_norm)}
    bathy = _bathy([[50.0, 500.0, 5000.0]])
    tb = water.bottom_temp_c(z, 0.35, bathy)
    assert tb[0, 0] > tb[0, 1] > tb[0, 2]
    assert abs(tb[0, 2] - water.T_DEEP_C) < 0.5


# ── fresh photic depth / bottom temperature (B4 fix 2026-08-01) ────────


def test_fresh_photic_clear_bog_bloom_and_bounds():
    """Clear lake water reads the open base; humic blackwater (the bog
    share fresh_ph reads) and the annual bloom each shade it; bounded
    [FRESH_PHOTIC_MIN, FRESH_PHOTIC_MAX]."""
    fresh = np.ones((1, 4), dtype=bool)
    bog = np.array([[0.0, 1.0, 0.0, 0.0]])
    prod = np.array([[0.0, 0.0, water.FRESH_PHOTIC_BLOOM_REF, 0.0]])
    d = water.fresh_photic_depth_m(bog, prod, fresh)
    assert d[0, 0] == water.FRESH_PHOTIC_OPEN_M    # clear water
    assert d[0, 1] < d[0, 0]                       # bog-ringed lake shades
    assert d[0, 2] < d[0, 0]                       # full bloom shades
    assert water.FRESH_PHOTIC_MIN_M <= d.min()
    assert d.max() <= water.FRESH_PHOTIC_MAX_M


def test_fresh_photic_zero_off_fresh_and_full_shade_clips():
    """Dry land (and ocean — the marine field owns it) reads 0; a lake
    at full bog + full bloom clips to the FRESH_PHOTIC_MIN floor."""
    fresh = np.zeros((1, 2), dtype=bool)
    d = water.fresh_photic_depth_m(np.zeros((1, 2)), np.zeros((1, 2)),
                                   fresh)
    assert (d == 0).all()
    bog = np.ones((1, 1))
    prod = np.full((1, 1), water.FRESH_PHOTIC_BLOOM_REF)
    d2 = water.fresh_photic_depth_m(bog, prod, np.ones((1, 1), dtype=bool))
    assert d2[0, 0] == water.FRESH_PHOTIC_MIN_M


def test_fresh_bottom_temp_damped_to_hypolimnion_and_zero():
    """Surface annual 20 C: a 1 m pond reads ~ the surface annual; a
    20 m lake bottom is damped toward the 4 C hypolimnion floor;
    zero-depth cells (rivers/pools) read the surface exactly. Off
    fresh water everything is 0 (dry land; ocean keeps the marine
    field)."""
    from exp.k11_worldgen.units import T_MAX_C, T_MIN_C
    t_norm = (20.0 - T_MIN_C) / (T_MAX_C - T_MIN_C)
    z = {"c_T_monthly": np.full((12, 1, 3), t_norm)}
    depth = _bathy([[1.0, 20.0, 0.0]])
    fresh = np.ones((1, 3), dtype=bool)
    tb = water.fresh_bottom_temp_c(z, 0.35, depth, fresh)
    assert tb[0, 0] == pytest.approx(20.0, abs=2.0)    # 1 m pond
    assert 4.0 <= tb[0, 1] <= 10.0                     # 20 m lake bottom
    assert tb[0, 2] == pytest.approx(20.0)             # zero depth
    land = np.zeros((1, 3), dtype=bool)
    assert (water.fresh_bottom_temp_c(z, 0.35, depth, land) == 0).all()


# ── water pH (column, not bed) ──────────────────────────────────────────

def test_ocean_ph_depth_gradient():
    bathy = _bathy(np.array([[0.0, 100.0, 5000.0]]))
    ph = water.ocean_ph(bathy)
    assert ph[0, 0] == pytest.approx(8.1)           # surface/land level
    assert ph[0, 1] == pytest.approx(8.1 - 0.3 * 100.0 / 4000.0)
    assert ph[0, 2] == pytest.approx(7.8)           # saturates at ref
    assert ph[0, 1] > ph[0, 2]


def test_fresh_ph_bed_catchment_peat():
    bed = np.array([[7.2, 7.2]])
    land = np.array([[6.0, 6.0]])
    bog = np.array([[0.0, 0.8]])
    ph = water.fresh_ph(bed, land, bog)
    base = 0.6 * 7.2 + 0.4 * 6.0                    # 6.72
    assert ph[0, 0] == pytest.approx(base)
    assert ph[0, 1] == pytest.approx(base - 1.3 * 0.8)
    # peat window turns neutral bed water into blackwater
    assert ph[0, 1] < 6.0


def test_box_mean_center_and_edges():
    f = np.zeros((5, 5))
    f[2, 2] = 25.0
    m = water._box_mean(f, 1)
    assert m[2, 2] == pytest.approx(25.0 / 9.0)     # 3x3 window
    assert m[0, 0] == 0.0
    g = np.ones((4, 4))
    assert water._box_mean(g, 2)[0, 0] == pytest.approx(1.0)  # edges
