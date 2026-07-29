"""K11 solar tests — latitude, day length, insolation, sea ice."""

from __future__ import annotations

import numpy as np

from exp.k11_worldgen.solar import (
    FREEZE_FRESH_C, FREEZE_SEA_C, day_length, ice_fraction, insolation,
    row_latitude)


def test_row_latitude_realistic():
    lat = row_latitude(256, True, 45.0, 1024.0, 4.0)
    # earth patch: rows span around the center, north highest
    assert lat[0] > lat[-1]
    assert abs(lat[128] - 45.0) < 1.0
    assert lat[0] <= 90.0 and lat[-1] >= 0.0


def test_row_latitude_invented_poles():
    north = row_latitude(256, False, 45.0, 1024.0, 4.0, north_cold=True)
    assert abs(north[0] - 90.0) < 0.5       # pole at the north rim
    assert abs(north[-1]) < 0.5             # equator at the south rim
    south = row_latitude(256, False, 45.0, 1024.0, 4.0,
                         north_cold=False)
    assert abs(south[-1] + 90.0) < 0.5      # pole at the south rim
    assert south[0] > south[-1]             # signed: phase flips


def test_day_length_equator_and_poles():
    dl = day_length(np.array([0.0, 90.0, -90.0, 45.0]))
    # equator: ~12 h every month
    assert np.all(np.abs(dl[:, 0] - 12.0) < 0.2)
    # north pole: 24 h at the June solstice, 0 at December
    june = int(np.argmax(dl[:, 1]))
    dec = int(np.argmin(dl[:, 1]))
    assert dl[june, 1] == 24.0
    assert dl[dec, 1] == 0.0
    # south pole is the mirror
    assert dl[dec, 2] == 24.0
    assert dl[june, 2] == 0.0
    # mid-latitudes: seasonal swing within 9..15 h
    assert dl[:, 3].min() > 8.0 and dl[:, 3].max() < 16.0


def test_insolation_shape_and_reasonableness():
    ins = insolation(np.array([0.0, 45.0, 90.0]))
    assert ins.shape == (12, 3)
    # equator leads year-round; pole is strongly seasonal
    assert ins[:, 0].min() > 0.8
    assert ins[:, 2].min() == 0.0
    assert ins[:, 2].max() > ins[:, 2].min()
    # mid-lat summer exceeds equator briefly (long days)
    assert ins[:, 1].max() > ins[:, 0].mean()


def test_ice_fraction_thresholds():
    # normalized T: -30..35 over 0..1; pick values around freezing
    from exp.k11_worldgen.units import T_MIN_C, T_MAX_C
    def norm(c):
        return (c - T_MIN_C) / (T_MAX_C - T_MIN_C)
    t = np.full((12, 2, 2), norm(-10.0))     # solidly frozen
    t2 = np.full((12, 2, 2), norm(10.0))     # warm
    water = np.ones((2, 2), bool)
    assert ice_fraction(t, water, FREEZE_SEA_C).min() == 1.0
    assert ice_fraction(t2, water, FREEZE_SEA_C).max() == 0.0
    # fresh freezes at 0, sea at -1.8: -1 deg is fresh-ice, not sea-ice
    t3 = np.full((12, 2, 2), norm(-1.0))
    assert ice_fraction(t3, water, FREEZE_FRESH_C).min() > 0.0
    assert ice_fraction(t3, water, FREEZE_SEA_C).max() < 1.0
    # off-mask cells stay zero
    assert ice_fraction(t, np.zeros((2, 2), bool), FREEZE_SEA_C).max() == 0.0


