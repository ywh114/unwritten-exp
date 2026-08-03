"""M4 tests — pin schema extensions: any-rank pins, radiation targets,
directional-drift derivations, invented-clade budget. Lint rules R8–R10
must each be able to fail (planted violations).

Backbone-side acceptance (radiation honored ~N, pins have relatives,
authored values byte-exact after build, drift measurably biases
descendants) is deferred to M7 — see docs/m4-pins.md.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

from exp.k13_treegen.fauna.content import ContentPack, load_content
from exp.k13_treegen.fauna.lint import lint

CONTENT = pathlib.Path(__file__).parent.parent / "content" / "fauna"


@pytest.fixture(scope="module")
def pack() -> ContentPack:
    return load_content(CONTENT)


def _pin(pack: ContentPack, label: str) -> dict:
    return next(p for p in pack.pins if p["label"] == label)


# ──  gate: real content  ──────────────────────────────────────────────────


def test_real_content_lints_clean(pack):
    assert lint(pack) == []


def test_texture_pins_carry_rank_and_radiation(pack):
    for label, rank in (("murid rodents", "family"),
                        ("passerine songbirds", "family"),
                        ("beetles", "order")):
        p = _pin(pack, label)
        assert p["rank"] == rank
        assert p["radiation"] > 0


def test_species_pins_default_rank(pack):
    """Pins without an explicit rank are species-rank and non-radiating."""
    horse = _pin(pack, "horse")
    assert horse.get("rank", "species") == "species"
    assert horse.get("radiation", 0) == 0


def test_equines_directional_drift(pack):
    """The "horse but more cursorial" demonstrator: positive signed bias on
    the cursorial proxy axes."""
    eq = _pin(pack, "equines")
    assert eq["rank"] == "genus" and eq["radiation"] == 3
    assert eq["drift"]["limb_length_to_trunk"] > 0
    assert eq["drift"]["neck_length_ratio"] > 0


def test_invented_pin_within_budget_and_small(pack):
    cr = _pin(pack, "coal-rat")
    assert "invented" in cr["flags"]
    assert cr["axes"]["body_mass"] <= 1.0
    n_invented = sum("invented" in p.get("flags", []) for p in pack.pins)
    assert n_invented <= pack.budget["invented_max"]


# ──  planted violations (R8–R10 must be able to fail)  ────────────────────


def _tampered(pack: ContentPack, mutate) -> ContentPack:
    p = copy.deepcopy(pack)
    mutate(p)
    return p


def test_plant_species_rank_radiation(pack):
    def m(p):
        _pin(p, "horse")["radiation"] = 5
    errs = lint(_tampered(pack, m))
    assert any("species-rank" in e and "horse" in e for e in errs)


def test_plant_unknown_rank(pack):
    def m(p):
        _pin(p, "horse")["rank"] = "tribe"
    errs = lint(_tampered(pack, m))
    assert any("unknown rank" in e for e in errs)


def test_plant_drift_on_enum_axis(pack):
    """A signed lean on an enum is meaningless — redraw is directionless."""
    def m(p):
        _pin(p, "equines")["drift"] = {"pattern_motif": 1.0}
    errs = lint(_tampered(pack, m))
    assert any("directionless" in e or "non-scalar" in e for e in errs)


def test_plant_drift_teleport(pack):
    def m(p):
        _pin(p, "equines")["drift"]["limb_length_to_trunk"] = 9.0
    errs = lint(_tampered(pack, m))
    assert any("teleport" in e for e in errs)


def test_plant_drift_on_nonradiating_pin(pack):
    def m(p):
        _pin(p, "horse")["drift"] = {"limb_length_to_trunk": 1.0}
    errs = lint(_tampered(pack, m))
    assert any("dead content" in e for e in errs)


def test_plant_invented_over_budget(pack):
    def m(p):
        for i in range(p.budget["invented_max"] + 2):
            p.pins.append({
                "preset": "tetrapod.squirrel", "label": f"invented-{i}",
                "rank": "genus", "radiation": 2,
                "axes": {"body_mass": 0.2}, "flags": ["pinned", "invented"]})
    errs = lint(_tampered(pack, m))
    assert any("exceed budget" in e for e in errs)


def test_plant_invented_megafauna(pack):
    """An invented elephant breaks the everyday register — critter tier only."""
    def m(p):
        _pin(p, "coal-rat")["axes"]["body_mass"] = 500.0
    errs = lint(_tampered(pack, m))
    assert any("small-bodied ceiling" in e for e in errs)
