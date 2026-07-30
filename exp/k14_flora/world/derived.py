"""K14 P6 — derived-products layer D0: ecology-relevant fields computed
from a K11 world dump (read-only input, via exp.artifacts).

    uv run python -m exp.k14_flora.world.derived --seed 1

Writes to exp/k14_flora/out/world/seed_NNNNNNNN/ (gitignored):
    derived.npz      the engine form (all products, delivery 1024²)
    derived.k11pack  the viewer form (unified overlay datapack)
    manifest.json    input provenance (exp.artifacts stamp+hash)

Everything here is a single-pass raster/graph op over the K11 fields —
no pipeline internals, no re-derived physics (growing season and HAND
come from K11's own products). Productivity follows biosphere addendum
B2: an ABSOLUTE constructed scale (curated per-class prior + bounded
abiotic bonus) — never rank- or percentile-normalized, so one extreme
cell can never re-anchor the rest of the world.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from exp.artifacts import require as artifact_require
from exp.artifacts import write_manifest
from exp.k11_worldgen.aquatic import AQUATIC, AQUATIC_ID
from exp.k11_worldgen.biomes import BIOMES
from exp.k11_worldgen.units import ELEV_MAX_M, alt_m, hand_m, precip_mm, \
    temp_c

HERE = Path(__file__).parent
OUT = HERE.parent / "out"          # out/seed_NNNNNNNN/ (shared with the
                                   # k14 tree json+report — one dir per
                                   # seed, derived products flat inside)

# ── waterfalls / rapids (single 4 km step drops at L0 fidelity) ─────────
RAPIDS_DROP_M = 25.0            # concentrated drop -> rapids
FALLS_DROP_M = 75.0             # gorge-grade drop -> waterfall

# ── productivity advection (semi-Lagrangian relaxation) ─────────────────
ADV_STEPS = 4                   # downstream spreading steps
ADV_RETAIN = 0.7                # fraction carried one step downstream
UPWELL_WEIGHT = 1.0             # upwelling vs plume source balance
PLUME_WEIGHT = 0.6
WIND_MIX_WEIGHT = 0.25          # mixed-layer renewal bonus at ~8 m/s
WIND_REF_MS = 8.0

# ── productivity on an absolute scale (biosphere addendum B2) ───────────
# value = prior_mix + g * F. The prior is the region's carrying capacity
# given its history (soil history folded in implicitly — the biome exists
# where it is because of it); F is the field's abiotic logic, de-ranked
# and bounded BY CONSTRUCTION (clips, exponentials, reference values —
# never rank or percentile normalization); g keeps the bonus visible
# (within-biome texture, seasonal variation) without reordering the
# biome baseline. Scale anchor: 1.0 = a good productive class; the
# reference-best (tropical moist forest) sits at 2.5 — rainforests
# out-produce the next tier by a wide margin, so the scale leaves
# headroom instead of compressing everything under 1.0.
G_TER = 0.2                   # terrestrial abiotic-bonus gain
G_MAR = 0.5                   # marine nutrient-bonus gain
G_FRESH = 0.3                 # freshwater abiotic-bonus gain
T_PLATEAU_C = 10.0            # full rate from here up — polar seas bloom
                              # hardest at 0-5 C given light, so no
                              # 25 C-optimum Eppley throttle
T_ROLLOFF_C = 20.0            # halving per this many degC below the plateau
T_ZERO_C = -2.0               # linear ramp to zero at this freezing edge
P_REF_MMYR = 1500.0           # annual precip saturating the water term
ACC_REF = 2000.0              # catchment (upstream cells) saturating deposition
HAND_REF_M = 5.0              # HAND waterlogging decay, meters
DEPTH_REF_M = 10.0            # lake-depth shading decay, meters
INSOL_W = 0.35                # open-ocean sunlight-base weight

# ── flood pulse (seasonal discharge swing -> floodplain footprint) ──────
FLOOD_SPREAD_C = 2            # channel-neighborhood rings a flood pulse
                              # reaches (8 km at 4 km anchor cells)


def _spread_max(a: np.ndarray, n: int) -> np.ndarray:
    """n-ring 8-connected neighborhood MAX (edge-clamped). One helper, two
    uses: dilating a mask (values 0/1) and spreading a halo. Deterministic,
    numpy-only. (ground.py imports this copy.)"""
    out = np.asarray(a, dtype=np.float64)
    H, W = out.shape
    for _ in range(n):
        p = np.pad(out, 1, mode="edge")
        acc = np.full((H, W), -np.inf)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                np.maximum(acc, p[1 + dy:H + 1 + dy, 1 + dx:W + 1 + dx],
                           out=acc)
        out = acc
    return out


def flood_pulse(z, sea: float) -> np.ndarray:
    """Flood-pulse footprint (H,W in [0,1]) at anchor res: how strongly the
    seasonal discharge SWING of nearby channels reworks and fertilizes
    this cell. Amplitude is the relative annual swing (max-min)/max of
    monthly discharge on channel cells — ephemeral washes and snowmelt
    rivers swing to ~1, steady equatorial rivers near 0. The amplitude
    spreads FLOOD_SPREAD_C rings and is gated by HAND waterlogging (a
    floodplain is low ground near a channel). Zero where no channel is
    near; the caller masks by domain. In arid country this doubles as
    the wadi-corridor signal: the channel and its banks are the only
    wet ground."""
    if "h_discharge_monthly" not in z or "h_river_width_monthly" not in z:
        return np.zeros(z["h_river_mask"].shape, dtype=np.float64)
    dis = z["h_discharge_monthly"].astype(np.float64)
    chan = (z["h_river_width_monthly"] > 0).any(axis=0)
    dmax = dis.max(axis=0)
    amp = np.where(chan,
                   (dmax - dis.min(axis=0)) / np.maximum(dmax, 1e-9), 0.0)
    near = _spread_max(amp, FLOOD_SPREAD_C)
    wet = np.exp(-hand_m(z["h_hand"], sea) / HAND_REF_M)
    return np.clip(near * wet, 0.0, 1.0)

# The prior tables ARE the main knob set (addendum B2 draft values, owner
# tunes). Indexed by the k11 class ids; the water "biomes" (lake/ocean)
# have no prior and stay 0.0 — they are masked out of the terrestrial
# product anyway.
_PRIOR_BIOME = {
    "tropical moist forest": 2.50,
    "tropical dry forest": 0.55,
    "tropical conifer forest": 0.60,
    "temperate broadleaf forest": 0.75,
    "temperate conifer forest": 0.65,
    "boreal taiga": 0.40,
    "tropical grassland": 0.50,
    "temperate grassland": 0.55,
    "flooded grassland": 0.65,
    "montane grassland": 0.35,
    "tundra": 0.15,
    "mediterranean scrub": 0.45,
    "desert xeric (hot)": 0.08,
    "desert xeric (cold)": 0.08,
    "mangrove": 1.00,
    "rock": 0.02,
    "ice": 0.00,
}
PRIOR_BIOME = np.array([_PRIOR_BIOME.get(b["name"], 0.0) for b in BIOMES])
MANGROVE_ID = next(i for i, b in enumerate(BIOMES)
                   if b["name"] == "mangrove")

OPEN_OCEAN_SENTINEL = -1.0    # open ocean has NO prior — sunlight-based
_PRIOR_AQUATIC = {
    "polar shelf": 0.45,
    "temperate shelf": 0.55,
    "tropical shelf": 0.50,
    "coral reef": 0.65,
    "temperate upwelling": 0.90,
    "tropical upwelling": 1.00,
    "inland sea": 0.40,
    "salt lake": 0.10,
    "large lake": 0.50,
    "polar lake": 0.20,
    "montane lake": 0.30,
    "tropical lake": 0.60,
    "temperate lake": 0.55,
    "delta": 0.70,
    "coastal river": 0.45,
    "floodplain river": 0.55,
    "upland river": 0.35,
    "polar river": 0.20,
    "montane river": 0.30,
    "xeric river": 0.25,
}
PRIOR_AQUATIC = np.array([_PRIOR_AQUATIC.get(a["name"], OPEN_OCEAN_SENTINEL)
                          for a in AQUATIC])

# ── growing season ──────────────────────────────────────────────────────
GROW_T_C = 5.0                  # months above this count (K11 convention)

# ── vents / hot springs ─────────────────────────────────────────────────
VENT_PERCENTILE = 90.0          # activity threshold for point extraction
FAULT_DECAY_CELLS = 3.0         # fault proximity decay (p_fault_dist is
                                # in CELLS, 0..~130 — not normalized)
VENT_SUPPRESS = 3               # non-max suppression radius (anchor cells)
VENT_MAX_POINTS = 40            # per kind, ranked by activity

_D8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0),
       (1, 1)]


# ── small array helpers ─────────────────────────────────────────────────


def _upsample(a: np.ndarray, factor: int) -> np.ndarray:
    """Bilinear upsample by an integer factor (numpy-only; kron reads
    blocky on continuous fields — the marine-biome lesson)."""
    H, W = a.shape
    ys = (np.arange(H * factor) + 0.5) / factor - 0.5
    xs = (np.arange(W * factor) + 0.5) / factor - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, H - 2)
    x0 = np.clip(np.floor(xs).astype(int), 0, W - 2)
    fy = np.clip(ys - y0, 0.0, 1.0)[:, None]
    fx = np.clip(xs - x0, 0.0, 1.0)[None, :]
    a00 = a[np.ix_(y0, x0)]
    a01 = a[np.ix_(y0, x0 + 1)]
    a10 = a[np.ix_(y0 + 1, x0)]
    a11 = a[np.ix_(y0 + 1, x0 + 1)]
    return (a00 * (1 - fy) * (1 - fx) + a01 * (1 - fy) * fx
            + a10 * fy * (1 - fx) + a11 * fy * fx)


def temp_response(t_c: np.ndarray) -> np.ndarray:
    """Shared cold-tolerant temperature response (addendum B2 — replaces
    the 25 C-optimum Eppley term that throttled polar summer to quarter
    speed when real polar seas bloom hardest at 0-5 C given light).
    1.0 at T_PLATEAU_C and up; a gentle 2**((T-plateau)/T_ROLLOFF_C)
    roll-off for 0 < T < plateau; a linear ramp from the 0 C value down
    to 0 at T_ZERO_C; 0 below that."""
    t = np.asarray(t_c, dtype=float)
    v0 = 2.0 ** (-T_PLATEAU_C / T_ROLLOFF_C)      # the 0 C value
    return np.where(
        t >= T_PLATEAU_C, 1.0,
        np.where(t > 0.0, 2.0 ** ((t - T_PLATEAU_C) / T_ROLLOFF_C),
                 np.clip((t - T_ZERO_C) / -T_ZERO_C, 0.0, 1.0) * v0))


def _local_maxima(a: np.ndarray, radius: int,
                  threshold: float) -> list[tuple[int, int, float]]:
    """Non-max suppression: candidates above threshold, taken in
    descending activity, each suppressing its (2r+1)² neighborhood.
    Plateau-tolerant (fault lines tie) and deterministic."""
    H, W = a.shape
    ys, xs = np.nonzero(a >= threshold)
    order = np.argsort(-a[ys, xs])
    suppressed = np.zeros((H, W), bool)
    out = []
    for i in order.tolist():
        y, x = int(ys[i]), int(xs[i])
        if suppressed[y, x]:
            continue
        out.append((y, x, float(a[y, x])))
        suppressed[max(0, y - radius):y + radius + 1,
                   max(0, x - radius):x + radius + 1] = True
    return out


def _advect(source: np.ndarray, u: np.ndarray, v: np.ndarray,
            retain: float) -> np.ndarray:
    """Semi-Lagrangian relaxation: f <- source + retain x f(back-
    trajectory), ADV_STEPS times. u/v normalized so the max speed moves
    ~1 cell per step. Deterministic, O(steps x cells)."""
    H, W = source.shape
    speed = np.hypot(u, v)
    vmax = float(speed.max())
    if vmax <= 0:
        return source.copy()
    un, vn = u / vmax, v / vmax
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    f = source.copy()
    for _ in range(ADV_STEPS):
        sy = np.clip(yy - vn, 0, H - 1.001)
        sx = np.clip(xx - un, 0, W - 1.001)
        y0, x0 = sy.astype(int), sx.astype(int)
        fy, fx = sy - y0, sx - x0
        adv = (f[y0, x0] * (1 - fy) * (1 - fx) + f[y0, x0 + 1] * (1 - fy) * fx
               + f[y0 + 1, x0] * fy * (1 - fx) + f[y0 + 1, x0 + 1] * fy * fx)
        f = source + retain * adv
    return f


# ── products ────────────────────────────────────────────────────────────


def _river_fields(z) -> tuple[np.ndarray, np.ndarray]:
    """The persisted K11 river-speed / river-ice fields (first-class in
    K11 hydrology+solar — K14 reads them, it does NOT re-derive
    hydraulics). Returns (speed (H,W) m/s, river ice (12,H,W))."""
    for k in ("h_river_speed", "c_riverice_monthly"):
        if k not in z:
            raise KeyError(
                f"{k} missing from the k11 dump — regenerate the world "
                f"(post-speed pipeline): uv run python -m "
                f"exp.k11_worldgen demo --seed N")
    return z["h_river_speed"], z["c_riverice_monthly"]


def waterfalls(z, sea: float) -> list[dict]:
    """Concentrated drops along flow_dir on river cells. At 4 km cells a
    single-step drop of 25 m+ is a real gorge/fall at L0 fidelity.
    Basin id = the terminal (outflow) cell's anchor index, found by
    path-halving over the downstream successor map."""
    alt = alt_m(z["w_elev"], sea)
    H, W = alt.shape
    fdir = z["h_flow_dir"]
    river = z["h_river_mask"]
    # terminal-basin map by path halving (terminals point to
    # themselves, so squaring the successor map converges in log2 steps)
    idx = np.arange(H * W, dtype=np.int64).reshape(H, W)
    down = np.full((H, W), -1, dtype=np.int64)
    drop = np.zeros((H, W))
    for i, (dy, dx) in enumerate(_D8):
        m = fdir == i
        ny = np.clip(np.arange(H)[:, None] + dy, 0, H - 1)
        nx = np.clip(np.arange(W)[None, :] + dx, 0, W - 1)
        down = np.where(m, idx[ny, nx], down)
        drop = np.where(m, alt - alt[ny, nx], drop)
    succ = np.where(down < 0, idx, down).ravel()
    for _ in range(17):             # 2^17 > H*W: any path fully jumped
        succ = succ[succ]
    basin = succ.reshape(H, W)
    out = []
    ys, xs = np.nonzero(river & (drop >= RAPIDS_DROP_M))
    for y, x in zip(ys.tolist(), xs.tolist()):
        out.append({"y": y, "x": x, "drop_m": round(float(drop[y, x]), 1),
                    "order": int(z["h_order"][y, x]),
                    "basin": int(basin[y, x]),
                    "kind": "waterfall" if drop[y, x] >= FALLS_DROP_M
                    else "rapids"})
    out.sort(key=lambda p: -p["drop_m"])
    return out


def _solar_fields(z) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The persisted solar/freezing fields (K11 solar.py, first-class
    since 2026-07-30 — no ad-hoc sunlight downstream). Returns
    (insolation (12,H), sea-ice (12,H,W), lake-ice (12,H,W))."""
    for k in ("c_insol_monthly", "c_seaice_monthly", "c_lakeice_monthly"):
        if k not in z:
            raise KeyError(
                f"{k} missing from the k11 dump — regenerate the world "
                f"(post-solar pipeline): uv run python -m "
                f"exp.k11_worldgen demo --seed N")
    return z["c_insol_monthly"], z["c_seaice_monthly"], \
        z["c_lakeice_monthly"]


