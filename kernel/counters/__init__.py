"""K4 — counters: analytic state variables. Deliberately trivial.

A counter is a chain of anchors `(t, value, law, regime)` evaluated at t,
never ticked. Committed events insert anchors; regime shifts re-anchor.
The entire function library (Logistic / ExpDecay / Step) fits on one page
— the test suite enforces it.

Promoted from exp/k4_counters (2026-07-19, verdict: works). The exp/
directory keeps the granary fixture, demo, and tests as living
documentation.
"""

from kernel.counters.laws import ExpDecay, Law, Logistic, Step
from kernel.counters.counters import Anchor, Counter

__all__ = ["Law", "Logistic", "ExpDecay", "Step", "Anchor", "Counter"]
