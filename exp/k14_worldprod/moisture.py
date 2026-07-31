"""K14 — plant water relations (B5 amendments, owner ruling 2026-07-31).

Two monthly anchor products answering two DIFFERENT questions:

- ``water_potential`` [0,1], land: how the SOIL treats roots — the
  unified water-status field the B5 ground stratum reads. Water
  availability, waterlogging's saturated end, and the osmotic salinity
  penalty, one field: moisture balance (monthly P vs temperature-driven
  demand, retention-weighted), saturation from HAND x retention x
  catchment feed, frozen months lock water as ice. 1 = saturated,
  0 = bone dry.

- ``fresh_availability`` [0,1]: whether UNWRITTEN freshwater habitat
  exists in the cell — the ponds/creeks below L0 granularity (owner
  ruling: freshwater flora may persist in implicit hydrology, graded
  and capped below mapped water; marine obligates stay strict). Built
  from the hydrology side, NOT from water potential: sub-threshold
  flow accumulation (the same field that maps rivers, thresholded
  lower — no parallel hydrology), ponding (low HAND + flat + retentive
  + fed), adjacency to mapped water; permanence vs seasonality from
  catchment size and the monthly water balance. Doubles as the L1/L2
  pond/creek PLACEMENT PRIOR.

A bog scores top water potential while offering a duckweed nothing; a
creekside loam scores moderate water potential while its creek holds a
full pond community. Saturated soil is not open water — two fields.
Everything here is pure functions of decoded arrays (testable without
a k11 dump); build_moisture() is the thin decode+mask wrapper.
"""

from __future__ import annotations

import numpy as np

from exp.k11_worldgen.units import alt_m, hand_m, precip_mm, temp_c

# ── water potential ───────────────────────────────────────────────────
PET_REF_MM = 120.0        # monthly potential evapotranspiration at T_PET_REF
T_PET_REF_C = 30.0
RET_BASE = 0.4            # effective-supply floor at retention 0 (bare sand)
HAND_REF_M = 5.0          # HAND waterlogging decay (B2 convention)
RET_SAT_REF = 0.75        # retention at which ponding capacity saturates
P_SAT_REF_MM = 100.0      # monthly local surplus feeding a wetland fully
ACC_WET_REF = 200.0       # upstream cells feeding a wetland fully
T_ICE_C = 0.0             # soil water locks as ice below this
T_ICE_SPAN_C = 5.0
SAL_PEN = 0.6             # osmotic availability loss at sal_add = 1

# ── freshwater availability ───────────────────────────────────────────
FRESH_ACC_LO = 4.0        # upstream cells: below this is overland flow only
FRESH_ACC_REF = 40.0      # ~the river-mapping threshold: certain stream
RELIEF_REF_M = 30.0       # 3x3 relief decay for ponding flatness
ADJ_W = 0.5               # adjacency-only habitat cap
FRESH_SPREAD_C = 1        # rings around mapped water (4 km at anchor)
FRESH_PERM_REF = 20.0     # upstream cells making a feature perennial
FRESH_LAND_CAP = 0.8      # implicit habitat on land NEVER equals mapped water
WET_GAIN = 1.5            # soil-moisture index -> pond-fullness gain


def _pet(t_c: np.ndarray) -> np.ndarray:
    """Monthly potential evapotranspiration proxy (mm): linear in T,
    zero at freezing."""
    return PET_REF_MM * np.clip(np.asarray(t_c, dtype=float)
                                / T_PET_REF_C, 0.0, 1.0)


def _mi(p_mm: np.ndarray, pet: np.ndarray, ret: np.ndarray) -> np.ndarray:
    """Moisture index [0,1): retention-weighted supply over supply +
    demand. 0.5 when effective supply equals demand."""
    supply = p_mm * (RET_BASE + (1.0 - RET_BASE) * ret)
    den = supply + pet
    return np.divide(supply, den, out=np.zeros_like(den),
                     where=den > 1e-9)


def _relief3(alt: np.ndarray) -> np.ndarray:
    """3x3 (max - min) local relief, edge-clamped."""
    hi = np.asarray(alt, dtype=float).copy()
    lo = hi.copy()
    p = np.pad(alt, 1, mode="edge")
    H, W = alt.shape
    for dy in range(3):
        for dx in range(3):
            win = p[dy:dy + H, dx:dx + W]
            np.maximum(hi, win, out=hi)
            np.minimum(lo, win, out=lo)
    return hi - lo