def _plume_source(z, ocean: np.ndarray, dis_ref: float) -> np.ndarray:
    """River-plume nutrient source (H,W in [0, PLUME_WEIGHT]): discharge
    at river cells whose downstream is ocean, bounded by dis_ref. Shared
    by marine_productivity (nutrient source) and water.photic_depth_m
    (turbidity proxy)."""
    dis = z["h_discharge"]
    fdir = z["h_flow_dir"]
    H, W = dis.shape
    plume = np.zeros_like(dis)
    for i, (dy, dx) in enumerate(_D8):
        m = fdir == i
        ny = np.clip(np.arange(H)[:, None] + dy, 0, H - 1)
        nx = np.clip(np.arange(W)[None, :] + dx, 0, W - 1)
        to_ocean = np.zeros((H, W), bool)
        to_ocean[ny, nx] = ocean[ny, nx]
        plume = np.where(m & z["h_river_mask"] & to_ocean, dis, plume)
    return np.clip(plume / dis_ref, 0.0, 1.0) * PLUME_WEIGHT


def marine_productivity(z, currents: dict | None,
                        rise_mod: np.ndarray | None = None) -> np.ndarray:
    """Monthly marine productivity (12, 256²) on the absolute B2 scale:
    prior + G_MAR x bounded nutrient bonus. Open ocean has NO prior —
    it is sunlight-based (persisted insolation x sea-ice-free fraction
    x the shared temperature response); the other marine classes carry
    their PRIOR_AQUATIC baseline. Nutrient = upwelling (r_rise_m) +
    river-plume injection at mouths, advected downstream, with the
    wind-mixing multiplier (bounded 1..1.25) on the bonus only.
    RISE_REF / DIS_REF are 99th-percentile BOUNDS computed once per
    world from the data (all 12 months share them) — they pin the cap
    so a single extreme cell clips instead of re-anchoring the rest;
    they are NOT a normalization. rise_mod (B4 nutrient-return loop):
    per-cell multiplier on the upwelling part of the source, from the
    deep-routing inventory — upwellings fed by rich polar seas
    out-produce ones fed by poor ones, bounded [0.5, 1.5]."""
    insol, seaice, _ = _solar_fields(z)
    ocean = z["h_ocean_mask"] | z["h_sea_mask"]
    H, W = ocean.shape
    aq = z["w_aquatic"]
    open_ocean = aq == AQUATIC_ID["open ocean"]
    rise_ref = max(float(np.percentile(
        np.clip(z["r_rise_m"], 0.0, None)[:, ocean], 99.0)), 1e-12)
    dis_ref = max(float(np.percentile(z["h_discharge"], 99.0)), 1e-12)
    plume = _plume_source(z, ocean, dis_ref)

    sst = temp_c(z["c_T_monthly"])                  # (12, H, W)
    wscale = float(z["c_wind_scale"]) if "c_wind_scale" in z else 1.0
    wind = (np.hypot(z["c_wind_u"].mean(axis=1),
                     z["c_wind_v"].mean(axis=1)) * wscale)  # (12,128,128)
    mixing = 1.0 + WIND_MIX_WEIGHT * np.clip(wind / WIND_REF_MS, 0.0, 1.0)

    out = np.zeros((12, H, W))
    for m in range(12):
        base = np.where(open_ocean,
                        INSOL_W * insol[m][:, None] * (1.0 - seaice[m])
                        * temp_response(sst[m]),
                        np.maximum(PRIOR_AQUATIC[aq], 0.0))
        up = np.clip(z["r_rise_m"][m], 0.0, None)
        upsrc = np.clip(up / rise_ref, 0.0, 1.0) * UPWELL_WEIGHT
        if rise_mod is not None:
            upsrc = upsrc * rise_mod
        source = upsrc + plume
        if currents is not None:
            from exp.k11_worldgen.currents import velocity_field
            u, v = velocity_field(currents, m)
        else:
            u = z["r_u"]
            v = z["r_v"]
        nutrient = _advect(source, u, v, ADV_RETAIN)
        bonus = nutrient * _upsample(mixing[m], 2)
        out[m] = np.where(ocean, base + G_MAR * bonus, 0.0)
    return out


