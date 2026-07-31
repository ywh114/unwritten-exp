"""M12 tests — descriptions are grammatical, traceable, and never
contradict the record."""

from __future__ import annotations

import pathlib

import pytest

from exp.k13_treegen.backbone import build
from exp.k13_treegen.content import load_content
from exp.k13_treegen.describe import describe
from exp.k13_treegen.model import Node, Rank
from exp.k13_treegen.nomenclature import assign_names

CONTENT = pathlib.Path(__file__).parent / "content" / "fauna"


@pytest.fixture(scope="module")
def pack():
    return load_content(CONTENT)


@pytest.fixture(scope="module")
def tree(pack):
    t = build(1, pack)
    assign_names(t, pack, 1)
    return t


def node(pack, **axes) -> Node:
    base = dict(body_mass=4.0, diet_spectrum={"carnivore": 1.0},
                tail_length_ratio=0.6, ear_size_ratio=0.08,
                mane_ruff_extent=0.0, horn_cover_texture="N/A")
    base.update(axes)
    return Node(path="k1.p1.c1.o1.f1.g1.s1", rank=Rank.SPECIES,
                parent="k1", sid="0" * 16, plan="tetrapod",
                preset="tetrapod.cat", axes=base,
                generics={"covering": "fur"})


# ──  template slots  ──────────────────────────────────────────────────────


def test_template_shape(pack):
    text, trace = describe(node(pack), pack)
    assert text.startswith("a medium fur cat-like carnivore")
    assert trace["size"] == "axes.body_mass"
    assert trace["covering"] == "generics.covering"
    assert trace["diet"] == "axes.diet_spectrum"


def test_article_agreement(pack):
    text, _ = describe(node(pack, body_mass=0.05), pack)
    assert text.startswith("a tiny")
    text, _ = describe(node(pack, body_mass=5000.0), pack)
    assert text.startswith("an enormous")


def test_diet_pair_when_close(pack):
    text, _ = describe(node(
        pack, diet_spectrum={"carnivore": 0.5, "frugivore": 0.45}), pack)
    assert "carnivore-frugivore" in text


# ──  salient part  ────────────────────────────────────────────────────────


def test_salient_part_is_highest_salience(pack):
    """mane (salience-heavy PART axis) beats a mildly deviant tail."""
    n = node(pack, mane_ruff_extent=0.9, tail_length_ratio=0.6)
    text, trace = describe(n, pack)
    assert "with a full mane" in text
    assert trace["salient_part"] == "axes.mane_ruff_extent"


def test_salient_part_deviation_required(pack):
    """A part at its preset value is not salient — no with-clause from it."""
    n = node(pack)   # all parts at cat-preset values, mane 0
    _, trace = describe(n, pack)
    assert trace.get("salient_part") != "axes.mane_ruff_extent"


# ──  no contradiction  ────────────────────────────────────────────────────


def test_na_is_silence(pack):
    """N/A axes are never mentioned."""
    n = node(pack, horn_cover_texture="N/A", mane_ruff_extent=0.0)
    text, _ = describe(n, pack)
    assert "horn" not in text


def test_no_flight_words_on_flightless(pack):
    n = node(pack, flight_style="flightless")
    n.preset = "winged_biped.penguin"
    n.generics = {"covering": "feathers"}
    text, _ = describe(n, pack)
    assert "soaring" not in text and "flight" not in text


# ──  trace completeness on the real tree  ─────────────────────────────────


def test_every_slot_traces(pack, tree):
    from exp.k13_treegen.model import Rank
    checked = 0
    for n in tree.nodes.values():
        if n.rank is not Rank.SPECIES:
            continue
        text, trace = describe(n, pack)
        assert text and trace["size"] and trace["diet"]
        for slot in ("size", "covering", "grade", "diet",
                     "salient_part"):
            if slot in trace:
                src = trace[slot]
                # the source must be committed on the node/preset
                assert src.startswith(("axes.", "generics.", "preset.")), src
        checked += 1
    assert checked > 300
