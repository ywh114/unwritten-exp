"""M0 tests — record model, quantity store, rebind, seeding.

Rigorous, K1-only (no random/uuid/time). Includes a K1-driven random-tree
property test and a source audit for forbidden nondeterminism imports.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from kernel.hashrng import Stream

from exp.k13_treegen.model import (
    NameRecord,
    Node,
    Provenance,
    Quantity,
    QuantityStore,
    Rank,
    RANK_PREFIX,
    RebindError,
    Tree,
    rebind,
)
from exp.k13_treegen.seeding import (
    naming_stage,
    root_stream,
    stage_stream,
)

HERE = pathlib.Path(__file__).parent


# ──  helpers  ─────────────────────────────────────────────────────────────


def _full_node(path="k1.p1.c1.o1.f1.g1.s1", rank=Rank.SPECIES,
               parent="k1.p1.c1.o1.f1.g1") -> Node:
    n = Node(path=path, rank=rank, parent=parent, sid="0123456789abcdef",
             plan="tetrapod", preset="tetrapod.cat", label=None,
             g=123.5, gen_time=2.0,
             axes={"body_mass": 4.0, "temp_opt_c": 18.0},
             generics={"locomotor": "cursorial_limb_set"},
             flags=["pinned"], edge_delta={"snout_ratio": [0.3, 0.35]})
    n.name = NameRecord(binomial="Felis silvestris", folk=None,
                        history=["Felis sp.1", "Felis silvestris"])
    n.provenance = Provenance(kind="lifted", source_id="src", site_id="ley1",
                              round=2)
    n.quantities.set("", "endemism", 0.7, provenance="M11", round=1)
    n.quantities.set("patch3", "presence", 1.0, round=1)  # flag-as-quantity
    return n


def _small_tree() -> Tree:
    t = Tree(seed=1)
    t.add(Node(path="k1", rank=Rank.KINGDOM, parent=None, sid="k" * 16,
               label="animalia"))
    t.add(Node(path="k1.p1", rank=Rank.PHYLUM, parent="k1", sid="a" * 16,
               flags=["inner"]))
    t.add(Node(path="k1.p2", rank=Rank.PHYLUM, parent="k1", sid="b" * 16,
               flags=["outer"]))
    t.add(Node(path="k1.p1.c1", rank=Rank.CLASS, parent="k1.p1", sid="c" * 16,
               plan="tetrapod"))
    return t


# ──  round-trip  ──────────────────────────────────────────────────────────


def test_node_roundtrip_full():
    n = _full_node()
    assert Node.from_json(n.to_json()).to_json() == n.to_json()


def test_node_roundtrip_minimal():
    n = Node(path="k1", rank=Rank.KINGDOM, parent=None, sid="0" * 16)
    assert Node.from_json(n.to_json()).to_json() == n.to_json()


def test_tree_roundtrip_and_dumps_stable():
    t = _small_tree()
    d1 = t.dumps()
    d2 = t.dumps()
    assert d1 == d2                                   # byte-stable
    t2 = Tree.from_json(json.loads(d1))
    assert t2.dumps() == d1                           # round-trip stable
    assert t2.seed == 1


def test_dumps_keys_sorted():
    t = _small_tree()
    obj = json.loads(t.dumps())
    # top-level and per-node keys must be sorted (canonical form)
    assert list(obj.keys()) == sorted(obj.keys())
    for nd in obj["nodes"]:
        assert list(nd.keys()) == sorted(nd.keys())


def test_duplicate_path_rejected():
    t = _small_tree()
    with pytest.raises(ValueError):
        t.add(Node(path="k1", rank=Rank.KINGDOM, parent=None, sid="z" * 16))


def test_children_and_roots_ordered():
    t = _small_tree()
    roots = t.roots()
    assert [r.path for r in roots] == ["k1"]
    kids = t.children("k1")
    assert [c.path for c in kids] == ["k1.p1", "k1.p2"]   # path-sorted


def test_rank_prefix_complete():
    assert set(RANK_PREFIX) == set(Rank)
    assert len(set(RANK_PREFIX.values())) == len(Rank)    # prefixes unique


# ──  quantity store  ──────────────────────────────────────────────────────


def test_quantity_set_get_value():
    s = QuantityStore()
    assert s.value("", "x") == 0.0                      # default
    s.set("", "x", 3.0, provenance="test", round=1)
    q = s.get("", "x")
    assert q is not None and q.value == 3.0 and q.round == 1
    assert s.value("", "x") == 3.0


def test_quantity_accumulate():
    s = QuantityStore()
    s.accumulate("", "biomass", 2.0, round=1)
    s.accumulate("", "biomass", 5.0, round=2)
    assert s.value("", "biomass") == 7.0


def test_quantity_flag_is_01_quantity():
    s = QuantityStore()
    s.set("", "relict", 1.0, round=1)
    assert s.value("", "relict") == 1.0


def test_quantity_expire():
    s = QuantityStore()
    s.set("", "old", 1.0, round=0)
    s.set("", "new", 2.0, round=3)
    removed = s.expire(before_round=2)
    assert removed == 1
    assert s.get("", "old") is None
    assert s.value("", "new") == 2.0


def test_quantity_json_order_independent():
    a = QuantityStore()
    a.set("z", "m", 1.0); a.set("a", "m", 2.0); a.set("a", "b", 3.0)
    b = QuantityStore()
    b.set("a", "b", 3.0); b.set("a", "m", 2.0); b.set("z", "m", 1.0)
    assert a.to_json() == b.to_json()                   # canonical order
    assert QuantityStore.from_json(a.to_json()).to_json() == a.to_json()


# ──  name + provenance  ───────────────────────────────────────────────────


def test_name_record_defaults_reserved():
    nr = NameRecord()
    assert nr.binomial is None and nr.folk is None and nr.history == []
    assert NameRecord.from_json(nr.to_json()) == nr


def test_provenance_regular_minimal():
    p = Provenance()
    assert p.to_json() == {"kind": "regular"}           # no lifted fields leak
    assert Provenance.from_json(p.to_json()).kind == "regular"


def test_provenance_lifted_roundtrip():
    p = Provenance(kind="lifted", source_id="s", site_id="ley", round=2)
    assert Provenance.from_json(p.to_json()) == p


# ──  rebind  ──────────────────────────────────────────────────────────────


PERMS = {"locomotor": ["cursorial_limb_set", "flipper"],
         "signal": ["antler"]}


def test_rebind_allowed():
    g = {}
    rebind(g, "locomotor", "flipper", PERMS)
    assert g["locomotor"] == "flipper"


def test_rebind_illegal_realization():
    with pytest.raises(RebindError):
        rebind({}, "locomotor", "jet_propulsion", PERMS)


def test_rebind_unknown_generic():
    with pytest.raises(RebindError):
        rebind({}, "respiration", "lungs", PERMS)


def test_rebind_force_bypasses_permissions():
    g = {}
    rebind(g, "locomotor", "aerial_buoyant", PERMS, force=True)
    assert g["locomotor"] == "aerial_buoyant"
    rebind(g, "brand_new_generic", "x", PERMS, force=True)  # even unknown
    assert g["brand_new_generic"] == "x"


# ──  seeding (C3)  ────────────────────────────────────────────────────────


def test_seeding_deterministic_same_seed():
    a = root_stream(42)
    b = root_stream(42)
    assert a.u64(0, 0) == b.u64(0, 0)
    assert a.uniform(7, 3) == b.uniform(7, 3)


def test_seeding_differs_across_seeds():
    assert root_stream(1).u64(0, 0) != root_stream(2).u64(0, 0)


def test_stage_stream_child_independence():
    # two different stage paths at the same coordinates must differ
    x = stage_stream(1, "backbone").u64(0, 0)
    y = stage_stream(1, "pins").u64(0, 0)
    assert x != y


def test_naming_stage_round_keyed():
    assert naming_stage(1, 0).u64(0, 0) != naming_stage(1, 1).u64(0, 0)
    assert naming_stage(1, 2).u64(5, 0) == naming_stage(1, 2).u64(5, 0)


# ──  property test: K1-driven random tree round-trips  ───────────────────


def test_random_tree_roundtrip_property():
    seed = 99
    s = Stream(seed, "m0.proptest")
    t = Tree(seed=seed)
    t.add(Node(path="k1", rank=Rank.KINGDOM, parent=None,
               sid=f"{s.u64(0, 0):016x}"))
    paths = ["k1"]
    ranks = {"k1": Rank.KINGDOM}
    for i in range(1, 200):
        # pick a parent whose rank < SPECIES
        eligible = [p for p in paths if ranks[p] < Rank.SPECIES]
        parent = eligible[s.randrange(len(eligible), i, 0)]
        prank = ranks[parent]
        crank = Rank(int(prank) + 1)
        # next child index under this parent
        nkids = sum(1 for p in paths if p.startswith(parent + "."))
        path = f"{parent}.{RANK_PREFIX[crank]}{nkids + 1}"
        node = Node(path=path, rank=crank, parent=parent,
                    sid=f"{s.u64(i, 1):016x}", g=float(i))
        if s.bernoulli(0.3, i, 2):
            node.axes["body_mass"] = s.uniform(i, 3) * 100
        if s.bernoulli(0.2, i, 4):
            node.quantities.set("", "score", s.uniform(i, 5), round=1)
        t.add(node)
        paths.append(path)
        ranks[path] = crank

    # invariants
    assert len(t.roots()) == 1
    for n in t.nodes.values():
        if n.parent is not None:
            assert n.parent in t.nodes
            assert t.nodes[n.parent].rank < n.rank      # strict rank order

    # round-trip byte-stable
    d = t.dumps()
    assert Tree.from_json(json.loads(d)).dumps() == d


# ──  K1-only source audit  ────────────────────────────────────────────────


@pytest.mark.parametrize("fname", ["model.py", "seeding.py"])
def test_no_nondeterministic_imports(fname):
    src = (HERE / fname).read_text()
    for line in src.splitlines():
        stripped = line.strip()
        for bad in ("import random", "from random", "import uuid",
                    "from uuid", "import time", "from time"):
            assert not stripped.startswith(bad), \
                f"{fname}: forbidden nondeterministic import: {stripped}"
