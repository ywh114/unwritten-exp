"""Derive layer (M-a): derived axes are populated, monotone in their
drivers, and idempotent; effective_climate reads [niche] metadata and
modulates by organs; wariness stays a trait."""

from __future__ import annotations

import pathlib

import pytest

from exp.k13_treegen.fauna.backbone import build
from exp.k13_treegen.fauna.content import load_content
from exp.k13_treegen.fauna.derive import (
    DERIVED_AXES, derive_derived, effective_climate)
from exp.k13_treegen.model import Node, Rank

CONTENT = pathlib.Path(__file__).parent.parent / "content" / "fauna"


@pytest.fixture(scope="module")
def pack():
    return load_content(CONTENT)


@pytest.fixture(scope="module")
def tree(pack):
    return build(1, pack)


def species(tree):
    return [n for n in tree.nodes.values() if n.rank is Rank.SPECIES]


def test_derived_axes_populated(tree):
    for n in species(tree):
        for ax in DERIVED_AXES:
            assert n.axes.get(ax) is not None, (n.path, ax)


def test_niche_breadth_entropy(tree):
    sp = species(tree)
    specialists = [n for n in sp
                   if len(n.axes.get("diet_spectrum") or {}) == 1]
    generalists = [n for n in sp
                   if len(n.axes.get("diet_spectrum") or {}) >= 3]
    assert specialists and generalists
    s = max(n.axes["niche_breadth"] for n in specialists)
    g = max(n.axes["niche_breadth"] for n in generalists)
    assert s == 0.0 and g > 0.3


def test_maturity_allometry(pack):
    small = Node(path="a", rank=Rank.SPECIES, parent="k1", sid="0" * 16,
                 axes={"body_mass": 0.01}, generics={"metabolism": "endotherm"})
    big = Node(path="b", rank=Rank.SPECIES, parent="k1", sid="0" * 16,
               axes={"body_mass": 100.0}, generics={"metabolism": "endotherm"})
    ecto = Node(path="c", rank=Rank.SPECIES, parent="k1", sid="0" * 16,
                axes={"body_mass": 100.0}, generics={"metabolism": "ectotherm"})
    for n in (small, big, ecto):
        derive_derived(n, pack)
    assert small.axes["maturity_age_yr"] < big.axes["maturity_age_yr"]
    assert ecto.axes["maturity_age_yr"] > big.axes["maturity_age_yr"]


def test_parental_care_from_fecundity(pack):
    def care(fec, social=None):
        n = Node(path="a", rank=Rank.SPECIES, parent="k1", sid="0" * 16,
                 axes={"fecundity": fec},
                 generics={"social": social} if social else {})
        if social:
            n.axes["social_system"] = social
        derive_derived(n, pack)
        return n.axes["parental_care"]
    assert care(100.0) == "none"
    assert care(15.0) == "guard"
    assert care(5.0) == "provision"
    assert care(1.0) == "extended"
    assert care(100.0, social="eusocial") == "guard"  # colony care


def test_territoriality_by_guild(pack):
    def terr(spectrum):
        n = Node(path="a", rank=Rank.SPECIES, parent="k1", sid="0" * 16,
                 axes={"diet_spectrum": spectrum}, generics={})
        derive_derived(n, pack)
        return n.axes["territoriality"]
    assert terr({"carnivore": 1.0}) > terr({"grazer": 1.0})


def test_dimorphism_needs_ornament(pack):
    plain = Node(path="a", rank=Rank.SPECIES, parent="k1", sid="0" * 16,
                 axes={}, generics={})
    maned = Node(path="b", rank=Rank.SPECIES, parent="k1", sid="0" * 16,
                 axes={"mane_ruff_extent": 0.6},
                 generics={"covering": "fur"})
    scaled = Node(path="c", rank=Rank.SPECIES, parent="k1", sid="0" * 16,
                  axes={"mane_ruff_extent": 0.6},
                  generics={"covering": "scales"})
    for n in (plain, maned, scaled):
        derive_derived(n, pack)
    assert plain.axes["size_dimorphism_ratio"] == 1.0
    assert plain.axes["dimorphism_direction"] == "none"
    assert maned.axes["size_dimorphism_ratio"] > 1.15
    assert maned.axes["dimorphism_direction"] == "male"
    # a mane dial on a scaled animal is no display organ (substrate)
    assert scaled.axes["size_dimorphism_ratio"] == 1.0


def test_derive_idempotent(pack, tree):
    n = species(tree)[0]
    before = {ax: n.axes.get(ax) for ax in DERIVED_AXES}
    derive_derived(n, pack)
    assert {ax: n.axes.get(ax) for ax in DERIVED_AXES} == before


def test_wariness_is_a_trait(tree):
    """wariness drifts (no derivation): rabbit authored 0.85, default 0.5,
    and it is NOT in DERIVED_AXES."""
    assert "wariness" not in DERIVED_AXES
    sp = species(tree)
    vals = {n.axes.get("wariness") for n in sp}
    assert None not in vals
    rabbits = [n for n in sp if n.preset == "tetrapod.rabbit"]
    assert rabbits and all(n.axes["wariness"] > 0.5 for n in rabbits)


def test_effective_climate(pack, tree):
    sp = species(tree)
    bear = next(n for n in sp if n.preset == "tetrapod.bear")
    ec = effective_climate(bear, pack)
    # bear [niche] temp_opt 10 minus 4 x the node's (drifted) blubber
    assert ec["temp_opt_c"] == pytest.approx(
        10.0 - 4.0 * bear.axes["blubber_thickness"])
    # endotherm widens breadth
    reptile = next(n for n in sp if n.preset == "tetrapod.reptile")
    er = effective_climate(reptile, pack)
    assert er["temp_breadth_c"] < ec["temp_breadth_c"]
    # a thicker-blubber species shifts further than the bear (the
    # blubber dial is 4 deg per unit; the penguin preset is no longer
    # generated under the radiate model — use any fatter species)
    fatter = max(sp, key=lambda n: n.axes.get("blubber_thickness", 0.0))
    assert fatter.axes.get("blubber_thickness", 0.0) > \
        bear.axes["blubber_thickness"]
    ef = effective_climate(fatter, pack)
    meta_bear = pack.presets["tetrapod.bear"]["niche"]["temp_opt_c"]
    meta_fat = pack.presets[fatter.preset]["niche"]["temp_opt_c"]
    assert (meta_fat - ef["temp_opt_c"]) > (meta_bear - ec["temp_opt_c"])
