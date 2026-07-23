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
meridional bands with random signs (outermost constrained equatorward
— polar outflow and equatorward trades); a HIGH layer (same bands,
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
Conditioning, not simulation: single rounds, no iteration to
convergence.
"""

from __future__ import annotations

import math

import numpy as np

from kernel.hashrng import Stream

from exp.k11_worldgen.raster import fbm
from exp.k11_worldgen.units import T_MAX_C, T_MIN_C

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

# adaptive-gain target for land-mean precipitation, normalized: real
# land averages ~65-80 mm/month (~800-1000 mm/yr) -> ~0.19 of the
# 0-400 mm units range. A higher pin floods the biome match — every
# cell reads wet-forest and grassland prototypes never win.
_TARGET_LAND_P = 0.19


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
    """Sample field at float coordinates (clipped to the grid)."""
    H, W = field.shape
    bx = np.clip(bx, 0.0, W - 1.001)
    by = np.clip(by, 0.0, H - 1.001)
    x0, y0 = bx.astype(int), by.astype(int)
    fx, fy = bx - x0, by - y0
    return (field[y0, x0] * (1 - fx) * (1 - fy)
            + field[y0, x0 + 1] * fx * (1 - fy)
            + field[y0 + 1, x0] * (1 - fx) * fy
            + field[y0 + 1, x0 + 1] * fx * fy)


def _curl(psi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Divergence-free wind from a stream function: u = dpsi/dy, v = -dpsi/dx."""
    u = np.zeros_like(psi)
    v = np.zeros_like(psi)
    u[1:-1, :] = (psi[2:, :] - psi[:-2, :]) / 2
    v[:, 1:-1] = -(psi[:, 2:] - psi[:, :-2]) / 2
    return u, v


def _grad(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Central-difference gradients (zeros at the border)."""
    gx = np.zeros_like(a)
    gy = np.zeros_like(a)
    gx[:, 1:-1] = (a[:, 2:] - a[:, :-2]) / 2
    gy[1:-1, :] = (a[2:, :] - a[:-2, :]) / 2
    return gx, gy


def lee_shadow(u: np.ndarray, v: np.ndarray, source: np.ndarray,
               steps: int, recharge: float, decay: float) -> np.ndarray:
    """Blocked momentum transported downstream with the (deflected)
    flow: a barrier — a range, a peninsula — keeps weakening the
    stream past its lee instead of letting it resume full strength.
    Recharged at the source, decaying with distance. Shared by the
    wind lee wake (WindLibrary) and the ocean-current shadow
    (currents._process). Returns 0..1."""
    H, W = u.shape
    gy, gx = np.mgrid[0:H, 0:W].astype(float)
    S = source.copy()
    for _ in range(steps):
        S = _bilinear(S, gx - u, gy - v)
        S = np.clip(S + recharge * source * (1.0 - S) - decay, 0.0, 1.0)
    return S


# lee wake (wind): the momentum a range strips is transported
# downstream with the deflected flow — the wind stays weakened a few
# cells past the lee (real wakes mix out over tens of km, 1-3 coarse
# cells). Shares the deficit-advection tooling (lee_shadow) with the
# ocean-current shadow.
_WAKE_STEPS = 12
_WAKE_RECHARGE = 0.25
_WAKE_DECAY = 0.20
_WAKE_DAMP = 0.6


class WindLibrary:
    """Precomputed wind-pattern components at the coarse grid."""

    def __init__(self, stream: Stream, shape: tuple[int, int],
                 land: np.ndarray, alt: np.ndarray | None = None,
                 n_gyres: int = 6, land_friction: float = 0.35) -> None:
        H, W = shape
        gy, gx = np.mgrid[0:H, 0:W].astype(float)
        lat = gy / (H - 1)  # 0 north (poleward) → 1 south (equatorward)

        # meridional circulation cells: a few semi-stable bands of
        # NORTH–SOUTH flow (crossing the parallels), each with a RANDOM
        # sign (equatorward or poleward), strength, center, and width —
        # one-time draws, never re-rolled per snapshot. Not an Earth
        # clone: where adjacent bands oppose, the flow converges (wet
        # belts, at whatever latitude the draw puts them) or diverges
        # (dry belts — where the subtropical highs park, see
        # _precip_pass). Flow tapers to zero at both rims; an
        # equatorward rim band piles up at the equator (ITCZ analog).
        self.lat = lat
        self.angle_jitter = 0.1 + 0.2 * stream.uniform(5, 4)
        self.bands: list[tuple[float, float, float, float]] = []
        n_bands = 2 + int(stream.uniform(5, 9) < 0.5)
        for b in range(n_bands):
            sgn = 1.0 if stream.uniform(5, 10 + 4 * b) < 0.5 else -1.0
            strength = 0.4 + 0.8 * stream.uniform(5, 11 + 4 * b)
            center = 0.15 + 0.7 * stream.uniform(5, 12 + 4 * b)
            width = 0.10 + 0.08 * stream.uniform(5, 13 + 4 * b)
            self.bands.append((sgn, strength, center, width))
        self.bands.sort(key=lambda b: b[2])
        # the two OUTERMOST cells are constrained equatorward: polar air
        # drains off the pole at the surface (the rim taper then makes
        # the pole a divergence zone — a dry polar high), and the trades
        # converge on the equator (the ITCZ) — otherwise random signs
        # leave half of all worlds with a desert equator. The variety
        # lives in the middle cells.
        self.bands[0] = (1.0,) + self.bands[0][1:]
        self.bands[-1] = (1.0,) + self.bands[-1][1:]

        # chaotic gyres: curl of K1 stream functions (each its own
        # substream — same-stream fields at the same coordinates would
        # be identical)
        self.gyres: list[tuple[np.ndarray, np.ndarray]] = []
        for k in range(n_gyres):
            psi = fbm(stream.child(f"gyre.{k}"), shape, base_cell=max(8, W // 3), octaves=3)
            self.gyres.append(_curl(psi))

        # land–sea breeze potential: blows onshore when land is warm.
        # Heavily smoothed land mask → a CONTINENTAL monsoon flow, not
        # just a coastal sea breeze
        ls = np.kron(land, np.ones((1, 1)))  # already coarse
        for _ in range(10):
            p = np.pad(ls, 1, mode="edge")
            ls = sum(p[dy:dy + H, dx:dx + W] for dy in range(3) for dx in range(3)) / 9.0
        bx, by = _grad(ls)
        norm = np.hypot(bx, by) + 1e-9
        self.breeze_u = bx / norm * np.clip(norm * 8, 0, 1)
        self.breeze_v = by / norm * np.clip(norm * 8, 0, 1)

        # land friction: the surface (low) layer runs weaker over land
        # than over the sea at the same pressure gradient — roughness
        # plus a deeper turbulent boundary layer; real over-land
        # surface winds run ~60-70% of over-ocean values. Lightly
        # smoothed: every land cell feels roughness at full strength,
        # and coastal water feels the shore it is about to strike. The
        # high layer never feels the surface (sample_high skips this).
        fr = land.astype(float)
        for _ in range(3):
            p = np.pad(fr, 1, mode="edge")
            fr = sum(p[dy:dy + H, dx:dx + W] for dy in range(3) for dx in range(3)) / 9.0
        self.friction = 1.0 - land_friction * fr

        # terrain interaction: mountains DEFLECT the
        # flow around them and DAMP it — moisture advection already sees
        # terrain in its rate/moisture terms; now momentum does too
        self.alt = alt
        if alt is not None:
            self.ahx, self.ahy = _grad(alt)

    def meridional(self, seasonal: float) -> np.ndarray:
        """The persistent N–S base flow (bands + rim tapers), drifting
        slightly with the seasons."""
        v = np.zeros_like(self.lat)
        for sgn, strength, center, width in self.bands:
            c = center + 0.03 * seasonal * sgn
            v = v + sgn * strength * np.exp(
                -0.5 * ((self.lat - c) / width) ** 2)
        fall = 0.06
        v = (v * np.clip((1.0 - self.lat) / fall, 0.0, 1.0)
             * np.clip(self.lat / fall, 0.0, 1.0))
        return v

    def _base(self, stream: Stream, clock: int,
              seasonal: float) -> tuple[np.ndarray, np.ndarray]:
        """The persistent wind for one snapshot: the meridional bands
        with a per-snapshot angle wobble (small zonal tilt)."""
        v = (0.8 + 0.4 * stream.uniform(clock, 0)) * self.meridional(seasonal)
        j = self.angle_jitter * (stream.uniform(clock, 8) - 0.5)
        return -v * math.sin(j), v * math.cos(j)

    def sample_high(self, stream: Stream, clock: int,
                    seasonal: float) -> tuple[np.ndarray, np.ndarray]:
        """The HIGH layer (free troposphere) for the same snapshot:
        zonal-dominant (stronger than the low layer), shares the low
        layer's random gyre phases (same weather systems aloft), but no
        land–sea breeze (a boundary-layer phenomenon) and no terrain
        deflection — upper air flows OVER ranges that block the low
        layer. This split is what lets subtropical highs park dry air
        over seas and coasts (Middle-East-style deserts need the layers
        decoupled, not a single terrain-blocked flow).
        """
        u, v = self._base(stream, clock, seasonal)
        u = 1.4 * u
        v = 1.4 * v
        for k, (gu, gv) in enumerate(self.gyres):
            alpha = stream.uniform(clock, 1 + k) - 0.5
            u = u + 2.4 * alpha * gu
            v = v + 2.4 * alpha * gv
        return u, v

    def sample(self, stream: Stream, clock: int, seasonal: float,
               monsoon: float | None = None) -> tuple[np.ndarray, np.ndarray]:
        """One chaotic wind field: the meridional band base + random
        gyre blend + monsoon (breeze_u/v scaled by `monsoon` — the
        actual land–sea temperature contrast when the caller passes it,
        else a fixed 0.9 * seasonal), slowed over land by surface
        friction. seasonal = +1 midsummer, -1 midwinter. Terrain
        deflects/damps the result."""
        u, v = self._base(stream, clock, seasonal)
        # random gyre phases: interpolate across the precomputed library
        for k, (gu, gv) in enumerate(self.gyres):
            alpha = stream.uniform(clock, 1 + k) - 0.5  # signed blend
            u = u + 2.4 * alpha * gu
            v = v + 2.4 * alpha * gv
        b = monsoon if monsoon is not None else 0.9 * seasonal
        u = u + b * self.breeze_u
        v = v + b * self.breeze_v
        # surface roughness: the low layer slows over land
        u = u * self.friction
        v = v * self.friction
        if self.alt is not None:
            # deflect: remove (most of) the upslope component over high
            # ground — air goes around, not over
            oro = u * self.ahx + v * self.ahy
            gn = np.hypot(self.ahx, self.ahy) + 1e-9
            block = np.clip((self.alt - 0.15) / 0.35, 0.0, 1.0)
            cut = 0.7 * block * np.maximum(oro, 0.0) / gn
            u = u - cut * self.ahx
            v = v - cut * self.ahy
            # lee wake: the stripped momentum rides the deflected flow
            # downstream — the lee stays slowed, not just the slope
            removed = np.clip(cut * gn / (np.hypot(u, v) + 1e-9),
                              0.0, 1.0)
            wake = lee_shadow(u, v, removed, _WAKE_STEPS,
                              _WAKE_RECHARGE, _WAKE_DECAY)
            wk = 1.0 - _WAKE_DAMP * wake
            u = u * wk
            v = v * wk
            # damp: high terrain slows the flow
            f = 1.0 - 0.4 * block
            u = u * f
            v = v * f
        return u, v


def _subsidence(u: np.ndarray, v: np.ndarray, band: np.ndarray,
                steps: int = 24) -> np.ndarray:
    """Subsiding (drying) air aloft, advected on the high-layer wind.

    The subtropical high band is the source; the dry-air field S is then
    transported by the upper flow (semi-Lagrangian, band-recharged,
    slowly decaying), so subsidence arrives downwind of the band core in
    shifting swirls instead of sitting as a static latitude stripe.
    Returns S in [0, 1]: 1 = full subtropical-high suppression.
    """
    H, W = u.shape
    gy, gx = np.mgrid[0:H, 0:W].astype(float)
    S = band.copy()
    for _ in range(steps):
        S = _bilinear(S, gx - u, gy - v)
        S = np.clip(S + 0.25 * band * (1.0 - S) - 0.012, 0.0, 1.0)
    return S


# convection: hot moist air rains regardless of the flow — the
# Hadley-cell thunderstorm budget the wind-driven terms miss. Scales
# with heat (same Clausius-Clapeyron curve as evaporation): the deep
# tropics rain year-round, mid-latitudes only in summer, polar never.
# Without this term the tropics only rain where the wind wrings
# moisture out — seasonal and orographic — and moist broadleaf forest
# can never exist.
_CONV_T0 = _FREEZE + 0.25      # ~20 degC: convection kicks in
_CONV_TSPAN = 0.125            # full strength ~10 degC hotter
_CONV_RAIN = 0.15              # rate budget, vs 0.06 baseline

# foehn: descending air warms at the DRY adiabat (steeper than the
# moist one the windward climb followed), so lee air arrives
# undersaturated — rain is ACTIVELY suppressed on descent, not merely
# absent from depletion. Same u.grad(h) units as the 3.0 orographic
# lift rate (descent dries harder than lift wets — the dry adiabat is
# steeper); the floor keeps an imported-moisture lee possible.
_FOEHN_DRY = 6.0
_FOEHN_FLOOR = 0.2
# the T-side of the foehn: lee warming per unit descent, normalized T
# (0.4 * a 3 km range's descent signal ~= 1-2 degC at the 65 degC span)
_FOEHN_WARM = 0.4


def _advect(u: np.ndarray, v: np.ndarray, h: np.ndarray, water: np.ndarray,
            lake_src: np.ndarray, T: np.ndarray,
            green: np.ndarray | None = None,
            sub: np.ndarray | None = None, steps: int = 36) -> np.ndarray:
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
    """
    H, W = h.shape
    gy, gx = np.mgrid[0:H, 0:W].astype(float)
    dhx, dhy = _grad(h)
    oro = np.maximum(0.0, u * dhx + v * dhy)
    sink = np.maximum(0.0, -(u * dhx + v * dhy))   # descent: foehn
    recycle = 0.15 if green is None else 0.15 + 0.25 * green
    intercept = 1.0 if green is None else 1.0 - 0.3 * green
    # evaporation factor: ~0 at -3 degC, full at +10 degC — real
    # saturation vapor pressure at 0 degC is ~20% of tropical values,
    # so cold seas barely humidify the air
    evap = np.clip((T - (_FREEZE - 0.05)) / 0.22, 0.05, 1.0)
    # subsidence suppression factors (1 = no high overhead)
    wet = 1.0 if sub is None else 1.0 - 0.65 * sub
    dry = 1.0 if sub is None else 1.0 - 0.75 * sub
    # bounded compressibility: convergent flow (trades piling into the
    # hot zone, flow crammed against a range) CONCENTRATES moisture
    # instead of just resampling it; divergent flow dilutes. Clipped so
    # a strong convergence spike cannot blow the budget up — this is a
    # correction, not a continuity equation.
    du_dx = _grad(u)[0]
    dv_dy = _grad(v)[1]
    conv = np.clip(1.0 - 1.5 * (du_dx + dv_dy), 0.6, 1.8)

    M = np.full((H, W), 0.85)
    P = np.zeros((H, W))
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
        # ocean): baseline rate everywhere; orographic lift adds over
        # land (h is flat over water, so oro ~ 0 there); convection
        # adds where the air is hot; descent SUPPRESSES (foehn — the
        # lee is dried by warming, not just by upstream depletion).
        # Genuinely depleted air barely rains (lee deserts stay dry)
        rate = np.clip(0.06 + 3.0 * oro
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


def _precip_pass(lib: WindLibrary, stream: Stream, T_m: np.ndarray,
                 land_c: np.ndarray, water_c: np.ndarray, lake_c: np.ndarray,
                 h_c: np.ndarray, lat: np.ndarray, n_samples: int,
                 green: np.ndarray | None = None
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """One monthly precipitation pass: monsoon strength from the land–sea
    heating anomaly of the given T field, N chaotic wind snapshots per
    month, moisture advected per snapshot on the coarse grid. Each
    snapshot also runs the HIGH layer: the subtropical-high band
    (migrating seasonally, as real highs do) seeds a subsidence field
    that is advected by the upper flow and dries the low layer where it
    descends. Returns RAW rates plus the per-snapshot surface winds —
    the (12, n_samples) wind fields ARE the world's weather pattern
    (gameplay walks between adjacent samples of a month), so they are
    delivered, not discarded."""
    ch, cw = h_c.shape
    P_m = np.zeros((12, ch, cw))
    wind_u = np.zeros((12, n_samples, ch, cw), dtype=np.float32)
    wind_v = np.zeros((12, n_samples, ch, cw), dtype=np.float32)
    T_ann_c = T_m.mean(axis=0)
    for m in range(12):
        seasonal = math.cos(2 * math.pi * (m - _SUMMER) / 12)
        # subtropical highs park where the persistent meridional flow
        # DIVERGES (low-level outflow = subsidence aloft) — no fixed
        # latitude: the dry belts sit wherever this world's circulation
        # cells pull apart, wet belts where they meet
        v0 = lib.meridional(seasonal)
        dvy = np.gradient(v0, axis=0)
        band = np.clip(dvy / 0.10, 0.0, 1.0)
        # monsoon driven by the ACTUAL land–sea heating ANOMALY (land
        # warming faster than sea in summer -> onshore flow; reverses
        # in winter). Anomaly, not absolute contrast: the constant
        # altitude-lapse offset would otherwise pin the flow offshore.
        anom = T_m[m] - T_ann_c
        if water_c.any() and land_c.any():
            contrast = float(anom[land_c].mean() - anom[water_c].mean())
        else:
            contrast = 0.0
        monsoon = float(np.clip(12.0 * contrast, -1.2, 1.2))
        for j in range(n_samples):
            clock = 1000 + m * 16 + j
            u, v = lib.sample(stream, clock, seasonal, monsoon)
            u_h, v_h = lib.sample_high(stream, clock, seasonal)
            sub = _subsidence(u_h, v_h, band)
            if green is not None:
                # forests are windbreaks: canopy roughness slows the
                # flow, so moisture transport across forests weakens
                wb = 1.0 - 0.25 * green
                u = u * wb
                v = v * wb
            wind_u[m, j] = u
            wind_v[m, j] = v
            P_m[m] += _advect(u, v, h_c, water_c, lake_c, T_m[m],
                              green=green, sub=sub)
        P_m[m] /= n_samples
    return P_m, wind_u, wind_v


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


def mean_surface_wind(elev: np.ndarray, hydro: dict, sea_level: float,
                      seed: int, coarse: int = 128, n: int = 16
                      ) -> tuple[np.ndarray, np.ndarray]:
    """Mean annual low-layer wind at the ANCHOR grid (for the ocean-
    current drift). Uses the same K1 stream as build_climate, so the
    WindLibrary (bands, gyres, breeze) is draw-identical to the one the
    precipitation passes run; sampled N times at the equinox
    (seasonal = 0, monsoon = 0 — summer/winter cancel on the annual
    mean) and averaged. Clocks 500+ never collide with the climate
    passes' 1000+ clocks."""
    H, W = elev.shape
    f = max(1, H // coarse)
    _, _, land_c, alt_c = _coarse_grids(elev, hydro, sea_level, f)
    stream = Stream(seed, "k11.climate")
    lib = WindLibrary(stream, land_c.shape, land_c, alt=alt_c)
    u = np.zeros(land_c.shape)
    v = np.zeros(land_c.shape)
    for k in range(n):
        uk, vk = lib.sample(stream, 500 + k, 0.0, monsoon=0.0)
        u += uk
        v += vk
    u, v = u / n, v / n
    if f > 1:
        u = np.kron(u, np.ones((f, f)))
        v = np.kron(v, np.ones((f, f)))
    return u, v


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

    Temperature first (it is wind-independent), then ONE precipitation
    pass; a conditioning round (refine_climate) adjusts T given P.
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

    lib = WindLibrary(stream, (ch, cw), land_c, alt=alt_c)

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

    # temperature first: it drives the monsoon and evaporation below;
    # each snapshot's equilibrium field is transported along its wind —
    # wind circulates heat (maritime moderation reaches downwind,
    # interiors keep their extremes). One damped transport per
    # snapshot, conditioning not simulation.
    dhx_c, dhy_c = _grad(h_c)
    T_m = np.zeros((12, ch, cw))
    for m in range(12):
        seasonal = math.cos(2 * math.pi * (m - _SUMMER) / 12)
        for j in range(n_samples):
            clock = 1000 + m * 16 + j
            jitter = 0.04 * (stream.uniform(clock, 15) - 0.5)
            T_eq = (T_lat + T_amp_lat * seasonal
                    + land_c * 0.30 * T_amp_lat * seasonal
                    - 0.45 * alt_c + jitter)
            if sst_m is not None:
                # the sea runs its own temperature (advected by the
                # gyre streams, monthly — swirls breathe seasonally)
                T_eq = np.where(water_c, sst_m[m] + jitter, T_eq)
            u_t, v_t = lib.sample(stream, clock, seasonal)
            T = T_eq
            for _ in range(_T_ADV_STEPS):
                T = _bilinear(T, gx - u_t, gy - v_t)
                T = T + _T_ADV_RELAX * (T_eq - T)
            # foehn warming: air descending a lee slope heats at the
            # dry adiabat, so the lee runs warmer than the windward at
            # the same altitude (also feeds moisture capacity below)
            T = T + _FOEHN_WARM * np.maximum(0.0, -(u_t * dhx_c
                                                    + v_t * dhy_c))
            T_m[m] += np.clip(T, 0.0, 1.0)
        T_m[m] /= n_samples

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
    if green is not None and green.shape != (ch, cw):
        green = _pool(green, f)
    P_raw, wind_u, wind_v = _precip_pass(
        lib, stream, T_m, land_c, water_c, lake_c, h_c, lat, n_samples,
        green=green)
    # no static aridity belt: the dry structure comes entirely from the
    # advected subsidence (which parks at the flow's divergence zones);
    # the belt multiplier stays only as the gain-pin interface
    belt = np.ones_like(lat)
    if gain is None:
        land_mean = float((P_raw * belt[None])[:, land_c].mean()) if land_c.any() else 0.0
        gain = float(np.clip(_TARGET_LAND_P / max(land_mean, 1e-6), 2.0, 24.0))
        P_m = _scale_precip(P_raw, gain, belt)
        # corrective step: heavy-tailed cells (windward spikes) saturate
        # the [0, 1] clip in _scale_precip, which drags the REALIZED
        # land mean below the pin target; rescale once so the pin holds
        realized = float(P_m[:, land_c].mean()) if land_c.any() else 0.0
        if realized > 1e-6:
            gain = float(np.clip(gain * _TARGET_LAND_P / realized, 2.0, 24.0))
    P_m = _scale_precip(P_raw, gain, belt)
    # conditioning round: T adjusted given P, snow cover, vegetation
    T_m = refine_climate(T_m, P_m, T_lat, green=green)

    # upsample the monthly means to the world grid (smudge pass)
    T_monthly = np.stack([_upsample(np.clip(T_m[m], 0, 1), (H, W)) for m in range(12)])
    P_monthly = np.stack([_upsample(np.clip(P_m[m], 0, 1), (H, W)) for m in range(12)])

    alt = np.clip((elev - sea_level) / (1.0 - sea_level), 0.0, 1.0)
    return {
        "T_monthly": T_monthly,
        "P_monthly": P_monthly,
        "T": T_monthly.mean(axis=0),
        "P": P_monthly.mean(axis=0),
        "alt": alt,
        "gain": gain,
        # the weather pattern proper: N chaotic surface-wind snapshots
        # per month at the coarse grid (the monthly means above are
        # their AVERAGE — gameplay interpolates between the samples of
        # adjacent days, it does not re-derive them). Snapshot (m, j)
        # is K1-reproducible: WindLibrary.sample(stream, 1000+m*16+j,
        # seasonal(m), monsoon) with the pipeline's own monsoon/windbreak
        # conditioning already baked in.
        "wind_u": wind_u,
        "wind_v": wind_v,
    }
