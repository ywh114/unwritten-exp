"""K4 — anchor-chain counters: analytic state variables.

A counter is a chain of anchors — (t, value, law, regime) — evaluated at
t, never ticked:

    c(t) = anchor.law.value_at(anchor.value, t − anchor.t, regime multipliers)

where anchor is the latest anchor at or before t. Committed events and
regime shifts insert new anchors. Evaluation is a pure function of the
anchor chain: no state, no stepping, no drift.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass

from kernel.counters.laws import Law

DEFAULT_REGIME = ""


@dataclass(frozen=True)
class Anchor:
    """A committed point in a counter's history.

    `note` is provenance ("granary burned") — the collapse log / promise
    ledger of later libraries supplies these; the counter itself only
    stores them.
    """

    t: float
    value: float
    law: Law
    regime: str = DEFAULT_REGIME
    note: str = ""


class Counter:
    """A scalar state variable as an anchor chain.

    `regimes` maps a regime name to parameter multipliers,
    e.g. {"harvest": {"rate": 2.0, "capacity": 1.2}}. The empty regime ""
    is the default and needs no entry.
    """

    def __init__(self, regimes: dict[str, dict[str, float]] | None = None) -> None:
        self.regimes: dict[str, dict[str, float]] = regimes if regimes is not None else {}
        self._anchors: list[Anchor] = []
        self._times: list[float] = []

    @property
    def anchors(self) -> tuple[Anchor, ...]:
        return tuple(self._anchors)

    def set_anchor(self, t: float, value: float, law: Law, regime: str = DEFAULT_REGIME, note: str = "") -> None:
        """Append an anchor. Anchors must be strictly time-increasing."""
        if self._times and t <= self._times[-1]:
            raise ValueError(f"anchor at t={t} is not after last anchor t={self._times[-1]}")
        self._times.append(float(t))
        self._anchors.append(Anchor(float(t), float(value), law, regime, note))

    def anchor_at(self, t: float) -> Anchor:
        """The latest anchor at or before t."""
        i = bisect_right(self._times, t) - 1
        if i < 0:
            raise ValueError(f"no anchor at or before t={t}")
        return self._anchors[i]

    def value_at(self, t: float) -> float:
        """Exact evaluation at t — the counter's only verb."""
        a = self.anchor_at(t)
        mults = self.regimes.get(a.regime, {})
        return a.law.value_at(a.value, t - a.t, mults.get("rate", 1.0), mults.get("capacity", 1.0))

    def insert_event(self, t: float, *, delta: float = 0.0, scale: float = 1.0,
                     law: Law | None = None, regime: str | None = None, note: str = "") -> float:
        """Commit an event at t: evaluate, apply the step (scale then
        delta), re-anchor. Returns the new value. Law/regime carry over
        unless overridden."""
        a = self.anchor_at(t)
        v = self.value_at(t) * scale + delta
        self.set_anchor(t, v, law if law is not None else a.law,
                        a.regime if regime is None else regime, note)
        return v

    def regime_shift(self, t: float, regime: str, note: str = "") -> None:
        """Re-anchor at t with a new regime (value and law carry over)."""
        a = self.anchor_at(t)
        self.set_anchor(t, self.value_at(t), a.law, regime, note)
