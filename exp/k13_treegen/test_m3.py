"""M3 tests — patternation: axes registered, palettes loaded, presets author
the full patternation set (vary-by-default, not vary-on-expose), and the
palette lint rule can fail (planted violations).

The planted blue-mammal test is the point: palette legality is exactly the
kind of semantic rule v1 had no place to express.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

from exp.k13_treegen.content import ContentPack, load_content
from exp.k13_treegen.lint import lint

CONTENT = pathlib.Path(__file__).parent / "content"

PATTERNATION_AXES = (
    "base_color", "belly_color", "accent_color", "pattern_motif",
    "pattern_coverage", "pattern_contrast", "pattern_juvenile",
    "seasonal_molt",
)


@pytest.fixture(scope="module")
def pack() -> ContentPack:
    return load_content(CONTENT)


# ──  gate: real content  ──────────────────────────────────────────────────


def test_patternation_axes_registered(pack):
    for name in PATTERNATION_AXES:
        a = pack.registry.axis(name)
        assert a.mutable, f"{name} must be mutable (vary-by-default)"


def test_palettes_loaded(pack):
    assert set(pack.palettes) == {"tetrapod", "winged_biped", "hexapod"}
    # the pigment-reach asymmetry the rule exists for
    assert "blue" not in pack.palettes["tetrapod"]
    assert "blue" in pack.palettes["winged_biped"]
    assert "iridescent" in pack.palettes["hexapod"]


def test_every_preset_authors_patternation(pack):
    """No preset may leave patternation unwritten — that is vary-on-expose,
    the v1 failure shape. Patternation is authored content, not a default."""
    for pid, p in pack.presets.items():
        for ax in PATTERNATION_AXES:
            assert ax in p.get("axes", {}), f"{pid}: missing {ax}"


def test_real_content_lints_clean(pack):
    assert lint(pack) == []


def test_pin_patternation_overrides_land(pack):
    """The tiger pin demonstrates the system: orange striped under the gray
    mottled cat preset; tapir carries a natal coat."""
    tiger = next(p for p in pack.pins if p["label"] == "tiger")
    assert tiger["axes"]["base_color"] == "orange"
    assert tiger["axes"]["pattern_motif"] == "striped"
    tapir = next(p for p in pack.pins if p["label"] == "tapir")
    assert tapir["axes"]["pattern_juvenile"] == "natal_coat"


# ──  planted violations (the palette rule must be able to fail)  ──────────


def _tampered(pack: ContentPack, mutate) -> ContentPack:
    p = copy.deepcopy(pack)
    mutate(p)
    return p


def test_plant_blue_mammal(pack):
    """A blue tetrapod preset is a pigment-reach error."""
    def m(p):
        p.presets["tetrapod.deer"]["axes"]["base_color"] = "blue"
    errs = lint(_tampered(pack, m))
    assert any("base_color" in e and "palette" in e for e in errs)


def test_blue_herp_allowed_via_palette_extra(pack):
    """...but the herp grade legitimately reaches the full gamut
    (xanthophores/erythrophores, structural blue/iridescent): the reptile
    preset widens its palette, and pins under it inherit the widened reach."""
    extra = pack.presets["tetrapod.reptile"]["preset"]["palette_extra"]
    for c in ("red", "orange", "yellow", "blue", "green", "iridescent"):
        assert c in extra
    def m(p):
        for pin in p.pins:
            if pin["label"] == "crocodile":
                pin["axes"]["base_color"] = "blue"
    assert lint(_tampered(pack, m)) == []


def test_plant_pin_color_outside_plan_palette(pack):
    """Pin overrides are checked against the PRESET's plan palette."""
    def m(p):
        for pin in p.pins:
            if pin["label"] == "wolf":
                pin["axes"]["accent_color"] = "iridescent"
    errs = lint(_tampered(pack, m))
    assert any("wolf" in e and "palette" in e for e in errs)


def test_plant_missing_palette(pack):
    def m(p):
        del p.palettes["hexapod"]
    errs = lint(_tampered(pack, m))
    assert any("no palette for plan" in e for e in errs)


# ──  N/A inapplicability pruning (user ruling: prune in the record)  ──────


def test_na_pruned_on_real_content(pack):
    """Herp-vocab dials are N/A on grades lacking the feature; the grades
    that DO have it keep real values."""
    cat = pack.presets["tetrapod.cat"]["axes"] | pack.presets["tetrapod.cat"]["knobs"]
    assert cat["skin_texture"] == "N/A"
    assert cat["horn_cover_texture"] == "N/A"
    deer = pack.presets["tetrapod.deer"]["axes"] | pack.presets["tetrapod.deer"]["knobs"]
    assert deer["horn_cover_texture"] == "velvet"      # antlers
    assert deer["skin_texture"] == "N/A"               # furred
    reptile = pack.presets["tetrapod.reptile"]["axes"] | pack.presets["tetrapod.reptile"]["knobs"]
    assert reptile["skin_texture"] == "keeled"         # crocodile


def test_plant_na_on_core_axis(pack):
    """Core axes are always applicable — N/A there is an error."""
    def m(p):
        p.presets["tetrapod.deer"]["axes"]["body_mass"] = "N/A"
    errs = lint(_tampered(pack, m))
    assert any("body_mass" in e and "N/A" in e for e in errs)


def test_plant_na_on_patternation_axis(pack):
    def m(p):
        p.presets["tetrapod.deer"]["axes"]["base_color"] = "N/A"
    errs = lint(_tampered(pack, m))
    assert any("base_color" in e and "N/A" in e for e in errs)


def test_pin_may_reactivate_na_dial(pack):
    """N/A -> real value via pin override is a legitimate derivation
    (horned-lizard class) and must lint clean."""
    def m(p):
        for pin in p.pins:
            if pin["label"] == "crocodile":
                pin.setdefault("knobs", {})["horn_cover_texture"] = "bare_keratin"
    assert lint(_tampered(pack, m)) == []