def water_potential(p_mm: np.ndarray, t_c: np.ndarray,
                    hand: np.ndarray, accum: np.ndarray,
                    ret: np.ndarray, sal_add: np.ndarray) -> np.ndarray:
    """(12,H,W) soil water status in [0,1]: max(moisture index,
    saturation) x ice-free fraction - osmotic salinity penalty.

    p_mm/t_c monthly (12,H,W); hand (m), accum (upstream cells), ret,
    sal_add (H,W). Unmasked — the caller applies the land mask."""
    pet = _pet(t_c)
    mi = _mi(p_mm, pet, ret[None])
    ice_free = np.clip((t_c - T_ICE_C) / T_ICE_SPAN_C, 0.0, 1.0)
    feed = np.clip((p_mm - pet) / P_SAT_REF_MM
                   + accum[None] / ACC_WET_REF, 0.0, 1.0)
    sat = (np.exp(-hand / HAND_REF_M)[None]
           * np.clip(ret / RET_SAT_REF, 0.0, 1.0)[None] * feed)
    psi = np.maximum(mi, sat) * ice_free - SAL_PEN * sal_add[None]
    return np.clip(psi, 0.0, 1.0).astype(np.float32)


def fresh_availability(p_mm: np.ndarray, t_c: np.ndarray,
                       hand: np.ndarray, accum: np.ndarray,
                       alt: np.ndarray, ret: np.ndarray,
                       lake: np.ndarray, river_m: np.ndarray,
                       mangrove: np.ndarray) -> np.ndarray:
    """(12,H,W) unwritten-freshwater habitat in [0,1].

    Base habitat = max(unwritten-stream score from sub-threshold
    accumulation, ponding from HAND x flatness x retention x annual
    feed, capped adjacency to mapped water). Monthly presence = base x
    (permanence + (1-permanence) x that month's wetness): big
    catchments ride through dry months, rain-fed pockets dry out.
    Mapped water overrides to 1 (lakes/mangrove always, rivers in
    their wet months); implicit habitat on land is capped at
    FRESH_LAND_CAP. Unmasked — the caller zeroes the ocean."""
    pet = _pet(t_c)
    mi = _mi(p_mm, pet, ret[None])
    feed_ann = np.clip((p_mm.mean(axis=0) - pet.mean(axis=0))
                       / P_SAT_REF_MM + accum / ACC_WET_REF, 0.0, 1.0)
    flat = np.exp(-_relief3(alt) / RELIEF_REF_M)
    pond = (np.exp(-hand / HAND_REF_M) * flat
            * np.clip(ret / RET_SAT_REF, 0.0, 1.0) * feed_ann)
    stream = np.clip((accum - FRESH_ACC_LO)
                     / (FRESH_ACC_REF - FRESH_ACC_LO), 0.0, 1.0)
    water_any = lake | river_m.any(axis=0)
    from exp.k14_worldprod.derived import _spread_max
    adj = _spread_max(water_any.astype(float), FRESH_SPREAD_C) * ADJ_W
    adj = np.where(water_any, 0.0, adj)        # NEIGHBORS of water only
    base = np.clip(np.maximum.reduce([stream, pond, adj]), 0.0, 1.0)
    perm = np.clip(accum / FRESH_PERM_REF + pond, 0.0, 1.0)
    wet = np.clip(mi * WET_GAIN, 0.0, 1.0)
    avail = base[None] * (perm[None] + (1.0 - perm[None]) * wet)
    avail = np.maximum(avail, river_m.astype(float))
    avail = np.where((lake | mangrove)[None], 1.0, avail)
    implicit = ~(water_any | mangrove)
    avail = np.where(implicit[None],
                     np.minimum(avail, FRESH_LAND_CAP), avail)
    return avail.astype(np.float32)


def build_moisture(z, sea: float, eff: dict) -> dict:
    """Both products at anchor res from a k11 dump + the ground
    effective properties. water_potential is masked to the terrestrial
    domain (river cells on land included, standing water out — same
    convention as terrestrial_productivity); fresh_availability spans
    land + fresh water, zero on the ocean."""
    p = precip_mm(z["c_P_monthly"]).astype(float)
    t = temp_c(z["c_T_monthly"]).astype(float)
    hand = hand_m(z["h_hand"], sea)
    alt = alt_m(z["w_elev"], sea)
    accum = z["h_accumulation"].astype(float)
    ret = eff["retention"].astype(float)
    sal = eff["sal_add"].astype(float)
    ocean = z["h_ocean_mask"] | z["h_sea_mask"]
    lake = z["h_lake_mask"]
    river_m = (z["h_river_monthly"] if "h_river_monthly" in z
               else np.broadcast_to(z["h_river_mask"], p.shape))
    from exp.k14_worldprod.derived import MANGROVE_ID
    mangrove = z["w_biome_map"] == MANGROVE_ID

    land = ~ocean & ~lake
    psi = water_potential(p, t, hand, accum, ret, sal)
    psi = np.where(land[None], psi, 0.0).astype(np.float32)
    avail = fresh_availability(p, t, hand, accum, alt, ret,
                               lake, river_m, mangrove)
    avail = np.where(ocean[None], 0.0, avail).astype(np.float32)
    return {"water_potential": psi, "fresh_availability": avail}
