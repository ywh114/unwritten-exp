"""K11 — ocean currents: stream-function gyres, SST, upwelling.

The barotropic textbook model, at worldgen fidelity. The velocity
field is never drawn directly — VORTICITY is drawn, and the flow is
solved for:

- Vorticity sources are an ABSOLUTE geographic feature (K1 draws,
  never re-rolled): a few Gaussian blobs in deep water, sign and
  strength random (fantasy world — no Earth-clone rule that outer
  bands must run a certain way).
- Each source solves ∇²ψ = ζ with ψ = 0 on the rim and a FREE
  constant per interior landmass (the value the unobstructed ocean
  would carry at its heart — the island-rule treatment: pinning all
  land to one value makes Δψ = 0 between any two boundaries, which
  kills all net transport — straits carry nothing, gyres cannot wrap
  continents). Land is automatically a streamline: the transport
  (ψ_y, −ψ_x) is EXACTLY divergence-free, bends around continents,
  and threads straits — no masks, no projections, no continuity
  hacks.
- The VELOCITY is transport / depth (barotropic continuity): flow
  accelerates over shelves and through gaps instead of being damped
  there.
- Gyres are huge features, so the solve runs COARSE (64²) and the
  transport is bicubic-upscaled to the anchor; depth division happens
  at the anchor.

WIND CORRELATION (the conditioning pass): surface currents are
wind-driven, and this pipeline runs currents BEFORE climate — so the
absolute field above stands alone at spawn, and refine_currents()
adds the curl of the world's OWN mean annual surface wind (the mean
of the delivered weather pattern, climate["wind_u"/"wind_v"]) as
another vorticity source once pass-1 climate exists (Sverdrup
dynamics). Pass-2 climate then reads the refined field. No stand-in
wind estimate, no invented coupling parameters thrown away later.

The streams CONDUCT temperature: `advect_sst` transports the latitude
baseline along the flow (semi-Lagrangian backtrace) with a slow
relaxation toward the local equilibrium (the thermostat — parcels do
not carry their origin climate forever), mixes DEEP COLD WATER UP
where the stream rises (upwelling: depth decreasing along the flow),
and finishes with a few coarse diffusion steps. The result is the
ocean's surface temperature field; the climate reads it instead of
the raw latitude profile over water, and the aquatic layer reads the
rise field for the upwelling biome classes.
"""

from __future__ import annotations

import numpy as np

from kernel.hashrng import Stream

from exp.k11_worldgen.climate import _bilinear, _grad
from exp.k11_worldgen.raster import upsample_bicubic
from exp.k11_worldgen.units import elev_m

# deep water mixed up by rising streams
_T_DEEP_C = 4.0

# upwelling mixing rate per advection step at the strongest sites.
# The rise field's tail is heavy (boundary-current slopes), so the
# term must be a RELAXATION (bounded mixing), never a raw
# rise-scaled subtraction — the old -0.1 * rise * (T - T_deep) form
# goes |1 - 0.1 * rise| > 1 for rise > 20 m/cell and detonates
# (oscillating geometric blowup, masked downstream only by the
# climate's T clip). rr = 1 - exp(-rise / p95) is asymptotic to 1,
# so per-step mixing is always <= _UPW_MIX.
_UPW_MIX = 0.1

# barotropic velocity = transport / max(depth, MIN_DEPTH): the floor
# is the model's equivalent depth — shelves accelerate the flow
# (boundary currents) instead of damping it, bounded so a 1 m shelf
# cannot spin up a singularity
_MIN_DEPTH_M = 50.0
# real surface circulation is predominantly wind-driven: the wind-curl
# source outweighs each vorticity seed
_WIND_FORCING_WEIGHT = 2.0


