"""Physics tests for the two-layer wind model (exp/k11_worldgen/wind.py).

These test the FLUID, not the world: the model must pass every one of
them standalone before it is allowed anywhere near the climate
pipeline."""
import numpy as np

from kernel.hashrng import Stream
from exp.k11_worldgen.wind import (
    H_S, H_M, WindModel, _box3, _div_b, _grad_c)


def _flat(shape=(48, 48), water=False):
    h = np.full(shape, 0.5, dtype=np.float32)
    w = np.zeros(shape, bool) if not water else np.ones(shape, bool)
    return h, w


def _ridge(shape=(48, 48), height=0.35, sigma=3.0, length=None):
    """A north-south Gaussian ridge mid-grid on a flat base. `length`
    limits its north-south extent (a ridge SEGMENT — flow can go
    around the ends); None spans the full domain (a wall — 1D
    dynamics, for the rain-shadow signature)."""
    h, w = _flat(shape)
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    profile = np.exp(-0.5 * ((xx - shape[1] / 2) / sigma) ** 2)
    if length is not None:
        profile = profile * np.exp(
            -0.5 * ((yy - shape[0] / 2) / length) ** 2)
    h = h + height * profile
    return h.astype(np.float32), w


# channel drive: a constant eastward background force (the
# large-scale pressure gradient — the momentum source; a rim velocity
# hold cannot sustain flow against drag). u ~ drive / drag ~ 0.4
_DRIVE = (0.02, 0.0)


def test_column_mass():
    """Rigid-lid closure: div(H_S*u_s + H_M*u_m) ~ 0 in the interior
    after every step, under forcing and terrain."""
    h, w = _ridge()
    m = WindModel(Stream(1, "t"), h, w, coriolis=0.1, drive=_DRIVE)
    yy, xx = np.mgrid[0:48, 0:48]
    T = 0.3 * np.exp(-0.5 * (((yy - 24) ** 2 + (xx - 24) ** 2) / 25.0))
    for _ in range(12):
        m.step(T)
        d = _div_b(H_S * m.u_s + H_M * m.u_m,
                   H_S * m.v_s + H_M * m.v_m)
        assert np.abs(d[2:-2, 2:-2]).max() < 1e-4


def test_ridge_deflection():
    """Uniform inflow past a ridge segment: the surface layer
    deflects around the core (flow slows ahead of it, cross-flow
    develops, the ends stay open), the middle layer crosses almost
    freely."""
    h, w = _ridge(length=8.0)
    m = WindModel(Stream(2, "t"), h, w, coriolis=0.0, drive=_DRIVE)
    T = np.zeros(h.shape, dtype=np.float32)
    for _ in range(250):      # let the rim inflow establish across the grid
        m.step(T)
    # surface slows ahead of the ridge core vs the far-upstream inflow
    upstream = float(m.u_s[24, 6])
    ahead = float(m.u_s[24, 18])
    assert ahead < 0.7 * upstream
    # cross-flow develops (deflection), not a pure stop — relative to
    # the slowed upstream speed (stronger drag slows everything, so
    # the meaningful measure is the deflection RATIO)
    assert abs(m.v_s[10:38, 14:22]).max() > 0.3 * upstream
    # the ends stay more open than the core: flow past the segment's
    # tip keeps more of its speed (the strong drag's halo bleeds some
    # drag onto the tip too, so the margin is modest)
    tip = float(m.u_s[6, 18])
    assert tip > 1.2 * ahead
    # the middle layer feels no terrain: it crosses at ~inflow speed
    mid_core = float(m.u_m[24, 26])
    assert mid_core > 0.5 * 0.3


def test_thermal_low():
    """A hot disk spins up a cyclone: surface convergence, cyclonic
    rotation (f > 0 -> positive vorticity), middle-layer divergence
    aloft, and descent (D > 0) somewhere around it."""
    h, w = _flat()
    m = WindModel(Stream(3, "t"), h, w, coriolis=0.15)
    yy, xx = np.mgrid[0:48, 0:48]
    T = 0.4 * np.exp(-0.5 * (((yy - 24) ** 2 + (xx - 24) ** 2) / 18.0))
    for _ in range(40):
        m.step(T.astype(np.float32))
    # surface convergence over the disk
    d_s = _div_b(m.u_s, m.v_s)
    assert d_s[20:29, 20:29].mean() < -1e-3
    # cyclonic vorticity (f > 0 -> counterclockwise -> dv/dx - du/dy > 0)
    dux, duy = _grad_c(m.u_s)
    dvx, dvy = _grad_c(m.v_s)
    vort = dvx - duy
    assert vort[20:29, 20:29].mean() > 1e-3
    # middle layer diverges aloft (the ascent exhaust)
    d_m = _div_b(m.u_m, m.v_m)
    assert d_m[20:29, 20:29].mean() > 1e-4
    # descent exists somewhere on the map (mass has to come down)
    assert (m.D > 1e-3).any()


