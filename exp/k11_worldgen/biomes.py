"""Month-vector biome classification for the K11 demo.

Each cell's 12-month (temperature, precipitation) curve is converted
to metric units (degC, mm/month — see units.py) and matched against
prototype MONTH VECTORS — one per biome, built from real-world climate
normals for that biome — by weighted Euclidean distance.
Nearest-distance in 24-dim climate space keeps biome boundaries
organic; axis-aligned threshold trees produce straight
isotherm/isohyet bands.

The vocabulary is exactly the WWF / Olson & Dinerstein (1998)
terrestrial system: the 14 biomes Wikipedia lists plus the abiotic
land zones (split into "rock" and "ice"), and nothing else — earlier
demo extras (montane forest, cloud forest, snow peak, ice cap) are
folded into the WWF classes.  Ocean/lake are WATER MASKS, not biomes
(the WWF freshwater / marine lists are modelled separately in
aquatic.py).

There is no official WWF colour scheme; the palette approximates the
de-facto colours used on WWF terrestrial-ecoregion maps.

A few classes are geographic by definition and apply as overrides
after the vector match: flooded grassland (inundation), mangrove
(tidal fringe), rock (nival zone) and ice (permanent ice cap).
Everything else is purely the month's curves.
"""

from __future__ import annotations

import numpy as np

from exp.k11_worldgen.raster import upsample_bicubic
from exp.k11_worldgen.units import alt_m, elev_m, hand_m, precip_mm, temp_c

# Order defines ids; PALETTE aligns with it.  "name" is the display /
# legend label (uppercased by the legend renderer).  kind="water"
# entries are masks, not biomes.
BIOMES: list[dict] = [
    # --- the WWF terrestrial classes (Olson & Dinerstein 1998): the 14
    # biomes + the abiotic land zones, split here into "rock" (barren
    # ground above the vegetation line) and "ice" (permanent ice cap) ---
    # house palette: lush reads as dark green, arid as sand; browns are
    # avoided (montane/med are sage/olive greens, not tan)
    {"name": "tropical moist forest",      "color": (0, 110, 45)},
    {"name": "tropical dry forest",        "color": (140, 190, 80)},
    {"name": "tropical conifer forest",    "color": (30, 140, 110)},
    {"name": "temperate broadleaf forest", "color": (80, 170, 80)},
    {"name": "temperate conifer forest",   "color": (50, 130, 115)},
    {"name": "boreal taiga",               "color": (40, 100, 95)},
    {"name": "tropical grassland",         "color": (200, 180, 100)},
    {"name": "temperate grassland",        "color": (150, 175, 90)},
    {"name": "flooded grassland",          "color": (90, 140, 160)},
    {"name": "montane grassland",          "color": (150, 170, 115)},
    {"name": "tundra",                     "color": (170, 175, 165)},
    {"name": "mediterranean scrub",        "color": (150, 170, 80)},
    {"name": "desert xeric shrubland",     "color": (225, 205, 140)},
    {"name": "mangrove",                   "color": (150, 70, 120)},
    {"name": "rock",                       "color": (150, 148, 152)},
    {"name": "ice",                        "color": (232, 240, 246)},
    # --- water masks (not biomes) ---
    {"name": "lake",                       "color": (48, 92, 150)},
    {"name": "ocean",                      "color": (23, 44, 92)},
]
BIOME_ID = {b["name"]: i for i, b in enumerate(BIOMES)}
PALETTE = np.array([b["color"] for b in BIOMES], dtype=np.uint8)

_MONTHS = np.arange(12.0)


def _curve(base: float, amp: float, phase: float) -> np.ndarray:
    """Cosine annual curve; phase = month of maximum (0 = Jan)."""
    return base + amp * np.cos(2 * np.pi * (_MONTHS - phase) / 12.0)


def _flat(v: float) -> np.ndarray:
    return np.full(12, v)


def _shaped(base: float, bumps: list[tuple[float, float, float]]) -> np.ndarray:
    """Baseline plus Gaussian bumps [(center_month, height, width)]."""
    out = np.full(12, base)
    for c, h, w in bumps:
        d = np.minimum(np.abs(_MONTHS - c), 12 - np.abs(_MONTHS - c))
        out = out + h * np.exp(-0.5 * (d / w) ** 2)
    return out


