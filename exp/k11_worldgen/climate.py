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

Couplings: mountains DEFLECT and DAMP the wind (air
goes around, not through); the monsoon is driven by the ACTUAL
land–sea temperature anomaly per month (temperature is computed
first — it is wind-independent); refine_climate() runs damped
conditioning rounds — snow-albedo feedback and evaporative/cloud
cooling adjust T given P; and precipitation runs in TWO passes: pass 1
on bare ground yields a provisional forest cover, pass 2 lets forests
join the water cycle (evapotranspiration recycling, canopy
interception, windbreak). Conditioning, not simulation: single rounds,
no iteration to convergence.
"""

from __future__ import annotations

import math

import numpy as np

from kernel.hashrng import Stream

from exp.k11_worldgen.raster import fbm
from exp.k11_worldgen.units import T_MAX_C, T_MIN_C

# months are the canon time period; summer solstice at month 6
_SUMMER = 6.0

# freezing point in normalized units (0 degC)
_FREEZE = (0.0 - T_MIN_C) / (T_MAX_C - T_MIN_C)


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


class WindLibrary:
    """Precomputed wind-pattern components at the coarse grid."""

    def __init__(self, stream: Stream, shape: tuple[int, int],
                 land: np.ndarray, alt: np.ndarray | None = None,
                 n_gyres: int = 6) -> None:
        H, W = shape
        gy, gx = np.mgrid[0:H, 0:W].astype(float)
        lat = gy / (H - 1)  # 0 north (poleward) → 1 south (equatorward)

        # base circulation: RANDOM per world, semi-stable — this is a
        # fantasy world with no global ocean currents and no
        # rest-of-world, so there is no justification for hardcoded
        # westerlies; the bearing/strength/band are drawn once per
        # world and held stable across months/samples, unlike the
        # chaotic gyres. The bearing OSCILLATES seasonally
        # (monsoon-style wind reversal): swing up to ~70° around the
        # base bearing.
        self.bearing0 = 2 * math.pi * stream.uniform(5, 0)
        self.swing = 0.4 + 0.8 * stream.uniform(5, 4)  # radians of seasonal swing
        strength = 0.6 + 0.6 * stream.uniform(5, 1)
        band_center = 0.25 + 0.5 * stream.uniform(5, 2)
        band_width = 0.25 + 0.25 * stream.uniform(5, 3)
        self.profile = strength * np.exp(-0.5 * ((lat - band_center) / band_width) ** 2)

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

        # terrain interaction: mountains DEFLECT the
        # flow around them and DAMP it — moisture advection already sees
        # terrain in its rate/moisture terms; now momentum does too
        self.alt = alt
        if alt is not None:
            self.ahx, self.ahy = _grad(alt)

    def sample(self, stream: Stream, clock: int, seasonal: float,
               monsoon: float | None = None) -> tuple[np.ndarray, np.ndarray]:
        """One chaotic wind field: seasonally-oscillating zonal + random
        gyre blend + monsoon (breeze_u/v scaled by `monsoon` — the
        actual land–sea temperature contrast when the caller passes it,
        else a fixed 0.9 * seasonal). seasonal = +1 midsummer, -1
        midwinter. Terrain deflects/damps the result."""
        bearing = self.bearing0 + self.swing * seasonal
        u = self.profile * math.cos(bearing) * (0.7 + 0.6 * stream.uniform(clock, 0))
        v = self.profile * math.sin(bearing) * (0.7 + 0.6 * stream.uniform(clock, 0))
        # random gyre phases: interpolate across the precomputed library
        for k, (gu, gv) in enumerate(self.gyres):
            alpha = stream.uniform(clock, 1 + k) - 0.5  # signed blend
            u = u + 2.4 * alpha * gu
            v = v + 2.4 * alpha * gv
        b = monsoon if monsoon is not None else 0.9 * seasonal
        u = u + b * self.breeze_u
        v = v + b * self.breeze_v
        if self.alt is not None:
            # deflect: remove (most of) the upslope component over high
            # ground — air goes around, not over
            oro = u * self.ahx + v * self.ahy
            gn = np.hypot(self.ahx, self.ahy) + 1e-9
            block = np.clip((self.alt - 0.15) / 0.35, 0.0, 1.0)
            cut = 0.7 * block * np.maximum(oro, 0.0) / gn
            u = u - cut * self.ahx
            v = v - cut * self.ahy
            # damp: high terrain slows the flow
            f = 1.0 - 0.4 * block
            u = u * f
            v = v * f
        return u, v


def _advect(u: np.ndarray, v: np.ndarray, h: np.ndarray, water: np.ndarray,
            lake_src: np.ndarray, green: np.ndarray | None = None,
            steps: int = 36) -> np.ndarray:
    """Semi-Lagrangian moisture advection along a wind field.

    Parcels backtrace along the wind, inherit moisture, recharge over
    water (strong) and lakes/wide rivers (weak), precipitate on
    orographic lift (wind . grad h), recycle over land. `green` is a
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
    recycle = 0.15 if green is None else 0.15 + 0.25 * green
    intercept = 1.0 if green is None else 1.0 - 0.3 * green

    M = np.full((H, W), 0.85)
    P = np.zeros((H, W))
    for _ in range(steps):
        M = _bilinear(M, gx - u, gy - v)
        M = np.where(water, np.minimum(1.0, M + 0.30 * (1.0 - M)), M)
        M = np.where(lake_src & ~water, np.minimum(1.0, M + 0.10 * (1.0 - M)), M)
        # low baseline: genuinely depleted air barely rains (lee deserts
        # stay dry); orographic lift dominates
        rate = np.where(water | lake_src, 0.0,
                        np.clip(0.06 + 3.0 * oro, 0.0, 0.9) * intercept)
        p = M * rate
        P += p
        # evapotranspiration feedback: recycling is proportional to the
        # moisture already present — wet stays wet, rain-shadow deserts
        # stay dry (a uniform +const recovery erased shadows in ~10
        # steps)
        M = np.where(water | lake_src, M,
                     np.clip(M - 0.30 * p + recycle * M * (1.0 - p), 0.02, 1.0))
    return P / steps


