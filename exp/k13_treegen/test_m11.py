"""M11 meta-tests — the harness must be able to fail.

Each checker gets a synthetic tree built to trip exactly it (planted
violation) and must flag it; the clean tree must pass everything. This is
the rebuild plan's M11 gate: low diversity, coupling breach, frozen axis,
crocodile-on-monkey.
"""

from __future__ import annotations

import pathlib

import pytest

from exp.k13_treegen.content import load_content
from exp.k13_treegen.metrics import run_checks
from exp.k13_treegen.model import Node, Rank, Tree

CONTENT = pathlib.Path(__file__).parent / "content"


@pytest.fixture(scope="module")
def pack():
    return load_content(CONTENT)


def sp(path: str, preset: str, plan: str = "tetrapod", label=None,
       flags=(), **axes) -> Node:
    return Node(path=path, rank=Rank.SPECIES, parent="k1.p1.c1.o1.f1.g1",
                sid="0" * 16, plan=plan, preset=preset, label=label,
                axes=axes, flags=list(flags))


def tree_of(*nodes: Node, seed: int = 1) -> Tree:
    t = Tree(seed=seed)
    for n in nodes:
        t.add(n)
    return t


@pytest.fixture
def clean_tree() -> Tree:
    return tree_of(
        sp("k1.p1.c1.o1.f1.g1.s1", "tetrapod.cat",
           body_mass=4.0, base_color="gray"),
        sp("k1.p1.c1.o2.f1.g1.s1", "tetrapod.deer",
           body_mass=100.0, base_color="rufous"),
    )


# ──  gate: clean tree passes everything  ──────────────────────────────────


def test_clean_tree_passes(pack, clean_tree):
    rep = run_checks(clean_tree, pack)
    assert rep.ok, rep.text()


def test_report_byte_stable(pack, clean_tree):
    a = run_checks(clean_tree, pack).text()
    b = run_checks(clean_tree, pack).text()
    assert a == b
    assert "seed 00000001" in a


# ──  planted violations (each check must be able to fail)  ────────────────


def test_plant_low_diversity(pack):
    rep = run_checks(tree_of(
        sp("k1.p1.c1.o1.f1.g1.s1", "tetrapod.cat", body_mass=4.0)), pack)
    assert any("only 1 species" in v for v in rep.violations["diversity"])


def test_plant_single_grade(pack):
    rep = run_checks(tree_of(
        sp("k1.p1.c1.o1.f1.g1.s1", "tetrapod.cat",
           body_mass=4.0, base_color="gray"),
        sp("k1.p1.c1.o1.f1.g2.s1", "tetrapod.cat",
           body_mass=6.0, base_color="tan")), pack)
    assert any("one preset" in v for v in rep.violations["diversity"])


def test_plant_frozen_axis(pack):
    """Two species, same plan, identical base_color — the v1 freeze bug."""
    rep = run_checks(tree_of(
        sp("k1.p1.c1.o1.f1.g1.s1", "tetrapod.cat",
           body_mass=4.0, base_color="gray"),
        sp("k1.p1.c1.o2.f1.g1.s1", "tetrapod.deer",
           body_mass=100.0, base_color="gray")), pack)
    assert any("base_color" in v for v in rep.violations["frozen_axis"])


def test_plant_coupling_breach(pack):
    rep = run_checks(tree_of(
        sp("k1.p1.c1.o1.f1.g1.s1", "winged_biped.penguin",
           plan="winged_biped", body_mass=20.0, flight_style="soaring"),
        sp("k1.p1.c1.o2.f1.g1.s1", "winged_biped.eagle",
           plan="winged_biped", body_mass=5.0,
           flight_style="sustained_flapping")), pack)
    assert any("soaring" in v for v in rep.violations["coupling_breach"])


def test_plant_crocodile_on_monkey(pack):
    rep = run_checks(tree_of(
        sp("k1.p1.c1.o1.f1.g1.s1", "tetrapod.cat", label="megacroc",
           flags=("pinned",), body_mass=40000.0, base_color="dark_green"),
        sp("k1.p1.c1.o2.f1.g1.s1", "tetrapod.deer",
           body_mass=100.0, base_color="rufous")), pack)
    assert any("megacroc" in v for v in rep.violations["pin_coherence"])


def test_plant_g_runs_backward(pack):
    child = sp("k1.p1.c1.o1.f1.g1.s1", "tetrapod.cat",
               body_mass=4.0, base_color="gray")
    child.g = 5.0
    parent = sp("k1.p1.c1.o2.f1.g1.s1", "tetrapod.deer",
                body_mass=100.0, base_color="rufous")
    parent.g = 50.0
    child.parent = parent.path
    rep = run_checks(tree_of(child, parent), pack)
    assert any("clock runs backward" in v for v in rep.violations["g_clock"])


def test_plant_gen_time_inverted(pack):
    whale = sp("k1.p1.c1.o1.f1.g1.s1", "tetrapod.bear",
               body_mass=90000.0, base_color="black")
    whale.gen_time = 0.1     # whale-grade on a mouse clock
    mouse = sp("k1.p1.c1.o2.f1.g1.s1", "tetrapod.squirrel",
               body_mass=0.05, base_color="rufous")
    mouse.gen_time = 30.0
    rep = run_checks(tree_of(whale, mouse), pack)
    assert any("ordering inverted" in v for v in rep.violations["g_clock"])


# ──  M7 checkers  ─────────────────────────────────────────────────────────


def test_plant_empty_order(pack):
    from exp.k13_treegen.model import Node, Rank
    root = Node(path="k1", rank=Rank.KINGDOM, parent=None, sid="0" * 16,
                flags=["animalia"])
    order = Node(path="k1.p1.c1.o1", rank=Rank.ORDER, parent="k1.p1.c1",
                 sid="0" * 16, plan="tetrapod", preset="tetrapod.cat")
    rep = run_checks(tree_of(root, order), pack)
    assert any("empty order" in v for v in rep.violations["backbone"])


def test_plant_frame_violation(pack):
    from exp.k13_treegen.model import Node, Rank
    root = Node(path="k1", rank=Rank.KINGDOM, parent=None, sid="0" * 16,
                flags=["animalia"])
    phylum = Node(path="k1.p1", rank=Rank.PHYLUM, parent="k1",
                  sid="0" * 16, flags=["outer_frame"])   # wrong frame
    cls = Node(path="k1.p1.c1", rank=Rank.CLASS, parent="k1.p1",
               sid="0" * 16, plan="tetrapod")
    rep = run_checks(tree_of(root, phylum, cls), pack)
    assert any("frame" in v for v in rep.violations["backbone"])


def test_plant_pin_axes_drifted(pack):
    tiger = sp("k1.p1.c1.o1.f1.g1.s1", "tetrapod.cat", label="tiger",
               flags=("pinned",), body_mass=999999.0)  # not the pin record
    deer = sp("k1.p1.c1.o1.f1.g1.s2", "tetrapod.cat",
              body_mass=5.0, base_color="gray")
    rep = run_checks(tree_of(tiger, deer), pack)
    assert any("byte-exact" in v
               for v in rep.violations["pin_integration"])


def test_plant_orphan_pin(pack):
    from exp.k13_treegen.content import merged_pin
    pin = next(p for p in pack.pins if p["label"] == "tiger")
    axes, _ = merged_pin(pack, pin)
    tiger = sp("k1.p1.c1.o1.f1.g1.s1", "tetrapod.cat", label="tiger",
               flags=("pinned",), **axes)   # byte-exact but alone
    rep = run_checks(tree_of(tiger), pack)
    assert any("orphan" in v for v in rep.violations["pin_integration"])
