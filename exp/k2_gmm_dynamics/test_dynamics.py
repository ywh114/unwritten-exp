"""K2 core tests — maps to the lab spec's done-when for `gmm_dynamics`.

1. mass conserved to 1e-9 over Δt ∈ {1 minute … 10^4 years}, field + schedule
2. OU exactness vs. Euler–Maruyama Monte Carlo through a multi-segment schedule
3. stationary distributions are fixed points; long evolves converge to them
4. associativity of evolve
5. deterministic, correctly-distributed sampling
7. O(1) time-skip (a century costs no more than a day, asymptotically)
8. θ = 0 pure-diffusion limit exact (and θ → 0 numerically clean)
"""

from __future__ import annotations

import math
import time

import numpy as np
import pytest

from kernel.gmm_dynamics.dynamics import (
    DriftField,
    Schedule,
    evolve,
    sample_at,
    stationary,
)
from kernel.gmm_dynamics.gmm import GMM, Gaussian
from kernel.hashrng import Stream

MINUTE = 1.0
DAY = 1440.0
YEAR = 365.25 * DAY
DTS = [MINUTE, DAY, YEAR, 100 * YEAR, 10_000 * YEAR]

FIELD = DriftField(mu=(10.0, -4.0), theta=(0.05, 0.02), sigma=(1.5, 0.8))
SCHEDULE = Schedule(
    period=DAY,
    segments=[
        (0.0, DriftField(mu=(0.0, 0.0), theta=(0.10, 0.10), sigma=(0.5, 0.5))),
        (360.0, DriftField(mu=(20.0, 5.0), theta=(0.05, 0.03), sigma=(1.0, 0.6))),
        (1020.0, DriftField(mu=(-5.0, 10.0), theta=(0.20, 0.08), sigma=(0.4, 1.2))),
    ],
)
START = Gaussian(mean=(3.0, 7.0), var=[[9.0, 2.0], [2.0, 4.0]])


# 1. mass conservation ---------------------------------------------------------


@pytest.mark.parametrize("dt", DTS)
def test_mass_conserved_single_field(dt):
    assert abs(evolve(START, 0.0, dt, FIELD).total_mass() - 1.0) <= 1e-9


@pytest.mark.parametrize("dt", DTS)
def test_mass_conserved_through_schedule(dt):
    assert abs(evolve(START, 0.0, dt, SCHEDULE).total_mass() - 1.0) <= 1e-9


def test_mass_conserved_mixture():
    g = GMM([0.3, 0.7], [[0.0, 0.0], [50.0, -20.0]], [np.eye(2), 4.0 * np.eye(2)])
    out = evolve(g, 13.7, 13.7 + 100 * YEAR, SCHEDULE)
    assert abs(out.total_mass() - 1.0) <= 1e-9
    assert np.allclose(out.weights, g.weights, atol=1e-12)  # weights pass through


# 2. OU exactness vs. Monte Carlo -----------------------------------------------


def _em_reference(dist, t0, t1, schedule, dt, n_particles, seed):
    """Euler–Maruyama through the schedule's piecewise-constant fields."""
    rng = np.random.default_rng(seed)
    lower = np.linalg.cholesky(dist.covs[0])
    pts = dist.means[0] + rng.standard_normal((n_particles, 2)) @ lower.T
    t = t0
    while t < t1 - 1e-12:
        step = min(dt, t1 - t)
        phase = t % schedule.period
        field = schedule.fields[
            max(k for k, s in enumerate(schedule.phase_starts) if s <= phase)
        ]
        pts += field.theta * (field.mu - pts) * step + field.sigma * math.sqrt(step) * rng.standard_normal((n_particles, 2))
        t += step
    mean = pts.mean(axis=0)
    d = pts - mean
    return mean, (d.T @ d) / (n_particles - 1)


def test_ou_exactness_vs_monte_carlo():
    n, dt = 20_000, 0.005
    exact = evolve(START, 0.0, 100.0, SCHEDULE)
    mean_mc, cov_mc = _em_reference(START, 0.0, 100.0, SCHEDULE, dt, n, seed=7)
    # ~4+ MC sigmas, with an allowance for EM's O(dt) discretization bias
    lam = float(np.max(np.linalg.eigvalsh(cov_mc)))
    tol_mean = 6.0 * math.sqrt(lam / n) + 0.02
    tol_cov = 8.0 * math.sqrt(2.0 / n) * lam + 0.05
    assert np.all(np.abs(exact.means[0] - mean_mc) < tol_mean)
    assert np.all(np.abs(exact.covs[0] - cov_mc) < tol_cov)


# 3. stationary distributions ----------------------------------------------------


def test_stationary_field_is_fixed_point():
    g = stationary(FIELD)
    for dt in (MINUTE, DAY, 100 * YEAR):
        assert evolve(g, 0.0, dt, FIELD).moments_close(g, tol=1e-9)


def test_long_evolve_converges_to_stationary():
    far = Gaussian(mean=(-500.0, 800.0), var=[[1e4, 3e3], [3e3, 2e3]])
    out = evolve(far, 0.0, 1.0e6, FIELD)
    assert out.moments_close(stationary(FIELD), tol=1e-9)


def test_stationary_schedule_is_cyclostationary_fixed_point():
    g0 = stationary(SCHEDULE, phase=0.0)
    assert evolve(g0, 0.0, SCHEDULE.period, SCHEDULE).moments_close(g0, tol=1e-9)
    for phase in (100.0, 720.5, 1439.9):
        g = stationary(SCHEDULE, phase=phase)
        out = evolve(g, phase, phase + SCHEDULE.period, SCHEDULE)
        assert out.moments_close(g, tol=1e-9)


