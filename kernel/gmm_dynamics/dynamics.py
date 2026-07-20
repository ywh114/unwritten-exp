"""Affine drift–diffusion dynamics with analytic time-skip.

Per axis the dynamics are Ornstein–Uhlenbeck: dx = θ(μ − x)dt + σ dW.
A `DriftField` is axis-aligned: attractor μ = (μx, μy), mean-reversion
rates θ = (θx, θy) ≥ 0, diffusivities σ = (σx, σy) ≥ 0. Over any interval
the exact propagator is affine per element:

* mean:       m_i(t) = μ_i + (m0_i − μ_i)·e^(−θ_i Δt)
* covariance: P_ij(t) = P∞_ij + (P0_ij − P∞_ij)·e^(−(θ_i+θ_j)Δt),
  P∞ diagonal with P∞_ii = σ_i²/(2θ_i); hence P_xy(t) = P0_xy·e^(−(θx+θy)Δt).

θ_i = 0 is the pure-diffusion limit (mean frozen, P_ii grows by σ_i² Δt);
all formulas use expm1-style forms so θ → 0 is numerically clean.

A `Schedule` is a period T with piecewise-constant fields
[(phase_start, DriftField), ...]; field k applies on [τ_k, τ_{k+1}).
The map over one full period is affine per element, so k periods are a
closed-form geometric series — `evolve` over a century costs the same as
over a day: O(segments-per-period), never O(days).
"""

from __future__ import annotations

import math

import numpy as np

from kernel.gmm_dynamics.gmm import GMM
from kernel.hashrng import Stream

# Draw-index plan for sample_at (Stream.normal consumes indices 2i, 2i+1):
# component choice lives at low indices, the two normals live high, so the
# index ranges never overlap (see exp/k1_hashrng/README.md spec-notes).
_IDX_COMPONENT = 0
_IDX_NORMAL_ZX = 1 << 20
_IDX_NORMAL_ZY = (1 << 20) + 1

_CHOL_JITTER = 1e-12
# Below |rate·Δt| ~ 1e-8 the exponential factor is 1 − rate·Δt to within
# float precision; we use expm1 there to keep the linear term exact.
_EXPM1_CUTOFF = 1e-8


def _exp_factor(rate: float, dt: float) -> tuple[float, float]:
    """(e^(−rate·Δt), 1 − e^(−rate·Δt)) with the second entry exact for
    rate·Δt → 0 (via −expm1), so θ → 0 limits stay clean."""
    x = rate * dt
    if abs(x) < _EXPM1_CUTOFF:
        one_minus = -math.expm1(-x)
        return 1.0 - one_minus, one_minus
    f = math.exp(-x)
    return f, 1.0 - f


class DriftField:
    """Axis-aligned OU drift field: attractor μ, rates θ ≥ 0, diffusivities σ ≥ 0."""

    __slots__ = ("mu", "theta", "sigma")

    def __init__(self, mu, theta, sigma) -> None:
        mu = np.asarray(mu, dtype=float).reshape(2)
        theta = np.asarray(theta, dtype=float).reshape(2)
        sigma = np.asarray(sigma, dtype=float).reshape(2)
        if np.any(theta < 0.0):
            raise ValueError("theta must be >= 0")
        if np.any(sigma < 0.0):
            raise ValueError("sigma must be >= 0")
        self.mu = mu
        self.theta = theta
        self.sigma = sigma

    def __repr__(self) -> str:
        return (
            f"DriftField(mu={self.mu.tolist()}, theta={self.theta.tolist()}, "
            f"sigma={self.sigma.tolist()})"
        )


class Schedule:
    """Period T with piecewise-constant fields; field k applies on
    [phase_starts[k], phase_starts[k+1]) (wrapping at T)."""

    __slots__ = ("period", "phase_starts", "fields")

    def __init__(self, period: float, segments) -> None:
        if not period > 0.0:
            raise ValueError("period must be positive")
        if not segments:
            raise ValueError("schedule needs at least one segment")
        starts = [float(s[0]) for s in segments]
        fields = [s[1] for s in segments]
        if starts[0] != 0.0:
            raise ValueError("first segment must start at phase 0")
        if any(b <= a for a, b in zip(starts, starts[1:])):
            raise ValueError("phase starts must be strictly increasing")
        if starts[-1] >= period:
            raise ValueError("last segment must start before the period ends")
        self.period = float(period)
        self.phase_starts = tuple(starts)
        self.fields = tuple(fields)

    @property
    def n_segments(self) -> int:
        return len(self.fields)

    def __repr__(self) -> str:
        return f"Schedule(period={self.period}, n_segments={self.n_segments})"


# --- single-step propagator ----------------------------------------------------


