"""Tests for the K15 TreeAuthority commit handshake (spec §9).

Most tests inject a small controlled metric (three axes, salience 1.0,
unit spans) so distances are exact arithmetic: with axes temp
(span 20), moisture (span 1) and leaf (enum), the distance between two
gene mappings is (|Δtemp|/20 + |Δmoisture| + leaf-mismatch) / 3.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from exp.k13_treegen.interface import InstanceView, Outcome
from exp.k13_treegen.model import Node, Rank, Tree
from exp.k15_simdiff.authority import (
    AXIS_METRIC,
    GENERIC_SALIENCE,
    MERGE_D,
    MERGE_GRACE,
    SPECIATION_D,
    SUB_D,
    AxisMetric,
    TreeAuthority,
    genes_distance,
)
from kernel.hashrng import Stream

# ── fixtures: controlled metric, record, tree, views ─────────────────

_METRIC = {
    "temp": AxisMetric(salience=1.0, span=20.0, value_type="scalar"),
    "moisture": AxisMetric(salience=1.0, span=1.0, value_type="scalar"),
    "leaf": AxisMetric(salience=1.0, value_type="enum"),
}

RECORD = {"temp": 10.0, "moisture": 0.5, "leaf": "entire"}
SID1 = "1111111111111111"
SID2 = "2222222222222222"


def _traits(temp=10.0, moisture=0.5, leaf="entire"):
    return {"temp": temp, "moisture": moisture, "leaf": leaf}


def _species(path, sid, axes, generics=None, plan="tree", preset="tree.oak"):
    return Node(path=path, rank=Rank.SPECIES, parent="k1.p0.c0.o0.f0.g0",
                sid=sid, plan=plan, preset=preset, axes=dict(axes),
                generics=dict(generics or {}))


def _tree(*species_nodes) -> Tree:
    t = Tree(seed=7)
    for n in species_nodes:
        t.add(n)
    return t


def _auth(*species_nodes, metric=_METRIC, seed=7) -> TreeAuthority:
    return TreeAuthority(_tree(*species_nodes), metric=metric)


def _view(sid, iid, traits, mass=1.0) -> InstanceView:
    return InstanceView(species_id=sid, instance_id=iid,
                        traits=dict(traits), mass=mass)


def _rng(seed=7, ctx="test") -> Stream:
    return Stream(seed, "k15.authority.test", ctx)


# ── mint / redraw ────────────────────────────────────────────────────


def test_mint_redraw_round_trip():
    auth = _auth(_species("1", SID1, RECORD,
                          generics={"support": "trunk_single"}))
    x = auth.mint(SID1, "i0", _rng())
    assert x.species_id == SID1 and x.instance_id == "i0"
    assert x.traits["temp"] == 10.0 and x.traits["leaf"] == "entire"
    assert x.traits["support"] == "trunk_single"     # generics ride along
    assert x.traits["plan"] == "tree"                # bookkeeping keys
    assert x.traits["preset"] == "tree.oak"
    # sim-side WIP drift, then commit amends the record
    x.traits["temp"] = 12.5
    log = auth.update([x.view(mass=3.0)], _rng())
    assert log.instances[0].outcome is Outcome.KEEP
    assert log.instances[0].orthodox
    y = auth.redraw("i0")
    assert y is not None
    assert y.species_id == SID1 and y.instance_id == "i0"
    assert y.traits["temp"] == 12.5                   # amended record
    assert y.traits["support"] == "trunk_single"      # generics preserved
    assert auth.redraw("ghost") is None
    with pytest.raises(KeyError):
        auth.mint("deadbeefdeadbeef", "i1", _rng())


def test_keep_undrifted():
    auth = _auth(_species("1", SID1, RECORD))
    log = auth.update([_view(SID1, "i0", RECORD, mass=2.0)], _rng())
    d = log.instances[0]
    assert d.outcome is Outcome.KEEP and d.orthodox and d.target is None
    assert len(auth.tree.nodes) == 1
    assert auth.reflog == []        # record unchanged: no amend entry


def test_small_drift_keeps_and_amends_record():
    auth = _auth(_species("1", SID1, RECORD))
    drifted = _traits(temp=11.0)                    # (1/20)/3 ≈ 0.0167
    assert genes_distance(drifted, RECORD, _METRIC) < SUB_D
    log = auth.update([_view(SID1, "i0", drifted, mass=1.0)], _rng())
    d = log.instances[0]
    assert d.outcome is Outcome.KEEP and d.orthodox
    assert auth.tree.nodes["1"].axes["temp"] == 11.0   # gerrit-style amend
    (amend,) = [e for e in auth.reflog if e["event"] == "amend"]
    assert amend["before"] == RECORD
    assert amend["after"] == drifted
    assert amend["instance"] == "i0"


def test_non_orthodox_keep_snaps_to_amended_record():
    # two close instances: the non-orthodox one's sub-SUB_D drift is
    # NOT retained (no micro-nodes for drift) — it re-mints from the
    # amended record.
    auth = _auth(_species("1", SID1, RECORD))
    b = _traits(temp=11.0)
    assert genes_distance(RECORD, b, _METRIC) < SUB_D
    log = auth.update([_view(SID1, "iA", RECORD, mass=2.0),
                       _view(SID1, "iB", b, mass=1.0)], _rng())
    by = {d.instance_id: d for d in log.instances}
    assert by["iA"].outcome is Outcome.KEEP and by["iA"].orthodox
    assert by["iB"].outcome is Outcome.KEEP and not by["iB"].orthodox
    assert by["iB"].target is None
    assert len(auth.tree.nodes) == 1
    assert auth.redraw("iB").traits["temp"] == 10.0   # snapped back


# ── divergence: SUBSPECIES band, SPLIT ───────────────────────────────


def test_subspecies_in_band():
    auth = _auth(_species("1", SID1, RECORD))
    b = _traits(moisture=0.9)      # 0.4/3 ≈ 0.133 ∈ [SUB_D, SPECIATION_D)
    d = genes_distance(RECORD, b, _METRIC)
    assert SUB_D <= d < SPECIATION_D
    log = auth.update([_view(SID1, "iA", RECORD, mass=5.0),
                       _view(SID1, "iB", b, mass=9.0)], _rng())
    by = {d.instance_id: d for d in log.instances}
    assert by["iA"].outcome is Outcome.KEEP and by["iA"].orthodox
    assert by["iB"].outcome is Outcome.SUBSPECIES
    assert by["iB"].target and len(by["iB"].target) == 16
    new = auth.tree.nodes["1.ss0"]
    assert new.rank is Rank.SUBSPECIES
    assert new.parent == "1" and new.sid == by["iB"].target
    assert new.axes == b                              # representative's genes
    (ss,) = [e for e in auth.reflog if e["event"] == "subspecies"]
    assert ss["sid"] == new.sid and ss["parent_sid"] == SID1
    assert ss["instances"] == ["iB"] and ss["genes"] == b


def test_split_above_speciation_d():
    auth = _auth(_species("1", SID1, RECORD))
    b = _traits(temp=30.0, moisture=0.6)    # (1.0 + 0.1)/3 = 0.367
    assert genes_distance(RECORD, b, _METRIC) >= SPECIATION_D
    log = auth.update([_view(SID1, "iA", RECORD, mass=1.0),
                       _view(SID1, "iB", b, mass=1.0)], _rng())
    by = {d.instance_id: d for d in log.instances}
    assert by["iA"].outcome is Outcome.KEEP and by["iA"].orthodox
    assert by["iB"].outcome is Outcome.SPLIT
    new = auth.tree.nodes["1.s0"]
    assert new.rank is Rank.SPECIES and new.parent == "1"
    assert new.sid == by["iB"].target and new.axes == b
    (split,) = [e for e in auth.reflog if e["event"] == "split"]
    assert split["genes"] == b and split["parent_sid"] == SID1


def test_split_cluster_all_members_rekey_to_one_node():
    auth = _auth(_species("1", SID1, RECORD))
    b1 = _traits(temp=30.0, moisture=0.6)
    b2 = _traits(temp=28.0, moisture=0.7)
    assert genes_distance(b1, b2, _METRIC) < SUB_D          # one cluster
    assert genes_distance(RECORD, b1, _METRIC) >= SPECIATION_D
    log = auth.update([_view(SID1, "iA", RECORD, mass=1.0),
                       _view(SID1, "iB", b1, mass=2.0),
                       _view(SID1, "iC", b2, mass=1.0)], _rng())
    by = {d.instance_id: d for d in log.instances}
    assert by["iB"].outcome is Outcome.SPLIT
    assert by["iC"].outcome is Outcome.SPLIT
    assert by["iB"].target == by["iC"].target               # same new node
    assert auth.tree.nodes["1.s0"].axes == b1               # highest mass
    assert auth.redraw("iB").species_id == by["iB"].target  # re-keyed
    assert auth.redraw("iC").species_id == by["iC"].target


# ── g-currency divide rank (ticket 0008, fauna RFC §1) ───────────────


def test_divide_rank_by_g_below_star_is_subspecies():
    """With the g bookkeeping supplied, a below-g* trait-separated
    cluster divides as SUBSPECIES — even a large trait-distance
    cluster stays SUBSPECIES below g* (the SPECIATION_D band is not a
    rounds currency)."""
    auth = _auth(_species("1", SID1, RECORD))
    b = _traits(temp=30.0, moisture=0.6)       # 0.367 >= SPECIATION_D
    assert genes_distance(RECORD, b, _METRIC) >= SPECIATION_D
    gs = {"iA": 120.0, "iB": 220.0}            # below the lineage g*
    log = auth.update([_view(SID1, "iA", RECORD, mass=5.0),
                       _view(SID1, "iB", b, mass=1.0)], _rng(),
                      g_since_split=gs, g_star={SID1: 500.0})
    by = {d.instance_id: d for d in log.instances}
    assert by["iB"].outcome is Outcome.SUBSPECIES
    assert by["iB"].target and len(by["iB"].target) == 16
    assert auth.tree.nodes["1.ss0"].rank is Rank.SUBSPECIES


def test_divide_beyond_g_star_waits_for_the_promotion():
    """A trait-separated cluster whose rep is BEYOND the lineage's g*
    is NOT divided individually (that would churn a species per
    extreme-mutant fragment — measured hundreds of spurious SPLITs per
    round at seed 1); it stays with the lineage until the wholesale
    g-promotion re-keys the whole gene pool when the ORTHODOX crosses
    g*."""
    auth = _auth(_species("1", SID1, RECORD))
    b = _traits(moisture=0.9)                  # 0.133: separated cluster
    assert SUB_D <= genes_distance(RECORD, b, _METRIC) < SPECIATION_D
    # orthodox below g*, fragment beyond: no divide at all
    gs = {"iA": 120.0, "iB": 700.0}
    log = auth.update([_view(SID1, "iA", RECORD, mass=5.0),
                       _view(SID1, "iB", b, mass=1.0)], _rng(),
                      g_since_split=gs, g_star={SID1: 500.0})
    by = {d.instance_id: d for d in log.instances}
    assert by["iA"].outcome is Outcome.KEEP
    assert by["iB"].outcome is Outcome.KEEP
    assert len(auth.tree.nodes) == 1
    # once the orthodox crosses, the whole lineage promotes as ONE
    gs2 = {"iA": 700.0, "iB": 720.0}
    log2 = auth.update([_view(SID1, "iA", RECORD, mass=5.0),
                        _view(SID1, "iB", b, mass=1.0)], _rng(),
                       g_since_split=gs2, g_star={SID1: 500.0})
    by2 = {d.instance_id: d for d in log2.instances}
    assert by2["iA"].outcome is Outcome.SPLIT
    assert by2["iA"].target == by2["iB"].target
    assert auth.tree.nodes["1.s0"].rank is Rank.SPECIES


def test_g_crossing_promotes_whole_lineage():
    """Ticket 0008: the LINEAGE's g — the orthodox instance's
    g_since_split (the record's representative) — crossing the
    lineage's g_star promotes the WHOLE gene pool to one new SPECIES
    node in a single divide, even though every instance remains
    trait-connected to the orthodox (a dense lineage is a continuous
    trait cloud — the trait cluster never forms, so the g crossing IS
    the divide trigger)."""
    auth = _auth(_species("1", SID1, RECORD))
    b = _traits(temp=10.5)                    # 0.025/3 < SUB_D: one cluster
    assert genes_distance(RECORD, b, _METRIC) < SUB_D
    gs = {"iA": 700.0, "iB": 720.0}           # orthodox crossed g*
    log = auth.update([_view(SID1, "iA", RECORD, mass=5.0),
                       _view(SID1, "iB", b, mass=1.0)], _rng(),
                      g_since_split=gs, g_star={SID1: 500.0})
    by = {d.instance_id: d for d in log.instances}
    assert by["iA"].outcome is Outcome.SPLIT
    assert by["iB"].outcome is Outcome.SPLIT
    assert by["iA"].target == by["iB"].target     # one node for all
    assert len(by["iA"].target) == 16
    assert auth.tree.nodes["1.s0"].rank is Rank.SPECIES
    assert auth.redraw("iB").species_id == by["iA"].target
    assert auth.redraw("iA").species_id == by["iA"].target


def test_g_crossing_promotion_is_one_shot_and_trait_clusters_rank():
    """Below the orthodox's crossing the lineage does NOT promote —
    the trait-cluster path ranks the divides by classify(rep g,
    g_star): a trait-separated cluster is SUBSPECIES below g*, SPLIT
    beyond. And the promotion is one-shot: a second commit with the
    same post-crossing g values does not re-promote (the species node
    is born promoted)."""
    auth = _auth(_species("1", SID1, RECORD))
    b = _traits(moisture=0.9)      # 0.133: trait-separated cluster
    assert SUB_D <= genes_distance(RECORD, b, _METRIC) < SPECIATION_D
    gs = {"iA": 120.0, "iB": 220.0}            # orthodox below g*
    log = auth.update([_view(SID1, "iA", RECORD, mass=5.0),
                       _view(SID1, "iB", b, mass=1.0)], _rng(),
                      g_since_split=gs, g_star={SID1: 500.0})
    by = {d.instance_id: d for d in log.instances}
    assert by["iA"].outcome is Outcome.KEEP and by["iA"].orthodox
    assert by["iB"].outcome is Outcome.SUBSPECIES    # below g*
    # the orthodox later crosses g*: the whole lineage promotes once
    gs2 = {"iA": 700.0, "iB": 740.0}
    log2 = auth.update([_view(SID1, "iA", RECORD, mass=5.0),
                        _view(SID1, "iB", b, mass=1.0)], _rng(),
                       g_since_split=gs2, g_star={SID1: 500.0})
    by2 = {d.instance_id: d for d in log2.instances}
    assert by2["iA"].outcome is Outcome.SPLIT
    assert by2["iB"].outcome is Outcome.SPLIT
    promoted = by2["iA"].target
    # one-shot: the same g values again do not re-promote the species
    # node — the orthodox stays under it; the beyond-g* separated
    # fragment waits for the promotion too (no trait-cluster SPLITs)
    log3 = auth.update([_view(promoted, "iA", RECORD, mass=5.0),
                        _view(promoted, "iB", b, mass=1.0)], _rng(),
                       g_since_split=gs2, g_star={promoted: 500.0})
    by3 = {d.instance_id: d for d in log3.instances}
    assert all(d.outcome is Outcome.KEEP for d in by3.values())


def test_merge_gate_uses_scalar_only_metric():
    """The merge gate reads the scalar-only subset of the metric
    (ticket 0008): enum flips are same-blob noise and do NOT gate
    merges — a pair whose FULL-metric distance (enum-inflated) is
    above MERGE_D merges anyway, while the same pair's scalar
    divergence still refuses. The leaf enum carries LOW salience here,
    mirroring the real flora table (a single enum flip among ~70 keys
    is a few % of V0, far below SUB_D)."""
    low = {"temp": AxisMetric(salience=1.0, span=20.0,
                              value_type="scalar"),
           "moisture": AxisMetric(salience=1.0, span=1.0,
                                  value_type="scalar"),
           "leaf": AxisMetric(salience=0.05, value_type="enum")}
    # enum flip + small scalar drift: full d = 0.0512 > MERGE_D (the
    # old full-metric gate refuses) but scalar-only d = 0.0275 <
    # MERGE_D -> the enum-inflated pair still merges
    auth = _auth(_species("1", SID1, RECORD), metric=low)
    b = _traits(temp=10.5, moisture=0.53, leaf="lobed")
    assert MERGE_D <= genes_distance(RECORD, b, low) < SUB_D
    pair = frozenset({"iA", "iB"})
    for _ in range(MERGE_GRACE + 1):
        log = auth.update([_view(SID1, "iA", RECORD, mass=5.0),
                           _view(SID1, "iB", b, mass=1.0)], _rng(),
                          merge_candidates={pair})
    by = {d.instance_id: d for d in log.instances}
    assert by["iB"].outcome is Outcome.MERGE
    # scalar divergence still refuses: temp 12.8 -> scalar d = 0.07
    auth2 = _auth(_species("1", SID1, RECORD), metric=low)
    far = _traits(temp=12.8, leaf="lobed")     # full d < SUB_D: one cluster
    assert genes_distance(RECORD, far, low) < SUB_D
    pair2 = frozenset({"iA", "iB"})
    for _ in range(MERGE_GRACE + 1):
        log2 = auth2.update([_view(SID1, "iA", RECORD, mass=5.0),
                             _view(SID1, "iB", far, mass=1.0)], _rng(),
                            merge_candidates={pair2})
    by2 = {d.instance_id: d for d in log2.instances}
    assert by2["iB"].outcome is Outcome.KEEP


# ── merges (engine-gated) ────────────────────────────────────────────


def test_merge_under_merge_d_with_grace():
    auth = _auth(_species("1", SID1, RECORD))
    b = _traits(temp=11.0)                # (0.05)/3 ≈ 0.0167 < MERGE_D
    assert genes_distance(RECORD, b, _METRIC) < MERGE_D
    pair = frozenset({"iA", "iB"})
    views = [_view(SID1, "iA", RECORD, mass=5.0),
             _view(SID1, "iB", b, mass=1.0)]
    # rounds 0..4: grace refuses (genesis siblings diverged at round 0)
    for _ in range(MERGE_GRACE):
        log = auth.update(views, _rng(), merge_candidates={pair})
        by = {d.instance_id: d for d in log.instances}
        assert by["iB"].outcome is Outcome.KEEP
    assert not [e for e in auth.reflog if e["event"] == "merge"]
    # round 5: rounds_since_divergence = 5 >= MERGE_GRACE -> merge
    log = auth.update(views, _rng(), merge_candidates={pair})
    by = {d.instance_id: d for d in log.instances}
    assert by["iB"].outcome is Outcome.MERGE and by["iB"].target == "iA"
    assert by["iA"].outcome is Outcome.KEEP and by["iA"].orthodox
    (merge,) = [e for e in auth.reflog if e["event"] == "merge"]
    assert merge["instance"] == "iB" and merge["into"] == "iA"
    assert auth.redraw("iB") is None                      # absorbed: gone
    assert auth.redraw("iA") is not None


def test_merge_requires_engine_gate():
    # without merge_candidates the authority never merges, however
    # similar and however long the grace
    auth = _auth(_species("1", SID1, RECORD))
    b = _traits(temp=11.0)
    views = [_view(SID1, "iA", RECORD, mass=5.0),
             _view(SID1, "iB", b, mass=1.0)]
    for _ in range(MERGE_GRACE + 2):
        log = auth.update(views, _rng())      # no candidates passed
        by = {d.instance_id: d for d in log.instances}
        assert by["iB"].outcome is Outcome.KEEP
    assert not [e for e in auth.reflog if e["event"] == "merge"]


def test_merge_refused_when_distance_too_large():
    auth = _auth(_species("1", SID1, RECORD))
    far = _traits(temp=13.6)              # (3.6/20)/3 = 0.06 in
    d = genes_distance(RECORD, far, _METRIC)   # [MERGE_D, SUB_D): same
    assert MERGE_D <= d < SUB_D                # cluster (KEEP), no merge
    pair = frozenset({"iA", "iB"})
    log = auth.update([_view(SID1, "iA", RECORD, mass=5.0),
                       _view(SID1, "iB", far, mass=1.0)], _rng(),
                      merge_candidates={pair})
    by = {d.instance_id: d for d in log.instances}
    assert by["iB"].outcome is Outcome.KEEP
    assert not [e for e in auth.reflog if e["event"] == "merge"]


def test_merge_orthodox_never_absorbed():
    auth = _auth(_species("1", SID1, RECORD))
    b = _traits(temp=11.0)
    pair = frozenset({"iA", "iB"})
    views = [_view(SID1, "iA", RECORD, mass=1.0),      # orthodox, light
             _view(SID1, "iB", b, mass=100.0)]         # drifted, heavy
    for _ in range(MERGE_GRACE + 1):
        log = auth.update(views, _rng(), merge_candidates={pair})
    by = {d.instance_id: d for d in log.instances}
    assert by["iB"].outcome is Outcome.MERGE and by["iB"].target == "iA"
    assert by["iA"].outcome is Outcome.KEEP and by["iA"].orthodox


def test_merge_mass_tie_survivor_lowest_id():
    auth = _auth(_species("1", SID1, RECORD))
    b = _traits(temp=11.0)
    pair = frozenset({"iB", "iA"})
    views = [_view(SID1, "iA", RECORD, mass=2.0),
             _view(SID1, "iB", b, mass=2.0)]
    for _ in range(MERGE_GRACE + 1):
        log = auth.update(views, _rng(), merge_candidates={pair})
    by = {d.instance_id: d for d in log.instances}
    assert by["iB"].outcome is Outcome.MERGE and by["iB"].target == "iA"


def test_cross_species_merge_candidates_ignored():
    auth = _auth(_species("1", SID1, RECORD), _species("2", SID2, RECORD))
    b = _traits(temp=11.0)
    pair = frozenset({"i1", "i2"})
    views = [_view(SID1, "i1", RECORD, mass=1.0),
             _view(SID2, "i2", b, mass=1.0)]
    for _ in range(MERGE_GRACE + 1):
        log = auth.update(views, _rng(), merge_candidates={pair})
    by = {d.instance_id: d for d in log.instances}
    assert by["i1"].outcome is Outcome.KEEP
    assert by["i2"].outcome is Outcome.KEEP     # speciation is a hard barrier
    assert not [e for e in auth.reflog if e["event"] == "merge"]


def test_merge_candidates_must_be_pairs():
    auth = _auth(_species("1", SID1, RECORD))
    with pytest.raises(ValueError):
        auth.update([_view(SID1, "i0", RECORD, mass=1.0)], _rng(),
                    merge_candidates={frozenset({"i0"})})


# ── orthodox rule ────────────────────────────────────────────────────


def test_orthodox_tie_breaks_distance_then_mass_then_id():
    auth = _auth(_species("1", SID1, RECORD))
    # equal distance (all record-exact): highest mass wins
    log = auth.update([_view(SID1, "iA", RECORD, mass=1.0),
                       _view(SID1, "iB", RECORD, mass=2.0),
                       _view(SID1, "iC", RECORD, mass=3.0)], _rng())
    by = {d.instance_id: d for d in log.instances}
    assert by["iC"].orthodox and by["iC"].outcome is Outcome.KEEP
    # equal distance and mass: lowest instance id wins
    log2 = auth.update([_view(SID1, "iA", RECORD, mass=5.0),
                        _view(SID1, "iB", RECORD, mass=5.0),
                        _view(SID1, "iC", RECORD, mass=5.0)], _rng())
    by2 = {d.instance_id: d for d in log2.instances}
    assert by2["iA"].orthodox and not by2["iB"].orthodox


def test_orthodox_distance_beats_mass():
    auth = _auth(_species("1", SID1, RECORD))
    drifted = _traits(temp=11.0)
    log = auth.update([_view(SID1, "iA", drifted, mass=1000.0),
                       _view(SID1, "iB", RECORD, mass=1.0)], _rng())
    by = {d.instance_id: d for d in log.instances}
    assert by["iB"].orthodox                # distance, not mass


# ── extinction ───────────────────────────────────────────────────────


def test_extinct_when_instances_vanish():
    auth = _auth(_species("1", SID1, RECORD), _species("2", SID2, RECORD))
    log1 = auth.update([_view(SID1, "i0", RECORD, mass=1.0)], _rng())
    assert log1.extinct_species == ()
    log2 = auth.update([], _rng())
    assert log2.extinct_species == (SID1,)
    assert SID2 not in log2.extinct_species     # never minted: never extinct
    assert "1" in auth.tree.nodes               # record stays as ghost
    (ex,) = [e for e in auth.reflog if e["event"] == "extinct"]
    assert ex == {"event": "extinct", "sid": SID1}


# ── determinism & hard rules ─────────────────────────────────────────


def test_determinism_identical_changelogs():
    def run(seed):
        auth = _auth(_species("1", SID1, RECORD), seed=seed)
        b = _traits(temp=30.0, moisture=0.6)
        views = [_view(SID1, "iA", RECORD, mass=1.0),
                 _view(SID1, "iB", b, mass=2.0)]
        logs = [auth.update(views, _rng(seed=seed)) for _ in range(2)]
        return auth, logs

    a1, logs1 = run(7)
    a2, logs2 = run(7)
    assert logs1 == logs2
    assert repr(logs1) == repr(logs2)               # byte-identical
    assert a1.tree.dumps() == a2.tree.dumps()
    assert a1.reflog == a2.reflog
    assert logs1[0].instances[1].target == logs2[0].instances[1].target


def test_hard_rule_audit_no_forbidden_imports():
    src = (Path(__file__).resolve().parent / "authority.py").read_text()
    for bad in ("random", "uuid", "time", "datetime"):
        assert not re.search(
            rf"^\s*(?:from\s+{bad}\s+import|import\s+{bad}\b)",
            src, re.M), f"forbidden {bad} import in authority.py"
    assert "hashrng" in src          # all randomness rides K1 streams


# ── the metric table & distance function ─────────────────────────────


def test_axis_metric_table_from_content_toml():
    assert AXIS_METRIC["height_m"].salience == 0.7
    assert AXIS_METRIC["height_m"].span == pytest.approx(200.0 - 0.005)
    assert AXIS_METRIC["height_m"].value_type == "scalar"
    assert AXIS_METRIC["layer"].value_type == "enum"
    assert AXIS_METRIC["dispersal_channels"].value_type == "set"
    assert AXIS_METRIC["leafout_month"].value_type == "int"
    assert genes_distance(RECORD, RECORD, AXIS_METRIC) == 0.0


def test_distance_full_divergence_with_real_metric():
    toml = tomllib.loads(
        (Path(__file__).resolve().parents[2] / "exp" / "k13_treegen"
         / "content" / "flora" / "axes_core.toml").read_text())
    lo, hi = {}, {}
    for name, t in toml["axis"].items():
        vt = t.get("value_type", "scalar")
        if vt in ("scalar", "int"):
            lo[name], hi[name] = t["bounds"]
        elif vt == "enum":
            lo[name], hi[name] = t["states"][0], t["states"][-1]
        elif vt == "weighted_set":
            lo[name] = {t["states"][0]: 1.0}
            hi[name] = {t["states"][-1]: 1.0}
    # every axis at full divergence -> weighted mean is exactly 1.0
    assert genes_distance(lo, hi, AXIS_METRIC) == pytest.approx(1.0)


def test_generic_keys_use_generic_salience():
    m = {**RECORD, "support": "trunk_single"}
    m2 = {**RECORD, "support": "trunk_multi"}
    expected = GENERIC_SALIENCE / (3.0 + GENERIC_SALIENCE)
    assert genes_distance(m, m2, _METRIC) == pytest.approx(expected)


def test_plan_preset_bookkeeping_keys_ignored_in_distance():
    a = {**RECORD, "plan": "tree", "preset": "tree.oak"}
    b = {**RECORD, "plan": "shrub", "preset": "tree.pine"}
    assert genes_distance(a, b, _METRIC) == 0.0


# ── _group_distances equivalence (the vectorized commit path) ────────

from exp.k15_simdiff.authority import _group_distances

_GMETRIC = dict(_METRIC)
_GMETRIC["chans"] = AxisMetric(salience=2.0, value_type="set")

_GROUP = [
    {"temp": 10.0, "moisture": 0.5, "leaf": "entire",
     "chans": {"wind": 0.5, "local": 0.5}},
    {"temp": 14.0, "moisture": 0.5, "leaf": "entire",
     "chans": {"wind": 0.7, "animal": 0.3}},
    {"temp": 2.0, "leaf": "lobed", "chans": {"local": 1.0}},
    {"moisture": 0.9, "leaf": "entire"},
    {"temp": 10.0, "moisture": 0.5, "leaf": "entire",
     "chans": {"wind": 0.5, "local": 0.5}, "novel_generic": 3},
    {},
]
_GRECORD = {"temp": 10.0, "moisture": 0.5, "leaf": "entire",
            "chans": {"wind": 0.5, "local": 0.5}}


def test_group_distances_matches_genes_distance():
    dist, rec = _group_distances(_GROUP, _GRECORD, _GMETRIC)
    n = len(_GROUP)
    assert dist.shape == (n, n) and rec.shape == (n,)
    for i, a in enumerate(_GROUP):
        assert rec[i] == pytest.approx(
            genes_distance(a, _GRECORD, _GMETRIC), abs=1e-12)
        for j, b in enumerate(_GROUP):
            assert dist[i][j] == pytest.approx(
                genes_distance(a, b, _GMETRIC), abs=1e-12)
            assert dist[i][j] == pytest.approx(dist[j][i], abs=1e-15)


def test_group_distances_empty_keys_match():
    dist, rec = _group_distances([{}, {}], {}, _GMETRIC)
    assert dist.tolist() == [[0.0, 0.0], [0.0, 0.0]]
    assert rec.tolist() == [0.0, 0.0]
