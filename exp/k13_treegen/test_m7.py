"""M7 tests — the blind tree-build: determinism, structure (frame map, no
empty orders), pin integration (ranks, byte-exact, relatives, radiation),
drift bias, and diversity geometry (sister ≈ σ, between > within,
convergent reachability)."""

from __future__ import annotations

import math
import pathlib
import statistics

import pytest

from exp.k13_treegen.backbone import build
from exp.k13_treegen.content import load_content, merged_pin
from exp.k13_treegen.forces import Condition, evolve
from exp.k13_treegen.metrics import run_checks
from exp.k13_treegen.model import Rank
from exp.k13_treegen.seeding import stage_stream

CONTENT = pathlib.Path(__file__).parent / "content"


@pytest.fixture(scope="module")
def pack():
    return load_content(CONTENT)


@pytest.fixture(scope="module")
def tree(pack):
    return build(1, pack)


def species(tree):
    return [n for n in tree.nodes.values() if n.rank is Rank.SPECIES]


def _zdist(pack, a: dict, b: dict) -> float:
    """sigma-normalized euclidean distance over shared scalar axes."""
    total, n = 0.0, 0
    for ax, spec in pack.registry.axes.items():
        va, vb = a.get(ax), b.get(ax)
        if (spec.sigma > 0 and isinstance(va, (int, float))
                and isinstance(vb, (int, float))):
            total += ((va - vb) / spec.sigma) ** 2
            n += 1
    return math.sqrt(total / n) if n else 0.0


# ──  determinism & census  ────────────────────────────────────────────────


def test_byte_identical_replay(pack, tree):
    assert tree.dumps() == build(1, pack).dumps()
    assert tree.dumps() != build(2, pack).dumps()


def test_census(pack, tree):
    counts: dict[Rank, int] = {}
    for n in tree.nodes.values():
        counts[n.rank] = counts.get(n.rank, 0) + 1
    assert counts[Rank.KINGDOM] == 1
    assert counts[Rank.PHYLUM] == 2
    assert counts[Rank.CLASS] == 3
    assert counts[Rank.ORDER] == 24
    assert counts[Rank.SPECIES] > 300


def test_metrics_gate_clean(pack, tree):
    rep = run_checks(tree, pack)
    assert rep.ok, rep.text()


# ──  structure  ───────────────────────────────────────────────────────────


def test_frame_map(pack, tree):
    chordate = None
    for n in tree.nodes.values():
        if n.rank is Rank.CLASS:
            phylum = tree.nodes[n.parent]
            plan = pack.registry.plans[n.plan]
            assert plan.frame in phylum.flags
            if n.plan in ("tetrapod", "winged_biped"):
                assert "inner_frame" in phylum.flags
                chordate = phylum.path if n.plan == "tetrapod" else chordate
                if n.plan == "winged_biped":
                    assert phylum.path == chordate  # same phylum
            if n.plan == "hexapod":
                assert "outer_frame" in phylum.flags


def test_no_empty_orders(pack, tree):
    sp = [n.path for n in species(tree)]
    for n in tree.nodes.values():
        if n.rank is Rank.ORDER:
            assert any(p.startswith(n.path + ".") for p in sp), n.path


# ──  pins  ────────────────────────────────────────────────────────────────


def _node(tree, label):
    return next(n for n in tree.nodes.values() if n.label == label)


def test_pins_at_authored_ranks(pack, tree):
    assert _node(tree, "beetles").rank is Rank.ORDER
    assert _node(tree, "murid rodents").rank is Rank.FAMILY
    assert _node(tree, "passerine songbirds").rank is Rank.FAMILY
    assert _node(tree, "equines").rank is Rank.GENUS
    assert _node(tree, "coal-rat").rank is Rank.GENUS
    assert _node(tree, "horse").rank is Rank.SPECIES


def test_pins_byte_exact(pack, tree):
    for pin in pack.pins:
        n = _node(tree, pin["label"])
        axes, _ = merged_pin(pack, pin)
        assert {k: str(v) for k, v in n.axes.items()} == \
               {k: str(v) for k, v in axes.items()}, pin["label"]


