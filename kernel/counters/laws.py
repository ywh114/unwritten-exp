"""K4 — the counter function library. Deliberately trivial.

The whole library is three closed forms. Per lab spec §2 (K4 done-when):
if the function library can't fit on one page, it's over-parameterized —
a spec violation. The test suite enforces the page limit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


class Law:
    """Closed-form evolution of a scalar over one segment.

    `value_at(c0, dt, rate_mult, cap_mult)` evaluates the law Δt after an
    anchor of value c0, with regime multipliers applied to the parameters.
    Laws must be exact flows: re-anchoring at an intermediate time with the
    current value must not change any later evaluation.
    """

    def value_at(self, c0: float, dt: float, rate_mult: float = 1.0, cap_mult: float = 1.0) -> float:
        raise NotImplementedError


@dataclass(frozen=True)
class Logistic(Law):
    """Growth toward capacity: dc/dt = r·c·(1 − c/K)."""

    rate: float
    capacity: float

    def value_at(self, c0: float, dt: float, rate_mult: float = 1.0, cap_mult: float = 1.0) -> float:
        if dt <= 0.0:
            return c0
        k = self.capacity * cap_mult
        if c0 == 0.0 or c0 == k:
            return c0
        r = self.rate * rate_mult
        a = (k - c0) / c0
        return k / (1.0 + a * math.exp(-r * dt))


@dataclass(frozen=True)
class ExpDecay(Law):
    """Exponential approach to a floor: dc/dt = −r·(c − floor)."""

    rate: float
    floor: float = 0.0

    def value_at(self, c0: float, dt: float, rate_mult: float = 1.0, cap_mult: float = 1.0) -> float:
        if dt <= 0.0:
            return c0
        f = self.floor * cap_mult
        return f + (c0 - f) * math.exp(-self.rate * rate_mult * dt)


@dataclass(frozen=True)
class Step(Law):
    """No dynamics — holds its anchor value; events create the steps."""

    def value_at(self, c0: float, dt: float, rate_mult: float = 1.0, cap_mult: float = 1.0) -> float:
        return c0
