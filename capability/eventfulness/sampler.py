"""C1 — calibrated eventfulness sampler (mechanical, no LLM).

Zero-inflated Poisson: with prob 1−π the interval is quiet (count 0);
otherwise count = 1 + Poisson(λ).  Both parameters scale with the
timescale and an optional regime multiplier.

The LLM never invents numbers — the count comes from here.
"""

from __future__ import annotations

import math

from kernel.hashrng import Stream

# Starting calibration per timescale (π, λ).  π is zero-inflation
# probability; λ is the Poisson rate for non-quiet intervals.
# Values are initial — the demo and spec-note may tune them.
SCALES: dict[str, tuple[float, float]] = {
    "week":   (0.35, 0.7),   # P(0)=0.65, mean ~0.60
    "season": (0.60, 1.0),   # P(0)=0.40, mean ~1.20
    "year":   (0.85, 1.3),   # P(0)=0.15, mean ~1.96
}


def sample_count(
    stream: Stream,
    clock: int,
    scale: str,
    regime: float = 1.0,
) -> int:
    """One draw from the zero-inflated Poisson for `scale`.

    Draw-index plan (mandatory):
      0 — the π coin (uniform < π → non-quiet branch)
      1+ — Knuth's Poisson algorithm on the non-quiet branch.
    """
    pi, lam = SCALES[scale]
    pi = max(0.0, min(0.99, pi * regime))
    lam = max(0.01, lam * regime)

    if stream.uniform(clock, 0) >= pi:
        return 0  # quiet interval

    # Knuth's algorithm for Poisson(λ)
    L = math.exp(-lam)
    k = 0
    p = 1.0
    idx = 1
    while True:
        k += 1
        p *= stream.uniform(clock, idx)
        idx += 1
        if p <= L:
            return k  # k − 1 + 1 = k (since we started k=0 and k+=1 first)


def target_distribution(
    stream: Stream,
    scale: str,
    regime: float = 1.0,
    n: int = 10_000,
) -> list[int]:
    """Generate `n` samples for reference-distribution comparison."""
    return [sample_count(stream, clock, scale, regime) for clock in range(n)]