def _precip_pass(lib: WindLibrary, stream: Stream, T_m: np.ndarray,
                 land_c: np.ndarray, water_c: np.ndarray, lake_c: np.ndarray,
                 h_c: np.ndarray, n_samples: int,
                 green: np.ndarray | None = None) -> np.ndarray:
    """One monthly precipitation pass: monsoon strength from the land–sea
    heating anomaly of the given T field, N chaotic wind snapshots per
    month, moisture advected per snapshot on the coarse grid. Returns
    RAW rates — build_climate applies the gain + aridity belt."""
    ch, cw = h_c.shape
    P_m = np.zeros((12, ch, cw))
    T_ann_c = T_m.mean(axis=0)
    for m in range(12):
        seasonal = math.cos(2 * math.pi * (m - _SUMMER) / 12)
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
            if green is not None:
                # forests are windbreaks: canopy roughness slows the
                # flow, so moisture transport across forests weakens
                wb = 1.0 - 0.25 * green
                u = u * wb
                v = v * wb
            P_m[m] += _advect(u, v, h_c, water_c, lake_c, green=green)
        P_m[m] /= n_samples
    return P_m


def _scale_precip(P_raw: np.ndarray, gain: float, belt: np.ndarray) -> np.ndarray:
    """Raw advection rates -> normalized precipitation: adaptive gain
    (per world, deterministic) + the subtropical aridity belt (the dry
    belt makes deserts actually appear)."""
    return np.clip(P_raw * gain, 0.0, 1.0) * belt


def _vegetation_prior(T_m: np.ndarray, P_m: np.ndarray) -> np.ndarray:
    """Provisional forest cover (0..1) from a first-pass climate: the
    biome month-vector match plus forest bases, no overrides. Feeds the
    forest evapotranspiration boost in the second precipitation pass."""
    from exp.k11_worldgen.biomes import _Acc, forest_cover
    from exp.k11_worldgen.units import precip_mm, temp_c
    acc = _Acc(T_m.shape[1:])
    for m in range(12):
        acc.add(temp_c(T_m[m]), precip_mm(P_m[m]), T_m[m], P_m[m], m)
    return forest_cover(acc.classify(), acc.grow_p / np.maximum(acc.grow_n, 1))


def refine_climate(T_m: np.ndarray, P_m: np.ndarray, T_lat: np.ndarray,
                   relaxation: float = 0.7) -> np.ndarray:
    """2nd-order conditioning round: recalculate T
    conditioned on P and snow cover, taking the one-pass output as the
    prior. Single DAMPED round — conditioning, not simulation; never
    iterated to convergence (feedback runaway is bounded by the
    relaxation factor and the small coefficients).

    - snow-albedo feedback: sub-zero months carry snow; snow cools,
      more under stronger sun (equatorward, proxied by T_lat)
    - evaporative/cloud cooling: wet months are cooler
    - cloud swing damping: wet cells have their seasonal swing shrunk
      toward their own annual mean (maritime character)
    """
    snow = T_m < _FREEZE
    sun = 0.4 + 0.6 * T_lat                      # stronger sun equatorward
    d_alb = 0.10 * snow * sun[None, :, :]
    d_evap = 0.03 * P_m
    T_ref = T_m - relaxation * (d_alb + d_evap)
    T_ann = T_ref.mean(axis=0)
    T_ref = T_ann[None] + (T_ref - T_ann[None]) * (1.0 - 0.15 * P_m)
    return np.clip(T_ref, 0.0, 1.0)