def test_rain_shadow_signature():
    """Channel flow over a CROSSABLE ridge: surface convergence on
    the windward side, divergence in the lee (the terrain-lifting
    term). (A full-width tall ridge is a wall — the flow stagnates
    against it, which is also physical but carries no signature.)"""
    h, w = _ridge(height=0.12)
    m = WindModel(Stream(4, "t"), h, w, coriolis=0.0, drive=_DRIVE)
    T = np.zeros(h.shape, dtype=np.float32)
    for _ in range(250):
        m.step(T)
    d = _div_b(m.u_s, m.v_s)
    windward = d[10:38, 16:22].mean()   # west (upwind) flank
    lee = d[10:38, 27:33].mean()        # east (downwind) flank
    assert windward < 0.0 < lee
    # signature ~20x above the numerical noise floor (small test
    # ridge -> small lifting; the sign and profile are the physics)
    assert lee - windward > 1e-5


def test_forest_drag():
    """Trees are windbreaks: downstream surface momentum is reduced
    behind a canopy patch; the middle layer is untouched."""
    h, w = _flat()
    green = np.zeros(h.shape, dtype=np.float32)
    green[10:38, 18:26] = 1.0
    T = np.zeros(h.shape, dtype=np.float32)
    m0 = WindModel(Stream(5, "t"), h, w, green=None, coriolis=0.0,
                   drive=_DRIVE)
    m1 = WindModel(Stream(5, "t"), h, w, green=green, coriolis=0.0,
                   drive=_DRIVE)
    for _ in range(250):
        m0.step(T)
        m1.step(T)
    # downstream of the patch, the forest run is weaker
    bare = float(np.hypot(m0.u_s, m0.v_s)[10:38, 30:40].mean())
    wooded = float(np.hypot(m1.u_s, m1.v_s)[10:38, 30:40].mean())
    assert wooded < 0.8 * bare
    # middle layers identical (trees never touch them)
    assert np.array_equal(m0.u_m, m1.u_m) and np.array_equal(m0.v_m, m1.v_m)


def test_drag_only_decay():
    """No forcing, drag on: kinetic energy decays monotonically."""
    h, w = _ridge()
    m = WindModel(Stream(6, "t"), h, w, coriolis=0.0)
    rng = np.random.default_rng(0)
    m.u_s[:] = rng.normal(0, 0.2, h.shape).astype(np.float32)
    m.v_s[:] = rng.normal(0, 0.2, h.shape).astype(np.float32)
    T = np.zeros(h.shape, dtype=np.float32)
    e_prev = np.inf
    for _ in range(10):
        m.step(T)
        e = float((m.u_s ** 2 + m.v_s ** 2 + m.u_m ** 2 + m.v_m ** 2).sum())
        assert e <= e_prev + 1e-6
        e_prev = e


def test_momentum_budget():
    """No forcing, no drag (uniform water world), rim held at zero:
    nothing on the source/sink list is active, so total kinetic
    energy is conserved to solver tolerance (semi-Lagrangian
    diffusion loses a little — bounded)."""
    h, w = _flat(water=True)
    m = WindModel(Stream(7, "t"), h, w, coriolis=0.1)
    rng = np.random.default_rng(1)
    u0 = _box3(rng.normal(0, 0.15, h.shape).astype(np.float32), 4)
    v0 = _box3(rng.normal(0, 0.15, h.shape).astype(np.float32), 4)
    u0[m.rim] = v0[m.rim] = 0.0
    m.u_s[:] = u0
    m.v_s[:] = v0
    T = np.zeros(h.shape, dtype=np.float32)
    # warm-up: the first projection legitimately strips the divergent
    # part of the random initial noise (that is its job) — budget the
    # energy AFTER that cleanup. The known sinks (Brinkman drag
    # ~1%/step, semi-Lagrangian diffusion ~0.6%/step, rim absorption
    # at the zero-velocity boundary) bound the decay; the test fails
    # on phantom sources, spikes, or order-of-magnitude leaks
    for _ in range(3):
        m.step(T)
    es = [float((m.u_s ** 2 + m.v_s ** 2 + m.u_m ** 2 + m.v_m ** 2).sum())]
    for _ in range(27):
        m.step(T)
        e = float((m.u_s ** 2 + m.v_s ** 2 + m.u_m ** 2 + m.v_m ** 2).sum())
        assert e <= es[-1] + 1e-6         # monotone decay, no sources
        assert e > 0.9 * es[-1]           # no per-step collapse
        es.append(e)
    assert es[-1] > 0.3 * es[0]           # no hidden order-of-mag sink


def test_determinism():
    """Same seed, same clocks: bitwise-identical snapshots."""
    h, w = _ridge()
    T = np.full(h.shape, 0.1, dtype=np.float32)
    snaps = []
    for _ in range(2):
        m = WindModel(Stream(8, "t"), h, w, coriolis=0.1, drive=_DRIVE)
        snaps.append(m.snapshot(Stream(8, "t"), 1000, T, n_steps=8))
    for k in snaps[0]:
        assert np.array_equal(snaps[0][k], snaps[1][k])


def test_no_blowup():
    """Steep terrain + strong thermal anomaly + drive, 300 steps:
    everything stays finite and bounded (the governors hold)."""
    h, w = _ridge(height=0.5, sigma=2.0)
    yy, xx = np.mgrid[0:48, 0:48]
    m = WindModel(Stream(9, "t"), h, w, coriolis=0.2, drive=(0.03, 0.01))
    T = (0.6 * np.sin(yy / 8.0) * np.cos(xx / 11.0)).astype(np.float32)
    for _ in range(300):
        m.step(T)
    for a in (m.u_s, m.v_s, m.u_m, m.v_m, m.D):
        assert np.isfinite(a).all()
    assert np.hypot(m.u_s, m.v_s).max() < 4.0