def _pool(a: np.ndarray, f: int) -> np.ndarray:
    H, W = a.shape
    return a.reshape(H // f, f, W // f, f).mean(axis=(1, 3))


# the world-edge rock rim is a magic map boundary, not terrain: it
# leaks water into the void (replenished by the currents that arrive
# from beyond the map) but still redirects part of the flow back
# along the edge. A Robin rim condition between wall (0.0 — the rim
# is a streamline, all flow redirected, meridional boundary currents
# recirculate and pile heat onto the poleward rim) and open water
# (1.0 — through-flow unchecked, no along-rim guidance).
_RIM_POROSITY = 0.5


def _poisson_sor(zeta: np.ndarray, water: np.ndarray,
                 pin: np.ndarray | None = None,
                 iters: int | None = None, omega: float = 1.85,
                 rim_porosity: float = 0.0,
                 rim_values: np.ndarray | None = None) -> np.ndarray:
    """Solve ∇²ψ = ζ with ψ fixed to `pin` values outside `water`
    (default 0). Deterministic red-black SOR.

    Rim boundary condition, parametrized by `rim_porosity` ρ:
    - ρ = 0 (closed wall): ψ = 0 on the rim, so the rim is a
      streamline and no transport crosses the domain edge.
    - ρ = 1 (fully open): zero normal gradient, transport crosses
      the rim freely.
    - in between (semi-porous): the ghost cell takes
      (2ρ − 1)·ψ_rim, interpolating between the Dirichlet
      reflection (−ψ) and the Neumann mirror (+ψ) — the edge
      leaks a ρ-share of the through-flow and redirects the rest.
    With ρ > 0 rim water cells take part in the solve; with ρ = 0
    they hold their pinned value.

    `iters` defaults to 600 at the production 64² psi grid and
    scales down with the grid (SOR needs O(diameter) sweeps to
    converge) so small test grids do not pay for full-size
    convergence.

    `rim_values` (through-flow sources): full Dirichlet rim — rim
    cells are FIXED to the given values and excluded from the solve,
    overriding the porosity machinery. A linear ramp along the rim
    drives a uniform transport across the domain that bends around
    the landmasses (the circulation arriving from beyond the map).

    `zeta` may carry leading batch axes — independent solves stacked
    into one Python loop (identical arithmetic per solve, K times
    fewer loop iterations; `pin`/`rim_values` broadcast or stack to
    match)."""
    single = zeta.ndim == 2
    z3 = zeta[None] if single else zeta
    H, W = z3.shape[-2:]
    if iters is None:
        iters = min(600, max(150, 10 * max(H, W)))
    psi = (np.zeros_like(z3) if pin is None
           else np.broadcast_to(np.where(water, 0.0, pin),
                                z3.shape).copy())
    interior = water.copy()
    interior[0, :] = interior[-1, :] = False
    interior[:, 0] = interior[:, -1] = False
    if rim_values is not None:
        rim = np.zeros((H, W), bool)
        rim[0, :] = rim[-1, :] = True
        rim[:, 0] = rim[:, -1] = True
        psi[:, rim] = (rim_values[rim] if rim_values.ndim == 2
                       else rim_values[:, rim])
    elif rim_porosity > 0.0:
        interior = water.copy()
    yy, xx = np.mgrid[0:H, 0:W]
    checker = (yy + xx) % 2
    # rim cells and how many domain edges they sit on (corners: 2)
    edge_n = np.zeros((H, W))
    edge_n[0, :] += 1
    edge_n[-1, :] += 1
    edge_n[:, 0] += 1
    edge_n[:, -1] += 1
    leak = 2.0 * (1.0 - rim_porosity)
    pad_width = ((0, 0), (1, 1), (1, 1))
    for _ in range(iters):
        for parity in (0, 1):
            p = np.pad(psi, pad_width, mode="edge")
            s = (p[:, :-2, 1:-1] + p[:, 2:, 1:-1]
                 + p[:, 1:-1, :-2] + p[:, 1:-1, 2:])
            if rim_porosity > 0.0:
                # replace the mirrored ghost (+ψ) with (2ρ−1)·ψ on
                # each domain edge the cell touches
                s = s - leak * edge_n * psi
            m = interior & (checker == parity)
            psi[:, m] = ((1.0 - omega) * psi[:, m]
                         + omega * (s[:, m] - z3[:, m]) / 4.0)
    return psi[0] if single else psi


def _land_constants(zeta: np.ndarray, water: np.ndarray,
                    rim_porosity: float = 0.0,
                    psi_open: np.ndarray | None = None,
                    rim_to_zero: bool = True) -> np.ndarray:
    """Per-landmass streamfunction constants (the multiply-connected
    part of the solve). Pinning every landmass to the SAME value (0)
    makes Δψ = 0 between any two boundaries — no net transport:
    straits carry nothing, gyres cannot wrap continents. Instead each
    interior landmass takes the value the UNOBSTRUCTED ocean carries
    at its heart (its area mean of the all-water solve), so the
    blocked flow still threads straits and wraps land at the
    large-scale transport the forcing drives — squeezed by continuity
    where the path narrows (Godfrey island-rule flavor).

    `psi_open` supplies the unobstructed solution directly when it is
    known analytically (through-flow ramps: the harmonic extension of
    a linear rim ramp is the ramp itself). `rim_to_zero=False` takes
    the unobstructed value for rim-touching landmasses too (ramp
    sources, where the rim is not a ψ ≈ 0 boundary); otherwise
    landmasses touching the rim stay pinned to 0 (with a porous rim
    the magic wall ring is water — see _coarse_grids — so no
    landmass abuts the domain edge and this case does not arise).

    Batched `zeta`/`psi_open` (leading axes) solves the landmass
    labeling ONCE and returns per-source pins."""
    if psi_open is None:
        psi_open = _poisson_sor(zeta, np.ones_like(water),
                                rim_porosity=rim_porosity)
    single = psi_open.ndim == 2
    po3 = psi_open[None] if single else psi_open
    H, W = water.shape
    land = ~water
    lab = np.zeros((H, W), dtype=np.int32)
    n = 0
    for sy in range(H):
        for sx in range(W):
            if land[sy, sx] and not lab[sy, sx]:
                n += 1
                stack = [(sy, sx)]
                lab[sy, sx] = n
                while stack:
                    y, x = stack.pop()
                    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                        ny, nx_ = y + dy, x + dx
                        if (0 <= ny < H and 0 <= nx_ < W
                                and land[ny, nx_] and not lab[ny, nx_]):
                            lab[ny, nx_] = n
                            stack.append((ny, nx_))
    # float64 pins even for float32 sources (NumPy-2 weak scalars:
    # np.where(water, 0.0, pin) follows pin's dtype, and a float32
    # pin would run the whole solve in float32)
    pin = np.zeros(po3.shape)
    for i in range(1, n + 1):
        comp = lab == i
        if rim_to_zero and (comp[0, :].any() or comp[-1, :].any()
                            or comp[:, 0].any() or comp[:, -1].any()):
            continue                    # rim-touching: rim value (0)
        # per-source 1D means: a (K, n) axis-1 reduction rounds
        # differently at 1 ulp than the 2D path's flat mean, and the
        # solves amplify it — keep the scalar form
        for k in range(po3.shape[0]):
            pin[k][comp] = float(po3[k][comp].mean())
    return pin[0] if single else pin


def _transport(psi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Divergence-free transport from a stream function."""
    gy_, gx_ = _grad(psi)
    return gy_, -gx_


def _vorticity_blob(cy: float, cx: float, sigma: float, amp: float,
                    shape: tuple[int, int]) -> np.ndarray:
    gy, gx = np.mgrid[0:shape[0], 0:shape[1]].astype(float)
    return amp * np.exp(-((gy - cy) ** 2 + (gx - cx) ** 2)
                        / (2.0 * sigma ** 2))


def _coarse_grids(elev: np.ndarray, ocean_mask: np.ndarray,
                  sea_level: float, f: int
                  ) -> tuple[np.ndarray, np.ndarray]:
    depth_m = -elev_m(elev, sea_level)
    water_c = _pool(ocean_mask.astype(float), f) > 0.5
    # the world-edge rock rim is a magic map boundary, not terrain
    # (_RIM_POROSITY): it must not pin the circulation like a real
    # continent — the coarse water mask runs to the domain edge, and
    # the semi-porous rim condition in _poisson_sor decides how much
    # of the edge flow leaks into the void vs. redirects along it
    water_c[0, :] = water_c[-1, :] = True
    water_c[:, 0] = water_c[:, -1] = True
    depth_c = np.maximum(_pool(depth_m, f), _MIN_DEPTH_M)
    return water_c, depth_c


def _anchor_velocity(psi_blend: np.ndarray, f: int, depth_m: np.ndarray,
                     ocean_mask: np.ndarray
                     ) -> tuple[np.ndarray, np.ndarray]:
    """Coarse blended stream function → anchor velocity: curl,
    upscale, divide by depth (continuity — shelves and straits
    accelerate the flow)."""
    tu, tv = _transport(psi_blend)
    tu = upsample_bicubic(tu, f) / np.clip(depth_m, _MIN_DEPTH_M, None)
    tv = upsample_bicubic(tv, f) / np.clip(depth_m, _MIN_DEPTH_M, None)
    return tu * ocean_mask, tv * ocean_mask


def _solve_sources(sources: list[np.ndarray],
                   water_c: np.ndarray) -> list[np.ndarray]:
    """Per-source stream functions (with per-landmass constants),
    normalized to unit-max transport so the blend weights (not the
    SOR's arbitrary scale) set the mix. One STACKED solve: the
    sources are independent, so they batch into a single SOR loop."""
    zs = np.stack(sources)
    pin = _land_constants(zs, water_c, rim_porosity=_RIM_POROSITY)
    psis = _poisson_sor(zs, water_c, pin=pin,
                        rim_porosity=_RIM_POROSITY)
    tmax = np.hypot(*_transport(psis)).max(axis=(-2, -1))
    return [psis[k] / max(float(tmax[k]), 1e-9)
            for k in range(len(sources))]


def _blend(psis: list[np.ndarray], weights: list[float],
           strengths: np.ndarray | None = None) -> np.ndarray:
    out = np.zeros_like(psis[0])
    for k, (psi, w) in enumerate(zip(psis, weights)):
        s = 1.0 if strengths is None else strengths[k]
        out = out + w * s * psi
    return out


def velocity_field(currents: dict, month: int = 6,
                   depth_m: np.ndarray | None = None,
                   ocean_mask: np.ndarray | None = None
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Seasonal velocity: each vorticity seed's strength breathes
    +-30% with its K1-drawn phase; the wind source is steady. The
    blend is normalized by the annual-reference vmax."""
    import math
    n_gyres = len(currents["gyres"])
    strengths = np.array([
        1.0 + 0.3 * math.cos(2 * math.pi * (month + phase) / 12.0)
        for _, _, _, _, phase in currents["gyres"]]
        + [1.0] * (len(currents["psi"]) - n_gyres))
    weights = list(currents["weights"])
    ramp = currents.get("ramp")
    if ramp is not None:
        # seasonal direction jitter: rotate the through-flow around
        # its seeded prevailing direction (no re-solve — the ramp
        # pair spans every direction by linearity)
        th = ramp["theta"] + ramp["jitter"] * math.sin(
            2.0 * math.pi * (month + ramp["phase"]) / 12.0)
        weights[ramp["i0"]] = ramp["strength"] * math.cos(th)
        weights[ramp["i0"] + 1] = ramp["strength"] * math.sin(th)
    psi = _blend(currents["psi"], weights, strengths)
    if depth_m is None:
        depth_m = currents["depth_m"]
    if ocean_mask is None:
        ocean_mask = currents["ocean_mask"]
    u, v = _anchor_velocity(psi, currents["factor"], depth_m, ocean_mask)
    return u / max(currents["vmax"], 1e-9), v / max(currents["vmax"], 1e-9)


def _finish(currents: dict, elev: np.ndarray, ocean_mask: np.ndarray,
            sea_level: float) -> dict:
    """(Re)build the annual-reference velocity, vmax and upwelling
    rise from the current source set."""
    depth_m = -elev_m(elev, sea_level)
    psi = _blend(currents["psi"], currents["weights"])
    u, v = _anchor_velocity(psi, currents["factor"], depth_m, ocean_mask)
    vmax = float(np.hypot(u, v).max())
    u, v = u / max(vmax, 1e-9), v / max(vmax, 1e-9)
    # upwelling: depth DECREASING along the flow = water rising
    ddx, ddy = _grad(depth_m)
    rise = np.maximum(0.0, -(u * ddx + v * ddy)) * ocean_mask
    currents.update(u=u, v=v, rise=rise, vmax=vmax, depth_m=depth_m,
                    ocean_mask=ocean_mask)
    return currents


def build_currents(elev: np.ndarray, ocean_mask: np.ndarray,
                   sea_level: float, seed: int = 0,
                   min_center_depth_m: float = 800.0,
                   min_center_sep: int = 60,
                   coarse: int = 64) -> dict:
    """Absolute vorticity-seeded gyre field (pre-wind — see module
    docstring; refine_currents adds the wind correlation later).

    Vorticity blob centers are spaced deep-ocean cells; each blob's
    sign/width/strength and seasonal phase are one-time K1 draws. The
    Poisson solve runs at `coarse`² — gyres are huge, the coastline
    detail returns when the transport meets the anchor bathymetry.
    """
    stream = Stream(seed, "k11.currents")
    H, W = elev.shape
    f = max(1, H // coarse)
    depth_m = -elev_m(elev, sea_level)
    deep = ocean_mask & (depth_m > min_center_depth_m)
    ys, xs = np.where(deep)
    # spaced random centers: stream-keyed shuffle, greedy spacing
    keys = np.array([stream.uniform(0, i) for i in range(len(ys))])
    order = np.argsort(keys)
    centers: list[tuple[int, int]] = []
    for i in order.tolist():
        y, x = int(ys[i]), int(xs[i])
        if all((y - cy) ** 2 + (x - cx) ** 2 >= min_center_sep ** 2
               for cy, cx in centers):
            centers.append((y, x))
        if len(centers) >= 4 + int(3.0 * stream.uniform(1, 0)):
            break
    gyres = []
    sources = []
    for k, (cy, cx) in enumerate(centers):
        sigma = 30.0 + 40.0 * stream.uniform(2 + k, 0)
        amp = (0.5 + stream.uniform(2 + k, 1)) * (
            1.0 if stream.uniform(2 + k, 2) < 0.5 else -1.0)
        phase = 12.0 * stream.uniform(2 + k, 3)   # seasonal wobble phase
        gyres.append((cy, cx, sigma, amp, phase))
        sources.append(_vorticity_blob(cy / f, cx / f, sigma / f, amp,
                                       (H // f, W // f)))
    water_c, _ = _coarse_grids(elev, ocean_mask, sea_level, f)
    psis = _solve_sources(sources, water_c)

    # through-flow: the circulation arriving from beyond the map —
    # enters from a seeded side (ANY direction, no hardcoded axis),
    # bends around the landmasses, leaves across the porous rim. Two
    # orthogonal unit Dirichlet-ramp solves; by linearity any
    # direction is a cos/sin blend of them, so the seeded prevailing
    # direction AND the seasonal direction jitter cost no re-solve
    # (velocity_field rotates the pair's weights per month).
    import math
    pc, pw = water_c.shape
    zero = np.zeros((2, pc, pw))
    ramps = np.stack([coord.astype(float) / max(coord.max(), 1.0)
                      for coord in np.mgrid[0:pc, 0:pw]])
    pin = _land_constants(zero, water_c, psi_open=ramps,
                          rim_to_zero=False)
    psi_r = _poisson_sor(zero, water_c, pin=pin, rim_values=ramps)
    tmax = np.hypot(*_transport(psi_r)).max(axis=(-2, -1))
    ramp_psis = [psi_r[k] / max(float(tmax[k]), 1e-9) for k in range(2)]
    theta = 2.0 * math.pi * stream.uniform(6, 0)      # any side
    strength = 0.8 + 0.4 * stream.uniform(6, 1)
    ramp = {"i0": len(psis), "theta": theta, "strength": strength,
            "jitter": 0.35, "phase": 12.0 * stream.uniform(6, 2)}
    currents = {"gyres": gyres, "psi": psis + ramp_psis,
                "weights": [1.0] * len(sources)
                + [strength * math.cos(theta),
                   strength * math.sin(theta)],
                "ramp": ramp,
                "factor": f, "n_gyres": len(centers)}
    out = _finish(currents, elev, ocean_mask, sea_level)
    # metric scale: the world's max current speed in m/s, wiggled
    # around CURRENT_VMAX_MS (boundary-current peak ~1.5) — seeded,
    # leaky-capped, so worlds vary but stay physical
    from exp.k11_worldgen.units import CURRENT_VMAX_MS, wiggle_metric
    out["vmax_ms"] = wiggle_metric(stream.child("metric"),
                                   CURRENT_VMAX_MS, 0.5, 0.3)
    return out


def refine_currents(currents: dict, elev: np.ndarray,
                    ocean_mask: np.ndarray, sea_level: float,
                    climate: dict,
                    wind_weight: float = _WIND_FORCING_WEIGHT) -> dict:
    """Conditioning-pass refinement: add the curl of the world's OWN
    mean annual surface wind (the mean of the delivered weather
    pattern — nothing invented) as a vorticity source, and rebuild
    the annual field. Pass-2 climate and the aquatic layer read this
    refined field, so the currents correlate with the atmospheric
    circulation instead of ignoring it."""
    wu = climate["wind_u"].mean(axis=(0, 1))
    wv = climate["wind_v"].mean(axis=(0, 1))
    zeta_w = _grad(wv)[0] - _grad(wu)[1]          # wind-stress curl
    f = currents["factor"]
    # pool the wind curl from the climate grid down to the psi grid
    g = wu.shape[0] // (ocean_mask.shape[0] // f)
    zeta_c = _pool(zeta_w, g) if g > 1 else zeta_w
    water_c, _ = _coarse_grids(elev, ocean_mask, sea_level, f)
    pin = _land_constants(zeta_c, water_c, rim_porosity=_RIM_POROSITY)
    psi_w = _poisson_sor(zeta_c, water_c, pin=pin,
                         rim_porosity=_RIM_POROSITY)
    tmax = float(np.hypot(*_transport(psi_w)).max())
    # keep the seeds-only normalization around: the loading screen's
    # pass-1/pass-2 current stages both render from the one dict
    currents["vmax_seeds"] = currents["vmax"]
    currents["psi"] = currents["psi"] + [psi_w / max(tmax, 1e-9)]
    currents["weights"] = currents["weights"] + [wind_weight]
    return _finish(currents, elev, ocean_mask, sea_level)


def velocity_ms(currents: dict, month: int = 6
                ) -> tuple[np.ndarray, np.ndarray]:
    """Surface current velocity in M/S: velocity_field's relative
    field scaled by the world's seeded max (vmax_ms — around
    CURRENT_VMAX_MS, see units.wiggle_metric). This is the metric
    store downstream consumers (ecology, gameplay) should read."""
    from exp.k11_worldgen.units import CURRENT_VMAX_MS
    u, v = velocity_field(currents, month)
    s = currents.get("vmax_ms", CURRENT_VMAX_MS)
    return u * s, v * s


def rise_monthly(currents: dict) -> np.ndarray:
    """Upwelling rise per month, (12, H, W) float32: the seasonal-
    breathing velocity fields' vertical-motion field. This is the
    nutrient-circulation store for downstream kernels (ecology reads
    where deep water surfaces, and that place moves with the
    seasons)."""
    depth_m = currents["depth_m"]
    ddx, ddy = _grad(depth_m)
    oc = currents["ocean_mask"]
    out = np.zeros((12, *depth_m.shape), dtype=np.float32)
    for m in range(12):
        u, v = velocity_field(currents, m)
        out[m] = np.maximum(0.0, -(u * ddx + v * ddy)) * oc
    return out


def advect_sst(t_base_c: np.ndarray, u: np.ndarray, v: np.ndarray,
               rise: np.ndarray,
               steps: int = 48, relax: float = 0.02,
               diffuse_passes: int = 3) -> np.ndarray:
    """Sea-surface temperature (metric degC) from a latitude baseline.

    Semi-Lagrangian advection along the gyre flow with thermostat
    relaxation, upwelling cooling toward the deep-water temperature
    (a bounded relaxation driven by the RELATIVE rise — see _UPW_MIX),
    and a few coarse diffusion passes at the end.
    """
    H, W = t_base_c.shape
    gy, gx = np.mgrid[0:H, 0:W].astype(float)
    nz = rise[rise > 0]
    ref = float(np.percentile(nz, 95)) if nz.size else 1.0
    rr = 1.0 - np.exp(-rise / max(ref, 1e-9))
    T = t_base_c.copy()
    for _ in range(steps):
        T = _bilinear(T, gx - u, gy - v)
        T = T + relax * (t_base_c - T)     # thermostat: local equilibrium
        T = T + _UPW_MIX * rr * (_T_DEEP_C - T)
    for _ in range(diffuse_passes):
        p = np.pad(T, 1, mode="edge")
        T = sum(p[dy:dy + H, dx:dx + W]
                for dy in range(3) for dx in range(3)) / 9.0
    return T