# Prototype month vectors in METRIC units (degC, mm/month), from
# real-world climate normals of each biome (summer solstice at month
# 6).  Water entries are placeholders — they only enter via override.
_PROTOTYPES: dict[str, tuple[np.ndarray, np.ndarray]] = {
    # Amazon/Congo modal: hot year-round, heavy but SEASONAL rain —
    # real moist broadleaf spans a short dry season (much of the
    # Amazon runs 1-3 months under 100 mm), so the prototype spans
    # 40..240 mm rather than 90..230
    "tropical moist forest":      (_flat(26.5), _curve(140.0, 100.0, 1)),
    # monsoon forest: hot, dry winter, violent wet season
    "tropical dry forest":        (_curve(26.0, 3.0, 6), _shaped(15.0, [(6.5, 260.0, 2)])),
    # subtropical highland pine-oak: mild, semihumid summer rain
    "tropical conifer forest":    (_curve(17.0, 4.0, 6), _shaped(30.0, [(7, 120.0, 2)])),
    # W. Europe + E. US / Beijing: full seasons, even rain. Winters run
    # below freezing on the continental side (Beijing Jan ~-4, Chicago
    # ~-6) — a Jan > 0 prototype would concede every sub-zero-winter
    # cell to taiga, but real temperate broadleaf spans them.
    "temperate broadleaf forest": (_curve(11.0, 13.0, 6), _curve(75.0, 10.0, 0)),
    # Pacific NW: cool, very wet (winter-max maritime)
    "temperate conifer forest":   (_curve(8.0, 9.0, 6), _curve(140.0, 50.0, 0)),
    # boreal belt centroid (Finland/Sweden/interior Canada), not the
    # Siberian extreme: Jan ~-15, Jul ~+15, modest summer-max rain
    "boreal taiga":               (_curve(0.0, 15.0, 6), _curve(40.0, 25.0, 6.5)),
    # Serengeti / cerrado: hot, semiarid, one wet season
    "tropical grassland":         (_curve(25.0, 3.0, 6), _shaped(5.0, [(6.5, 140.0, 2)])),
    # steppe / prairie: continental seasons, low summer-max rain
    "temperate grassland":        (_curve(8.0, 14.0, 6), _curve(25.0, 15.0, 6)),
    # Pantanal: warm, strong seasonal flood pulse
    "flooded grassland":          (_curve(20.0, 6.0, 6), _shaped(10.0, [(6.5, 190.0, 2)])),
    # paramo / puna / Tibet: cold year-round, SMALL swing (altitude,
    # not latitude, is what makes it cold)
    "montane grassland":          (_curve(2.0, 7.0, 6), _curve(50.0, 30.0, 6.5)),
    # arctic coast: brutal swing, brief cool summer, dry
    "tundra":                     (_curve(-10.0, 18.0, 6), _curve(20.0, 10.0, 6.5)),
    # Mediterranean basin: warm dry summer, winter rain
    "mediterranean scrub":        (_curve(16.0, 8.0, 6), _shaped(3.0, [(0.5, 90.0, 2.5)])),
    # Sahara: hot, bone dry
    "desert xeric shrubland":     (_curve(24.0, 9.0, 6), _flat(2.0)),
    # frost-free tidal forest (override-only in practice)
    "mangrove":                   (_flat(27.0), _flat(150.0)),
    # barren ground above the vegetation line (override-only)
    "rock":                       (_flat(-5.0), _flat(30.0)),
    # permanent ice cap (override-only)
    "ice":                        (_flat(-30.0), _flat(10.0)),
    "lake":                       (_flat(10.0), _flat(100.0)),
    "ocean":                      (_flat(10.0), _flat(100.0)),
}

# distance weights: scale the units so ~12 degC ~ ~100 mm ~ one unit
_W_T, _W_P = 1.0 / 12.0, 1.0 / 100.0