def build_climate(elev: np.ndarray, hydro: dict, sea_level: float,
                  seed: int = 0, coarse: int = 128,
                  n_samples: int = 8) -> dict:
    """Seasonal climate as 12 monthly (T, P) mean curves per cell.

    Temperature first (it is wind-independent), then TWO precipitation
    passes: bare ground, provisional forest cover, then again with
    forest feedback (evapotranspiration, interception, windbreak) —
    each pass reads its monsoon strength off the actual land–sea
    heating anomaly. A conditioning round (refine_climate) adjusts T
    after each pass. Monthly means upsampled to the world grid.
    Deterministic from `seed` (K1 draws are pure hash lookups, so the
    passes replay identical wind randomness).
    """
    H, W = elev.shape
    f = max(1, H // coarse)
    ch, cw = H // f, W // f
    stream = Stream(seed, "k11.climate")

    # coarse terrain: moving air sees the water surface only where
    # standing water actually exists. w is the priority-flood FILL
    # level (outlet-sill height) for every basin, including underfed
    # ones that hold no lake — using it everywhere would show climate a
    # phantom flood surface over dry basins and wetland flats.
    h_clim = elev.copy()
    h_clim[hydro["lake_mask"]] = np.maximum(elev, hydro["w"])[hydro["lake_mask"]]
    h_clim[hydro["ocean_mask"]] = sea_level
    h_c = _pool(h_clim, f)
    water_c = _pool(hydro["ocean_mask"].astype(float), f) > 0.5
    lake_c = _pool((hydro["lake_mask"] | (hydro["width"] >= 2)).astype(float), f) > 0.3
    land_c = ~water_c
    # altitude may go negative: below-sea basins (dry depressions exist
    # since ocean is border-connected) are HOT in reality — the lapse
    # term then warms instead of cools (bounded at -0.3 ≈ -1800 m).
    alt_c = np.clip((h_c - sea_level) / (1.0 - sea_level), -0.3, 1.0)

    lib = WindLibrary(stream, (ch, cw), land_c, alt=alt_c)

    gy = np.mgrid[0:ch, 0:cw][0].astype(float)
    lat = gy / (ch - 1)                            # 0 north → 1 south
    T_lat = 0.12 + 0.88 * lat                      # spatial delta: cold
                                                   # north (~-22 degC,
                                                   # no big Siberia),
                                                   # hottest south
    # seasonal swing peaks at MID-LATITUDES and is minimal at both rims
    #: the north stays frozen year-round, the southern
    # tropics stay warm year-round (real equatorial swing is a few degC).
    # Kept moderate — full Illinois-grade continental swings are real
    # but dominate the map's character. Land contrast
    # is part of the swing and scales with it, not a fixed extra.
    T_amp_lat = 0.05 + 0.25 * np.sin(math.pi * lat)

    # temperature first: it is wind-independent, and the monsoon reads
    # its land–sea contrast below
    T_m = np.zeros((12, ch, cw))
    for m in range(12):
        seasonal = math.cos(2 * math.pi * (m - _SUMMER) / 12)
        for j in range(n_samples):
            clock = 1000 + m * 16 + j
            jitter = 0.04 * (stream.uniform(clock, 15) - 0.5)
            T = (T_lat + T_amp_lat * seasonal
                 + land_c * 0.30 * T_amp_lat * seasonal
                 - 0.45 * alt_c + jitter)
            T_m[m] += np.clip(T, 0.0, 1.0)
        T_m[m] /= n_samples

    # pass 1: bare-ground precipitation (raw rates). The advection's
    # absolute scale is free, so the gain is ADAPTIVE per world: pin
    # the land-mean rain AFTER the aridity belt (deterministic) — the
    # mm the classifier reads via units then means the same thing in
    # every world, instead of hand-chasing a fixed gain per layout.
    P_raw = _precip_pass(lib, stream, T_m, land_c, water_c, lake_c, h_c,
                         n_samples)
    belt = 1.0 - 0.40 * np.exp(-0.5 * ((lat - 0.78) / 0.18) ** 2)
    land_mean = float((P_raw * belt[None])[:, land_c].mean()) if land_c.any() else 0.0
    gain = float(np.clip(0.34 / max(land_mean, 1e-6), 2.0, 16.0))
    P_m = _scale_precip(P_raw, gain, belt)
    P_pass1_ann = P_m.mean(axis=0)  # kept for the loading-screen render
    T_m = refine_climate(T_m, P_m, T_lat)
    # pass 2: forests join the water cycle —
    # provisional forest cover from the pass-1 climate boosts
    # evapotranspiration recycling, intercepts local rain-out (moisture
    # travels downwind instead), and acts as a windbreak
    green = _vegetation_prior(T_m, P_m)
    P_raw = _precip_pass(lib, stream, T_m, land_c, water_c, lake_c, h_c,
                         max(1, n_samples // 2), green=green)
    P_m = _scale_precip(P_raw, gain, belt)
    # final conditioning round: T adjusted given P and snow cover
    T_m = refine_climate(T_m, P_m, T_lat)

    # upsample the monthly means to the world grid (smudge pass)
    T_monthly = np.stack([_upsample(np.clip(T_m[m], 0, 1), (H, W)) for m in range(12)])
    P_monthly = np.stack([_upsample(np.clip(P_m[m], 0, 1), (H, W)) for m in range(12)])

    alt = np.clip((elev - sea_level) / (1.0 - sea_level), 0.0, 1.0)
    return {
        "T_monthly": T_monthly,
        "P_monthly": P_monthly,
        "T": T_monthly.mean(axis=0),
        "P": P_monthly.mean(axis=0),
        "P_pass1": _upsample(P_pass1_ann, (H, W)),
        "green": _upsample(green, (H, W)),
        "alt": alt,
    }