def terrestrial_productivity(z, sea: float,
                             pulse: np.ndarray | None = None) -> np.ndarray:
    """Land productivity on the absolute B2 scale: the soft-matched
    biome prior (inverse-distance over the persisted top-2 d2 fields)
    + G_TER x bounded bonuses — climate (light x warmth x water, each
    term in [0,1] by construction), deposition (catchment
    accumulation, HAND waterlogging penalty — the de-ranked old
    soil_fertility core; alluvial plains out-produce their biome
    baseline), and flood pulse (the seasonal discharge swing of
    nearby channels: snowmelt floodplains are re-fertilized every
    year, and in arid country the wash corridor is the only wet
    ground — wadi gallery effect). River cells on land get it;
    standing water is masked."""
    d1, d2 = z["w_biome_d2_1"], z["w_biome_d2_2"]
    s = d1 + d2
    # inverse-distance weights: equidistant -> 50/50, exact match -> pure
    w1 = np.where(s > 1e-12, d2 / s, 1.0)
    w2 = 1.0 - w1
    base = (w1 * PRIOR_BIOME[z["w_biome_map"]]
            + w2 * PRIOR_BIOME[z["w_biome_second"]])
    insol, _, _ = _solar_fields(z)
    light = np.clip(insol.mean(axis=0), 0.0, 1.0)[:, None]
    p_ann = precip_mm(z["c_P_monthly"]).sum(axis=0)      # mm/yr
    f_clim = (light * temp_response(temp_c(z["c_T"]))
              * np.clip(p_ann / P_REF_MMYR, 0.0, 1.0))
    f_dep = (np.clip(z["h_accumulation"] / ACC_REF, 0.0, 1.0)
             * np.exp(-hand_m(z["h_hand"], sea) / HAND_REF_M))
    if pulse is None:
        pulse = flood_pulse(z, sea)
    land = ~z["h_ocean_mask"] & ~z["h_sea_mask"] & ~z["h_lake_mask"]
    return np.where(land, base + G_TER * (f_clim + f_dep + pulse), 0.0)


