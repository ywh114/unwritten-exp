"""K14 B4 — water-column attributes (biosphere addendum B4).

Ocean cells get stratified ATTRIBUTES, not volumetric layers: bathymetry,
photic depth, depth zones + bottom_lit, marine-snow food flux (vertical
settling + slope-gated downslope routing), bottom temperature, vent
benthos halo, and the deep nutrient-return inventory that feeds the
upwelling modifier (the B2 two-phase marine loop). Everything here is
anchor-res (H,W) or (12,H,W); delivery/upsampling stays in derived.py.

Two routing systems share the hydrology pattern (second home):
  - downslope redistribution: steepest descent on RAW bathymetry, no
    fill — sediment ponds in pits (trenches are sediment traps);
  - deep return flow: priority-flood FROM the upwelling exits so every
    ocean cell drains to one; accumulated snow along the path is the
    remineralized nutrient inventory the upwelling surfaces.
"""

from __future__ import annotations

import heapq

import numpy as np

from exp.k11_worldgen.hydrology import flow_accumulation, flow_direction, \
    priority_flood
from exp.k11_worldgen.units import elev_m, temp_c

# ── draft constants (addendum B4 §open questions — owner-tunable) ──────
SNOW_REF_M = 800.0          # remineralization attenuation depth, meters
TBOT_REF_M = 500.0          # bottom-temperature decay scale, meters
T_DEEP_C = 2.0              # deep-ocean floor temperature
SLOPE_EXPORT_REF_M = 400.0  # per-cell drop for full downslope export
MAX_EXPORT = 0.9            # export fraction cap
VENT_OASIS = 0.8            # chemosynthetic halo peak productivity
VENT_HALO_SIGMA = 1.5       # halo gaussian sigma, anchor cells
PHOTIC_OPEN_M = 150.0       # clear open-ocean photic depth
PHOTIC_TURB_PLUME_M = 100.0 # plume turbidity shading, meters at full plume
PHOTIC_TURB_BLOOM_M = 80.0  # bloom turbidity shading at bloom reference
PHOTIC_BLOOM_REF = 0.6      # surface productivity of a full bloom
PHOTIC_MIN_M, PHOTIC_MAX_M = 10.0, 250.0
INV_LO, INV_HI = 0.5, 1.5   # upwelling inventory-modifier clip
CELL_M = 4000.0             # anchor cell size (L0 granularity)
PH_OCEAN_SURF = 8.1         # surface seawater pH
PH_OCEAN_DROP = 0.3         # surface->abyss column pH decrease (OMZ/age)
PH_DEPTH_REF_M = 4000.0     # bathy at which the drop saturates (B3's
                            # abyssal reference, same fixed scale)
PH_BED_W = 0.6              # fresh pH: bed weight (catchment gets 1-w)
PH_BOG_SHIFT = 1.3          # humic-acid shift at 100% peat window
PH_WINDOW_C = 2             # catchment proxy: box radius, anchor cells
PH_LO, PH_HI = 3.5, 9.5     # clip (B3 class-table extremes)
# fresh-water derivations (B4 fix 2026-08-01 — the submerged FRESH
# strata read these; the marine fields above are ocean-only, and
# reading them on a lake/river used to zero every submerged freshwater
# plan). FRESH_PHOTIC_BLOOM_REF mirrors the marine PHOTIC_BLOOM_REF on
# the shared B2 scale: annual-mean productivity of a full bloom.
FRESH_PHOTIC_OPEN_M = 30.0      # clear-lake photic base, meters
FRESH_PHOTIC_TURB_BOG_M = 20.0  # humic-blackwater shading at full bog share
FRESH_PHOTIC_TURB_BLOOM_M = 10.0  # bloom shading at a full annual bloom
FRESH_PHOTIC_BLOOM_REF = 0.6    # productivity of a full annual bloom
FRESH_PHOTIC_MIN_M, FRESH_PHOTIC_MAX_M = 1.0, 60.0
T_HYPO_C = 4.0                  # hypolimnion floor (fresh water's
                                # density maximum — deep lakes hold ~4 C)
FBOT_REF_M = 10.0               # fresh bottom-temp decay scale, meters

