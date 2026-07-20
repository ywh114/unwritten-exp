"""K2 open question: how much context-dependent drift field survives the
closed-form requirement?

Setup: a two-patch map split at x = 0. The left patch (x < 0) and the right
patch (x >= 0) have different (μ, θ, σ). A particle's drift is the field of
the patch it is currently in — so the true dynamics are *not* affine and no
single-Gaussian closed form exists. This module measures, for a Gaussian
straddling the boundary:

* reference: fine-grained Euler–Maruyama where each particle uses the field
  of the patch it is in (seeded, deterministic);
* strategy (a) "ignore": one exact OU step under a single patch's field —
  closed form, wrong moments;
* strategy (b) "split": split the component at the boundary into two
  half-plane-truncated pieces, moment-match each to a Gaussian, evolve each
  under its own patch's field (exact OU step per piece), recombine —
  closed form per piece, much smaller moment error, at the cost of mixture
  growth (1 component -> 2 per boundary crossing). Re-splitting at the
  half-horizon (2 -> 4 components) roughly halves the remaining error:
  accuracy is bought with mixture growth, so a merge policy is mandatory.

All errors are reported relative to the reference's natural scales
(std for the mean, ||cov||_F for the covariance).
"""

from __future__ import annotations

import math

import numpy as np

from kernel.gmm_dynamics.dynamics import DriftField, evolve
from kernel.gmm_dynamics.gmm import GMM, Gaussian


