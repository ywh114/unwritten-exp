"""K15 shared seed-1 world fixtures (ticket 0021 item 4, folding 0016).

``load_world(1)`` (plus the capacity anchor) was the dominant repeated
cost of the k15 fast tier: every ``Engine(1)`` construction re-opened
the K11 dump and re-derived the water fields (~1.5 s) and the currents
payload (~0.5 s). These session-scoped fixtures build the seed-1
WorldContext and its K capacity ONCE per worker process; tests share
them via ``Engine(1, ctx=..., capacity=...)``, which skips its own
loads (the engine falls back to per-engine loads when the args are
None, so a missed call site is merely slower, never wrong).

Safety: the ctx is READ-ONLY after ``load_world`` (every ``ctx.*``
write lives inside it; ``evaluate`` / ``_ensure_snow_glacier`` only
read, the latter idempotently attaching the B6 §3 fields) and K is
only ever indexed, never written — so sharing is determinism-neutral
and xdist-safe (each worker process builds its own session copy).
"""

from __future__ import annotations

import pytest

from exp.k15_simdiff import stress_adapter as sa
from exp.k15_simdiff.genesis import load_capacity


@pytest.fixture(scope="session")
def k15_world():
    """The seed-1 WorldContext, built once per worker process."""
    return sa.load_world(1)


@pytest.fixture(scope="session")
def k15_capacity(k15_world):
    """The seed-1 capacity anchor K (genesis.load_capacity), derived
    once from the shared world."""
    return load_capacity(1, k15_world)
