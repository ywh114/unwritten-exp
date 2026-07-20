"""K2 — gmm_dynamics: the position kernel.

Gaussian mixtures + affine drift–diffusion (Ornstein–Uhlenbeck) with
analytic time-skip: no ticking, ever. Time-periodic attractors are
piecewise-constant `Schedule`s of `DriftField`s; one full period is an
affine map per element, so k periods collapse to a closed-form geometric
series — evolve cost is O(segments-per-period), independent of Δt.

Promoted from exp/k2_gmm_dynamics (2026-07-19, verdict: works). The exp/
directory keeps the demo, fixtures, and tests as living documentation.
"""

from kernel.gmm_dynamics.gmm import GMM, Gaussian
from kernel.gmm_dynamics.dynamics import (
    DriftField,
    Schedule,
    evolve,
    sample_at,
    stationary,
)

__all__ = [
    "GMM",
    "Gaussian",
    "DriftField",
    "Schedule",
    "evolve",
    "stationary",
    "sample_at",
]
