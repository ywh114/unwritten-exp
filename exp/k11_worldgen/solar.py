"""K11 — solar geometry and freezing: latitude, day length, insolation,
sea/lake ice. FIRST-CLASS persisted fields (owner 2026-07-30: "simulate
24h sunlight/daylight times... k11 engine rework+persist, drop ad-hoc
sunlight calculations") — downstream consumers (K14 productivity, later
ecology) read the persisted arrays, never re-derive their own.

The world is flat: "latitude" is a MODEL field, not a claim about
planetary shape. Realistic (earth-patch) worlds map rows to real
degrees via the persisted center-lat convention; invented worlds use
pseudo-latitude — the pole sits at the profile's cold rim, the row
fraction spans 0..90 deg.
"""

from __future__ import annotations

import numpy as np

from exp.k11_worldgen.units import precip_mm, temp_c

AXIAL_TILT_DEG = 23.44          # Earth-like obliquity (the year driver)
FREEZE_SEA_C = -1.8             # salt-water freezing point
FREEZE_FRESH_C = 0.0            # fresh-water freezing point
FREEZE_TRANSITION_C = 2.0       # smooth freeze band (slush -> solid)

# snowpack: monthly-mean thresholds. The owner note applies: these are
# MONTHLY MEANS — a -5 degC mean month holds -30/-40 degC days, so snow
# starts well above 0 degC mean and melt lags it.
SNOW_FALL_T_C = 2.0             # below this mean, precip falls as snow
SNOW_RAIN_BAND_C = 4.0          # snow->rain transition band
SNOW_MELT_COEF = 3.0            # mm water-equivalent per degree-day
SNOW_SPINUP_YEARS = 3           # annual-cycle reruns so January inherits
                                # December's pack (memory-field loop closure)

# snow/ice albedo feedback: cover fraction (pack depth -> whiteness)
# times insolation times a damped gain. One conditioning round, never
# iterated (the refine_climate doctrine: conditioning, not simulation).
SNOW_COVER_MM = 80.0            # pack depth that reads as full white cover
ALBEDO_COOL_K = 0.05            # normalized-T cooling at full cover,
                                # peak sun (~3 degC on the T range)


def albedo_round(t_monthly_norm: np.ndarray, pack_mm: np.ndarray,
                 seaice: np.ndarray, lakeice: np.ndarray,
                 insol_rows: np.ndarray, land_mask: np.ndarray
                 ) -> np.ndarray:
    """Snow/ice-albedo conditioning round: white cover rejects the
    insolation the temperature was built from, cooling in proportion
    to cover x sun. Applied ONCE (damped feedback); the caller
    recomputes the snow/ice fields from the adjusted temperature.

    t_monthly_norm, pack_mm, seaice, lakeice: (12, h, w); insol_rows:
    the (12, h) row field; land_mask: (h, w). Returns adjusted
    normalized monthly temperature.
    """
    cover_land = np.clip(pack_mm / SNOW_COVER_MM, 0.0, 1.0)
    cover = np.where(land_mask[None], cover_land,
                     np.maximum(seaice, lakeice))
    cool = ALBEDO_COOL_K * cover * insol_rows[:, :, None]
    return np.clip(t_monthly_norm - cool, 0.0, 1.0)


def row_latitude(h: int, realistic: bool, center_lat: float,
                 shape_km: float, shrink: float,
                 north_cold: bool = True) -> np.ndarray:
    """Per-row latitude in SIGNED degrees, (h,). Sign flips the season
    phase (a south-pole world has southern-hemisphere seasons).

    realistic: earth-patch northern hemisphere — the climate.py
    center_lat/shrink formula, row 0 the northernmost.
    invented: pseudo-latitude — the pole at the cold rim (north_cold
    comes from the T-profile params: t_span > 0 means the north rim is
    the cold one), the opposite rim the equator.
    """
    rows = (np.arange(h) + 0.5) / h
    if realistic:
        span_deg = shape_km * shrink / 111.19
        return np.clip(center_lat + (0.5 - rows) * span_deg, 0.0, 90.0)
    if north_cold:
        return (1.0 - rows) * 90.0
    return -rows * 90.0


def _declination_rad() -> np.ndarray:
    """Solar declination per mid-month day, (12,)."""
    mid_day = (np.arange(12) + 0.5) * 30.4
    return np.radians(AXIAL_TILT_DEG
                      * np.cos(2.0 * np.pi * (mid_day - 172.0) / 365.0))


def day_length(lat_deg: np.ndarray) -> np.ndarray:
    """Monthly mean day length in hours, (12, h) — the sunrise
    equation. Polar day reads 24, polar night 0."""
    phi = np.radians(lat_deg)[None, :]
    decl = _declination_rad()[:, None]
    cos_h = np.clip(-np.tan(phi) * np.tan(decl), -1.0, 1.0)
    return 2.0 * np.degrees(np.arccos(cos_h)) / 15.0


