"""M8 tests — nomenclature: pins named from content, generated names
well-formed and salience-driven, within-genus uniqueness, collision chain,
determinism, gender agreement, and the NameContext world hook."""

from __future__ import annotations

import pathlib

import pytest

from exp.k13_treegen.backbone import build
from exp.k13_treegen.content import load_content
from exp.k13_treegen.metrics import run_checks
from exp.k13_treegen.model import Node, Rank, Tree
from exp.k13_treegen.nomenclature import (
    NameContext, _agree, assign_names)

CONTENT = pathlib.Path(__file__).parent / "content"


@pytest.fixture(scope="module")
def pack():
    return load_content(CONTENT)


@pytest.fixture(scope="module")
def tree(pack):
    t = build(1, pack)
    assign_names(t, pack, 1)
    return t


def species(tree):
    return [n for n in tree.nodes.values() if n.rank is Rank.SPECIES]


# ──  gate: the named tree passes metrics  ─────────────────────────────────


def test_metrics_clean_on_named_tree(pack, tree):
    rep = run_checks(tree, pack)
    assert rep.ok, rep.text()


def test_every_species_named(pack, tree):
    assert all(n.name.binomial for n in species(tree))


def test_pins_carry_authored_names(pack, tree):
    def node(label):
        return next(n for n in tree.nodes.values() if n.label == label)
    assert node("horse").name.binomial == "Equus caballus"
    assert node("horse").name.folk == "horse"
    assert node("tiger").name.binomial == "Panthera tigris"
    assert node("equines").name.binomial == "Equus"
    assert node("murid rodents").name.binomial == "Muridae"
    assert node("beetles").name.binomial == "Coleoptera"
    assert node("coal-rat").name.binomial == "Carbonomys"


def test_horse_inside_equines_genus(pack, tree):
    """parent_pin placement: Equus caballus sits in the Equus genus."""
    horse = next(n for n in tree.nodes.values() if n.label == "horse")
    equines = next(n for n in tree.nodes.values() if n.label == "equines")
    assert horse.parent == equines.path


def test_well_formed_binomials(pack, tree):
    for n in species(tree):
        if n.label is not None:
            continue
        genus, epithet = n.name.binomial.split()
        assert genus[0].isupper() and epithet.islower()
        assert epithet.isalpha() or epithet.startswith("sp")


def test_unique_within_genus_cross_genus_allowed(pack, tree):
    by_genus: dict[str, list] = {}
    for n in species(tree):
        if n.name.binomial and " " in n.name.binomial:
            by_genus.setdefault(n.path.rsplit(".s", 1)[0], []).append(
                n.name.binomial.split()[-1])
    for g, eps in by_genus.items():
        assert len(eps) == len(set(eps)), g
    # convergent epithets across genera are LEGAL (the rufus rule)
    all_eps = [e for eps in by_genus.values() for e in eps]
    assert len(all_eps) > len(set(all_eps))  # and they do happen


def test_determinism(pack, tree):
    t2 = build(1, pack)
    assign_names(t2, pack, 1)
    assert tree.dumps() == t2.dumps()
    t3 = build(2, pack)
    assign_names(t3, pack, 2)
    assert tree.dumps() != t3.dumps()


def test_epithet_is_salience_driven(pack, tree):
    """A species with an extreme axis gets the matching stem: find any
    longicauda and check its tail is above its genus median."""
    for n in species(tree):
        if n.name.binomial and n.name.binomial.endswith("longicauda"):
            genus = n.path.rsplit(".s", 1)[0]
            tails = [m.axes["tail_length_ratio"] for m in species(tree)
                     if m.path.startswith(genus + ".")]
            med = sorted(tails)[len(tails) // 2]
            assert n.axes["tail_length_ratio"] > med
            return
    pytest.skip("no longicauda in this seed's tree")


def test_gender_agreement_mechanics():
    assert _agree("ruf", "us", "m") == "rufus"
    assert _agree("ruf", "us", "f") == "rufa"
    assert _agree("ruf", "us", "n") == "rufum"
    assert _agree("terrestr", "is", "n") == "terrestre"
    assert _agree("arboricola", "invariant", "f") == "arboricola"


def test_collision_chain(pack):
    """Two identical species in one genus must get distinct epithets."""
    t = Tree(seed=9)
    t.add(Node(path="k1", rank=Rank.KINGDOM, parent=None, sid="0" * 16,
               flags=["animalia"]))
    axes = dict(body_mass=5.0, base_color="rufous", tail_length_ratio=0.9,
                ear_size_ratio=0.2, pattern_motif="striped")
    for i in (1, 2):
        t.add(Node(path=f"k1.g1.s{i}", rank=Rank.SPECIES, parent="k1.g1",
                   sid=f"{i:016x}", plan="tetrapod", preset="tetrapod.cat",
                   axes=dict(axes)))
    g = Node(path="k1.g1", rank=Rank.GENUS, parent="k1", sid="3" * 16,
             plan="tetrapod", axes={})
    t.add(g)
    assign_names(t, pack, 9)
    names = [t.nodes[f"k1.g1.s{i}"].name.binomial for i in (1, 2)]
    assert all(names) and names[0] != names[1]
    assert names[0].split()[0] == names[1].split()[0]  # same genus


def test_context_hook(pack):
    """Geography stems are silent in the blind build, live with facts."""
    t1 = build(1, pack)
    assign_names(t1, pack, 1)
    assert not any(n.name.binomial and "borealis" in n.name.binomial
                   for n in species(t1))
    t2 = build(1, pack)
    assign_names(t2, pack, 1,
                 context=NameContext(facts={"region": "boreal"}))
    assert any(n.name.binomial and n.name.binomial.endswith("borealis")
               for n in species(t2))