# the vector match is CLIMATE-ONLY: classes that are places, not
# climates (flooded grassland, mangrove, rock, ice, lake, ocean) are
# excluded from the prototypes and exist purely via geographic
# overrides / water masks — otherwise a Pantanal-like climate vector
# would flood-classify any warm seasonal lowland regardless of where it
# sits
_GEOGRAPHIC = {"flooded grassland", "mangrove", "rock", "ice",
               "lake", "ocean"}
_PROTO_NAMES = [k for k in _PROTOTYPES if k not in _GEOGRAPHIC]
_PROTO_T = np.stack([_PROTOTYPES[k][0] for k in _PROTO_NAMES])  # (P, 12)
_PROTO_P = np.stack([_PROTOTYPES[k][1] for k in _PROTO_NAMES])
_PROTO_IDS = np.array([BIOME_ID[k] for k in _PROTO_NAMES], dtype=np.uint8)
_PROTO_C = (_W_T ** 2 * (_PROTO_T ** 2).sum(1)
            + _W_P ** 2 * (_PROTO_P ** 2).sum(1))


def _dilate(mask: np.ndarray, n: int) -> np.ndarray:
    """Chebyshev dilation by n cells (mechanical, any grid)."""
    out = mask
    for _ in range(n):
        p = np.pad(out, 1, mode="edge")
        out = np.zeros_like(mask)
        for dy in range(3):
            for dx in range(3):
                out |= p[dy:dy + mask.shape[0], dx:dx + mask.shape[1]]
    return out


class _Acc:
    """Streaming accumulators: nearest-prototype distance (via the
    expansion |v-p|^2 = |v|^2 - 2 v.p + |p|^2, so no (H,W,24,proto)
    array materializes) plus the override/render reductions."""

    def __init__(self, shape: tuple[int, int]) -> None:
        z = lambda v=0.0: np.full(shape, v, dtype=np.float32)
        self.s2 = z()
        self.dot = np.zeros((len(_PROTO_NAMES),) + shape, dtype=np.float32)
        self.t_max, self.t_min = z(-np.inf), z(np.inf)
        self.p_max = z(-np.inf)
        self.t_sum = z()
        self.grow_p, self.grow_n = z(), z()
        self.t_norm_sum, self.p_norm_sum = z(), z()

    def add(self, t_c: np.ndarray, p_mm: np.ndarray,
            t_norm: np.ndarray, p_norm: np.ndarray, month: int) -> None:
        t_c = t_c.astype(np.float32)
        p_mm = p_mm.astype(np.float32)
        self.s2 += _W_T ** 2 * t_c ** 2 + _W_P ** 2 * p_mm ** 2
        self.dot += (_W_T ** 2 * _PROTO_T[:, month, None, None] * t_c
                     + _W_P ** 2 * _PROTO_P[:, month, None, None] * p_mm)
        np.maximum(self.t_max, t_c, out=self.t_max)
        np.minimum(self.t_min, t_c, out=self.t_min)
        np.maximum(self.p_max, p_mm, out=self.p_max)
        self.t_sum += t_c
        grow = t_c > 5.0  # growing season: months above 5 degC
        self.grow_p += np.where(grow, p_mm, 0.0)
        self.grow_n += grow
        self.t_norm_sum += t_norm
        self.p_norm_sum += p_norm

    def classify2(self) -> tuple[np.ndarray, np.ndarray]:
        """(nearest, second-nearest) prototype ids per cell."""
        d2 = self.s2[None] - 2 * self.dot + _PROTO_C[:, None, None]
        i2 = np.argpartition(d2, 1, axis=0)[:2]
        return _PROTO_IDS[i2[0]], _PROTO_IDS[i2[1]]

    def classify(self) -> np.ndarray:
        return self.classify2()[0]


# ---- geographic overrides (the classes that are places, not climates) --

_MONTANE_MIN_ALT_M = 800.0