def test_snow_pack_hysteresis():
    """The bucket: accumulation in cold months, degree-day melt, and
    memory — a one-month warm spell does not clear a deep pack."""
    from exp.k11_worldgen.solar import snow_pack
    from exp.k11_worldgen.units import T_MIN_C, T_MAX_C, P_MAX_MM
    def norm_t(c):
        return (c - T_MIN_C) / (T_MAX_C - T_MIN_C)
    # cold-wet winter (3 mo), one warm month, cold again, hot summer
    t_seq = [-5.0, -5.0, -5.0, 8.0, -5.0, 20.0, 20.0, 20.0, 20.0, 20.0,
             20.0, 20.0]
    p_seq = [0.5] * 12          # 200 mm/month everywhere
    t = np.full((12, 1, 2), 0.0)
    for m, c in enumerate(t_seq):
        t[m] = norm_t(c)
    p = np.full((12, 1, 2), 0.5)
    land = np.ones((1, 2), bool)
    pack, melt, snowfall, meltpot = snow_pack(t, p, land)
    # accumulates over the 3 cold months (all precip is snow)
    assert pack[2, 0, 0] > pack[1, 0, 0] > pack[0, 0, 0] > 0
    # the single 8 degC month melts hard but the pack returns next cold
    assert melt[3, 0, 0] > 0
    assert pack[4, 0, 0] > 0
    # hot summer clears it eventually (200mm/mo * 3 mo = 600mm pack;
    # melt at (20-2)*30.4*3 = 1642 mm/mo potential)
    assert pack[-1, 0, 0] == 0.0
    # summer melt exceeds snowfall once warm (the delayed release)
    assert melt[5, 0, 0] > 0
    # partition is returned: cold months all-snow, hot months none
    assert snowfall[0, 0, 0] == 0.5 * P_MAX_MM
    assert snowfall[5, 0, 0] == 0.0
    assert meltpot[5, 0, 0] > meltpot[0, 0, 0] == 0.0
    # zero off land
    assert pack.max() >= 0 and snow_pack(t, p, ~land)[0].max() == 0.0


def test_snow_pack_loop_closure():
    """Memory fields need a head start: in a year-round-cold climate,
    January must inherit December's pack (spin-up), not start empty."""
    from exp.k11_worldgen.solar import snow_pack
    from exp.k11_worldgen.units import T_MIN_C, T_MAX_C, P_MAX_MM
    t = np.full((12, 1, 2), (-5.0 - T_MIN_C) / (T_MAX_C - T_MIN_C))
    p = np.full((12, 1, 2), 0.5)            # 200 mm/month, all snow
    land = np.ones((1, 2), bool)
    pack, melt, _, _ = snow_pack(t, p, land)
    monthly = 0.5 * P_MAX_MM                # one month of snowfall
    # without carryover January would hold exactly one month's snow;
    # with spin-up it holds at least a full year's accumulation
    assert pack[0, 0, 0] > 12 * monthly
    # never warm: no melt anywhere
    assert melt.max() == 0.0
    # monotonic growth through the recorded year
    assert pack[-1, 0, 0] > pack[0, 0, 0]


def test_river_ice_speed_gate():
    """River ice = fresh freeze band x smooth speed gate: still water
    freezes like a lake, rapids stay open, mid speed halves cover."""
    from exp.k11_worldgen.solar import (
        FREEZE_FRESH_C, V_ICE_OPEN_MS, V_ICE_STILL_MS, ice_fraction,
        river_ice_fraction)
    t = np.zeros((12, 2, 2))                # T_MIN_C — deep freeze
    river = np.ones((2, 2), bool)
    still = np.zeros((2, 2))
    assert river_ice_fraction(t, river, still).min() == 1.0
    fast = np.full((2, 2), V_ICE_OPEN_MS * 2)
    assert river_ice_fraction(t, river, fast).max() == 0.0
    mid = np.full((2, 2), (V_ICE_STILL_MS + V_ICE_OPEN_MS) / 2)
    base = ice_fraction(t, river, FREEZE_FRESH_C)
    assert np.allclose(river_ice_fraction(t, river, mid), base * 0.5)
    # off-river stays zero; annual (h,w) and monthly (12,h,w) speed both
    # accepted
    assert river_ice_fraction(t, np.zeros((2, 2), bool), still).max() == 0
    v12 = np.zeros((12, 2, 2))
    assert river_ice_fraction(t, river, v12).shape == (12, 2, 2)
    # above freezing: no ice even on still water
    hot = np.ones((12, 2, 2))
    assert river_ice_fraction(hot, river, still).max() == 0.0
