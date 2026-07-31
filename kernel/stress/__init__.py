"""kernel/stress — organism-agnostic environmental stress math (B5).

Suitability primitives, the monthly climate stratum, and the signed
composition (F product, s = 1 - 2F, factor-vector provenance). Shared
by flora and fauna; adapters live in K15 sim-diff.
"""

from kernel.stress.stress import (
    StressResult,
    climate_suit,
    compose,
    dist_suit,
    excess_suit,
    invert,
    sat,
    shortfall_suit,
)

__all__ = [
    "StressResult",
    "climate_suit",
    "compose",
    "dist_suit",
    "excess_suit",
    "invert",
    "sat",
    "shortfall_suit",
]