def _altitude_swap(first: np.ndarray, second: np.ndarray,
                   alt_m: np.ndarray) -> np.ndarray:
    """Montane grassland <-> tundra split along the montane altitude
    line.  WWF lumps ALPINE tundra into montane grasslands, so tundra
    high up is really the montane class; and the montane climate
    signature (cold, small swing) also fits subpolar maritime LOWLANDS
    (Iceland at sea level), which are not montane anything — those fall
    back to their second-nearest climate class."""
    b = first
    mg, tu = BIOME_ID["montane grassland"], BIOME_ID["tundra"]
    low = alt_m < _MONTANE_MIN_ALT_M
    mon_low = (first == mg) & low
    tun_high = (first == tu) & ~low
    b[mon_low] = second[mon_low]
    b[tun_high] = mg
    return b

def _apply_overrides(biome: np.ndarray, st: dict) -> np.ndarray:
    b = biome.copy()
    land = ~st["ocean_m"] & ~st["lake_m"]
    # rock: barren nival-zone ground above the vegetation line —
    # vegetation gives out ~4500 m even in the tropics, and lower
    # (~2500 m) where the warm season barely exists
    b[(st["alt_m"] > 4500.0) & land] = BIOME_ID["rock"]
    b[(st["alt_m"] > 2500.0) & (st["T_warm"] < 4.0) & land] = \
        BIOME_ID["rock"]
    # ice: permanent ice cap — never above freezing at any altitude
    # (applied after rock: a frozen summit is ice-covered, not bare)
    b[(st["T_warm"] < 0.0) & land] = BIOME_ID["ice"]
    # flooded grassland: a SPECIAL place (Pantanal/Okavango), not a
    # default wet lowland — the ACTIVE FLOODPLAIN of a real river
    # (within ~3 cells of a width-2+ channel and ~8 m of the drainage
    # surface) AND a violent wet season (>= 240 mm in the wettest
    # month). The width gate keeps creek gullies and generic riparian
    # strips out.
    big = st["river_m"] & (st["width"] >= 2)
    b[(st["hand_m"] < 8.0) & (st["P_wet"] >= 240.0)
      & _dilate(big, 3) & land] = BIOME_ID["flooded grassland"]
    # water masks
    b[st["ocean_m"]] = BIOME_ID["ocean"]
    b[st["lake_m"]] = BIOME_ID["lake"]
    # mangrove (after the water masks so shallow-water stands win):
    # frost-free, and either tidal LAND directly bordering the sea
    # (adjacency to the ocean itself — never chained inland via rivers
    # or other mangrove cells) or the tidal-flat SEA FRINGE next to
    # land (bed within ~8 m of the surface — real mangroves colonize
    # the intertidal edge, not the open shelf)
    frost_free = st["T_cold"] >= 18.0
    tidal_land = _dilate(st["ocean_m"], 1) & (st["alt_m"] < 10.0) & land
    shallow_sea = st["ocean_m"] & (st["alt_m"] > -8.0) & _dilate(land, 1)
    b[(tidal_land | shallow_sea) & frost_free] = BIOME_ID["mangrove"]
    return b


def _mode_filter(biome: np.ndarray, passes: int = 2) -> np.ndarray:
    """Vectorized 3x3 modal smoothing (biological-scale denoise)."""
    b = biome
    n = len(BIOMES)
    for _ in range(passes):
        counts = np.zeros((n,) + b.shape, np.int8)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                nb = np.roll(np.roll(b, dy, 0), dx, 1)
                for c in range(n):
                    counts[c] += nb == c
        b = np.argmax(counts, axis=0).astype(np.uint8)
    return b


def _masks_state(elev: np.ndarray, ocean_m: np.ndarray, lake_m: np.ndarray,
                 river_m: np.ndarray, sea_level: float,
                 hand: np.ndarray, width: np.ndarray | None = None) -> dict:
    return {
        "ocean_m": ocean_m, "lake_m": lake_m, "river_m": river_m,
        "alt_m": alt_m(elev, sea_level),
        "hand_m": hand_m(hand, sea_level),
        "width": width,
    }


