"""K11 — aquatic biomes: the WWF freshwater and neritic marine classes,
a SEPARATE layer from the terrestrial biome map.

A water cell has an aquatic class AND sits in a climate zone; the two
axes are orthogonal, so this is its own map, not extra BIOMES entries.
Classification is per water BODY (relational — lakes/seas are decided
component-wise at the anchor grid, rivers cell-wise from anchor
fields, marine pointwise on the shelf) and carried to delivery.

WWF coverage and the pruning choices:

- Freshwater, lakes: inland sea (saline + Aral-scale area — decided in
  hydrology.classify_salinity), salt lake (smaller brine), large lake,
  polar / montane / tropical / temperate by climate and altitude.
- Freshwater, rivers: delta (mouth zone of the biggest rivers),
  coastal (tidal reach), floodplain (high-order, wide), upland
  (headwaters), and polar / montane / xeric variants by climate.
- Marine, neritic only (shelf shallower than ~200 m; the deep ocean
  stays "open ocean", unclassed): polar / temperate / tropical shelf,
  and coral reef — the azonal one (warm + shallow + clear, kept away
  from big-river sediment). Upwelling is DEFERRED: it needs a stored
  annual-mean wind field that the climate pass does not keep yet.
"""

from __future__ import annotations

import numpy as np

from exp.k11_worldgen.units import SALINITY_OCEAN_GKG, alt_m, elev_m, \
    precip_mm, temp_c

AQUATIC: list[dict] = [
    {"name": "open ocean",       "color": (23, 44, 92)},
    # marine shelf (neritic)
    {"name": "polar shelf",      "color": (150, 190, 220)},
    {"name": "temperate shelf",  "color": (60, 110, 180)},
    {"name": "tropical shelf",   "color": (40, 160, 170)},
    {"name": "coral reef",       "color": (90, 220, 210)},
    {"name": "temperate upwelling", "color": (75, 135, 160)},
    {"name": "tropical upwelling",  "color": (80, 190, 140)},
    # lakes / inland seas
    {"name": "inland sea",       "color": (30, 70, 140)},
    {"name": "salt lake",        "color": (228, 200, 208)},
    {"name": "large lake",       "color": (70, 130, 195)},
    {"name": "polar lake",       "color": (170, 200, 225)},
    {"name": "montane lake",     "color": (120, 170, 210)},
    {"name": "tropical lake",    "color": (80, 190, 170)},
    {"name": "temperate lake",   "color": (48, 92, 150)},
    # rivers (shades of yellow — one hue family, classes read as
    # brightness/warmth, not as alien colors on the map)
    {"name": "delta",            "color": (250, 225, 90)},
    {"name": "coastal river",    "color": (225, 205, 110)},
    {"name": "floodplain river", "color": (190, 175, 85)},
    {"name": "upland river",     "color": (240, 235, 130)},
    {"name": "polar river",      "color": (215, 215, 160)},
    {"name": "montane river",    "color": (205, 195, 115)},
    {"name": "xeric river",      "color": (220, 170, 80)},
]
AQUATIC_ID = {a["name"]: i for i, a in enumerate(AQUATIC)}
AQUATIC_PALETTE = np.array([a["color"] for a in AQUATIC], dtype=np.uint8)

_SHELF_MAX_DEPTH_M = 200.0
_CORAL_MAX_DEPTH_M = 30.0
_LAKE_LARGE_KM2 = 2000.0     # WWF "large lakes" scale, map-relative
_XERIC_P_MM_YR = 250.0


def _dilate(mask: np.ndarray, n: int) -> np.ndarray:
    out = mask
    for _ in range(n):
        p = np.pad(out, 1, mode="edge")
        out = np.zeros_like(mask)
        for dy in range(3):
            for dx in range(3):
                out |= p[dy:dy + mask.shape[0], dx:dx + mask.shape[1]]
    return out


