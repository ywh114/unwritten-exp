"""K11 — ocean currents: gyre streams, sea-surface temperature, upwelling.

Spawned right after elevation as an ABSOLUTE geographic feature (K1
draws, never re-rolled): a few gyres in deep water, rotation and
strength random (fantasy world — no Earth-clone rule that outer bands
must run a certain way). The velocity field is the curl of a Gaussian
stream function per gyre (divergence-free, calm eye, strongest flow at
the rim), damped over shallow shelf — currents are deep-water streams.

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
from exp.k11_worldgen.units import elev_m

# deep water mixed up by rising streams
_T_DEEP_C = 4.0


def _gyre_field(gyres: list[tuple], shape: tuple[int, int],
                strength: np.ndarray | None = None
                ) -> tuple[np.ndarray, np.ndarray]:
    """(u, v) from a list of (cy, cx, sigma, amp) gyres — curl of the
    Gaussian stream functions. `strength` optionally rescales each
    gyre (seasonal wobble)."""
    H, W = shape
    gy, gx = np.mgrid[0:H, 0:W].astype(float)
    u = np.zeros((H, W))
    v = np.zeros((H, W))
    for k, (cy, cx, sigma, amp) in enumerate(gyres):
        a = amp if strength is None else amp * strength[k]
        r2 = (gy - cy) ** 2 + (gx - cx) ** 2
        g = a * np.exp(-r2 / (2.0 * sigma ** 2)) / sigma ** 2
        u += -(gy - cy) * g     # u = dpsi/dy
        v += (gx - cx) * g      # v = -dpsi/dx
    return u, v


def velocity_field(currents: dict, month: int = 6,
                   depth_m: np.ndarray | None = None,
                   ocean_mask: np.ndarray | None = None
                   ) -> tuple[np.ndarray, np.ndarray]:
    """Seasonal velocity: each gyre's strength breathes +-30% with a
    per-gyre phase (K1-drawn at spawn). Month 6 = the annual-mean
    reference the normalization was computed against."""
    import math
    gyres = currents["gyres"]
    strength = np.array([
        1.0 + 0.3 * math.cos(2 * math.pi * (month + phase) / 12.0)
        for _, _, _, _, phase in gyres])
    u, v = _gyre_field([(cy, cx, sigma, amp)
                        for cy, cx, sigma, amp, _ in gyres],
                       currents["u"].shape, strength)
    if depth_m is None:
        depth_m = currents["depth_m"]
    if ocean_mask is None:
        ocean_mask = currents["ocean_mask"]
    damp = np.clip(depth_m / 300.0, 0.15, 1.0)
    u = u * damp * ocean_mask / max(currents["vmax"], 1e-9)
    v = v * damp * ocean_mask / max(currents["vmax"], 1e-9)
    return u, v


def build_currents(elev: np.ndarray, ocean_mask: np.ndarray,
                   sea_level: float, seed: int = 0,
                   min_center_depth_m: float = 800.0,
                   min_center_sep: int = 60) -> dict:
    """Gyre velocity field (u, v, ~1 cell/step max) + upwelling rise.

    Gyre centers are spaced deep-ocean cells; each gyre's tangential
    speed peaks at one sigma from the eye. Everything downstream
    (SST advection, upwelling classes) reads this dict.
    """
    stream = Stream(seed, "k11.currents")
    H, W = elev.shape
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
        if len(centers) >= 2 + int(stream.uniform(1, 0) < 0.5):
            break
    gyres = []
    for k, (cy, cx) in enumerate(centers):
        sigma = 30.0 + 40.0 * stream.uniform(2 + k, 0)
        amp = (0.5 + stream.uniform(2 + k, 1)) * (
            1.0 if stream.uniform(2 + k, 2) < 0.5 else -1.0)
        phase = 12.0 * stream.uniform(2 + k, 3)   # seasonal wobble phase
        gyres.append((cy, cx, sigma, amp, phase))
    damp = np.clip(depth_m / 300.0, 0.15, 1.0)
    u, v = _gyre_field([(cy, cx, sigma, amp)
                        for cy, cx, sigma, amp, _ in gyres], (H, W))
    u = u * damp * ocean_mask
    v = v * damp * ocean_mask
    vmax = float(np.hypot(u, v).max())
    if vmax > 1e-9:
        u, v = u / vmax, v / vmax
    # upwelling: depth DECREASING along the flow = water rising
    ddx, ddy = _grad(depth_m)
    rise = np.maximum(0.0, -(u * ddx + v * ddy)) * ocean_mask
    return {"u": u, "v": v, "rise": rise, "n_gyres": len(centers),
            "gyres": gyres, "vmax": vmax, "depth_m": depth_m,
            "ocean_mask": ocean_mask}


def advect_sst(t_base_c: np.ndarray, u: np.ndarray, v: np.ndarray,
               rise: np.ndarray,
               steps: int = 48, relax: float = 0.02,
               diffuse_passes: int = 3) -> np.ndarray:
    """Sea-surface temperature (metric degC) from a latitude baseline.

    Semi-Lagrangian advection along the gyre flow with thermostat
    relaxation, upwelling cooling toward the deep-water temperature,
    and a few coarse diffusion passes at the end.
    """
    H, W = t_base_c.shape
    gy, gx = np.mgrid[0:H, 0:W].astype(float)
    T = t_base_c.copy()
    for _ in range(steps):
        T = _bilinear(T, gx - u, gy - v)
        T = T + relax * (t_base_c - T)     # thermostat: local equilibrium
        T = T - 0.1 * rise * (T - _T_DEEP_C)
    for _ in range(diffuse_passes):
        p = np.pad(T, 1, mode="edge")
        T = sum(p[dy:dy + H, dx:dx + W]
                for dy in range(3) for dx in range(3)) / 9.0
    return T