def classify_biomes(elev: np.ndarray, hydro: dict, climate: dict,
                    sea_level: float) -> np.ndarray:
    """Anchor-grid biome map: vector match + modal smoothing + overrides.

    Smoothing runs on the climate-matched classes only; the geographic
    overrides (rock, ice, flooded grassland, mangrove) apply last so
    the modal filter can neither erase them nor grow them beyond their
    geographic criteria."""
    ocean_m = hydro["ocean_mask"]
    acc = _Acc(elev.shape)
    for m in range(12):
        acc.add(temp_c(climate["T_monthly"][m]),
                precip_mm(climate["P_monthly"][m]),
                climate["T_monthly"][m], climate["P_monthly"][m], m)
    b = _altitude_swap(*acc.classify2(), alt_m(elev, sea_level))
    st = _masks_state(elev, ocean_m, hydro["lake_mask"], hydro["river_mask"],
                      sea_level, hydro["hand"], hydro["width"])
    st.update(T_warm=acc.t_max, T_cold=acc.t_min, P_wet=acc.p_max)
    b = _mode_filter(b, passes=2)
    # smoothing must not move standing water
    b[ocean_m] = BIOME_ID["ocean"]
    b[hydro["lake_mask"]] = BIOME_ID["lake"]
    b = _apply_overrides(b, st)
    return b


def classify_streaming(elev_hi: np.ndarray, ocean_hi: np.ndarray,
                       lake_hi: np.ndarray, river_hi: np.ndarray,
                       hand_hi: np.ndarray,
                       climate: dict, sea_level: float, factor: int,
                       width_hi: np.ndarray | None = None):
    """Biomes at the delivered resolution.

    Classification is pointwise (delivery rule), so the monthly curves
    are bicubic-upsampled month by month, converted to metric, and the
    prototype-match accumulators stream — no (12, H, W) hi-res stack is
    held.  Returns (biome_hi, T_hi, P_hi, p_grow_hi, t_cold_hi) with
    T/P as normalized annual means (render input), p_grow in mm/month,
    and t_cold the metric coldest-month temperature (the delivered-res
    marine classification reads it).
    """
    acc = _Acc(elev_hi.shape)
    for m in range(12):
        t_n = upsample_bicubic(climate["T_monthly"][m], factor)
        p_n = upsample_bicubic(climate["P_monthly"][m], factor)
        acc.add(temp_c(t_n), precip_mm(p_n), t_n, p_n, m)
    b = _altitude_swap(*acc.classify2(), alt_m(elev_hi, sea_level))
    st = _masks_state(elev_hi, ocean_hi, lake_hi, river_hi, sea_level,
                      hand_hi, width_hi)
    st.update(T_warm=acc.t_max, T_cold=acc.t_min, P_wet=acc.p_max)
    b = _apply_overrides(b, st)
    T_hi = acc.t_norm_sum / 12
    P_hi = acc.p_norm_sum / 12
    p_grow_hi = acc.grow_p / np.maximum(acc.grow_n, 1)
    return b, T_hi, P_hi, p_grow_hi, acc.t_min


def growing_season_p(climate: dict) -> np.ndarray:
    """Mean monthly mm over months above 5 degC — crop-relevant rain."""
    acc = _Acc(climate["T"].shape)
    for m in range(12):
        acc.add(temp_c(climate["T_monthly"][m]),
                precip_mm(climate["P_monthly"][m]),
                climate["T_monthly"][m], climate["P_monthly"][m], m)
    return acc.grow_p / np.maximum(acc.grow_n, 1)


_FOREST_BASE = {
    "tropical moist forest": 1.0, "tropical dry forest": 0.6,
    "tropical conifer forest": 0.85, "temperate broadleaf forest": 0.9,
    "temperate conifer forest": 0.9, "boreal taiga": 0.85,
    "mangrove": 0.6, "flooded grassland": 0.3,
    "mediterranean scrub": 0.5, "montane grassland": 0.1,
}


def forest_cover(biome_map: np.ndarray, p_grow: np.ndarray) -> np.ndarray:
    """Forest density per cell: biome base modulated by growing-season
    rain (full density at ~150+ mm/month, quarter density at 0)."""
    f = np.zeros(biome_map.shape, np.float32)
    for name, v in _FOREST_BASE.items():
        f[biome_map == BIOME_ID[name]] = v
    return np.clip(f * np.clip(p_grow / 150.0, 0.25, 1.0), 0.0, 1.0)