def freshwater_productivity(z, sea: float) -> np.ndarray:
    """MONTHLY lake/river productivity (12,H,W) on the absolute B2 scale:
    the aquatic-class prior + G_FRESH x bounded warmth x inflow x
    shallowness, cut by that month's ice cover (persisted lake/river
    ice). The water mask is monthly too — seasonal river cells carry
    water only in their wet months (h_river_monthly); a dry month is
    flow below L0 granularity, so the product is 0 there. Mangrove
    biome cells are dual-domain (owner ruling): they keep their
    terrestrial product AND join the fresh domain every month, on the
    mangrove biome prior — their aquatic class is the ADJACENT marine
    class (often the open-ocean sentinel -> 0), which would zero them."""
    _, _, lakeice = _solar_fields(z)
    _, riverice = _river_fields(z)
    river_m = z["h_river_monthly"]                       # (12,H,W)
    mang = z["w_biome_map"] == MANGROVE_ID
    water_m = river_m | z["h_lake_mask"][None] | mang[None]
    # a fresh cell is never the open-ocean sentinel class; clip is a guard
    base = np.maximum(PRIOR_AQUATIC[z["w_aquatic"]], 0.0)
    base = np.where(mang, np.maximum(base, PRIOR_BIOME[MANGROVE_ID]), base)
    # lake/river cells sit above sea level, so the above-sea linear
    # segment of the elevation units applies to their depth
    depth_m = z["h_depth"] / (1.0 - sea) * ELEV_MAX_M
    t_m = temp_c(z["c_T_monthly"])                       # (12,H,W)
    f = (temp_response(t_m)
         * np.clip(z["h_accumulation"][None] / ACC_REF, 0.0, 1.0)
         * np.exp(-depth_m[None] / DEPTH_REF_M))
    ice = np.where(river_m, riverice, lakeice)
    return np.where(water_m, (base[None] + G_FRESH * f) * (1.0 - ice), 0.0)


