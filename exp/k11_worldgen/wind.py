"""K11 surface/middle wind: a two-layer rigid-lid fluid.

Replaces the kinematic WindLibrary (prescribed bands + random gyres +
stapled divergence terms) with a momentum-conserving model:

SURFACE layer — the weather. Semi-Lagrangian momentum advection,
thermal pressure forcing (hot = low), constant-f Coriolis (flat
world), Brinkman terrain/forest drag, and a pressure projection to a
TARGET divergence (the vertical-motion budget), never to zero.

MIDDLE layer — mass compensation only. No thermal forcing, no
terrain drag. Rigid-lid closure div(H_S*u_s + H_M*u_m) = 0, so the
interface vertical velocity is w = -H_S*div(u_s) = H_M*div(u_m).
Middle-layer convergence = descent into the surface column (the
subsidence seed the high-layer highway transports); middle-layer
divergence = ascent below.

Terrain is continuous everywhere: Brinkman drag -u/K(x) with K from
local relief (a foothill and an escarpment are not the same object),
and terrain lifting enters the target divergence as -(u.grad h)/H_EFF
(upslope convergence, downslope foehn divergence). Trees are
windbreaks: canopy cover adds to the surface drag field, surface
layer only.

Momentum budget: sources are the thermal pressure force and rim
inflow; sinks are ground drag (terrain form drag, canopy) and rim
outflow; Coriolis and the projection redistribute. Rising air carries
surface momentum into the middle layer, subsiding air brings it back
(interfacial exchange proportional to w).

The pressure projection is EXACT: backward-difference divergence +
forward-difference gradient compose to the textbook 5-point
Laplacian, solved spectrally (DST via FFT, Dirichlet-zero rim — the
rim is porous, normal flow passes uncorrected). Determinism: every
random input comes from the K1 stream.
"""
from __future__ import annotations

import math

import numpy as np

from kernel.hashrng import Stream
from exp.k11_worldgen.raster import fbm

# layer depths (ratio is what matters): the middle layer is the deeper
# one — surface convergence of a given strength drives a weaker (and
# smoother) return flow aloft, like the real boundary layer vs the
# free troposphere
H_S, H_M = 1.0, 3.0
# Coriolis parameter per step (f*dt in velocity units): strong enough
# that convergence winds up into rotation within ~10 steps (a weather
# system lifetime), weak enough that straight monsoon/monsoon-like
# flows still exist. Seeded sign + wiggle per world.
_CORIOLIS = 0.15
# thermal pressure coupling: velocity kicked per step per unit
# T-anomaly gradient (normalized T per cell). With synoptic-scale
# anomalies ~0.1 over ~10 cells this yields drift speeds ~0.1-0.3
# cells/step — the same order as the advection speed
_THERMAL_ALPHA = 4.0
# Brinkman drag rates per step (u *= 1/(1 + nu)):
_NU_WATER = 0.01      # open water: nearly free
_NU_LAND = 0.05       # lowland roughness
# relief drag: full local relief (ELEV range within the relief
# window) adds _NU_RELIEF — an escarpment core (relief ~half the
# world span inside one window) gets nu ~ 4 (momentum dies in a few
# steps, near-solid), a mid-slope gets ~1 (strong deflection), a
# foothill ~0.1 (felt, crossed)
_NU_RELIEF = 8.0
# the relief amplitude (as a fraction of the world's height range)
# that earns full relief drag — ABSOLUTE, not normalized per world:
# ~a quarter of the range (~1.5 km) of local relief inside the
# window is a serious barrier; a 100 m hill is not, whatever the
# world's tallest mountain is
_RELIEF_DRAG_SPAN = 0.25
_NU_FOREST = 0.5      # canopy: a strong windbreak, not a wall
_NU_MID = 0.005       # middle layer: slow spin-down only
# terrain-lifting depth: the slope length over which forced ascent
# converges the surface column — small enough that a few-% slope at
# channel speed produces divergence well above numerical noise
_H_EFF = 10.0
# buoyancy divergence: hot anomaly -> ascent -> surface convergence.
# Same order as the terrain term for a mid-strength anomaly
_BUOY_D = 0.5
# interfacial momentum exchange: the fraction of the layer-momentum
# difference transferred per unit of vertical motion per step
_EXCH = 0.5
# synoptic smoothing of the thermal forcing (box passes): pressure
# gradients are synoptic, not cell-scale
_T_SMOOTH = 3
# relief window (cells) for the Brinkman relief amplitude
_RELIEF_WINDOW = 7


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


