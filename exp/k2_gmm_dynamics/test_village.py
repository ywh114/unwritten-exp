"""K2 village-fixture tests: the day cycle visibly works (done-when 6)."""

from __future__ import annotations

import math

from exp.k2_gmm_dynamics import fixtures
from kernel.gmm_dynamics.dynamics import evolve, sample_at
from kernel.hashrng import Stream

SEED = 1
DAY = fixtures.MINUTES_PER_DAY
SEASON = 90
SITE_RADIUS = 10.0
NOON = 720.0
NIGHT = 1380.0  # 23:00, an hour into the walk-home segment


def _at(index: int, phase: float):
    t1 = (SEASON - 1) * DAY + phase
    return evolve(
        fixtures.initial_dist(SEED, index),
        0.0,
        t1,
        fixtures.villager_schedule(SEED, index),
    )


def test_noon_farmers_at_fields():
    on_site = total = 0
    for i in range(fixtures.N_VILLAGERS):
        if fixtures.villager_role(SEED, i) != "farmer":
            continue
        total += 1
        d = _at(i, NOON)
        x, y = sample_at(d, Stream(SEED, f"villager:{i:03d}", context_digest="test-noon"), clock=0)
        if math.hypot(x - fixtures.FIELDS[0], y - fixtures.FIELDS[1]) <= SITE_RADIUS:
            on_site += 1
    assert total > 0
    assert on_site / total >= 0.60


def test_night_villagers_home_or_tavern():
    on_site = 0
    for i in range(fixtures.N_VILLAGERS):
        d = _at(i, NIGHT)
        x, y = sample_at(d, Stream(SEED, f"villager:{i:03d}", context_digest="test-night"), clock=0)
        hx, hy = fixtures.villager_home(SEED, i)
        near_home = math.hypot(x - hx, y - hy) <= SITE_RADIUS
        near_tavern = math.hypot(x - fixtures.TAVERN[0], y - fixtures.TAVERN[1]) <= SITE_RADIUS
        if near_home or near_tavern:
            on_site += 1
    assert on_site / fixtures.N_VILLAGERS >= 0.60


def test_fixture_is_deterministic():
    a = fixtures.initial_gmm(SEED)
    b = fixtures.initial_gmm(SEED)
    assert a.moments_close(b.normalized(), tol=0.0)