def test_stationary_rejects_zero_theta():
    with pytest.raises(ValueError):
        stationary(DriftField(mu=(0.0, 0.0), theta=(0.0, 0.1), sigma=(1.0, 1.0)))


# 4. associativity ----------------------------------------------------------------


def test_associativity_single_field():
    t0, t1, t2 = 100.3, 537.7, 129_600.5
    direct = evolve(START, t0, t2, FIELD)
    composed = evolve(evolve(START, t0, t1, FIELD), t1, t2, FIELD)
    assert direct.moments_close(composed, tol=1e-9)


def test_associativity_through_schedule():
    t0, t1, t2 = 100.3, 537.7, 129_600.5
    direct = evolve(START, t0, t2, SCHEDULE)
    composed = evolve(evolve(START, t0, t1, SCHEDULE), t1, t2, SCHEDULE)
    assert direct.moments_close(composed, tol=1e-9)


def test_associativity_across_period_boundary():
    # t0 mid-period, t1 exactly on a boundary, t2 many periods later
    t0, t1, t2 = 390.0, 1440.0, 1440.0 * 1000 + 720.0
    direct = evolve(START, t0, t2, SCHEDULE)
    composed = evolve(evolve(START, t0, t1, SCHEDULE), t1, t2, SCHEDULE)
    assert direct.moments_close(composed, tol=1e-9)


# 5. sampling ---------------------------------------------------------------------


SAMPLE_GMM = GMM(
    [0.4, 0.6],
    [[0.0, 0.0], [10.0, 5.0]],
    [[[4.0, 1.0], [1.0, 2.0]], [[9.0, -2.0], [-2.0, 3.0]]],
)


def test_sampling_reproduces_mixture_moments():
    n = 20_000
    stream = Stream(1, "k2:test:sampling")
    pts = np.array([sample_at(SAMPLE_GMM, stream, clock=c) for c in range(n)])
    mean = pts.mean(axis=0)
    cov = np.cov(pts.T)
    lam = float(np.max(np.linalg.eigvalsh(SAMPLE_GMM.mixture_cov())))
    assert np.all(np.abs(mean - SAMPLE_GMM.mixture_mean()) < 6.0 * math.sqrt(lam / n))
    assert np.all(np.abs(cov - SAMPLE_GMM.mixture_cov()) < 8.0 * math.sqrt(2.0 / n) * lam)


def test_sampling_deterministic_same_stream_and_clock():
    g = evolve(SAMPLE_GMM, 0.0, DAY, SCHEDULE)
    s1, s2 = Stream(1, "k2:test:det"), Stream(1, "k2:test:det")
    assert sample_at(g, s1, 42) == sample_at(g, s2, 42)
    assert sample_at(g, s1, 0) == sample_at(g, s1, 0)


def test_sampling_decorrelated_across_clocks():
    n = 10_000
    stream = Stream(1, "k2:test:decorr")
    pts = np.array([sample_at(SAMPLE_GMM, stream, clock=c) for c in range(n)])
    r = np.corrcoef(pts[:-1, 0], pts[1:, 0])[0, 1]
    assert abs(r) < 0.02


def test_sampling_degenerate_covariance():
    g = Gaussian(mean=(1.0, 2.0), var=0.0)  # PSD edge: cholesky jitter path
    x, y = sample_at(g, Stream(1, "k2:test:degenerate"), clock=0)
    assert math.hypot(x - 1.0, y - 2.0) < 1e-3


# 7. O(1) time-skip -----------------------------------------------------------------


def _best_time(repeats=60):
    def measure(dt):
        best = float("inf")
        for _ in range(3):
            t = time.perf_counter()
            for _ in range(repeats):
                evolve(START, 0.0, dt, SCHEDULE)
            best = min(best, (time.perf_counter() - t) / repeats)
        return best

    return measure


def test_evolve_is_o1_in_dt():
    measure = _best_time()
    day = measure(DAY)
    century = measure(100 * YEAR)
    assert century < 50.0 * day


# 8. θ = 0 pure diffusion ------------------------------------------------------------


def test_zero_theta_pure_diffusion_exact():
    field = DriftField(mu=(100.0, -100.0), theta=(0.0, 0.0), sigma=(2.0, 3.0))
    dt = 123.4
    out = evolve(START, 0.0, dt, field)
    assert np.allclose(out.means[0], START.means[0], atol=1e-12)  # mean frozen
    expected = START.covs[0] + np.diag([4.0 * dt, 9.0 * dt])
    assert np.allclose(out.covs[0], expected, atol=1e-9)


def test_zero_theta_offdiagonal_unchanged():
    # independent Brownian axes: no spurious cross-correlation may appear
    field = DriftField(mu=(0.0, 0.0), theta=(0.0, 0.0), sigma=(2.0, 3.0))
    out = evolve(START, 0.0, 10.0, field)
    assert out.covs[0][0, 1] == START.covs[0][0, 1]


def test_tiny_theta_matches_pure_diffusion_limit():
    dt = 1000.0
    tiny = DriftField(mu=(50.0, 50.0), theta=(1e-12, 1e-12), sigma=(2.0, 3.0))
    zero = DriftField(mu=(50.0, 50.0), theta=(0.0, 0.0), sigma=(2.0, 3.0))
    a = evolve(START, 0.0, dt, tiny)
    b = evolve(START, 0.0, dt, zero)
    assert np.allclose(a.means[0], b.means[0], atol=1e-9)
    assert np.allclose(a.covs[0], b.covs[0], atol=1e-6)
    assert np.all(np.isfinite(a.covs[0]))
