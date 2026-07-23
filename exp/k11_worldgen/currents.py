"""K11 — ocean currents: gyre streams, sea-surface temperature, upwelling.

Spawned right after hydrology as an ABSOLUTE geographic feature (K1
draws, never re-rolled): a few gyres in deep water, rotation and
strength random (fantasy world — no Earth-clone rule that outer bands
must run a certain way), riding on a fraction of the mean annual
low-layer wind (surface currents are wind-driven — Ekman drift — so
the streams correlate with the persistent circulation instead of
ignoring it). The velocity field is the curl of a Gaussian
stream function per gyre (divergence-free, calm eye, strongest flow at
the rim).

The raw gyre field knows nothing about land, so processing gives it
the same treatment wind gets over terrain, hardened for water:

- SLIP WALL: at coast cells the into-land momentum component is
  projected out — the stream bends and runs ALONG the shore (boundary
  currents) instead of stopping dead at the mask.
- LEE SHADOW: the removed momentum is transported downstream with the
  flow and damps it — a stream that struck a peninsula does not resume
  full strength in the lee. (Same deficit-advection idea as the wind
  lee wake.)
- Depth damping (currents are deep-water streams) and the land mask
  finish the field. Both the annual reference and every monthly
  (seasonal-breathing) field pass through the SAME pipeline.

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

from exp.k11_worldgen.climate import _bilinear, _grad, lee_shadow
from exp.k11_worldgen.units import elev_m

# deep water mixed up by rising streams
_T_DEEP_C = 4.0

# land treatment of the raw gyre field (see module docstring)
_SLIP_SMOOTH = 2        # smoothing passes for a stable coast normal
_SHADOW_STEPS = 24      # downstream transport of the blocked deficit
_SHADOW_RECHARGE = 0.25 # the coast keeps feeding its own shadow
_SHADOW_DECAY = 0.05    # tail ~20 cells — a peninsula's lee, not a sea's
_SHADOW_DAMP = 0.8      # speed floor inside a full shadow


def _slip_boundary(u: np.ndarray, v: np.ndarray,
                   ocean_mask: np.ndarray
                   ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project out the into-land momentum at coast cells (a SLIP wall —
    water runs along the shore, not through it). Returns the deflected
    field and the removed component (the blockage source for the lee
    shadow)."""
    land = (~ocean_mask).astype(float)
    H, W = land.shape
    for _ in range(_SLIP_SMOOTH):
        p = np.pad(land, 1, mode="edge")
        land = sum(p[dy:dy + H, dx:dx + W]
                   for dy in range(3) for dx in range(3)) / 9.0
    nx, ny = _grad(land)
    norm = np.hypot(nx, ny) + 1e-9
    nx, ny = nx / norm, ny / norm
    into = np.maximum(u * nx + v * ny, 0.0)
    return u - into * nx, v - into * ny, into


def _lee_shadow(u: np.ndarray, v: np.ndarray,
                source: np.ndarray) -> np.ndarray:
    """Current-flavored wrapper of the shared deficit advection
    (climate.lee_shadow) with the current-tuned constants."""
    return lee_shadow(u, v, source, _SHADOW_STEPS,
                      _SHADOW_RECHARGE, _SHADOW_DECAY)


def _process(u: np.ndarray, v: np.ndarray, depth_m: np.ndarray,
             ocean_mask: np.ndarray, vmax: float | None = None
             ) -> tuple[np.ndarray, np.ndarray, float]:
    """The full land treatment + normalization, shared by the annual
    reference (vmax=None: compute and return it) and every monthly
    field (vmax given) so all months see identical land behavior."""
    u, v, into = _slip_boundary(u, v, ocean_mask)
    # shadow source relative to the world's own typical current, so a
    # lazy drift cannot cast as hard a shadow as a real stream
    ref = max(float(np.percentile(np.hypot(u, v)[ocean_mask], 99)),
              1e-9) if ocean_mask.any() else 1.0
    shadow = _lee_shadow(u, v, np.clip(into / ref, 0.0, 1.0))
    damp = np.clip(depth_m / 300.0, 0.15, 1.0) * (1.0 - _SHADOW_DAMP
                                                  * shadow)
    u = u * damp * ocean_mask
    v = v * damp * ocean_mask
    if vmax is None:
        vmax = float(np.hypot(u, v).max())
    u = u / max(vmax, 1e-9)
    v = v / max(vmax, 1e-9)
    return u, v, vmax


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
    per-gyre phase (K1-drawn at spawn), then the SAME land treatment
    the annual reference got (slip wall, lee shadow, depth damping,
    mask) and normalization by the annual vmax. Month 6 = the
    annual-mean reference the normalization was computed against."""
    import math
    gyres = currents["gyres"]
    strength = np.array([
        1.0 + 0.3 * math.cos(2 * math.pi * (month + phase) / 12.0)
        for _, _, _, _, phase in gyres])
    u, v = _gyre_field([(cy, cx, sigma, amp)
                        for cy, cx, sigma, amp, _ in gyres],
                       currents["u"].shape, strength)
    if currents.get("drift") is not None:
        u = u + currents["drift"][0]
        v = v + currents["drift"][1]
    if depth_m is None:
        depth_m = currents["depth_m"]
    if ocean_mask is None:
        ocean_mask = currents["ocean_mask"]
    u, v, _ = _process(u, v, depth_m, ocean_mask, vmax=currents["vmax"])
    return u, v


def build_currents(elev: np.ndarray, ocean_mask: np.ndarray,
                   sea_level: float, seed: int = 0,
                   min_center_depth_m: float = 800.0,
                   min_center_sep: int = 60,
                   wind_drift: tuple[np.ndarray, np.ndarray] | None = None,
                   drift_coeff: float = 0.25) -> dict:
    """Gyre velocity field (u, v, ~1 cell/step max) + upwelling rise.

    Gyre centers are spaced deep-ocean cells; each gyre's tangential
    speed peaks at one sigma from the eye. The raw field is then given
    the land treatment (`_process`): a slip wall at coasts (streams
    bend along shores), a lee shadow (streams that struck land stay
    weakened downstream), depth damping and the mask. `wind_drift` is
    the mean annual low-layer wind at this grid: surface currents are
    wind-driven (Ekman drift — westerlies push drift currents, trades
    push equatorial ones), so the drawn gyres ride on a fraction of
    the prevailing wind instead of ignoring it. Everything downstream
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
    u, v = _gyre_field([(cy, cx, sigma, amp)
                        for cy, cx, sigma, amp, _ in gyres], (H, W))
    drift_u = drift_v = 0.0
    if wind_drift is not None:
        drift_u, drift_v = wind_drift
        u = u + drift_coeff * drift_u
        v = v + drift_coeff * drift_v
    u, v, vmax = _process(u, v, depth_m, ocean_mask)
    # upwelling: depth DECREASING along the (deflected, shadowed) flow
    # = water rising
    ddx, ddy = _grad(depth_m)
    rise = np.maximum(0.0, -(u * ddx + v * ddy)) * ocean_mask
    return {"u": u, "v": v, "rise": rise, "n_gyres": len(centers),
            "gyres": gyres, "vmax": vmax, "depth_m": depth_m,
            "ocean_mask": ocean_mask,
            "drift": (drift_coeff * drift_u, drift_coeff * drift_v)
            if wind_drift is not None else None}


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
