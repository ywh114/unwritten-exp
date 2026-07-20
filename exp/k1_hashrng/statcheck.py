"""Tiny statistical checkers shared by the K1 demo and its tests.

Acceptance tooling only — not part of the hashrng library API.
"""

from __future__ import annotations

import math
from collections.abc import Iterable


def normal_sf(z: float) -> float:
    """Upper tail P(Z > z) of the standard normal."""
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def chi2_pvalue(stat: float, df: int) -> float:
    """Approximate upper-tail p-value via the Wilson–Hilferty transform."""
    z = ((stat / df) ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * df))) / math.sqrt(2.0 / (9.0 * df))
    return normal_sf(z)


def chi2_uniformity(draws: Iterable[float], bins: int) -> tuple[float, int, float]:
    """χ² uniformity test of [0,1) draws over `bins` equal bins.

    Returns (statistic, degrees_of_freedom, p_value).
    """
    counts = [0] * bins
    n = 0
    for u in draws:
        assert 0.0 <= u < 1.0, f"draw out of range: {u}"
        counts[min(int(u * bins), bins - 1)] += 1
        n += 1
    expected = n / bins
    stat = sum((c - expected) ** 2 / expected for c in counts)
    return stat, bins - 1, chi2_pvalue(stat, bins - 1)


def pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation coefficient of two equal-length samples."""
    assert len(xs) == len(ys) and len(xs) > 1
    n = len(xs)
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((y - my) ** 2 for y in ys)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return sxy / math.sqrt(sxx * syy)
