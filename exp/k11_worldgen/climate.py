"""K11 — climate: wind-pattern library, monthly sample lattice, seasonal
(T, P) curves, and a 2nd-order conditioning round.

Climate is chaotic and intractable — we do not simulate it. Instead: a
small library of wind patterns is precomputed
(latitude zonal base + chaotic gyres from stream-function curl +
land–sea breeze), N sample snapshots per month interpolate randomly
across the library (K1-seeded phases), and a semi-Lagrangian moisture
advection runs per snapshot on a COARSE grid (upsampled afterwards —
refinement smudges anyway). The canonical output is the 12 monthly
(T, P) mean curves per cell. Per-day states are a gameplay concern
(random-walk mix between adjacent samples — similar before the
Lyapunov horizon, divergent after) and are NOT generated here.

Couplings: mountains DEFLECT and DAMP the (low-layer) wind (air
goes around, not through); the persistent circulation is a few
bands of along-axis flow with random signs along a SEEDED
prevailing axis — any compass direction, no hardcode (outermost
prefer an equatorward meridional component — polar outflow and
equatorward trades); a HIGH layer (same bands,
stronger, no terrain, no breeze) advects the subsidence field, which
parks where the low-level flow DIVERGES and dries it where it
descends — two layers, not one, so subtropical deserts can sit beside
warm seas; moisture recharges over water (temperature-scaled), rains
out everywhere (ocean included), wrings out where air gets cold
(thermodynamic capacity), concentrates where the flow converges, and
convects where the air is hot (Hadley-cell thunderstorms);
the monsoon is driven by the ACTUAL land–sea temperature anomaly per
month (temperature is computed first and transported along the
low-layer wind — maritime moderation reaches downwind);
refine_climate() runs damped conditioning rounds — snow-albedo
feedback and evaporative/cloud cooling adjust T given P. Forest
feedback (evapotranspiration, interception, windbreak) is a
SECOND-ORDER input: pass 1 runs bare-ground, and the coarse pipeline
rerun (pass 2) supplies the real cover from the biome pass.
Memory terms: the surface follows the forcing with a thermal LAG
(circular filter, land ~1 month / ocean ~3), soil moisture is a
leaky monthly bucket felt by land recycling (spun up over the year —
both wrap December into January exactly), katabatic drainage blows
downslope off deeply frozen ground, and the high layer's band flow
returns anti-phase (Hadley closure).
Conditioning, not simulation: single rounds, no iteration to
convergence.
"""

from __future__ import annotations

import math

import numpy as np

from kernel.hashrng import Stream

from exp.k11_worldgen.raster import fbm
from exp.k11_worldgen.wind import Highway, WindModel
from exp.k11_worldgen.units import (
    ELEV_MAX_M, T_MAX_C, T_MIN_C, WIND_MEAN_OCEAN_MS, wiggle_metric)

# months are the canon time period; summer solstice at month 6
_SUMMER = 6.0

# Earth northern-hemisphere zonal-mean anchors by latitude (degN):
# annual mean surface temperature and seasonal half-swing (July minus
# annual), degC. Realistic mode interpolates these instead of using
# the invented profile; winds stay random in both modes.
_EARTH_LAT = (0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 90.0)
_EARTH_T_ANN = (26.5, 25.5, 21.0, 13.0, 2.0, -11.0, -19.0)
_EARTH_T_AMP = (1.5, 3.5, 7.0, 11.0, 14.0, 14.5, 13.0)
_KM_PER_DEG = 111.19


def resolve_center_lat(seed: int, center_lat: float | None,
                       base: float = 45.0, band: float = 5.0,
                       leak: float = 0.3) -> float:
    """Effective earth-patch center latitude.

    None -> seeded wiggle around `base`: a triangular draw in +-12 deg,
    softly compressed beyond +-`band` (LEAKY cap — slope `leak`, never
    a hard clamp): mean abs deviation ~3 deg, most worlds center in
    40..50 degN, a rare one leaks a little past. Deterministic per
    seed (own substream — does not touch the climate draws).
    """
    if center_lat is not None:
        return center_lat
    stream = Stream(seed, "k11.centerlat")
    w = sum(stream.uniform(0, i) for i in range(3)) - 1.5
    w = w / 1.5 * 12.0
    if abs(w) > band:
        w = math.copysign(band + (abs(w) - band) * leak, w)
    return base + w

# freezing point in normalized units (0 degC)
_FREEZE = (0.0 - T_MIN_C) / (T_MAX_C - T_MIN_C)


def evap_factor(T: np.ndarray) -> np.ndarray:
    """Temperature-conditioned evaporation multiplier, ~0.05 at -3 degC
    to full at +10 degC (normalized-units T): real saturation vapor
    pressure at 0 degC is ~20% of tropical values, so cold surfaces
    barely evaporate. Shared by the atmospheric moisture pass and the
    lake-salinity balance (hydrology) — one Clausius-Clapeyron curve,
    two consumers."""
    return np.clip((T - (_FREEZE - 0.05)) / 0.22, 0.05, 1.0)

# adaptive-gain DEFAULT for land-mean precipitation, normalized: real
# land averages ~65-80 mm/month (~800-1000 mm/yr) -> ~0.19 of the
# 0-400 mm units range. Not a hard pin — each world's target wiggles
# around this (seeded, leaky: see units.wiggle_metric), so worlds run
# drier and wetter but stay physical. A fixed pin floods the biome
# match — every cell reads wet-forest and grassland prototypes never
# win.
_TARGET_LAND_P = 0.19