# depth-zone table: (name, upper bound m, color). Categorical like the
# B3 ground table — the palette's source of truth travels in the pack.
ZONES = [
    dict(name="epipelagic bottom", max_m=200.0, color=(70, 130, 210)),
    dict(name="mesopelagic bottom", max_m=1000.0, color=(45, 95, 175)),
    dict(name="bathypelagic bottom", max_m=4000.0, color=(28, 62, 135)),
    dict(name="abyssal bottom", max_m=6000.0, color=(14, 36, 92)),
    dict(name="hadal", max_m=np.inf, color=(6, 16, 52)),
]

_D8 = ((0, 1), (0, -1), (1, 0), (-1, 0),
       (1, 1), (1, -1), (-1, 1), (-1, -1))


def bathymetry_m(z, sea: float) -> np.ndarray:
    """Meters below sea level on ocean/sea cells (0 elsewhere). Reads
    w_elev — h_depth is the lakes/rivers field with an ocean sentinel."""
    ocean = z["h_ocean_mask"] | z["h_sea_mask"]
    return np.where(ocean, np.maximum(-elev_m(z["w_elev"], sea), 0.0), 0.0)


def depth_zone(bathy: np.ndarray) -> np.ndarray:
    """Zone id per cell (uint8); 255 on non-ocean. By bottom depth."""
    out = np.full(bathy.shape, 255, np.uint8)
    ocean = bathy > 0
    for i, zn in enumerate(ZONES):
        out[ocean & (bathy <= zn["max_m"]) & (out == 255)] = i
    return out


def bottom_temp_c(z, sea: float, bathy: np.ndarray) -> np.ndarray:
    """Annual bottom temperature: shelf bottoms track the damped annual
    SST, deep bottoms tend to T_DEEP_C. The deep ocean has no seasons at
    L0 granularity — one annual field."""
    sst_ann = temp_c(z["c_T_monthly"]).mean(axis=0)
    t = T_DEEP_C + (sst_ann - T_DEEP_C) * np.exp(-bathy / TBOT_REF_M)
    return np.where(bathy > 0, t, 0.0)


def _box_mean(f: np.ndarray, r: int) -> np.ndarray:
    """Box mean over a (2r+1)^2 window, edge-truncated (small windows at
    anchor res — no scipy)."""
    acc = np.zeros_like(f, dtype=np.float64)
    cnt = np.zeros_like(f, dtype=np.float64)
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            ys = slice(max(0, dy), f.shape[0] + min(0, dy))
            xs = slice(max(0, dx), f.shape[1] + min(0, dx))
            yt = slice(max(0, -dy), f.shape[0] + min(0, -dy))
            xt = slice(max(0, -dx), f.shape[1] + min(0, -dx))
            acc[yt, xt] += f[ys, xs]
            cnt[yt, xt] += 1.0
    return acc / cnt


def ocean_ph(bathy_m: np.ndarray) -> np.ndarray:
    """Column pH from depth: 8.1 at the surface easing to 7.8 (old deep
    water, OMZ/age) on the fixed 4000 m reference. Pointwise — runs at
    any resolution, so it re-derives at delivery res from the delivered
    bathymetry (bilinear-upsampling across the coastline leaves zero
    holes, same ruling as the depth-zone re-derivation)."""
    return PH_OCEAN_SURF - PH_OCEAN_DROP * np.clip(
        bathy_m / PH_DEPTH_REF_M, 0.0, 1.0)


def fresh_ph(bed_ph: np.ndarray, land_ph_mean: np.ndarray,
             bog_share: np.ndarray) -> np.ndarray:
    """Lake/river water pH: bed- and catchment-driven — PH_BED_W x the
    bed pH (B3 class rows) + the surrounding land-soil mean — shifted
    acid by the neighborhood peat share (humic blackwater: bog drainage
    reads pH 4.5-5.5, not the bed's 7). Pointwise; the catchment inputs
    arrive pre-windowed (PH_WINDOW_C box at anchor, upsampled)."""
    return np.clip(PH_BED_W * bed_ph + (1.0 - PH_BED_W) * land_ph_mean
                   - PH_BOG_SHIFT * bog_share, PH_LO, PH_HI)


