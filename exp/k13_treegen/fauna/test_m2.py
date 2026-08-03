"""M2 tests — content pack loads, lints clean, and every linter rule can
fail (planted violations).

The planted-violation tests are the point: a linter that can't fail is
decorative. Each rule gets a case that must trip it.
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


# ──  gate: real content  ──────────────────────────────────────────────────


def test_registry_loads(pack):
    assert len(pack.registry.axes) >= 100
    assert pack.registry.mass_axis() == "body_mass"
    assert len(pack.presets) == 24
    assert len(pack.pins) == 23


def test_real_content_lints_clean(pack):
    assert lint(pack) == []


def test_exactly_one_mass_axis(pack):
    masses = [a.name for a in pack.registry.axes.values()
              if a.unit.value == "mass"]
    assert masses == ["body_mass"]


def test_starting_plans_present(pack):
    assert set(pack.registry.plans) == {"tetrapod", "winged_biped", "hexapod"}


def test_functional_checklist_coverage(pack):
    """The starting pins cover the functional roles (eat/threaten/carry/
    see-daily + exotic) — a taste/coverage check."""
    labels = {p["label"] for p in pack.pins}
    for needed in ("horse", "red deer", "wolf", "tiger", "sparrow", "crow"):
        assert needed in labels, f"missing functional pin {needed}"
    # exotic flavor present
    assert {"tapir", "anteater", "pangolin"} & labels


# ──  planted violations (each rule must be able to fail)  ────────────────


def _tampered(pack: ContentPack, mutate) -> ContentPack:
    p = copy.deepcopy(pack)
    mutate(p)
    return p


def test_plant_diet_feeding_mismatch(pack):
    def m(p):
        # a filter-feeder with hypsodont molars is nonsense
        p.presets["tetrapod.deer"]["axes"]["diet_spectrum"] = {
            "filter_feeder": 1.0}
    errs = lint(_tampered(pack, m))
    assert any("filter_feeder" in e and "incompatible" in e for e in errs)


def test_plant_flightless_overridden_to_soaring(pack):
    def m(p):
        for pin in p.pins:
            if pin["label"] == "mallard":
                pin["preset"] = "winged_biped.penguin"   # flightless preset
                pin.setdefault("knobs", {})["flight_style"] = "soaring"
    errs = lint(_tampered(pack, m))
    assert any("flightless preset overridden" in e for e in errs)


def test_plant_crocodile_on_monkey(pack):
    """The v1 bug: a demersal pin under an arboreal preset (crocodile-on-
    monkey). Caught by the medium-consistency rule (monkey is terrestrial)."""
    def m(p):
        for pin in p.pins:
            if pin["label"] == "crocodile":
                pin["preset"] = "tetrapod.monkey"   # the actual v1 mistake
    errs = lint(_tampered(pack, m))
    assert any("medium jump" in e for e in errs)


def test_plant_eusocial_singleton(pack):
    def m(p):
        p.presets["hexapod.bee"]["axes"]["group_size"] = 1.0
    errs = lint(_tampered(pack, m))
    assert any("eusocial" in e or "group_size" in e for e in errs)


def test_plant_unknown_preset_reference(pack):
    def m(p):
        p.pins[0]["preset"] = "tetrapod.does_not_exist"
    errs = lint(_tampered(pack, m))
    assert any("unknown preset" in e for e in errs)


def test_plant_unregistered_axis_typo(pack):
    def m(p):
        p.presets["tetrapod.deer"]["knobs"]["snout_ratoo"] = 0.5  # typo
    errs = lint(_tampered(pack, m))
    assert any("not a registered axis" in e for e in errs)


# ──  vary-by-default: core axes are mutable (freeze-bug regression)  ─────


def test_core_axes_mutable(pack):
    """Every non-clade-steady, non-invariant axis must be mutable — the
    freeze-bug fix holds across the real content."""
    frozen = [a.name for a in pack.registry.axes.values()
              if not a.mutable and not a.clade_steady
              and a.tier.value != "invariant"]
    assert frozen == [], f"axes frozen that shouldn't be: {frozen}"


def test_behavior_diet_axes_present(pack):
    """The blocks v1 lacked are registered and mutable."""
    for name in ("diet_spectrum", "activity_period", "social_system",
                 "fecundity", "lifespan_yr", "wariness", "reproductive_mode"):
        a = pack.registry.axis(name)
        assert a.mutable, f"{name} should be mutable"
