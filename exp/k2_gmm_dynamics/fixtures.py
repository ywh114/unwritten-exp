"""Toy-village fixture for K2: 50 villagers with role-based day schedules.

Map (units: meters, time unit: minutes):
* market at (0, 0) — everyone gathers at dawn,
* fields at (40, 10) — farmers by day,
* tavern at (5, -8) — everyone in the evening,
* homes on a ring of radius ~25 — everyone at night.

Roles: farmer (day at the fields), merchant (day at the market). Every
villager gets a per-villager `Schedule` (period 1440 min = one day):
night home → dawn market → day by role → evening tavern → night home.
Deterministic in `--seed`: roles, homes and starts derive from K1 streams.
"""

from __future__ import annotations

import math

from kernel.gmm_dynamics.dynamics import DriftField, Schedule
from kernel.gmm_dynamics.gmm import GMM
from kernel.hashrng import Stream

MINUTES_PER_DAY = 1440.0

# Phase boundaries (minutes after midnight).
PHASE_DAWN = 360.0  # 06:00 — walk to the market
PHASE_DAY = 480.0  # 08:00 — work begins
PHASE_EVENING = 1020.0  # 17:00 — tavern
PHASE_NIGHT = 1320.0  # 22:00 — walk home

MARKET = (0.0, 0.0)
FIELDS = (40.0, 10.0)
TAVERN = (5.0, -8.0)
HOME_RING_RADIUS = 25.0
HOME_RING_JITTER = 4.0

N_VILLAGERS = 50
FARMER_FRACTION = 0.6

# Movement feel: brisk mean-reversion (≈15 min to close most of a commute)
# with a few meters of wandering. Rates are per minute. The stationary
# spread (σ/√(2θ) ≈ 4 m) spans several demo grid cells.
_THETA = 0.2
_SIGMA = 2.5  # m / sqrt(min)
_START_SPREAD = 15.0  # initial per-axis std of every villager's position


def _field(mu, theta: float = _THETA, sigma: float = _SIGMA) -> DriftField:
    return DriftField(mu=mu, theta=(theta, theta), sigma=(sigma, sigma))


def villager_role(world_seed: int, index: int) -> str:
    stream = Stream(world_seed, f"villager:{index:03d}", context_digest="role")
    return "farmer" if stream.uniform(0) < FARMER_FRACTION else "merchant"


def villager_home(world_seed: int, index: int) -> tuple[float, float]:
    stream = Stream(world_seed, f"villager:{index:03d}", context_digest="home")
    angle = stream.uniform(0, index=1) * 2.0 * math.pi
    radius = HOME_RING_RADIUS + HOME_RING_JITTER * (stream.uniform(0, index=2) - 0.5)
    return radius * math.cos(angle), radius * math.sin(angle)


def villager_schedule(world_seed: int, index: int) -> Schedule:
    """One villager's day: dawn market / day by role / evening tavern / night home."""
    day_site = FIELDS if villager_role(world_seed, index) == "farmer" else MARKET
    home = villager_home(world_seed, index)
    return Schedule(
        period=MINUTES_PER_DAY,
        segments=[
            (0.0, _field(home)),  # 00:00 night: asleep at home
            (PHASE_DAWN, _field(MARKET)),  # 06:00 dawn: market
            (PHASE_DAY, _field(day_site)),  # 08:00 day: fields or market
            (PHASE_EVENING, _field(TAVERN)),  # 17:00 evening: tavern
            (PHASE_NIGHT, _field(home)),  # 22:00 night: home
        ],
    )


def initial_gmm(world_seed: int) -> GMM:
    """Season-start belief: every villager somewhere near the market."""
    means = []
    for i in range(N_VILLAGERS):
        stream = Stream(world_seed, f"villager:{i:03d}", context_digest="start")
        means.append([stream.normal(0, index=10) * 5.0, stream.normal(0, index=11) * 5.0])
    n = N_VILLAGERS
    return GMM(
        weights=[1.0 / n] * n,
        means=means,
        covs=[[[_START_SPREAD**2, 0.0], [0.0, _START_SPREAD**2]]] * n,
    )


def initial_dist(world_seed: int, index: int) -> GMM:
    """The single-villager (unit-mass) component of `initial_gmm`."""
    g = initial_gmm(world_seed)
    return GMM([1.0], g.means[index : index + 1], g.covs[index : index + 1])