def _grad_c(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Central-difference gradients (zeros at the border)."""
    gx = np.zeros_like(a)
    gy = np.zeros_like(a)
    gx[:, 1:-1] = (a[:, 2:] - a[:, :-2]) / 2
    gy[1:-1, :] = (a[2:, :] - a[:-2, :]) / 2
    return gx, gy


def _div_b(u: np.ndarray, v: np.ndarray) -> np.ndarray:
    """BACKWARD-difference divergence: div(i,j) = (u(i,j)-u(i,j-1)) +
    (v(i,j)-v(i-1,j)). Pairs with _grad_f to compose the exact
    5-point Laplacian (MAC consistency — the projection is exact)."""
    du = np.zeros_like(u)
    dv = np.zeros_like(v)
    du[:, 1:] = u[:, 1:] - u[:, :-1]
    dv[1:, :] = v[1:, :] - v[:-1, :]
    return du + dv


def _grad_f(a: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """FORWARD-difference gradient: gx(i,j) = a(i,j+1)-a(i,j),
    gy(i,j) = a(i+1,j)-a(i,j)."""
    gx = np.zeros_like(a)
    gy = np.zeros_like(a)
    gx[:, :-1] = a[:, 1:] - a[:, :-1]
    gy[:-1, :] = a[1:, :] - a[:-1, :]
    return gx, gy


def _box3(a: np.ndarray, passes: int = 1) -> np.ndarray:
    """3x3 box smoothing, edge-padded, `passes` times."""
    for _ in range(passes):
        p = np.pad(a, 1, mode="edge")
        a = (sum(p[dy:dy + a.shape[0], dx:dx + a.shape[1]]
                 for dy in range(3) for dx in range(3)) / 9.0)
    return a


def _poisson_solve(rhs: np.ndarray) -> np.ndarray:
    """Solve the 5-point Laplacian L phi = rhs on the INTERIOR with
    phi = 0 on the rim (Dirichlet — a porous rim: the correction has
    no prescribed normal component there, flow passes uncorrected).
    Exact spectral solve via a DST-I built on an odd-extension FFT
    (no scipy): eigenvalues 2cos(pi k/(N+1)) - 2 per axis."""
    interior = rhs[1:-1, 1:-1]
    ny, nx = interior.shape

    def dst1(x: np.ndarray, axis: int) -> np.ndarray:
        n = x.shape[axis]
        ext = [slice(None)] * x.ndim
        shape = list(x.shape)
        shape[axis] = 2 * (n + 1)
        y = np.zeros(shape, dtype=x.dtype)
        ext[axis] = slice(1, n + 1)
        y[tuple(ext)] = x
        ext[axis] = slice(n + 2, 2 * (n + 1))
        y[tuple(ext)] = -np.flip(x, axis=axis)
        Y = np.fft.fft(y, axis=axis)
        ext[axis] = slice(1, n + 1)
        return (-Y.imag[tuple(ext)]) / 2.0

    ky = 2.0 * np.cos(np.pi * np.arange(1, ny + 1) / (ny + 1)) - 2.0
    kx = 2.0 * np.cos(np.pi * np.arange(1, nx + 1) / (nx + 1)) - 2.0
    lam = ky[:, None] + kx[None, :]
    phi_i = dst1(dst1(dst1(dst1(interior, 0), 1) / lam, 0), 1)
    # DST-I is its own inverse up to a factor: idst = dst * 2/(N+1)
    # per dimension (applied twice above the division — normalize)
    phi_i = phi_i * (2.0 / (ny + 1)) * (2.0 / (nx + 1))
    phi = np.zeros_like(rhs)
    phi[1:-1, 1:-1] = phi_i
    return phi


class WindModel:
    """Two-layer rigid-lid wind on a regular grid.

    h: normalized elevation (0..1 over the world's height range) on
    the wind grid. water: boolean mask. green: optional 0..1 canopy
    cover (pass 2 — trees are windbreaks in the surface drag field).
    drive: (fx, fy) constant background force — the large-scale
    pressure gradient of the surrounding atmosphere (the general
    circulation's momentum source; a rim velocity hold alone cannot
    sustain flow against drag — pressure work does). bc_u/bc_v:
    optional rim velocity hold (default calm/porous)."""

    def __init__(self, stream: Stream, h: np.ndarray, water: np.ndarray,
                 green: np.ndarray | None = None,
                 coriolis: float | None = None,
                 drive: tuple[float, float] = (0.0, 0.0),
                 bc_u: np.ndarray | None = None,
                 bc_v: np.ndarray | None = None) -> None:
        h = np.asarray(h, dtype=np.float32)
        self.h = h
        self.water = np.asarray(water, bool)
        H, W = h.shape
        self.shape = (H, W)
        gy, gx = np.mgrid[0:H, 0:W].astype(np.float32)
        self._gx, self._gy = gx, gy
        self.rim = np.zeros((H, W), bool)
        self.rim[0, :] = self.rim[-1, :] = True
        self.rim[:, 0] = self.rim[:, -1] = True

        # Coriolis: seeded sign (hemisphere analog) + strength wiggle
        if coriolis is None:
            sgn = 1.0 if stream.uniform(0, 60) < 0.5 else -1.0
            coriolis = sgn * _CORIOLIS * (0.7 + 0.6 * stream.uniform(0, 61))
        self.f = float(coriolis)
        self.fx, self.fy = float(drive[0]), float(drive[1])

        # Brinkman drag field (surface): water/land base + continuous
        # relief amplitude (local max-min over the relief window of
        # smoothed terrain — a foothill and an escarpment are not the
        # same object) + canopy cover
        from numpy.lib.stride_tricks import sliding_window_view
        sm = _box3(h, 2)
        w = min(_RELIEF_WINDOW, min(H, W) // 2 * 2 + 1)
        ap = np.pad(sm, w // 2, mode="edge")
        sw = sliding_window_view(ap, (w, w))[:H, :W]
        relief = sw.max(axis=(-2, -1)) - sw.min(axis=(-2, -1))
        nu = np.where(self.water, _NU_WATER, _NU_LAND).astype(np.float32)
        nu = nu + _NU_RELIEF * (relief / _RELIEF_DRAG_SPAN)
        if green is not None:
            nu = nu + _NU_FOREST * np.asarray(green, dtype=np.float32)
        self.nu = nu
        # smoothed terrain gradient for the lifting term
        self.dhx, self.dhy = _grad_c(_box3(h, 3))

        # state: surface + middle horizontal velocities
        self.u_s = np.zeros((H, W), dtype=np.float32)
        self.v_s = np.zeros((H, W), dtype=np.float32)
        self.u_m = np.zeros((H, W), dtype=np.float32)
        self.v_m = np.zeros((H, W), dtype=np.float32)
        # rim boundary condition: None = FREE rim (porous — velocity
        # is whatever the dynamics produce, the projection's
        # Dirichlet-zero pressure lets normal flow pass); a given
        # array is held every step (a prescribed inflow wall)
        self.bc_u = (None if bc_u is None
                     else np.asarray(bc_u, dtype=np.float32))
        self.bc_v = (None if bc_v is None
                     else np.asarray(bc_v, dtype=np.float32))
        # the last target-divergence field (the vertical-motion budget:
        # D > 0 = descent into the surface column, D < 0 = ascent)
        self.D = np.zeros((H, W), dtype=np.float32)

    # -- one momentum step ------------------------------------------------

    def _step_layer(self, u: np.ndarray, v: np.ndarray,
                    nu: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Advect momentum semi-Lagrangian, Coriolis-rotate, Brinkman
        drag. Shared by both layers (forcing and the projection are
        applied by the caller — they couple the layers). The tanh
        speed shape is the numerical governor: identity at weather
        speeds, asymptotic at the top — a runaway cell brakes instead
        of exploding (semi-Lagrangian is stable at any step, but a
        garbage trajectory is still garbage)."""
        u = _bilinear(u, self._gx - u, self._gy - v)
        v = _bilinear(v, self._gx - u, self._gy - v)
        u, v = u + self.f * v, v - self.f * u
        fac = (1.0 / (1.0 + nu)).astype(np.float32)
        u, v = u * fac, v * fac
        sp = np.hypot(u, v)
        cap = 2.0 * np.tanh(sp / 2.0) / np.maximum(sp, 1e-9)
        return u * cap, v * cap

    def _project(self, u: np.ndarray, v: np.ndarray,
                 target: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Pressure projection to TARGET divergence (not zero): solve
        L phi = div(u) - target, subtract the forward gradient. The
        physical divergence (terrain lifting, buoyancy) survives; the
        acoustic/numerical part is removed."""
        rhs = _div_b(u, v) - target
        phi = _poisson_solve(rhs)
        gx, gy = _grad_f(phi)
        return u - gx, v - gy

    def step(self, T_anom: np.ndarray) -> None:
        """One momentum step against the given normalized temperature
        ANOMALY field (wind grid). Rim velocities are held at the
        boundary condition afterwards (the porous rim)."""
        T = _box3(np.asarray(T_anom, dtype=np.float32), _T_SMOOTH)
        # thermal pressure force: hot = LOW pressure, so the force is
        # +ALPHA * grad(T) (air flows INTO the heat) — plus the
        # constant background drive (the surrounding circulation's
        # pressure gradient). BOTH layers feel the synoptic pressure
        # field — terrain and canopy drag are what differ between
        # them, not the drive
        px, py = _grad_c(T)
        for u, v in ((self.u_s, self.v_s), (self.u_m, self.v_m)):
            u += _THERMAL_ALPHA * px + self.fx
            v += _THERMAL_ALPHA * py + self.fy
        # advect + Coriolis + drag, per layer
        self.u_s, self.v_s = self._step_layer(self.u_s, self.v_s, self.nu)
        self.u_m, self.v_m = self._step_layer(self.u_m, self.v_m,
                                              np.full_like(self.nu, _NU_MID))
        # interfacial momentum exchange (driven by the PREVIOUS step's
        # vertical motion; runs before the projection so the column
        # closure is restored afterwards): w = -H_S * D, ascent > 0.
        # Rising air carries surface momentum up, subsiding air brings
        # middle-layer momentum down. The w/(w+1) shape bounds the
        # transfer fraction below 1 — a strong plume relaxes toward
        # equilibrium instead of overshooting (numerical stability,
        # asymptotic not a hard cap)
        w = -H_S * self.D
        up = _EXCH * np.clip(w, 0.0, None)
        down = _EXCH * np.clip(-w, 0.0, None)
        up = up / (1.0 + up)
        down = down / (1.0 + down)
        self.u_m = self.u_m + _EXCH * up * (self.u_s - self.u_m)
        self.v_m = self.v_m + _EXCH * up * (self.v_s - self.v_m)
        self.u_s = self.u_s + _EXCH * down * (self.u_m - self.u_s)
        self.v_s = self.v_s + _EXCH * down * (self.v_m - self.v_s)
        # target divergence: terrain lifting + buoyancy (hot ascends).
        # The buoyancy term is SPATIALLY zero-mean: ascent over hot
        # spots is balanced by broad weak descent everywhere else (the
        # Hadley cell closes — net vertical motion over the map is 0)
        lift = (self.u_s * self.dhx + self.v_s * self.dhy) / _H_EFF
        D = (-lift - _BUOY_D * (T - float(T.mean()))).astype(np.float32)
        # project surface to div = D, middle to the rigid-lid
        # compensation div = -(H_S/H_M) D
        self.u_s, self.v_s = self._project(self.u_s, self.v_s, D)
        self.u_m, self.v_m = self._project(self.u_m, self.v_m,
                                           -(H_S / H_M) * D)
        self.D = D
        # porous rim: if a boundary condition was prescribed, hold it
        # (both layers share the large-scale through-flow boundary);
        # otherwise the rim is free
        if self.bc_u is not None:
            for u, bc in ((self.u_s, self.bc_u), (self.v_s, self.bc_v),
                          (self.u_m, self.bc_u), (self.v_m, self.bc_v)):
                u[self.rim] = bc[self.rim]

    def snapshot(self, stream: Stream, clock: int, T_anom: np.ndarray,
                 n_steps: int = 16) -> dict:
        """Advance n_steps and return the surface wind + the
        vertical-motion field. The state carries over between
        snapshots (a continuous trajectory — the weather pattern).
        Each snapshot opens with a small ROTATIONAL kick (curl of a
        K1 noise field — divergence-free, so it never fights the
        projection): the weather systems' chaotic variability."""
        if _KICK > 0.0:
            k = fbm(stream.child(f"kick.{clock}"), self.shape,
                    base_cell=8, octaves=2)
            k = k - float(k.mean())
            kx, ky = _grad_c(k)
            spd = float(np.hypot(self.u_s, self.v_s).mean())
            self.u_s = self.u_s + _KICK * spd * ky
            self.v_s = self.v_s - _KICK * spd * kx
        for _ in range(n_steps):
            self.step(T_anom)
        return {"u_s": self.u_s.copy(), "v_s": self.v_s.copy(),
                "u_m": self.u_m.copy(), "v_m": self.v_m.copy(),
                "D": self.D.copy()}


# per-snapshot rotational kick strength (fraction of the current mean
# surface speed): the trajectory's chaotic jitter — big enough that
# adjacent snapshots are distinct weather, small enough that the
# monthly mean keeps the season's structure
_KICK = 0.5


class Highway:
    """The HIGH layer (free troposphere): a non-interacting flow
    aloft — it transports the subsidence plumes and touches nothing
    else. Blended fbm stream functions (phase-jittered per clock)
    plus a weak seeded return drift; no terrain, no drag, no
    coupling. (This is the same role the old WindLibrary's
    sample_high played; the surface two-layer fluid replaces
    everything else.)"""

    def __init__(self, stream: Stream, shape: tuple[int, int],
                 n_src: int = 3) -> None:
        H, W = shape
        self.shape = shape
        self.psi = [fbm(stream.child(f"high.{k}"), shape,
                        base_cell=max(8, W // 3), octaves=3)
                    for k in range(n_src)]
        # weak large-scale drift (the return flow aloft): seeded
        # direction, small against the gyres
        ang = 2.0 * math.pi * stream.uniform(0, 80)
        self.drift = (0.25 * math.cos(ang), 0.25 * math.sin(ang))

    def sample(self, stream: Stream, clock: int
               ) -> tuple[np.ndarray, np.ndarray]:
        psi = np.zeros(self.shape, dtype=np.float32)
        for k, p in enumerate(self.psi):
            # phase-jittered rolls: the aloft systems wander like the
            # surface ones but share nothing with them
            a = 0.4 + 0.6 * stream.uniform(clock, 30 + k)
            q = int(3 * stream.uniform(clock, 40 + k))
            psi = psi + a * np.roll(p, (q, q), axis=(0, 1))
        gu, gv = _grad_c(psi)
        return (gv + self.drift[0], -gu + self.drift[1])