def classify_aquatic(elev: np.ndarray, hydro: dict, climate: dict,
                     sea_level: float, cell_km2: float = 16.0,
                     currents: dict | None = None) -> np.ndarray:
    """Aquatic class map at the anchor grid (uint8; 0 = open ocean)."""
    ocean = hydro["ocean_mask"]
    lake = hydro["lake_mask"]
    river = hydro["river_mask"]
    a = np.zeros(elev.shape, dtype=np.uint8)

    t_ann = temp_c(climate["T_monthly"]).mean(axis=0)
    t_cold = temp_c(climate["T_monthly"]).min(axis=0)
    p_ann_mm = precip_mm(climate["P_monthly"]).mean(axis=0) * 12.0
    alt = alt_m(elev, sea_level)
    depth_m = -elev_m(elev, sea_level)

    # ---- marine (neritic shelf only) ----
    shelf = ocean & (depth_m < _SHELF_MAX_DEPTH_M)
    a[ocean] = AQUATIC_ID["open ocean"]
    a[shelf] = AQUATIC_ID["temperate shelf"]
    a[shelf & (t_ann < 2.0)] = AQUATIC_ID["polar shelf"]
    # upwelling: the top decile of the shelf's rise field (world-
    # relative — gyre strength varies) where streams climb the slope.
    # Cold nutrient water: no coral there.
    upw = np.zeros_like(shelf)
    if currents is not None:
        rise = currents["rise"]
        if shelf.any():
            thr = np.percentile(rise[shelf], 90)
            if thr > 0:
                upw = shelf & (rise >= thr)
    # coral: frost-free, very shallow, and CLEAR — not beside the
    # sediment plume of a big river mouth (width class 3 at the sea)
    big_mouth = river & _dilate(ocean, 1) & (hydro["width"] >= 3)
    clear = ~_dilate(big_mouth, 3)
    coral = shelf & (t_cold >= 18.0) & (depth_m < _CORAL_MAX_DEPTH_M) \
        & clear & ~upw
    a[coral] = AQUATIC_ID["coral reef"]
    a[upw & (t_cold >= 18.0)] = AQUATIC_ID["tropical upwelling"]
    a[upw & (t_cold < 18.0) & (t_ann >= 2.0)] = \
        AQUATIC_ID["temperate upwelling"]
    tropical_shelf = shelf & (t_cold >= 18.0) & ~coral & ~upw
    a[tropical_shelf] = AQUATIC_ID["tropical shelf"]

    # ---- lakes / inland seas (per component, relational) ----
    sal = hydro["salinity"]
    sea = hydro["sea_mask"]
    H, W = lake.shape
    seen = np.zeros_like(lake)
    for sy in range(H):
        for sx in range(W):
            if not (lake[sy, sx] and not seen[sy, sx]):
                continue
            comp, stack = [], [(sy, sx)]
            while stack:
                y, x = stack.pop()
                if seen[y, x] or not lake[y, x]:
                    continue
                seen[y, x] = True
                comp.append((y, x))
                for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                    ny, nx_ = y + dy, x + dx
                    if 0 <= ny < H and 0 <= nx_ < W and not seen[ny, nx_]:
                        stack.append((ny, nx_))
            cys = tuple(c[0] for c in comp)
            cxs = tuple(c[1] for c in comp)
            if sea[cys[0], cxs[0]]:
                cls = "inland sea"
            elif float(sal[cys, cxs].mean()) > 10.0:
                cls = "salt lake"
            elif len(comp) * cell_km2 >= _LAKE_LARGE_KM2:
                cls = "large lake"
            elif float(t_ann[cys, cxs].mean()) < 0.0:
                cls = "polar lake"
            elif float(alt[cys, cxs].mean()) > 800.0:
                cls = "montane lake"
            elif float(t_cold[cys, cxs].mean()) >= 18.0:
                cls = "tropical lake"
            else:
                cls = "temperate lake"
            a[tuple(cys), tuple(cxs)] = AQUATIC_ID[cls]

    # ---- rivers (cell-wise from anchor fields) ----
    a[river] = AQUATIC_ID["floodplain river"]
    a[river & (hydro["order"] <= 2)] = AQUATIC_ID["upland river"]
    a[river & (p_ann_mm < _XERIC_P_MM_YR)] = AQUATIC_ID["xeric river"]
    a[river & (alt > 800.0)] = AQUATIC_ID["montane river"]
    a[river & (t_ann < 0.0)] = AQUATIC_ID["polar river"]
    coastal = river & _dilate(ocean, 5) & (alt < 10.0)
    a[coastal] = AQUATIC_ID["coastal river"]
    a[river & _dilate(big_mouth, 2)] = AQUATIC_ID["delta"]
    return a


def aquatic_legend_hist(aquatic: np.ndarray,
                        water: np.ndarray) -> tuple[list, list]:
    """(freshwater_rows, marine_rows) for the world.png legend:
    [(name, count, color)] sorted by count, full vocabulary kept.
    `water` excludes land (masked-to-0 cells are not open ocean)."""
    fresh, marine = [], []
    for i, aq in enumerate(AQUATIC):
        n = int(((aquatic == i) & water).sum())
        row = (aq["name"], n, tuple(int(c) for c in aq["color"]))
        if aq["name"] in ("open ocean", "polar shelf", "temperate shelf",
                          "tropical shelf", "coral reef",
                          "temperate upwelling", "tropical upwelling"):
            marine.append(row)
        else:
            fresh.append(row)
    fresh.sort(key=lambda t: -t[1])
    marine.sort(key=lambda t: -t[1])
    return fresh, marine