def insolation(lat_deg: np.ndarray) -> np.ndarray:
    """Monthly mean daily insolation proxy, (12, h): day fraction x
    sin(noon solar elevation), normalized so the equator at equinox is
    ~1. A relative light index for productivity/growth consumers, not
    watts."""
    phi = np.radians(lat_deg)[None, :]
    decl = _declination_rad()[:, None]
    dl = day_length(lat_deg) / 24.0
    noon_elev = np.clip(np.pi / 2.0 - np.abs(phi - decl), 0.0, None)
    insol = dl * np.sin(noon_elev)
    return insol / 0.5            # equator equinox: dl 0.5 x sin(90) = 0.5


def ice_fraction(t_monthly_norm: np.ndarray, water_mask: np.ndarray,
                 freeze_c: float) -> np.ndarray:
    """Monthly ice-cover fraction (12, h, w), 0..1: a smooth band over
    FREEZE_TRANSITION_C below the freezing point (slush to solid),
    zero off the given water mask."""
    t_c = temp_c(t_monthly_norm)
    frac = np.clip((freeze_c - t_c) / FREEZE_TRANSITION_C, 0.0, 1.0)
    return np.where(water_mask[None], frac, 0.0)


# river ice: moving water resists freezing. The same MONTHLY-MEAN caveat
# as the snowpack thresholds applies, and the speed field is the
# persisted reach AVERAGE (hydrology.river_speed, jittered for sub-grid
# variance) — so the gate is SMOOTH, never a hard cutoff on an estimate.
V_ICE_STILL_MS = 0.3            # slower than this: freezes like a lake
V_ICE_OPEN_MS = 1.5             # faster than this: stays open (rapids)


def river_ice_fraction(t_monthly_norm: np.ndarray,
                       river_mask: np.ndarray,
                       speed_ms: np.ndarray) -> np.ndarray:
    """Monthly river-ice cover fraction (12, h, w), 0..1: the fresh-water
    freeze band gated by flow speed — slow reaches freeze solid, fast
    water stays open. `speed_ms` is monthly (12, h, w) or annual (h, w).
    """
    base = ice_fraction(t_monthly_norm, river_mask, FREEZE_FRESH_C)
    v = speed_ms if speed_ms.ndim == 3 else speed_ms[None]
    gate = np.clip((V_ICE_OPEN_MS - v) / (V_ICE_OPEN_MS - V_ICE_STILL_MS),
                   0.0, 1.0)
    return base * gate


def snow_pack(t_monthly_norm: np.ndarray, p_monthly_norm: np.ndarray,
              land_mask: np.ndarray
              ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Monthly snow state, all (12, h, w) in mm water-equivalent, on
    land cells: (pack depth, meltwater release, snowfall, melt
    potential).

    A bucket with MEMORY (hysteresis): snow accumulates whenever the
    month is cold enough, and melts by degree-days — a cold autumn
    builds a pack a single warm spell cannot clear, and the spring
    melt pulse is the delayed water release that feeds snowmelt
    rivers (the water accounting hook).

    Monthly-mean thresholds, deliberately above 0 degC: a +1 degC mean
    month still holds sub-zero nights and -30/-40 degC cold snaps
    (owner note: these are monthly averages).

    The bucket has memory, so it needs a head start or January would
    begin empty even where December ended deep in snow: the annual
    cycle is spun up SNOW_SPINUP_YEARS times and the LAST year is
    recorded. Cells whose pack never melts out (glaciers) keep a
    lower-bound depth that grows with the spin-up count — bounded by
    SNOW_SPINUP_YEARS x annual snowfall, and only ever used as
    "permanent ice" + melt-pulse timing, never as a true ice volume
    (ice export is the glacier pass's job — hydrology.glacier_flow).

    Snowfall and melt potential are returned so downstream passes
    (glacier flow, albedo) never re-derive the partition.
    """
    t = temp_c(t_monthly_norm)
    p = precip_mm(p_monthly_norm)
    # fraction of precip falling as snow: 1 at/below SNOW_FALL_T_C,
    # 0 above SNOW_FALL_T_C + SNOW_RAIN_BAND_C, linear between
    snow_frac = np.clip(
        (SNOW_FALL_T_C + SNOW_RAIN_BAND_C - t) / SNOW_RAIN_BAND_C,
        0.0, 1.0)
    snowfall = p * snow_frac
    melt_potential = (np.clip(t - SNOW_FALL_T_C, 0.0, None)
                      * 30.4 * SNOW_MELT_COEF)
    pack = np.zeros_like(t)
    melt = np.zeros_like(t)
    acc = np.zeros(t.shape[1:])
    for year in range(SNOW_SPINUP_YEARS):
        for m in range(12):
            acc = acc + snowfall[m]
            mel = np.minimum(acc, melt_potential[m])
            acc = acc - mel
            if year == SNOW_SPINUP_YEARS - 1:
                pack[m] = acc
                melt[m] = mel
    lm = land_mask[None]
    return (np.where(lm, pack, 0.0),
            np.where(lm, melt, 0.0),
            np.where(lm, snowfall, 0.0),
            np.where(lm, melt_potential, 0.0))