def test_species_pins_have_relatives(pack, tree):
    sp = species(tree)
    for pin in pack.pins:
        if pin.get("rank", "species") != "species":
            continue
        n = _node(tree, pin["label"])
        genus = n.path.rsplit(".s", 1)[0]
        assert any(s.path != n.path and s.path.startswith(genus + ".")
                   for s in sp), pin["label"]


def test_radiation_soft_range(pack, tree):
    sp = [n.path for n in species(tree)]
    for label, target in (("murid rodents", 60),
                          ("passerine songbirds", 80), ("beetles", 120)):
        n = _node(tree, label)
        desc = sum(1 for p in sp if p.startswith(n.path + "."))
        assert target / 3 <= desc <= target * 3, (label, desc)


def test_drift_biases_descendants(pack, tree):
    """Existence proof: equines' descendants are more cursorial than the
    deer order's background species."""
    eq = _node(tree, "equines")
    eq_sp = [n for n in species(tree) if n.path.startswith(eq.path + ".")]
    assert len(eq_sp) >= 2
    deer_order = eq.path.rsplit(".f", 1)[0]
    bg_sp = [n for n in species(tree)
             if n.path.startswith(deer_order + ".f1.g1.")
             and n.label is None]
    assert bg_sp
    eq_mean = statistics.mean(n.axes["limb_length_to_trunk"]
                              for n in eq_sp)
    bg_mean = statistics.mean(n.axes["limb_length_to_trunk"]
                              for n in bg_sp)
    assert eq_mean > bg_mean


# ──  diversity geometry  ──────────────────────────────────────────────────


def test_within_order_variance_nonzero(pack, tree):
    sp = species(tree)
    orders: dict[str, list] = {}
    for n in sp:
        orders.setdefault(n.path.rsplit(".f", 1)[0], []).append(n)
    for opath, members in orders.items():
        if len(members) >= 3:
            dists = [_zdist(pack, a.axes, b.axes)
                     for a, b in zip(members, members[1:])]
            assert statistics.mean(dists) > 0.1, opath


def test_between_order_exceeds_within(pack, tree):
    sp = species(tree)
    orders: dict[str, list] = {}
    for n in sp:
        orders.setdefault(n.path.rsplit(".f", 1)[0], []).append(n)
    big = [m for ms in orders.values() if len(ms) >= 3 for m in ms[:3]]
    by_order: dict[str, list] = {}
    for n in sp:
        by_order.setdefault(n.path.rsplit(".f", 1)[0], []).append(n)
    within, between = [], []
    keys = sorted(by_order)
    for i, ka in enumerate(keys):
        for kb in keys[i + 1:]:
            between.append(_zdist(pack, by_order[ka][0].axes,
                                  by_order[kb][0].axes))
        ms = by_order[ka]
        within += [_zdist(pack, a.axes, b.axes)
                   for a, b in zip(ms, ms[1:])]
    assert statistics.mean(between) > statistics.mean(within)


def test_convergent_grade_reachable(pack, tree):
    """Carcinization class: a lineage under descent toward a target grade
    converges into its neighborhood (convergence is selection-driven)."""
    cat = pack.presets["tetrapod.cat"]
    bear = pack.presets["tetrapod.bear"]
    center = {**cat.get("knobs", {}), **cat.get("axes", {})}
    target = {**bear.get("knobs", {}), **bear.get("axes", {})}
    cur = _node(tree, "tiger")          # cat-grade start, real node
    center = {k: v for k, v in target.items()
              if isinstance(v, (int, float))}
    d0 = _zdist(pack, cur.axes, target)
    s = stage_stream(7, "conv", "c")
    for i in range(30):
        cur = evolve(cur, pack, s.child(str(i)), 100.0, path=f"x.{i}",
                     condition=Condition(stress=1.0),
                     clade_center=center, couplings=False)
    d1 = _zdist(pack, cur.axes, target)
    assert d1 < 0.5 * d0, f"no convergence: {d0:.2f} -> {d1:.2f}"