def fresh_photic_depth_m(bog_share: np.ndarray, prod_ann: np.ndarray,
                         fresh: np.ndarray) -> np.ndarray:
    """How deep light reaches in LAKES/RIVERS: clear-water base shaded
    by humic blackwater (the bog-peat share, the SAME windowed input
    fresh_ph reads — a bog-ringed lake goes brown) and by the annual
    bloom (freshwater_productivity annual mean on the shared B2 scale).
    Bounded [FRESH_PHOTIC_MIN, FRESH_PHOTIC_MAX]. Zero off fresh water
    — the ocean keeps the marine photic_depth_m (that field reads 0 on
    every lake/river, which made submerged freshwater plans lethal by
    construction; B4 fix 2026-08-01)."""
    turb = (np.clip(bog_share, 0.0, 1.0) * FRESH_PHOTIC_TURB_BOG_M
            + np.clip(prod_ann / FRESH_PHOTIC_BLOOM_REF, 0.0, 1.0)
            * FRESH_PHOTIC_TURB_BLOOM_M)
    d = np.clip(FRESH_PHOTIC_OPEN_M - turb, FRESH_PHOTIC_MIN_M,
                FRESH_PHOTIC_MAX_M)
    return np.where(fresh, d, 0.0)


def fresh_bottom_temp_c(z, sea: float, depth_fresh: np.ndarray,
                        fresh: np.ndarray) -> np.ndarray:
    """Annual bottom temperature in lakes/rivers: the surface annual
    mean damped over the column toward the hypolimnion floor —
    t = T_HYPO + (SST_ann - T_HYPO) x exp(-depth_fresh / FBOT_REF_M).
    Shallow cells/rivers read ~ the surface annual; deep lake bottoms
    tend to T_HYPO_C (4 C). Zero off fresh water — the ocean keeps the
    marine bottom_temp_c (which reads 0 on every lake/river, so fresh
    bottoms used to be frozen at 0 C; B4 fix 2026-08-01)."""
    sst_ann = temp_c(z["c_T_monthly"]).mean(axis=0)
    t = (T_HYPO_C + (sst_ann - T_HYPO_C)
         * np.exp(-depth_fresh / FBOT_REF_M))
    return np.where(fresh, t, 0.0)


def photic_depth_m(bathy: np.ndarray, plume: np.ndarray,
                   surf_prod_ann: np.ndarray,
                   plume_weight: float) -> np.ndarray:
    """How deep light reaches: clear-water base shaded by plume
    turbidity and the overlying bloom. Bounded [PHOTIC_MIN, PHOTIC_MAX].
    Zero on land. plume arrives PRE-weighted (PLUME_WEIGHT product), so
    its full-strength value is plume_weight."""
    turb = (np.clip(plume / max(plume_weight, 1e-9), 0.0, 1.0)
            * PHOTIC_TURB_PLUME_M
            + np.clip(surf_prod_ann / PHOTIC_BLOOM_REF, 0.0, 1.0)
            * PHOTIC_TURB_BLOOM_M)
    d = np.clip(PHOTIC_OPEN_M - turb, PHOTIC_MIN_M, PHOTIC_MAX_M)
    return np.where(bathy > 0, d, 0.0)


def _downslope_route(bathy: np.ndarray, snow_ann: np.ndarray) -> np.ndarray:
    """Redistribute annual snow downslope: each cell keeps (1-export)
    of (local + incoming) and donates the rest to its deepest neighbor.
    Steepest descent on RAW bathymetry — pits (trench floors, abyssal
    lows) are sediment traps, exactly where Earth ponds detritus.
    Export is slope-gated: flat abyssal plains keep their snow, the
    continental slope funnels it to the base-of-slope fan."""
    H, W = bathy.shape
    ocean = bathy > 0
    acc = np.where(ocean, snow_ann, 0.0)
    order = sorted(((float(bathy[y, x]), y, x)
                    for y in range(H) for x in range(W) if ocean[y, x]))
    for _, y, x in order:
        if acc[y, x] == 0.0:
            continue
        best_drop, best = 0.0, None
        for dy, dx in _D8:
            ny, nx = y + dy, x + dx
            if 0 <= ny < H and 0 <= nx < W and ocean[ny, nx]:
                drop = bathy[ny, nx] - bathy[y, x]
                if drop > best_drop:
                    best_drop, best = drop, (ny, nx)
        if best is None:
            continue
        export = min(best_drop / SLOPE_EXPORT_REF_M, MAX_EXPORT)
        give = acc[y, x] * export
        acc[y, x] -= give
        acc[best] += give
    return acc