def growing_season(z) -> np.ndarray:
    """Months with mean T above GROW_T_C (K11's own threshold
    convention), at anchor res."""
    t = temp_c(z["c_T_monthly"])          # (12, 256, 256)
    return (t > GROW_T_C).sum(axis=0).astype(np.float64)


def vents(z, manifest: dict) -> tuple[np.ndarray, list[dict], list[dict]]:
    """Vent field (fault activity) + point extraction: marine vents on
    active convergent/subduction faults, hot springs on land activity
    maxima. Ranked by activity, capped per kind. fault_conv is SIGNED —
    only the positive (active) half feeds the field; fault_dist is in
    cells, decayed over FAULT_DECAY_CELLS."""
    activity = (np.clip(z["p_fault_conv"], 0.0, None)
                * np.exp(-z["p_fault_dist"] / FAULT_DECAY_CELLS))
    thr = float(np.percentile(activity, VENT_PERCENTILE))
    ocean = z["h_ocean_mask"] | z["h_sea_mask"]
    pts = _local_maxima(activity, VENT_SUPPRESS, max(thr, 1e-9))
    vents_m = sorted((p for p in pts if ocean[p[0], p[1]]),
                     key=lambda p: -p[2])
    springs = sorted((p for p in pts if not ocean[p[0], p[1]]),
                     key=lambda p: -p[2])
    vp = [{"y": y, "x": x, "activity": round(a, 4), "kind": "vent"}
          for y, x, a in vents_m[:VENT_MAX_POINTS]]
    # spring kind (B4 ruling: keep + flag — the extractor treats every
    # non-ocean cell as land, so springs emerge on lakes and rivers too;
    # sublacustrine springs and thermal streams are real). No thermal
    # modeling at L0; the flag is for L1 and fauna.
    river_any = (z["h_river_monthly"].any(axis=0)
                 if "h_river_monthly" in z else z["h_river_mask"])
    sp = []
    for y, x, a in springs[:VENT_MAX_POINTS]:
        if z["h_lake_mask"][y, x]:
            kind = "sublacustrine"
        elif river_any[y, x]:
            kind = "riverine"
        else:
            kind = "terrestrial"
        sp.append({"y": y, "x": x, "activity": round(a, 4), "kind": kind})
    return activity, vp, sp