# surface-wind obstacle threshold, meters: what BLOCKS low-level flow
# is the RISE the air must cross, not the altitude it sits at —
# Mongolia at 1500 m is windy, a 500 m escarpment makes a foehn. The
# obstacle mask is local relief of the SMOOTHED terrain: fine
# ruggedness is surface roughness (friction's job), not blocking —
# only massifs and escarpments larger than the smoothing scale count.
# Rims and range cores block; plateau interiors (however high) stay
# open and the wind hugs the escarpment into the interior.
_BLOCK_RISE_M = 500.0
_RELIEF_WINDOW = 3
_RELIEF_SMOOTH = 6

# over-the-top bleed: where terrain IS blocked, the column above
# still crosses (Froude < 1 stops the surface flow, not the free
# troposphere) and turbulent mixing drives a weaker surface wind over
# the high interior. Asymptotic in altitude (no hard cap), starting
# at _BLOCK_ALT_M, saturating at _BLEED_MAX of the high-layer flow.
_BLOCK_ALT_M = 1000.0
_BLEED_MAX = 0.5
_BLEED_SCALE_M = 800.0

# rim porosity for the ATMOSPHERIC stream solve: the sky above the
# magic rim is open — air exchanges with the world beyond the map
# more freely than water leaks through the rock (currents use 0.5).
# Weather systems enter, swirl around the terrain, and leave.
_RIM_POROSITY_AIR = 0.8


# thermal inertia: the surface follows the seasonal forcing with a
# LAG — interior land ~1 month (soil column + boundary layer), the
# ocean ~3 (mixed-layer heat capacity). Real lags shift monsoon
# timing and growing seasons; see _thermal_lag.
_LAG_TAU_LAND, _LAG_TAU_OCEAN = 1.0, 3.0

# soil-moisture memory: a leaky monthly bucket — rain in, evaporative
# demand out at the Clausius-Clapeyron rate. Recycling (land
# evapotranspiration) scales as S/(S + _SOIL_HALF) — asymptotic, no
# cap. Memory is the point: a wet April makes May moister.
_SOIL_RAIN, _SOIL_EVAP, _SOIL_HALF = 3.0, 1.0, 1.0
_SOIL_SPIN = 3





# subsidence plume decay per advection step (_subsidence): the dry
# plume a rain core sheds downstream loses this fraction of its
# strength per step — 24 steps at 0.98 leaves ~0.6 at the plume's
# end (belt-scale descent a thousand km from the rain core)
_SUB_DECAY = 0.98
# seed gain before injection: the plume dilutes along the path
# (decay + spreading), and the drying response needs strong zones,
# not a haze — cores must enter the transport saturated
_SUB_GAIN = 2.0