def marine_snow(bathy: np.ndarray, mprod_prov: np.ndarray) -> np.ndarray:
    """(12,H,W) detrital food flux at the bottom. Vertical settling
    (overlying productivity x exp(-depth/SNOW_REF)), then ONE downslope
    routing on the annual sum; monthly planes scale by their month's
    vertical fraction (the deep sea has no seasons of its own).
    Currents advection of snow is rejected (addendum B4 ruling)."""
    vert = mprod_prov * np.exp(-bathy[None] / SNOW_REF_M)
    vert = np.where(bathy[None] > 0, vert, 0.0)
    ann = vert.sum(axis=0)
    routed = _downslope_route(bathy, ann)
    frac = np.divide(vert, np.where(ann > 0, ann, 1.0))
    return routed[None] * frac


def deep_return_inventory(bathy: np.ndarray, snow_ann: np.ndarray,
                          rise_ann: np.ndarray) -> np.ndarray:
    """(H,W) upwelling inventory modifier in [INV_LO, INV_HI], 1.0 off
    upwelling cells. Deep water drains to the upwelling exits
    (priority-flood FROM them); the snow accumulated along each exit's
    deep catchment is its remineralized nutrient inventory. Bounded by
    the 99th-percentile exit (the world's best-fed upwelling), same
    convention as RISE_REF — a bound, never a re-normalization."""
    ocean = bathy > 0
    exits = ocean & (rise_ann > 0)
    if not exits.any():
        return np.ones(bathy.shape)
    # conveyor height field: seafloor elevation (deep = low). Exits are
    # the SINKS of the deep circulation — pin them below everything, or
    # they sit at the same level as the surrounding abyss and no cell
    # ever drains into them.
    h_conv = -bathy
    h_conv = np.where(exits, -1e9, h_conv)
    w = priority_flood(h_conv, exits)
    direction, flat = flow_direction(w, h_conv)
    acc = flow_accumulation(w, direction, flat,
                            weight=np.where(ocean, snow_ann, 0.0))
    inv = acc[exits]
    ref = max(float(np.percentile(inv, 99.0)), 1e-12)
    mod = np.ones(bathy.shape)
    mod[exits] = INV_LO + np.clip(acc[exits] / ref, 0.0, 1.0) * (INV_HI - INV_LO)
    return mod


def vent_benthos(vent_pts: list[dict], active: list[bool],
                 shape: tuple[int, int]) -> np.ndarray:
    """(H,W) chemosynthetic halo around ACTIVE marine vents: gaussian
    with VENT_HALO_SIGMA, peak VENT_OASIS. Dormant vents cast nothing —
    same K1 dormancy roll as the ground pass (shared draw)."""
    H, W = shape
    halo = np.zeros((H, W))
    r = int(np.ceil(VENT_HALO_SIGMA * 3))
    for p, act in zip(vent_pts, active):
        if not act:
            continue
        y, x = p["y"], p["x"]
        y0, y1 = max(0, y - r), min(H, y + r + 1)
        x0, x1 = max(0, x - r), min(W, x + r + 1)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        g = VENT_OASIS * np.exp(-0.5 * ((yy - y) ** 2 + (xx - x) ** 2)
                                / VENT_HALO_SIGMA ** 2)
        np.maximum(halo[y0:y1, x0:x1], g, out=halo[y0:y1, x0:x1])
    return halo


def build_column(z, sea: float, mprod_prov: np.ndarray,
                 plume: np.ndarray, plume_weight: float,
                 vent_pts: list[dict], vent_active: list[bool]) -> dict:
    """All water-column products at anchor res + the upwelling modifier
    for the second marine phase. mprod_prov is the PROVISIONAL marine
    productivity (local rise-strength bonus); it is what snow reads —
    the final marine field differs only at upwellings."""
    bathy = bathymetry_m(z, sea)
    zone = depth_zone(bathy)
    ocean = bathy > 0
    snow = marine_snow(bathy, mprod_prov)
    rise_ann = np.clip(z["r_rise_m"], 0.0, None).mean(axis=0)
    rise_mod = deep_return_inventory(bathy, snow.sum(axis=0), rise_ann)
    halo = vent_benthos(vent_pts, vent_active, bathy.shape)
    halo = np.where(ocean, halo, 0.0)
    photic = photic_depth_m(bathy, plume, mprod_prov.mean(axis=0),
                            plume_weight)
    return {
        "bathymetry_m": bathy,
        "depth_zone": zone,
        "bottom_lit": ocean & (bathy <= photic),
        "photic_depth_m": photic,
        "bottom_temp_c": bottom_temp_c(z, sea, bathy),
        "marine_snow": snow,
        "vent_benthos": halo,
        "benthic_food": np.maximum(snow, halo[None]),
        "rise_mod": rise_mod,
    }