# ── assembly ────────────────────────────────────────────────────────────


class _Npz(dict):
    """dict over the npz (single open) so products read fields without
    re-opening; carries the seed dir for the currents payload."""
    _seed_dir: Path

    def __init__(self, seed_dir: Path):
        with np.load(seed_dir / "world.npz") as z:
            super().__init__((k, z[k]) for k in z.files)
        self._seed_dir = seed_dir


def load_inputs(seed: int) -> tuple[dict, dict, Path]:
    """(npz fields, world.json manifest, seed_dir) for a K11 dump."""
    seed_dir = artifact_require("k11", seed)
    z = _Npz(seed_dir)
    manifest = json.loads((seed_dir / "world.json").read_text())
    return z, manifest, seed_dir


def build(seed: int) -> dict:
    """All D0 products at delivery resolution (1024²) + point lists."""
    z, manifest, _ = load_inputs(seed)
    sea = float(manifest["sea_level"])
    factor = 4  # 256² anchor -> 1024² delivery
    # delivery-resolution masks (mask AFTER upsampling — bilinear bleed
    # across the shoreline otherwise leaks ocean products onto land)
    d_ocean = z["d_ocean_mask"] | z["d_sea_mask"]
    d_land = ~d_ocean & ~z["d_lake_mask"]
    d_fresh = z["d_lake_mask"] | z["d_river_mask"]
    d_mang = z["d_biome_map"] == MANGROVE_ID   # dual-domain (owner ruling)

    products: dict[str, np.ndarray] = {}
    points: dict[str, list] = {}

    if "d_river_speed" in z:
        # painted at delivered res along the stamped river path (k11
        # deliver): every delivered river pixel carries its edge's reach
        # speed. The old upsample of the anchor field left 82% of
        # delivered river pixels at 0 (grid misalignment).
        products["river_speed"] = np.where(
            z["d_river_mask"], z["d_river_speed"], 0.0)
    else:
        spd, _ = _river_fields(z)
        products["river_speed"] = np.where(
            z["d_river_mask"], _upsample(spd, factor), 0.0)
    points["waterfalls"] = waterfalls(z, sea)
    # snap each falls/rapids point ONTO the delivered river line: the
    # bare anchor coord x4 lands beside the meandering stamped path —
    # often in a NEIGHBORING block, since the polyline's corner cuts
    # and lake/ocean masking can keep the line out of the anchor
    # cell's own 4x4 block entirely (same misalignment class as the
    # river-speed bleed). Search a 2-block radius for the nearest
    # stamped river pixel; the anchor cell the drop was measured on is
    # kept as provenance (ay/ax) since p//factor can shift a block.
    if "d_river_mask" in z:
        drm = z["d_river_mask"]
        H2, W2 = drm.shape
        r = 3 * factor
        for p in points["waterfalls"]:
            ay, ax = p["y"], p["x"]
            p["ay"], p["ax"] = ay, ax
            cy, cx = ay * factor + (factor - 1) / 2.0, \
                ax * factor + (factor - 1) / 2.0
            y0, y1 = max(0, int(cy) - r), min(H2, int(cy) + r + 1)
            x0, x1 = max(0, int(cx) - r), min(W2, int(cx) + r + 1)
            win = drm[y0:y1, x0:x1]
            if win.any():
                ys, xs = np.nonzero(win)
                k = int(np.argmin((ys + y0 - cy) ** 2
                                  + (xs + x0 - cx) ** 2))
                p["y"], p["x"] = int(ys[k] + y0), int(xs[k] + x0)
            else:
                p["y"], p["x"] = int(cy), int(cx)
    pulse = flood_pulse(z, sea)
    vent_field, vent_pts, spring_pts = vents(z, manifest)
    currents = _currents_payload(z)
    # B4 water column, two-phase marine loop (addendum B4): snow reads
    # the PROVISIONAL marine field (local rise-strength bonus); the
    # deep-routing inventory then modifies the upwelling bonus in the
    # final pass. The provisional field is never persisted. Vent
    # dormancy shares the ground pass's K1 roll (same point list, same
    # stream) so "active" means the same thing everywhere.
    mprod_prov = marine_productivity(z, currents)
    from exp.k14_flora.world import water as _water
    from exp.k14_flora.world.ground import _vent_active
    dis_ref = max(float(np.percentile(z["h_discharge"], 99.0)), 1e-12)
    plume = _plume_source(z, z["h_ocean_mask"] | z["h_sea_mask"], dis_ref)
    wc = _water.build_column(
        z, sea, mprod_prov, plume, PLUME_WEIGHT,
        vent_pts, _vent_active(vent_pts + spring_pts, seed)[:len(vent_pts)])
    mprod = marine_productivity(z, currents, rise_mod=wc["rise_mod"])
    products["marine_productivity"] = np.stack(
        [np.where(d_ocean, _upsample(mprod[m], factor), 0.0)
         for m in range(12)])
    products["marine_productivity_ann"] = np.where(
        d_ocean, _upsample(mprod.mean(axis=0), factor), 0.0)
    # water-column products (delivery res; zone + lit are RE-DERIVED at
    # delivery from the bilinear fields — kron-stamping the anchor
    # categories leaves 255 holes on coastal cells whose anchor cell is
    # land but whose delivered cell is ocean)
    products["bathymetry_m"] = np.where(
        d_ocean, _upsample(wc["bathymetry_m"], factor), 0.0)
    products["photic_depth_m"] = np.where(
        d_ocean, _upsample(wc["photic_depth_m"], factor), 0.0)
    products["bottom_temp_c"] = np.where(
        d_ocean, _upsample(wc["bottom_temp_c"], factor), 0.0)
    d_bathy = products["bathymetry_m"]
    d_zone = np.full(d_bathy.shape, 255, np.uint8)
    for i, zn in enumerate(_water.ZONES):
        d_zone[d_ocean & (d_bathy <= zn["max_m"]) & (d_zone == 255)] = i
    products["depth_zone"] = d_zone
    products["bottom_lit"] = d_ocean & (
        d_bathy <= products["photic_depth_m"])
    products["marine_snow"] = np.stack(
        [np.where(d_ocean, _upsample(wc["marine_snow"][m], factor), 0.0)
         for m in range(12)])
    products["vent_benthos"] = np.where(
        d_ocean, _upsample(wc["vent_benthos"], factor), 0.0)
    products["benthic_food"] = np.stack(
        [np.where(d_ocean, _upsample(wc["benthic_food"][m], factor), 0.0)
         for m in range(12)])
    products["rise_mod"] = np.where(
        d_ocean, _upsample(wc["rise_mod"], factor), 0.0)
    # vent points gain depth-zone attribution (anchor coords here)
    for p in vent_pts:
        b = float(wc["bathymetry_m"][p["y"], p["x"]])
        p["depth_m"] = round(b, 1)
        if b > 0:
            p["depth_zone"] = _water.ZONES[
                int(wc["depth_zone"][p["y"], p["x"]])]["name"]
    products["terrestrial_productivity"] = np.where(
        d_land, _upsample(terrestrial_productivity(z, sea, pulse), factor),
        0.0)
    # the flood-pulse footprint itself, persisted for the viewer and for
    # downstream consumers (substrate alluvium rule reads it at anchor)
    products["flood_pulse"] = np.where(
        d_land, _upsample(pulse, factor), 0.0)
    fprod = freshwater_productivity(z, sea)              # (12, 256²)
    d_river_m = z["d_river_width_monthly"] > 0           # (12, 1024²)
    d_fresh_m = d_river_m | z["d_lake_mask"][None] | d_mang[None]
    products["freshwater_productivity"] = np.stack(
        [np.where(d_fresh_m[m], _upsample(fprod[m], factor), 0.0)
         for m in range(12)])
    products["freshwater_productivity_ann"] = np.where(
        d_fresh | d_mang,
        _upsample(fprod.mean(axis=0), factor), 0.0)
    products["growing_season"] = np.where(
        d_land, _upsample(growing_season(z), factor), 0.0)
    products["vent_field"] = _upsample(vent_field, factor)
    points["vents"] = vent_pts
    points["hot_springs"] = spring_pts

    # substrate ("ground") classification — biosphere addendum B3. Ground
    # builds its OWN volcanic evidence from the vent/spring points (most
    # vents dormant — K1 roll inside), not from the raw fault field above.
    from exp.k14_flora.world.ground import build_ground, build_ground_hires
    g = build_ground(z, manifest, sea, vent_pts + spring_pts)
    # d2 stays at ANCHOR res on purpose: 41x1024² float32 is ~170 MB/world
    # vs ~11 MB at 256². Similarity is a consume-time transform over the
    # full vector (biosphere_conv ruling), so there is nothing to upsample.
    products["ground_d2"] = g["d2"]
    # the display map is RE-DERIVED at delivery res (deliver.py rule:
    # pointwise quantities rerun at the target resolution from interpolated
    # parents) — the rule is pointwise per cell, so it reruns at 1024² from
    # bilinear-upsampled evidence instead of kron-stamping 4x4 px blocks.
    hi = build_ground_hires(z, manifest, sea, vent_pts + spring_pts, factor)
    products["ground_class"] = hi["class_id"]
    products["ground_mix_ids"] = hi["mix_ids"]
    products["ground_mix_w"] = hi["mix_w"]

    # points carry anchor coords; scale to delivery for the viewer
    # (waterfalls already snapped to the delivered river line above)
    for name, lst in points.items():
        if name == "waterfalls":
            continue
        for p in lst:
            p["y"], p["x"] = p["y"] * factor, p["x"] * factor
    return {"seed": seed, "products": products, "points": points,
            "ground_meta": g["meta"]}


def _currents_payload(z) -> dict | None:
    """The persisted currents payload for monthly velocity_field (falls
    back to the annual mean field when absent)."""
    try:
        from exp.k11_worldgen.persist import load_world
        return load_world(str(z._seed_dir))["world"]["currents"]
    except Exception:
        return None


def save(result: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_dir / "derived.npz",
                        **result["products"],
                        **{f"pts_{k}": json.dumps(v)
                           for k, v in result["points"].items()},
                        # the ground class table (names/colors/flags/props)
                        # travels as JSON, same convention as the point lists
                        ground_meta=json.dumps(result["ground_meta"]))
    write_manifest(out_dir, inputs=[("k11", result["seed"])],
                   note="k14 D0 derived products")
    from exp.k14_flora.world.datapack import build_pack
    build_pack(result, out_dir / "derived.k11pack")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out = args.out or (OUT / f"seed_{args.seed:08d}")
    result = build(args.seed)
    save(result, out)
    for name, a in result["products"].items():
        print(f"  {name}: {a.shape} mean={a.mean():.4f} "
              f"max={a.max():.4f}")
    for name, lst in result["points"].items():
        print(f"  {name}: {len(lst)} points")
    print(out)


if __name__ == "__main__":
    main()