def _field_step(means: np.ndarray, covs: np.ndarray, field: DriftField, dt: float):
    """Vectorized exact step of every component under one field."""
    th = field.theta
    mu = field.mu
    sig = field.sigma

    new_means = np.empty_like(means)
    for i in range(2):
        if th[i] == 0.0:
            new_means[:, i] = means[:, i]
        else:
            f, _ = _exp_factor(th[i], dt)
            new_means[:, i] = mu[i] + (means[:, i] - mu[i]) * f

    new_covs = np.empty_like(covs)
    for i in range(2):
        for j in range(2):
            rate = th[i] + th[j]
            if rate == 0.0:
                # both axes are pure diffusion; only the diagonal grows
                new_covs[:, i, j] = covs[:, i, j] + (sig[i] * sig[j] * dt if i == j else 0.0)
            else:
                f, _ = _exp_factor(rate, dt)
                p_inf = sig[i] * sig[j] / rate if i == j else 0.0
                new_covs[:, i, j] = p_inf + (covs[:, i, j] - p_inf) * f
    return new_means, new_covs


# --- period-map composition ---------------------------------------------------


def _period_map(schedule: Schedule):
    """Compose one full period into an affine map per element.

    Returns (a, b, e, q) with a, b shape (2,) and e, q shape (2,2) such that
    after one full period:  m' = a·m + b   and   P'_ij = e_ij·P_ij + q_ij.
    Composition is exact (b and q accumulate under earlier multipliers).
    """
    a = np.ones(2)
    b = np.zeros(2)
    e = np.ones((2, 2))
    q = np.zeros((2, 2))
    starts = schedule.phase_starts
    n = schedule.n_segments
    for k in range(n):
        dt = (starts[k + 1] if k + 1 < n else schedule.period) - starts[k]
        field = schedule.fields[k]
        for i in range(2):
            th = field.theta[i]
            if th == 0.0:
                fi = 1.0
            else:
                fi, _ = _exp_factor(th, dt)
            b[i] = fi * b[i] + (1.0 - fi) * field.mu[i]
            a[i] = fi * a[i]
        for i in range(2):
            for j in range(2):
                rate = field.theta[i] + field.theta[j]
                if rate == 0.0:
                    fij = 1.0
                    p_inf_dt = field.sigma[i] * field.sigma[j] * dt if i == j else 0.0
                else:
                    fij, one_minus = _exp_factor(rate, dt)
                    p_inf = field.sigma[i] * field.sigma[j] / rate if i == j else 0.0
                    p_inf_dt = p_inf * one_minus
                q[i, j] = fij * q[i, j] + p_inf_dt
                e[i, j] = fij * e[i, j]
    return a, b, e, q


def _apply_periods(means: np.ndarray, covs: np.ndarray, schedule: Schedule, k: int):
    """Apply k full periods of `schedule` via the closed-form geometric series.

    m → aᵏ m + b·(aᵏ−1)/(a−1)  and  P_ij → e_ijᵏ P_ij + q_ij·(e_ijᵏ−1)/(e_ij−1),
    with the A → 1 / e → 1 guards falling back to the linear k·b / k·q forms.
    """
    if k <= 0:
        return means, covs
    a, b, e, q = _period_map(schedule)
    new_means = np.empty_like(means)
    for i in range(2):
        fk = a[i] ** k
        series = _geo_series(a[i], k, fk)
        new_means[:, i] = fk * means[:, i] + series * b[i]
    new_covs = np.empty_like(covs)
    for i in range(2):
        for j in range(2):
            fk = e[i, j] ** k
            series = _geo_series(e[i, j], k, fk)
            new_covs[:, i, j] = fk * covs[:, i, j] + series * q[i, j]
    return new_means, new_covs


def _geo_series(x: float, k: int, xk: float) -> float:
    """(xᵏ − 1)/(x − 1) with the x → 1 guard (returns k)."""
    if x == 1.0:
        return float(k)
    return (xk - 1.0) / (x - 1.0)


# --- evolve -------------------------------------------------------------------


