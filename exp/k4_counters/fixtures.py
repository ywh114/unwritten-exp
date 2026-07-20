"""Granary fixture: grain and population counters over one year (days 0..360).

The spec-mandated shape: evaluate grain across a year, insert a "burned"
event anchor, watch population lag behind. Counters never couple
continuously (that would break the closed forms) — coupling happens only
at anchor insertion: when the granary burns, the population counter is
re-anchored with a carrying capacity snapshotted from the grain counter
at that moment. Grain recovers logistically; people don't.
"""

from __future__ import annotations

from kernel.counters.counters import Counter
from kernel.counters.laws import Logistic

DAYS = 360
HARVEST_DAY = 180
BURN_DAY = 270

GRAIN_PER_PERSON = 2.0  # one grain unit feeds half a person, for fixture purposes


def build_village() -> tuple[Counter, Counter]:
    """(grain, population) counters with the year's events committed."""
    grain = Counter(regimes={"harvest": {"rate": 2.0}})
    grain.set_anchor(0, 100.0, Logistic(rate=0.02, capacity=1000.0), note="spring sowing")
    grain.regime_shift(HARVEST_DAY, "harvest", note="harvest surplus")
    grain.insert_event(BURN_DAY, scale=0.1, note="granary burned")

    population = Counter()
    population.set_anchor(0, 200.0, Logistic(rate=0.01, capacity=500.0), note="census")
    # Snapshot coupling at the event: demographers revise carrying capacity
    # from the post-burn grain level. The slow rate is the lag mechanism.
    post_burn_grain = grain.value_at(BURN_DAY)
    population.insert_event(
        BURN_DAY,
        law=Logistic(rate=0.003, capacity=post_burn_grain / GRAIN_PER_PERSON),
        note="famine revision",
    )
    return grain, population
