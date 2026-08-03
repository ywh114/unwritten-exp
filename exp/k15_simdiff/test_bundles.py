"""K15 frozen-bundle machinery — fast-tier tests (ticket 0012, Task B).

The sim-side bundle registry (ruling 13): each authored bundle record
becomes ONE frozen generic niche-dweller minted OUTSIDE the taxonomy
(sid ``bundle.<label>``, never authority.mint). Bundles participate in
population/dispersal/stress but never adapt (no select/mutate in the
verdict feed), never accrue g (Δg = 0), never split/speciate, and never
reach the authority (no reflog / tree / _alive presence).

Speed idiom: full genesis is too slow for the fast tier, so these tests
build a bare engine the way test_engine.py does (the conftest
k15_world/k15_capacity session fixtures stash the shared seed-1 world
in ``_CTX``/``_CAP``), SLICE the bundle list to the first 3 records,
and call ``Engine._seed_bundles()`` DIRECTLY (the seeding step genesis
runs; the first 3 bundles all seed on seed 1 — temperate land bundles).
"""

from __future__ import annotations

import numpy as np
import pytest

from exp.k15_simdiff import stress_adapter as sa
from exp.k15_simdiff.engine import Engine

SEED = 1
N_BUNDLES = 3

# The seed-1 world ctx + capacity anchor, built ONCE per worker process
# by the conftest session fixtures (same idiom as test_engine.py).
_CTX: sa.WorldContext | None = None
_CAP: np.ndarray | None = None


@pytest.fixture(scope="session", autouse=True)
def _k15_shared_world(k15_world, k15_capacity):
    global _CTX, _CAP
    _CTX, _CAP = k15_world, k15_capacity


def _engine() -> Engine:
    """A bare engine (world + tree + authority, NO genesis rain)."""
    return Engine(SEED, ctx=_CTX, capacity=_CAP)


def _bundles(eng: Engine, n: int = N_BUNDLES) -> Engine:
    """SLICE the bundle list to the first *n* records and seed the
    niche-dwellers (the fast-tier stand-in for the genesis bundle step).
    Mutates only this engine's own pack (fresh per engine)."""
    eng.pack.bundles = eng.pack.bundles[:n]
    eng._seed_bundles()
    return eng


def _digest(traits: dict) -> tuple:
    """The trait digest — sorted items, keys unique so values are never
    compared (nested dicts like dispersal_channels are fine)."""
    return tuple(sorted(traits.items()))


def _bundle_instances(eng: Engine) -> list:
    return [d for d in eng.instances.values()
            if d.x.species_id in eng.bundle_sids]


def test_seed_mints_one_instance_per_seeded_bundle():
    eng = _bundles(_engine())
    # the first 3 bundles all seed on seed 1 (temperate land bundles);
    # the machinery's contract is that EVERY seeded bundle gets exactly
    # ONE niche-dweller with the bundle sid
    assert eng.bundle_sids
    seeded = {f"bundle.{b['label']}"
              for b in eng.pack.bundles[:N_BUNDLES]}
    assert eng.bundle_sids == seeded
    bundle_inst = _bundle_instances(eng)
    assert len(bundle_inst) == len(seeded)       # ONE instance per bundle
    by_sid = {d.x.species_id: d for d in bundle_inst}
    for b in eng.pack.bundles[:N_BUNDLES]:
        d = by_sid[f"bundle.{b['label']}"]
        # traits = base preset (axes + generics) overlaid with the
        # envelope; the envelope carries the layer
        assert d.x.traits["plan"] == b["plan"]
        assert d.x.traits["layer"] == b["layer"]
        pid = d.x.traits["preset"]
        assert pid in eng.pack.presets
        assert eng.pack.presets[pid]["preset"]["plan"] == b["plan"]
        # envelope values ride through (a spot check: the envelope's
        # propagule_count is an authored field, not a preset default)
        assert d.x.traits["propagule_count"] == \
            b["envelope"]["propagule_count"]


def test_frozen_traits_and_g():
    """Frozen by construction: after 2 rounds every surviving bundle
    instance's trait digest is unchanged from genesis and Δg = 0 (no
    verdict-feed select/mutate/accrual — split-off fragments and
    foundlings inherit the bundle's genes and its 0 g)."""
    eng = _bundles(_engine())
    digest0 = {d.x.species_id: _digest(d.x.traits)
               for d in eng.instances.values()
               if d.x.species_id in eng.bundle_sids}
    eng.round(0)
    eng.round(1)
    survivors = _bundle_instances(eng)
    assert survivors
    for d in survivors:
        assert _digest(d.x.traits) == digest0[d.x.species_id]
        assert eng._g_since_split.get(d.x.instance_id, 0.0) == 0.0


def test_authority_invisible():
    """Bundles never reach the authority: no bundle sid in the reflog,
    the tree's nodes, or _alive (they never commit, never mint via the
    authority, never register as unseeded)."""
    eng = _bundles(_engine())
    eng.round(0)
    eng.round(1)
    bset = set(eng.bundle_sids)
    for entry in eng.authority.reflog:
        assert not (bset & set(entry.values())), entry
    for node in eng.tree.nodes.values():
        assert node.sid not in bset, node.sid
    assert not (bset & eng.authority._alive)


def test_participates():
    """Bundles participate in the dynamics: the population update runs
    through them, so after 2 rounds at least one bundle instance still
    holds mass."""
    eng = _bundles(_engine())
    eng.round(0)
    eng.round(1)
    assert any(d.mass > 0.0 for d in _bundle_instances(eng))


def test_rounds_with_only_bundles_no_crash():
    """Edge: rounds on an engine whose instances are ONLY bundle
    instances — _commit hands the authority an EMPTY views list (and an
    empty g map / candidate set) and must not crash. (The authority
    tolerates it: with no live species and an empty _alive the
    extinction pass is a no-op.)"""
    eng = _bundles(_engine())
    assert eng.bundle_sids
    assert not any(d.x.species_id not in eng.bundle_sids
                   for d in eng.instances.values())
    log0 = eng.round(0)
    assert log0.instances == ()
    eng.round(1)


def test_deterministic_seed():
    """Same sliced bundles + _seed_bundles => byte-identical per-iid
    cells mask and N field (all draws ride the pinned k15.genesis
    stream keyed by the bundle sid; sorted-label processing order)."""
    eng1 = _bundles(_engine())
    eng2 = _bundles(_engine())
    assert sorted(eng1.instances) == sorted(eng2.instances)
    assert sorted(eng1.bundle_sids) == sorted(eng2.bundle_sids)
    for iid in sorted(eng1.instances):
        d1, d2 = eng1.instances[iid], eng2.instances[iid]
        assert d1.box == d2.box
        assert d1.cells.tobytes() == d2.cells.tobytes()
        assert d1.N.tobytes() == d2.N.tobytes()