def evolve(dist: GMM, t0: float, t1: float, field_or_schedule) -> GMM:
    """Analytic time-skip of `dist` from t0 to t1. No ticking, ever.

    Under a `DriftField` this is one exact OU step per component. Under a
    `Schedule`, [t0, t1] decomposes into a partial head segment chain, k
    full periods (closed-form geometric series) and a partial tail chain —
    O(segments-per-period) work regardless of Δt. Component weights pass
    through unchanged, so total mass is conserved exactly by construction.
    """
    if t1 < t0:
        raise ValueError("t1 must be >= t0")
    if t1 == t0:
        return dist.copy()
    dt = t1 - t0
    means = dist.means.copy()
    covs = dist.covs.copy()

    if isinstance(field_or_schedule, DriftField):
        means, covs = _field_step(means, covs, field_or_schedule, dt)
    elif isinstance(field_or_schedule, Schedule):
        T = field_or_schedule.period
        phase = t0 - math.floor(t0 / T) * T  # t0 mod T, safe for t0 < 0
        # Head: from t0's phase to the next period boundary (or t1).
        remaining = dt
        if phase > 0.0:
            head = min(remaining, T - phase)
            means, covs = _evolve_partial(means, covs, field_or_schedule, phase, head)
            remaining -= head
        # Middle: k full periods as one closed-form geometric series.
        k_full = int(math.floor(remaining / T))
        if k_full > 0:
            means, covs = _apply_periods(means, covs, field_or_schedule, k_full)
            remaining -= k_full * T
        # Tail: the remaining partial period from phase 0.
        if remaining > 0.0:
            means, covs = _evolve_partial(means, covs, field_or_schedule, 0.0, remaining)
    else:
        raise TypeError("field_or_schedule must be a DriftField or Schedule")

    return GMM(dist.weights.copy(), means, covs)


def _evolve_partial(means, covs, schedule: Schedule, phase: float, length: float):
    """Evolve `length` (< period) starting at cycle `phase`, walking only the
    segments that overlap [phase, phase + length)."""
    starts = schedule.phase_starts
    bounds = starts + (schedule.period,)
    n = schedule.n_segments
    # first segment whose end is past `phase`
    k = 0
    while bounds[k + 1] <= phase:
        k += 1
    cursor = phase
    end = phase + length
    while cursor < end - 0.0 and k < n:
        seg_end = min(bounds[k + 1], end)
        dt = seg_end - cursor
        if dt > 0.0:
            means, covs = _field_step(means, covs, schedule.fields[k], dt)
        cursor = seg_end
        k += 1
    return means, covs


# --- stationary -----------------------------------------------------------------


def stationary(field_or_schedule, phase: float = 0.0) -> GMM:
    """Stationary distribution.

    For a `DriftField`: mean μ, diagonal P∞ with P∞_ii = σ_i²/(2θ_i)
    (θ_i = 0 has no stationary distribution — ValueError).

    For a `Schedule`: the cyclostationary fixed point of the composed
    period map — m* = (I−A)⁻¹b, P*_ij = q_ij/(1−e_ij) — computed at phase
    0, then evolved forward to the requested phase. Requires every rate of
    the composed map to be < 1 (some mean-reversion on each axis).
    """
    if isinstance(field_or_schedule, DriftField):
        field = field_or_schedule
        if np.any(field.theta == 0.0):
            raise ValueError("no stationary distribution where theta == 0")
        p_inf = np.diag(field.sigma**2 / (2.0 * field.theta))
        return GMM([1.0], field.mu.reshape(1, 2), p_inf.reshape(1, 2, 2))

    schedule = field_or_schedule
    a, b, e, q = _period_map(schedule)
    if np.any(a == 1.0) or np.any(e == 1.0):
        raise ValueError("schedule has a θ = 0 axis on some element; no cyclostationary state")
    m_star = b / (1.0 - a)
    p_star = q / (1.0 - e)
    g = GMM([1.0], m_star.reshape(1, 2), p_star.reshape(1, 2, 2))
    if phase == 0.0:
        return g
    if not 0.0 <= phase < schedule.period:
        raise ValueError("phase must lie in [0, period)")
    return evolve(g, 0.0, phase, schedule)


# --- sampling -------------------------------------------------------------------


def sample_at(dist: GMM, stream: Stream, clock: int) -> tuple[float, float]:
    """Deterministic position sample from the mixture at `clock`.

    Component is picked by weight from `stream.uniform(clock, 0)`; the two
    standard normals come from `stream.normal` at disjoint high indices;
    x = m + L·z with L = cholesky(P) (1e-12·I jitter on LinAlgError).
    Same stream + clock → identical sample, always.
    """
    u = stream.uniform(clock, _IDX_COMPONENT)
    cdf = np.cumsum(dist.weights)
    total = cdf[-1]
    idx = int(np.searchsorted(cdf, u * total, side="right"))
    if idx >= dist.n_components:  # u * total can round up to the last edge
        idx = dist.n_components - 1

    z = np.array(
        [
            stream.normal(clock, _IDX_NORMAL_ZX),
            stream.normal(clock, _IDX_NORMAL_ZY),
        ]
    )
    m = dist.means[idx]
    p = dist.covs[idx]
    try:
        lower = np.linalg.cholesky(p)
    except np.linalg.LinAlgError:
        lower = np.linalg.cholesky(p + _CHOL_JITTER * np.eye(2))
    x = m + lower @ z
    return float(x[0]), float(x[1])