# scipy is not a dependency; Φ and φ come from math.erf.
def _Phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _phi(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def truncated_normal_moments(mean: float, sd: float, side: str) -> tuple[float, float, float]:
    """(mass, mean, var) of N(mean, sd²) truncated to a half plane at x = 0.

    side="right" keeps x >= 0, side="left" keeps x < 0. Closed-form moments
    of the truncated normal (inverse-Mills-ratio formulas).
    """
    alpha = (0.0 - mean) / sd
    if side == "right":
        mass = 1.0 - _Phi(alpha)
        lam = _phi(alpha) / mass if mass > 0.0 else 0.0
        tmean = mean + sd * lam
        tvar = sd * sd * (1.0 + alpha * lam - lam * lam)
    else:
        mass = _Phi(alpha)
        lam = _phi(alpha) / mass if mass > 0.0 else 0.0
        tmean = mean - sd * lam
        tvar = sd * sd * (1.0 - alpha * lam - lam * lam)
    return mass, tmean, max(tvar, 0.0)


def split_at_boundary(dist: GMM, x0: float = 0.0, min_mass: float = 1e-300) -> GMM:
    """Split every component at the plane x = x0 into two half-plane pieces.

    Each piece is moment-matched to a Gaussian (exact truncated-normal
    moments; the y moments follow from the linear regression of y on x).
    The result has at most 2n components and conserves total mass to float
    tolerance.
    """
    weights, means, covs = [], [], []
    for w, m, p in zip(dist.weights, dist.means, dist.covs):
        mx, my = m
        vx, vy, cxy = p[0, 0], p[1, 1], p[0, 1]
        sd = math.sqrt(vx)
        beta = cxy / vx  # regression slope of y on x
        for side in ("left", "right"):
            # shift so the boundary sits at 0 in local coordinates
            mass, tmx, tvx = truncated_normal_moments(mx - x0, sd, side)
            w_piece = w * mass
            if w_piece <= min_mass:
                continue
            tmy = my + beta * (tmx - (mx - x0))
            tvy = vy - beta * beta * (vx - tvx)
            tcxy = beta * tvx
            weights.append(w_piece)
            means.append([tmx + x0, tmy])
            covs.append([[tvx, tcxy], [tcxy, tvy]])
    return GMM(weights, means, covs)


def em_reference(
    dist: GMM,
    field_left: DriftField,
    field_right: DriftField,
    horizon: float,
    dt: float,
    n_particles: int,
    seed: int,
    x0: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """Euler–Maruyama reference: each particle feels the field of the patch
    it is currently in. Returns (mean, cov) of the particle cloud."""
    rng = np.random.default_rng(seed)
    # initial cloud sampled from the mixture
    comp = rng.choice(dist.n_components, size=n_particles, p=dist.weights / dist.weights.sum())
    z = rng.standard_normal((n_particles, 2))
    pts = np.empty((n_particles, 2))
    for c in range(dist.n_components):
        mask = comp == c
        if not mask.any():
            continue
        try:
            lower = np.linalg.cholesky(dist.covs[c])
        except np.linalg.LinAlgError:
            lower = np.linalg.cholesky(dist.covs[c] + 1e-12 * np.eye(2))
        pts[mask] = dist.means[c] + z[mask] @ lower.T

    steps = int(round(horizon / dt))
    sqdt = math.sqrt(dt)
    for _ in range(steps):
        left = pts[:, 0] < x0
        mu = np.where(left[:, None], field_left.mu, field_right.mu)
        theta = np.where(left[:, None], field_left.theta, field_right.theta)
        sigma = np.where(left[:, None], field_left.sigma, field_right.sigma)
        pts += theta * (mu - pts) * dt + sigma * sqdt * rng.standard_normal((n_particles, 2))

    mean = pts.mean(axis=0)
    d = pts - mean
    cov = (d.T @ d) / (n_particles - 1)
    return mean, cov


def moment_errors(mean_ref, cov_ref, mean_hat, cov_hat) -> dict:
    """Relative moment errors against the reference's natural scales."""
    scale = math.sqrt(max(float(np.trace(cov_ref)), 1e-300))
    cov_scale = max(float(np.linalg.norm(cov_ref)), 1e-300)
    return {
        "mean_abs": float(np.linalg.norm(np.asarray(mean_hat) - np.asarray(mean_ref))),
        "mean_rel": float(np.linalg.norm(np.asarray(mean_hat) - np.asarray(mean_ref)) / scale),
        "cov_abs": float(np.linalg.norm(np.asarray(cov_hat) - np.asarray(cov_ref))),
        "cov_rel": float(np.linalg.norm(np.asarray(cov_hat) - np.asarray(cov_ref)) / cov_scale),
    }


# --- the measured configuration (used by tests, the demo report, and the spec-note)


FIELD_LEFT = DriftField(mu=(-10.0, 0.0), theta=(0.6, 0.6), sigma=(1.5, 1.5))
FIELD_RIGHT = DriftField(mu=(5.0, 0.0), theta=(0.02, 0.02), sigma=(3.0, 3.0))
START = Gaussian(mean=(2.0, 0.0), var=(64.0, 64.0))  # straddles x = 0
HORIZON = 2.0
EM_DT = 0.005
EM_PARTICLES = 20_000


def _evolve_by_patch(dist: GMM, dt: float) -> GMM:
    """Evolve each component under the field of the patch its mean sits in."""
    left_idx = [i for i, m in enumerate(dist.means) if m[0] < 0.0]
    right_idx = [i for i, m in enumerate(dist.means) if m[0] >= 0.0]
    parts = []
    for idx, field in ((left_idx, FIELD_LEFT), (right_idx, FIELD_RIGHT)):
        if not idx:
            continue
        sub = GMM(dist.weights[idx], dist.means[idx], dist.covs[idx])
        parts.append(evolve(sub, 0.0, dt, field))
    return GMM(
        np.concatenate([g.weights for g in parts]),
        np.concatenate([g.means for g in parts]),
        np.concatenate([g.covs for g in parts]),
    )


def run_experiment(seed: int = 1, n_particles: int = EM_PARTICLES, dt: float = EM_DT) -> dict:
    """Run the two-patch comparison; returns every number the spec-note cites."""
    mean_ref, cov_ref = em_reference(
        START, FIELD_LEFT, FIELD_RIGHT, HORIZON, dt, n_particles, seed
    )

    # (a) ignore the boundary: single exact OU step under the right patch
    # (the patch containing the initial mean).
    ignored = evolve(START, 0.0, HORIZON, FIELD_RIGHT)
    err_a = moment_errors(mean_ref, cov_ref, ignored.mixture_mean(), ignored.mixture_cov())

    # (b) split at the boundary, evolve each piece under its own patch,
    # recombine. Mass is conserved exactly by construction.
    pieces = split_at_boundary(START, x0=0.0)
    mass_before = START.total_mass()
    mass_after_split = pieces.total_mass()
    recombined = _evolve_by_patch(pieces, HORIZON)
    err_b = moment_errors(mean_ref, cov_ref, recombined.mixture_mean(), recombined.mixture_cov())

    # (b+) same, but re-split at the half-horizon: accuracy vs. mixture growth.
    resplit = _evolve_by_patch(split_at_boundary(START, x0=0.0), HORIZON / 2.0)
    resplit = _evolve_by_patch(split_at_boundary(resplit, x0=0.0), HORIZON / 2.0)
    err_b2 = moment_errors(mean_ref, cov_ref, resplit.mixture_mean(), resplit.mixture_cov())

    return {
        "config": {
            "horizon": HORIZON,
            "em_dt": dt,
            "em_particles": n_particles,
            "start_mean": START.means[0].tolist(),
            "start_var": START.covs[0].diagonal().tolist(),
        },
        "reference": {"mean": mean_ref.tolist(), "cov": cov_ref.tolist()},
        "ignore": {
            "mean": ignored.mixture_mean().tolist(),
            "cov": ignored.mixture_cov().tolist(),
            "errors": err_a,
        },
        "split": {
            "mean": recombined.mixture_mean().tolist(),
            "cov": recombined.mixture_cov().tolist(),
            "errors": err_b,
            "n_components_before": START.n_components,
            "n_components_after": recombined.n_components,
            "mass_error_split": abs(mass_after_split - mass_before),
            "mass_error_evolved": abs(recombined.total_mass() - mass_before),
        },
        "resplit": {
            "mean": resplit.mixture_mean().tolist(),
            "cov": resplit.mixture_cov().tolist(),
            "errors": err_b2,
            "n_components_after": resplit.n_components,
            "mass_error_evolved": abs(resplit.total_mass() - mass_before),
        },
    }