def _pool(a: np.ndarray, f: int) -> np.ndarray:
    """Mean-pool by integer factor f (256 -> 128 with f=2)."""
    H, W = a.shape
    return a.reshape(H // f, f, W // f, f).mean(axis=(1, 3))


def _upsample(a: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Nearest 2x upsample + one box-smooth pass (smudge)."""
    f_y, f_x = shape[0] // a.shape[0], shape[1] // a.shape[1]
    up = np.kron(a, np.ones((f_y, f_x)))
    p = np.pad(up, 1, mode="edge")
    return sum(p[dy:dy + up.shape[0], dx:dx + up.shape[1]]
               for dy in range(3) for dx in range(3)) / 9.0


def _bilinear(field: np.ndarray, bx: np.ndarray, by: np.ndarray) -> np.ndarray:
    """Sample field at float coordinates (clipped to the grid). One
    leading axis is an independent batch (per-batch gather, identical
    values and arithmetic as the 2D path)."""
    H, W = field.shape[-2:]
    bx = np.clip(bx, 0.0, W - 1.001)
    by = np.clip(by, 0.0, H - 1.001)
    x0, y0 = bx.astype(int), by.astype(int)
    fx, fy = bx - x0, by - y0
    if field.ndim == 2:
        return (field[y0, x0] * (1 - fx) * (1 - fy)
                + field[y0, x0 + 1] * fx * (1 - fy)
                + field[y0 + 1, x0] * (1 - fx) * fy
                + field[y0 + 1, x0 + 1] * fx * fy)
    K = field.shape[0]
    out = np.empty_like(field)
    for k in range(K):
        # per-snapshot 2D fancy indexing — the fastest gather numpy
        # has (2.3x any batched-gather form), and bitwise the
        # original arithmetic
        fk, bxk, byk = field[k], bx[k], by[k]
        xk, yk = x0[k], y0[k]
        fxk, fyk = fx[k], fy[k]
        out[k] = (fk[yk, xk] * (1 - fxk) * (1 - fyk)
                  + fk[yk, xk + 1] * fxk * (1 - fyk)
                  + fk[yk + 1, xk] * (1 - fxk) * fyk
                  + fk[yk + 1, xk + 1] * fxk * fyk)
    return out


def _grad(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Central-difference gradients (zeros at the border), over the
    last two axes — leading axes are an independent batch."""
    gx = np.zeros_like(a)
    gy = np.zeros_like(a)
    gx[..., 1:-1] = (a[..., 2:] - a[..., :-2]) / 2
    gy[..., 1:-1, :] = (a[..., 2:, :] - a[..., :-2, :]) / 2
    return gx, gy


def _subsidence(u: np.ndarray, v: np.ndarray, band: np.ndarray,
                steps: int = 24) -> np.ndarray:
    """Subsiding (drying) air aloft, advected on the high-layer wind.

    The seed band sheds dry plumes DOWNSTREAM: pure advect-and-
    decay, no band recharge — the source core keeps only what
    upstream cores feed it (wet stays wet), while the spent air
    descends over the cells the high layer carries it to (desert
    forms BESIDE the source). And it CONCENTRATES where the upper
    flow converges: descent is convergence aloft, so plume strength
    accumulates in convergence zones (belt cores saturate,
    divergence zones bleed to zero) instead of diluting uniformly
    along the path. Returns S in [0, 1]: 1 = full subtropical-high
    suppression.

    float32 working precision (see _poisson_sor). u/v may carry a
    leading batch axis (independent snapshots in one call — identical
    arithmetic per snapshot)."""
    u = np.asarray(u, dtype=np.float32)
    v = np.asarray(v, dtype=np.float32)
    band = np.asarray(band, dtype=np.float32)
    H, W = u.shape[-2:]
    gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
    conv = np.maximum(-(_grad(u)[0] + _grad(v)[1]), 0.0)
    S = np.broadcast_to(np.clip(_SUB_GAIN * band, 0.0, 1.0),
                        u.shape).copy()
    for _ in range(steps):
        S = _bilinear(S, gx - u, gy - v)
        S = np.clip(_SUB_DECAY * S * (1.0 + conv), 0.0, 1.0)
    return S


def _box3(a: np.ndarray, passes: int = 1) -> np.ndarray:
    """3x3 box smoothing, edge-padded, `passes` times."""
    for _ in range(passes):
        p = np.pad(a, 1, mode="edge")
        a = (sum(p[dy:dy + a.shape[0], dx:dx + a.shape[1]]
                 for dy in range(3) for dx in range(3)) / 9.0)
    return a


# convection: hot moist air rains regardless of the flow — the
# Hadley-cell thunderstorm budget the wind-driven terms miss. Scales
# with heat (same Clausius-Clapeyron curve as evaporation): the deep
# tropics rain year-round, mid-latitudes only in summer, polar never.
_CONV_T0 = _FREEZE + 0.25      # ~20 degC: convection kicks in
_CONV_TSPAN = 0.125            # full strength ~10 degC hotter
_CONV_RAIN = 0.15              # rate budget, vs 0.03 baseline

# ascent rain: convergent (ascending) flow rains at up to this rate
# — the vertical-motion field's direct wet/dry signature (ascent =
# wet). _ASCENT_DIV is the divergence of a strong convergence core
# in the field's units
_ASCENT_RAIN, _ASCENT_DIV = 0.15, 0.2

# foehn: descending air warms at the DRY adiabat (steeper than the
# moist one the windward climb followed), so lee air arrives
# undersaturated — rain is ACTIVELY suppressed on descent, not merely
# absent from depletion. Same u.grad(h) units as the orographic lift
# rate (descent dries harder than lift wets — the dry adiabat is
# steeper); _FOEHN_FLOOR keeps a drizzle floor
_FOEHN_DRY = 6.0
_FOEHN_FLOOR = 0.2
# foehn warming of the air itself in the temperature transport (lee
# side runs warmer at the same altitude)
_FOEHN_WARM = 0.4


def _advect(u: np.ndarray, v: np.ndarray, h: np.ndarray, water: np.ndarray,
            lake_src: np.ndarray, T: np.ndarray,
            green: np.ndarray | None = None,
            sub: np.ndarray | None = None, steps: int = 24,
            soil: np.ndarray | None = None) -> np.ndarray:
    """Semi-Lagrangian moisture advection along a wind field.

    Parcels backtrace along the wind, inherit moisture, recharge over
    water (strong) and lakes/wide rivers (weak), precipitate on
    orographic lift (wind . grad h), recycle over land. Recharge scales
    with the water's temperature — evaporation collapses as water nears
    freezing (Clausius–Clapeyron), so polar seas barely moisturize the
    air while tropical ones recharge at full rate. `sub` is the
    high-layer subsidence field (0..1): descending dry air aloft
    suppresses BOTH recharge and rain-out, so cells under a subtropical
    high stay dry even beside warm seas. `green` is a
    0..1 forest-cover field (pass 2 feedback): forests
    evapotranspire (multiplying the recycling rate — moisture delivered
    into the airflow) but also INTERCEPT — canopy re-evaporation lowers
    the local rain-out rate, so forested cells rain a little less and
    somewhere downwind rains a little more. Returns mean precipitation
    rate per cell over the advection.

    float32 working precision (bandwidth-bound — see _poisson_sor).
    u/v may carry a leading batch axis (independent snapshots in one
    call — identical arithmetic per snapshot)."""
    u = np.asarray(u, dtype=np.float32)
    v = np.asarray(v, dtype=np.float32)
    h = np.asarray(h, dtype=np.float32)
    T = np.asarray(T, dtype=np.float32)
    if green is not None:
        green = np.asarray(green, dtype=np.float32)
    if sub is not None:
        sub = np.asarray(sub, dtype=np.float32)
    if soil is not None:
        soil = np.asarray(soil, dtype=np.float32)
    H, W = h.shape
    gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
    dhx, dhy = _grad(h)
    oro = np.maximum(0.0, u * dhx + v * dhy)
    sink = np.maximum(0.0, -(u * dhx + v * dhy))   # descent: foehn
    # land recycling (evapotranspiration): moist regions re-water
    # their own air — the Amazon mechanism. This is what keeps a
    # wet season's rain falling (weaker) into the dry season:
    # charged soil keeps feeding the airflow after the oceanic
    # supply reverses. Dry soil gates it off (deserts stay dry)
    recycle = 0.30 if green is None else 0.30 + 0.25 * green
    if soil is not None:
        # recycling drinks from the soil bucket: wet ground feeds the
        # airflow, dry ground doesn't (S/(S+half) — asymptotic, no
        # hard cap). Memory: last month's rain is this month's
        # evapotranspiration
        recycle = recycle * soil / (soil + _SOIL_HALF)
    intercept = 1.0 if green is None else 1.0 - 0.3 * green
    evap = evap_factor(T)
    # bounded compressibility: convergent flow (trades piling into the
    # hot zone, flow crammed against a range) CONCENTRATES moisture
    # instead of just resampling it; divergent flow dilutes. Clipped so
    # a strong convergence spike cannot blow the budget up — this is a
    # correction, not a continuity equation.
    du_dx = _grad(u)[0]
    dv_dy = _grad(v)[1]
    conv = np.clip(1.0 - 1.5 * (du_dx + dv_dy), 0.6, 1.8)
    # a subsidence plume cannot stack over ACTIVE ASCENT: where the
    # low-level flow converges, the column is rising and the high's
    # downwelling is displaced (ITCZ vs subtropical highs — never the
    # same column). Without this exclusion the advected plumes park
    # on the hot convergence belt and sterilize the wet tropics.
    ascent = np.clip(-(du_dx + dv_dy) / _ASCENT_DIV, 0.0, 1.0)
    # subsidence suppression factors (1 = no high overhead)
    wet = np.ones(u.shape)
    dry = np.ones(u.shape)
    if sub is not None:
        sub = sub * (1.0 - ascent)
        wet = 1.0 - 0.65 * sub
        dry = 1.0 - 0.75 * sub

    M = np.full(u.shape, 0.85)
    P = np.zeros(u.shape)
    for _ in range(steps):
        M = _bilinear(M, gx - u, gy - v)
        M = M * conv
        M = np.where(water, np.minimum(1.0, M + 0.30 * evap * wet * (1.0 - M)), M)
        M = np.where(lake_src & ~water, np.minimum(1.0, M + 0.10 * evap * wet * (1.0 - M)), M)
        # thermodynamic capacity: cold air holds little moisture (same
        # Clausius–Clapeyron curve as evaporation), so advected moisture
        # WRINGS OUT on entering cold cells — polar-front snow — and
        # cold interiors then stay dry instead of raining freely off
        # imported moisture
        excess = np.maximum(M - evap, 0.0)
        P += excess
        M = M - excess
        # rain-out happens over water too (most real rain falls on the
        # ocean): a LOW baseline everywhere; ascent rain where the
        # flow CONVERGES (cyclonic lift — the gyre cells' wet/dry
        # signature; the baseline alone would rain uniformly and
        # level the map); orographic lift adds over
        # land (h is flat over water, so oro ~ 0 there); convection
        # adds where the air is hot; descent SUPPRESSES (foehn — the
        # lee is dried by warming, not just by upstream depletion).
        # Genuinely depleted air barely rains (lee deserts stay dry)
        rate = np.clip(0.03
                       + _ASCENT_RAIN * np.clip(-(du_dx + dv_dy)
                                                / _ASCENT_DIV, 0.0, 1.0)
                       + 3.0 * oro
                       + _CONV_RAIN * np.clip((T - _CONV_T0) / _CONV_TSPAN,
                                              0.0, 1.0),
                       0.0, 0.9) * intercept * dry
        rate = rate * np.clip(1.0 - _FOEHN_DRY * sink, _FOEHN_FLOOR, 1.0)
        p = M * rate
        P += p
        # rain depletes the parcel EVERYWHERE (water included — ocean
        # rain wrings the flow before landfall); recycling is the land
        # evapotranspiration feedback, proportional to the moisture
        # already present — wet stays wet, rain-shadow deserts stay dry
        # (a uniform +const recovery erased shadows in ~10 steps)
        M = np.clip(M - 0.30 * p
                    + np.where(water | lake_src, 0.0, recycle * M * (1.0 - p)),
                    0.02, 1.0)
    return P / steps


def _thermal_lag(T_m: np.ndarray, water_c: np.ndarray) -> np.ndarray:
    """Thermal inertia as a CIRCULAR exponential filter over the year:
    the surface follows the seasonal forcing with a lag (_LAG_TAU_*
    months, land vs ocean). Relaxation x_m = a*x_{m-1} + (1-a)*eq_m
    over a periodic eq has a closed-form periodic steady state — a
    circular convolution — so December wraps into January exactly and
    there is no spin-up bias. Real lags shift monsoon timing and
    growing seasons and damp the swing (ocean more than land)."""
    a = np.where(water_c, math.exp(-1.0 / _LAG_TAU_OCEAN),
                 math.exp(-1.0 / _LAG_TAU_LAND))
    out = np.zeros_like(T_m)
    for k in range(12):
        out = out + ((1.0 - a) * a ** k)[None] * np.roll(T_m, k, axis=0)
    return out / (1.0 - a ** 12)[None]


def _soil_schedule(P_m: np.ndarray, T_m: np.ndarray) -> np.ndarray:
    """Monthly soil-moisture schedule, (12, ch, cw): a leaky bucket —
    rain in, evaporative demand out at the Clausius-Clapeyron rate
    (the linear decay can never take S negative). Spun up _SOIL_SPIN
    times over the year from the annual-mean state so the December
    bucket feeds January (the year is a loop, no cold start), then
    recorded once more around the loop."""
    evap_m = evap_factor(T_m)
    S = (_SOIL_RAIN * P_m.mean(axis=0)
         / np.maximum(_SOIL_EVAP * evap_m.mean(axis=0), 0.05))

    def step(S, m):
        return S + _SOIL_RAIN * P_m[m] - _SOIL_EVAP * evap_m[m] * S

    for _ in range(_SOIL_SPIN):
        for m in range(12):
            S = step(S, m)
    out = np.zeros_like(P_m)
    for m in range(12):
        S = step(S, m)
        out[m] = S
    return out


def _wind_ensemble(model: WindModel, highway: Highway, stream: Stream,
                   T_eq_m: np.ndarray, n_samples: int
                   ) -> dict[str, np.ndarray]:
    """The weather pattern: ONE continuous trajectory of the
    two-layer fluid through the year, forced by the equilibrium
    temperature ANOMALY (hot = low — heat lows, monsoon inflow and
    terrain blocking emerge; see exp/k11_worldgen/wind.py). The
    (12, n_samples) surface snapshots ARE the delivered weather
    pattern (gameplay walks between adjacent snapshots of a month) —
    the same ensemble drives the temperature transport and both
    precipitation passes, so those passes differ only in the water
    cycle, never in the wind. The high layer (the non-interacting
    highway) is sampled alongside for the subsidence transport."""
    ch, cw = model.shape
    T_ann = T_eq_m.mean(axis=0)
    out = {k: np.zeros((12, n_samples, ch, cw), dtype=np.float32)
           for k in ("u_s", "v_s", "u_h", "v_h", "D")}
    for m in range(12):
        anom = T_eq_m[m] - T_ann
        for j in range(n_samples):
            clock = 1000 + m * 16 + j
            snap = model.snapshot(stream, clock, anom)
            out["u_s"][m, j] = snap["u_s"]
            out["v_s"][m, j] = snap["v_s"]
            out["D"][m, j] = snap["D"]
            uh, vh = highway.sample(stream, clock)
            out["u_h"][m, j] = uh
            out["v_h"][m, j] = vh
    return out


def _precip_pass(ens: dict[str, np.ndarray], T_m: np.ndarray,
                 land_c: np.ndarray, water_c: np.ndarray, lake_c: np.ndarray,
                 h_c: np.ndarray, n_samples: int,
                 green: np.ndarray | None = None,
                 soil_m: np.ndarray | None = None
                 ) -> tuple[np.ndarray, np.ndarray]:
    """One monthly precipitation pass against a SIMULATED wind
    ensemble (see _wind_ensemble): moisture advected per snapshot on
    the coarse grid. The subsidence seed is the snapshot's own
    vertical-motion field — where the middle layer converges, spent
    air descends into the surface column (emergent subtropical
    highs), then rides the high-layer highway downstream. Returns RAW
    rates plus the monthly-mean subsidence fields."""
    ch, cw = h_c.shape
    P_m = np.zeros((12, ch, cw))
    sub_m = np.zeros((12, ch, cw))
    for m in range(12):
        # subsidence seed: the descent (D > 0) half of the vertical
        # motion, but only its ANOMALY above mean + 1 std — the broad
        # seasonal descent blanket dries nothing (the gain pin just
        # absorbs it), the descent CORES are what park as subtropical
        # highs. One light box pass against speckle, p90-normalized
        # (adaptive — the fluid's D scale varies with world/season)
        seeds = []
        for j in range(n_samples):
            D = ens["D"][m, j]
            a = _box3(np.clip(
                D - (float(D.mean()) + float(D.std())), 0.0, None), 1)
            pos = a[a > 0.0]
            scale = float(np.percentile(pos, 90.0)) if pos.size else 1.0
            seeds.append(np.clip(a / max(scale, 1e-9), 0.0, 1.0))
        sub = _subsidence(ens["u_h"][m], ens["v_h"][m], np.stack(seeds))
        P_b = _advect(ens["u_s"][m], ens["v_s"][m], h_c, water_c,
                      lake_c, T_m[m], green=green, sub=sub,
                      soil=None if soil_m is None else soil_m[m])
        P_m[m] = sum(P_b) / n_samples
        # monthly-mean subsidence field is delivered too: the drying
        # pattern (where the spent air descends) is part of the
        # weather pattern the ecology layers read
        sub_m[m] = sub.mean(axis=0)
    return P_m, sub_m


def _coarse_grids(elev: np.ndarray, hydro: dict, sea_level: float,
                  f: int) -> tuple[np.ndarray, np.ndarray, np.ndarray,
                                   np.ndarray]:
    """Coarse terrain + masks shared by build_climate and the mean-wind
    estimate (identical computation — the wind library must see the
    same geometry in both)."""
    # moving air sees the water surface only where standing water
    # actually exists. w is the priority-flood FILL level (outlet-sill
    # height) for every basin, including underfed ones that hold no
    # lake — using it everywhere would show climate a phantom flood
    # surface over dry basins and wetland flats.
    h_clim = elev.copy()
    h_clim[hydro["lake_mask"]] = np.maximum(elev, hydro["w"])[hydro["lake_mask"]]
    h_clim[hydro["ocean_mask"]] = sea_level
    h_c = _pool(h_clim, f)
    water_c = _pool(hydro["ocean_mask"].astype(float), f) > 0.5
    land_c = ~water_c
    # altitude may go negative: below-sea basins (dry depressions exist
    # since ocean is border-connected) are HOT in reality — the lapse
    # term then warms instead of cools (bounded at -0.3 ≈ -1800 m).
    alt_c = np.clip((h_c - sea_level) / (1.0 - sea_level), -0.3, 1.0)
    return h_c, water_c, land_c, alt_c


# temperature advection: semi-Lagrangian transport of the equilibrium
# field along the snapshot wind with relaxation back to equilibrium.
# A single 0.3-weighted backtrace step moderates only ~1-2 coarse
# cells (~10 km) of coastline; a 10-step run smears the ocean's coolth
# so far inland that poleward continents lose their summer entirely
# (ice cap eats the taiga belt). 4 steps at 0.35 reaches ~30-60 km
# downwind and leaves continental interiors their seasons.
_T_ADV_STEPS, _T_ADV_RELAX = 4, 0.35


def _scale_precip(P_raw: np.ndarray, gain: float, belt: np.ndarray) -> np.ndarray:
    """Raw advection rates -> normalized precipitation: adaptive gain
    (per world, deterministic) + the subtropical aridity belt (the dry
    belt makes deserts actually appear)."""
    return np.clip(P_raw * gain, 0.0, 1.0) * belt


def refine_climate(T_m: np.ndarray, P_m: np.ndarray, T_lat: np.ndarray,
                   green: np.ndarray | None = None,
                   relaxation: float = 0.7) -> np.ndarray:
    """2nd-order conditioning round: recalculate T
    conditioned on P, snow cover, and vegetation, taking the one-pass
    output as the prior. Single DAMPED round — conditioning, not
    simulation; never iterated to convergence (feedback runaway is
    bounded by the relaxation factor and the small coefficients).

    - snow-albedo feedback: sub-zero months carry snow; snow cools,
      more under stronger sun (equatorward, proxied by T_lat)
    - evaporative/cloud cooling: wet months are cooler
    - vegetation (when `green` is supplied — the second-order rerun):
      canopy MASKS snow (a boreal forest floor under snow is dark, so
      forests lose less heat to the snow-albedo feedback than open
      tundra) and transpiration cools the warm months (the same water
      cycle the precipitation pass sees, from the temperature side)
    - cloud swing damping: wet cells have their seasonal swing shrunk
      toward their own annual mean (maritime character)
    """
    snow = T_m < _FREEZE
    sun = 0.4 + 0.6 * T_lat                      # stronger sun equatorward
    d_alb = 0.10 * snow * sun[None, :, :]
    d_veg = 0.0
    if green is not None:
        d_alb = d_alb * (1.0 - 0.5 * green[None])
        d_veg = (0.04 * green[None]
                 * np.clip((T_m - _FREEZE) / 0.2, 0.0, 1.0))
    d_evap = 0.03 * P_m
    T_ref = T_m - relaxation * (d_alb + d_evap + d_veg)
    T_ann = T_ref.mean(axis=0)
    T_ref = T_ann[None] + (T_ref - T_ann[None]) * (1.0 - 0.15 * P_m)
    return np.clip(T_ref, 0.0, 1.0)


def _lat_profile(lat: np.ndarray, shape_km: float,
                 t_north: float, t_span: float, t_pow: float,
                 t_amp: float, realistic: bool = False,
                 center_lat: float = 40.0, shrink: float = 4.0
                 ) -> tuple[np.ndarray, np.ndarray]:
    """(T_lat, T_amp_lat) normalized base profile fields.

    lat is the grid row fraction (0 = north rim, 1 = south rim).

    INVENTED mode: T_lat = t_north + t_span * lat**t_pow with an
    equatorial soft-cap (the wide flat hot zone the tropics live in),
    swing peaking at mid-latitudes and minimal at both rims.

    REALISTIC mode: the grid is a patch of the real Earth's northern
    hemisphere. Row -> latitude via `center_lat` and a planet `shrink`
    times smaller (span = shape_km * shrink / 111.19 deg), then the
    zonal-mean anchors above give annual mean and seasonal half-swing.
    Default center 45 degN at shrink 4 spans ~27..63 degN:
    subtropics -> temperate -> taiga -> tundra in one map.
    """
    if realistic:
        span_deg = shape_km * shrink / _KM_PER_DEG
        lat_deg = np.clip(center_lat + (0.5 - lat) * span_deg, 0.0, 90.0)
        t_ann = np.interp(lat_deg, _EARTH_LAT, _EARTH_T_ANN)
        t_amp_lat = np.interp(lat_deg, _EARTH_LAT, _EARTH_T_AMP)
        return ((t_ann - T_MIN_C) / (T_MAX_C - T_MIN_C),
                t_amp_lat / (T_MAX_C - T_MIN_C))
    ramp = lat ** t_pow
    f_cap = 0.88
    T_lat = t_north + t_span * ramp * (
        f_cap ** 8 / (f_cap ** 8 + ramp ** 8)) ** 0.125
    T_amp_lat = 0.03 + t_amp * np.sin(math.pi * lat)
    return T_lat, T_amp_lat

def build_climate(elev: np.ndarray, hydro: dict, sea_level: float,
                  seed: int = 0, coarse: int = 128,
                  n_samples: int = 8,
                  t_north: float = 0.06, t_span: float = 0.93,
                  t_pow: float = 0.40, t_amp: float = 0.12,
                  realistic: bool = False, center_lat: float | None = None,
                  shrink: float = 4.0, cell_km: float = 4.0,
                  currents: dict | None = None,
                  green: np.ndarray | None = None,
                  gain: float | None = None) -> dict:
    """Seasonal climate as 12 monthly (T, P) mean curves per cell, plus
    the per-month wind snapshots those means average over (`wind_u` /
    `wind_v`, (12, n_samples) coarse-grid fields — the delivered
    weather pattern, persisted with the world).

    Equilibrium temperature first (it is wind-independent), then ONE
    wind trajectory through the year (the two-layer fluid in
    exp/k11_worldgen/wind.py, forced by the equilibrium anomaly), the
    temperature transported along it, then TWO precipitation passes
    (bare, then soil-corrected) against that same ensemble; a
    conditioning round (refine_climate) adjusts T given P.
    `green` is the 0..1 forest cover the water cycle should feel
    (evapotranspiration recycling, canopy interception, windbreak) —
    None means bare ground. Forests are a SECOND-ORDER input: they
    only exist after the biome pass, so an honest pipeline runs this
    bare in pass 1 and with the real cover in the coarse rerun (pass
    2). Never fabricate a cover inside climate. Monthly means
    upsampled to the world grid. Deterministic from `seed` (K1 draws
    are pure hash lookups, so reruns replay identical wind randomness
    — same weather systems, new surface conditions).

    Temperature profile knobs (generation-side variation — never tune
    units or the classifier): invented mode T_lat = t_north +
    t_span * lat**t_pow (lat 0 = north rim), T_amp_lat = 0.03 +
    t_amp * sin(pi * lat). REALISTIC mode (earth patch, northern
    hemisphere) replaces the profile with the zonal-mean Earth anchors
    — see _lat_profile; the invented knobs are then inert.
    """
    H, W = elev.shape
    f = max(1, H // coarse)
    ch, cw = H // f, W // f
    stream = Stream(seed, "k11.climate")

    h_c, water_c, land_c, alt_c = _coarse_grids(elev, hydro, sea_level, f)
    lake_c = _pool((hydro["lake_mask"] | (hydro["width"] >= 2)).astype(float), f) > 0.3

    gy, gx = np.mgrid[0:ch, 0:cw]
    gy = gy.astype(float)
    gx = gx.astype(float)
    lat = gy / (ch - 1)                            # 0 north → 1 south
    # equatorial plateau (invented mode): the profile rises through the
    # mid-latitudes then SOFT-CAPS (soft-min at f_cap) — the hot zone
    # flattens around 26-28 degC across the equatorward quarter instead
    # of climbing to a 35 degC rim (no real place averages 35 degC; the
    # wide flat hot zone is where the tropics live). Mid-latitudes are
    # untouched by construction (t_span compensates the small cap
    # suppression there). Seasonal swing peaks at MID-LATITUDES and is
    # minimal at both rims: the north stays frozen year-round, the
    # southern tropics stay warm year-round (real equatorial swing is a
    # few degC — and the swing drives the monsoon reversal, so an
    # oversized equatorial swing kills year-round rain at the rim).
    # Land contrast is part of the swing and scales with it, not a
    # fixed extra. Realistic mode swaps all of this for the Earth
    # zonal-mean anchors (see _lat_profile).
    T_lat, T_amp_lat = _lat_profile(
        lat, H * cell_km, t_north, t_span, t_pow, t_amp,
        realistic=realistic,
        center_lat=resolve_center_lat(seed, center_lat), shrink=shrink)

    # ocean currents: the sea surface runs its OWN temperature — the
    # latitude baseline ADVECTED along the gyre streams (warm pools,
    # cold upwelling tongues), monthly: the baseline carries the
    # (damped, maritime) seasonal swing and each gyre's strength
    # breathes with its own seasonal phase, so the swirls visibly
    # shift over the year. Pooled to the coarse grid; the raw latitude
    # profile then governs land only.
    sst_m = None
    if currents is not None:
        from exp.k11_worldgen.currents import advect_sst, velocity_field
        lat_a = (np.arange(H)[:, None] / (H - 1)) * np.ones((H, W))
        T_lat_a, T_amp_a = _lat_profile(
            lat_a, H * cell_km, t_north, t_span, t_pow, t_amp,
            realistic=realistic,
            center_lat=resolve_center_lat(seed, center_lat), shrink=shrink)
        span_c = T_MAX_C - T_MIN_C
        base_c = T_lat_a * span_c + T_MIN_C
        amp_c = T_amp_a * span_c * 0.5          # ocean swing, damped
        sst_m = np.zeros((12, ch, cw))
        for m in range(12):
            seasonal = math.cos(2 * math.pi * (m - _SUMMER) / 12)
            um, vm = velocity_field(currents, m)
            sst_m[m] = (_pool(advect_sst(base_c + amp_c * seasonal,
                                         um, vm, currents["rise"]), f)
                        - T_MIN_C) / span_c

    # equilibrium temperature (wind-independent): the latitude
    # profile + seasonal swing + land contrast + altitude lapse, the
    # sea on its own advected temperature. The fluid is FORCED by this
    # field's anomaly; the delivered temperature is then this
    # equilibrium transported along the simulated wind (below)
    T_eq_m = np.zeros((12, ch, cw))
    for m in range(12):
        seasonal = math.cos(2 * math.pi * (m - _SUMMER) / 12)
        T_eq = (T_lat + T_amp_lat * seasonal
                + land_c * 0.30 * T_amp_lat * seasonal
                - 0.45 * alt_c)
        if sst_m is not None:
            # the sea runs its own temperature (advected by the gyre
            # streams, monthly — swirls breathe seasonally)
            T_eq = np.where(water_c, sst_m[m], T_eq)
        T_eq_m[m] = T_eq

    # the weather pattern: a two-layer rigid-lid fluid (surface +
    # mass-compensating middle layer, see exp/k11_worldgen/wind.py)
    # forced by the equilibrium-temperature anomaly — heat lows,
    # monsoon inflow, terrain blocking and forests-as-windbreaks all
    # emerge from the momentum equation, nothing is prescribed but
    # the seeded prevailing drive and Coriolis sign. ONE trajectory
    # through the year: the same ensemble drives the temperature
    # transport and both precipitation passes
    if green is not None and green.shape != (ch, cw):
        green = _pool(green, f)
    d_ang = 2.0 * math.pi * stream.uniform(0, 70)
    d_mag = 0.012 + 0.008 * stream.uniform(0, 71)
    model = WindModel(stream, h_c, water_c, green=green,
                      drive=(d_mag * math.cos(d_ang),
                             d_mag * math.sin(d_ang)))
    highway = Highway(stream, (ch, cw))
    ens = _wind_ensemble(model, highway, stream, T_eq_m, n_samples)

    # temperature: each snapshot's equilibrium field is transported
    # along its wind — wind circulates heat (maritime moderation
    # reaches downwind, interiors keep their extremes). One damped
    # transport per snapshot, conditioning not simulation.
    dhx_c, dhy_c = _grad(h_c)
    dhx_c32 = dhx_c.astype(np.float32)
    dhy_c32 = dhy_c.astype(np.float32)
    gx32 = gx.astype(np.float32)
    gy32 = gy.astype(np.float32)
    T_m = np.zeros((12, ch, cw))
    for m in range(12):
        T_eqs = []
        for j in range(n_samples):
            clock = 1000 + m * 16 + j
            jitter = 0.04 * (stream.uniform(clock, 15) - 0.5)
            T_eqs.append(T_eq_m[m] + jitter)
        # the month's snapshots transport as one batch (independent
        # fields stacked — identical arithmetic, one Python loop).
        # float32 working precision
        TE = np.stack(T_eqs).astype(np.float32)
        U = ens["u_s"][m]
        V = ens["v_s"][m]
        T = TE.copy()
        for _ in range(_T_ADV_STEPS):
            T = _bilinear(T, gx32 - U, gy32 - V)
            T = T + _T_ADV_RELAX * (TE - T)
        # foehn warming: air descending a lee slope heats at the
        # dry adiabat, so the lee runs warmer than the windward at
        # the same altitude (also feeds moisture capacity below)
        T = T + _FOEHN_WARM * np.maximum(
            0.0, -(U * dhx_c32 + V * dhy_c32)).astype(np.float32)
        # Python-sum keeps the accumulation order of the old loop
        T_m[m] = sum(np.clip(T, 0.0, 1.0)) / n_samples

    # thermal inertia: the surface follows the forcing with a LAG —
    # circular filter, the year wraps exactly (see _thermal_lag)
    T_m = _thermal_lag(T_m, water_c)

    # ONE precipitation pass. `green` (forest cover, second-order
    # input — see the docstring) joins the water cycle here:
    # evapotranspiration recycling, canopy interception, windbreak.
    # The advection's absolute scale is free, so the gain is ADAPTIVE
    # per world: pin the land-mean rain AFTER the aridity belt
    # (deterministic) — the mm the classifier reads via units then
    # means the same thing in every world, instead of hand-chasing a
    # fixed gain per layout. A caller-supplied `gain` is used as-is:
    # the second-order rerun takes the pass-1 gain so feedback
    # (forest recycling, new water) shows as a real delta instead of
    # being normalized away by a fresh pin.
    P_raw, _ = _precip_pass(
        ens, T_m, land_c, water_c, lake_c, h_c, n_samples, green=green)
    # no static aridity belt: the dry structure comes entirely from the
    # advected subsidence (which parks at the flow's divergence zones);
    # the belt multiplier stays only as the gain-pin interface
    belt = np.ones_like(lat)
    if gain is None:
        # the world's wetness: seeded wiggle around the Earth-like
        # default (_TARGET_LAND_P — leaky, not a hard pin; pass 2
        # reuses this gain, so the wiggle is drawn once)
        target_p = wiggle_metric(Stream(seed, "k11.pgain"),
                                 _TARGET_LAND_P, 0.05, 0.03)
        land_mean = float((P_raw * belt[None])[:, land_c].mean()) if land_c.any() else 0.0
        gain = float(np.clip(target_p / max(land_mean, 1e-6), 2.0, 24.0))
        P_m = _scale_precip(P_raw, gain, belt)
        # corrective step: heavy-tailed cells (windward spikes) saturate
        # the [0, 1] clip in _scale_precip, which drags the REALIZED
        # land mean below the target; rescale once so it holds
        realized = float(P_m[:, land_c].mean()) if land_c.any() else 0.0
        if realized > 1e-6:
            gain = float(np.clip(gain * target_p / realized, 2.0, 24.0))
    P_m = _scale_precip(P_raw, gain, belt)
    # soil-moisture memory: spin the bucket over the year from this
    # first P (see _soil_schedule), then ONE corrective precip pass
    # with the soil felt in the recycling. Same ensemble, so the
    # delivered wind snapshots are identical between the two passes —
    # only the water cycle shifts. The pinned gain is reused
    # (feedback shows as a real delta, same philosophy as `green`).
    soil_m = _soil_schedule(P_m, T_m)
    P_raw, sub_m = _precip_pass(
        ens, T_m, land_c, water_c, lake_c, h_c, n_samples,
        green=green, soil_m=soil_m)
    P_m = _scale_precip(P_raw, gain, belt)
    # conditioning round: T adjusted given P, snow cover, vegetation
    T_m = refine_climate(T_m, P_m, T_lat, green=green)

    # upsample the monthly means to the world grid (smudge pass)
    T_monthly = np.stack([_upsample(np.clip(T_m[m], 0, 1), (H, W)) for m in range(12)])
    P_monthly = np.stack([_upsample(np.clip(P_m[m], 0, 1), (H, W)) for m in range(12)])

    # metric wind: internal advection units -> m/s. Earth's mean
    # surface wind over ocean is ~7 m/s (WIND_MEAN_OCEAN_MS); the
    # world's calibration target wiggles around that (seeded, leaky —
    # see units.wiggle_metric), so worlds vary but stay physical.
    # Consumers of the snapshots are scale-invariant (direction,
    # curl); the delivered store is metric.
    target = wiggle_metric(Stream(seed, "k11.windmetric"),
                           WIND_MEAN_OCEAN_MS, 2.0, 1.0)
    wind_u = ens["u_s"]
    wind_v = ens["v_s"]
    speed_oc = (float(np.hypot(wind_u, wind_v)[:, :, water_c].mean())
                if water_c.any() else 1.0)
    wscale = target / max(speed_oc, 1e-9)
    wind_u = (wind_u * wscale).astype(np.float32)
    wind_v = (wind_v * wscale).astype(np.float32)

    alt = np.clip((elev - sea_level) / (1.0 - sea_level), 0.0, 1.0)
    return {
        "T_monthly": T_monthly,
        "P_monthly": P_monthly,
        "T": T_monthly.mean(axis=0),
        "P": P_monthly.mean(axis=0),
        "alt": alt,
        "gain": gain,
        # the weather pattern proper: N fluid-simulated surface-wind
        # snapshots per month at the coarse grid, in M/S (see the
        # calibration above; `wind_scale` is the internal-units
        # multiplier, kept for provenance). The monthly means above are
        # their AVERAGE — gameplay interpolates between the samples of
        # adjacent days, it does not re-derive them. Snapshot (m, j) is
        # K1-reproducible: same seed, same trajectory through the year.
        "wind_u": wind_u,
        "wind_v": wind_v,
        "wind_scale": np.float32(wscale),
        # monthly-mean subsidence (drying) field on the coarse grid —
        # the corrective pass's, same clocks as the delivered winds
        "sub_monthly": np.stack(sub_m).astype(np.float32),
    }
