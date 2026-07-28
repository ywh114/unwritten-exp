"""M1 tests — axis registry schema, validation, and the freeze-bug lint.

Every validation rule has a positive and a planted-violation case. K1-only
(the registry is pure schema; the audit keeps it that way).
"""

from __future__ import annotations

import pathlib

import pytest

from exp.k13_treegen.model import rebind, RebindError
from exp.k13_treegen.registry import (
    AxisSpec,
    Block,
    GrammarRole,
    MutationKind,
    Registry,
    RegistryError,
    Tier,
    Unit,
    ValueType,
)

HERE = pathlib.Path(__file__).parent


# ──  fixture builders  ────────────────────────────────────────────────────


def _mass() -> dict:
    return {"block": "morphometrics", "tier": "steady", "value_type": "scalar",
            "mutation": "log_gaussian", "sigma": 0.3, "bounds": [0.001, 1e5],
            "unit": "mass", "plan_scope": "all",
            "consumers": ["stress", "pop", "name"], "salience": 0.9,
            "grammar_role": "size"}


def _labile_scalar() -> dict:
    return {"block": "morphometrics", "tier": "labile", "value_type": "scalar",
            "mutation": "gaussian", "sigma": 0.05, "bounds": [0.0, 1.0],
            "plan_scope": ["tetrapod"], "consumers": ["draw", "name"],
            "salience": 0.6, "grammar_role": "part"}


def _enum() -> dict:
    return {"block": "morphometrics", "tier": "steady", "value_type": "enum",
            "mutation": "enum_redraw",
            "states": ["plantigrade", "digitigrade", "unguligrade"],
            "plan_scope": ["tetrapod"], "consumers": ["draw", "stress"],
            "salience": 0.5, "grammar_role": "grade"}


def _invariant() -> dict:
    return {"block": "morphometrics", "tier": "invariant",
            "value_type": "enum", "mutation": "none",
            "states": ["fusiform", "anguilliform"], "plan_scope": ["finned"],
            "consumers": ["id"], "salience": 0.2}


def _good_axis_defs() -> dict:
    return {"body_mass": _mass(), "ear_size_ratio": _labile_scalar(),
            "foot_posture": _enum(), "body_form_class": _invariant()}


def _plan_defs() -> dict:
    return {"tetrapod": {"medium": "land",
                         "slots": ["head.cheek", "limb.fore.L"],
                         "generics": {"locomotor": ["cursorial_limb_set",
                                                    "flipper"]}},
            "finned": {"medium": "water",
                       "generics": {"locomotor": ["axial_undulation"]}}}


def _good_registry() -> Registry:
    return Registry.from_toml(_good_axis_defs(), _plan_defs())


# ──  happy path  ──────────────────────────────────────────────────────────


def test_good_registry_builds():
    reg = _good_registry()
    assert set(reg.axes) == {"body_mass", "ear_size_ratio", "foot_posture",
                             "body_form_class"}
    assert reg.mass_axis() == "body_mass"


def test_mutable_flag():
    reg = _good_registry()
    assert reg.axis("ear_size_ratio").mutable       # labile gaussian
    assert reg.axis("foot_posture").mutable         # enum_redraw
    assert not reg.axis("body_form_class").mutable  # invariant
    assert reg.axis("body_mass").mutable            # steady log_gaussian


def test_applicable_axes_plan_scope():
    reg = _good_registry()
    tet = {a.name for a in reg.applicable_axes("tetrapod")}
    # body_mass is "all"; ear_size_ratio + foot_posture are tetrapod-scoped;
    # body_form_class is finned-only
    assert tet == {"body_mass", "ear_size_ratio", "foot_posture"}
    fin = {a.name for a in reg.applicable_axes("finned")}
    assert "body_form_class" in fin and "foot_posture" not in fin


def test_salience_order_descending():
    reg = _good_registry()
    order = [a.name for a in reg.salience_order()]
    sals = [a.salience for a in reg.salience_order()]
    assert sals == sorted(sals, reverse=True)
    assert order[0] == "body_mass"                    # 0.9 highest


def test_grammar_index():
    reg = _good_registry()
    idx = reg.grammar_index()
    assert "body_mass" in idx[GrammarRole.SIZE]
    assert "ear_size_ratio" in idx[GrammarRole.PART]
    assert "foot_posture" in idx[GrammarRole.GRADE]


def test_plan_permissions_feed_rebind():
    reg = _good_registry()
    perms = reg.plan_permissions("tetrapod")
    g: dict = {}
    rebind(g, "locomotor", "flipper", perms)
    assert g["locomotor"] == "flipper"
    with pytest.raises(RebindError):
        rebind(g, "locomotor", "jet_propulsion", perms)


# ──  validation: planted violations  ─────────────────────────────────────


def _expect_error(axis_defs: dict, plan_defs: dict | None = None,
                  substring: str = "") -> None:
    with pytest.raises(RegistryError) as ei:
        Registry.from_toml(axis_defs, plan_defs)
    if substring:
        assert substring in str(ei.value)


def test_invariant_must_be_mutation_none():
    defs = _good_axis_defs()
    defs["body_form_class"]["mutation"] = "enum_redraw"
    _expect_error(defs, _plan_defs(), "invariant")


def test_clade_steady_forces_none():
    defs = _good_axis_defs()
    defs["ear_size_ratio"]["clade_steady"] = True     # but mutation=gaussian
    _expect_error(defs, _plan_defs(), "clade_steady")


def test_freeze_bug_mutable_needs_positive_sigma():
    defs = _good_axis_defs()
    defs["ear_size_ratio"]["sigma"] = 0.0             # frozen non-steady axis
    _expect_error(defs, _plan_defs(), "sigma>0")


def test_enum_redraw_needs_states():
    defs = _good_axis_defs()
    defs["foot_posture"]["states"] = []
    _expect_error(defs, _plan_defs(), "states")


def test_enum_value_type_needs_enum_mutation():
    defs = _good_axis_defs()
    defs["foot_posture"]["mutation"] = "gaussian"
    _expect_error(defs, _plan_defs(), "enum_redraw or none")


def test_scalar_needs_bounds():
    defs = _good_axis_defs()
    defs["ear_size_ratio"]["bounds"] = None
    _expect_error(defs, _plan_defs(), "bounds")


def test_bounds_lo_lt_hi():
    defs = _good_axis_defs()
    defs["ear_size_ratio"]["bounds"] = [1.0, 0.0]
    _expect_error(defs, _plan_defs(), "lo<hi")


def test_log_gaussian_must_be_positive():
    defs = _good_axis_defs()
    defs["body_mass"]["bounds"] = [0.0, 1e5]
    _expect_error(defs, _plan_defs(), "strictly positive")


def test_consumer_required():
    defs = _good_axis_defs()
    defs["ear_size_ratio"]["consumers"] = []
    _expect_error(defs, _plan_defs(), "consumer")


def test_unknown_consumer_rejected():
    defs = _good_axis_defs()
    defs["ear_size_ratio"]["consumers"] = ["vibes"]
    _expect_error(defs, _plan_defs(), "unknown consumers")


def test_plan_scope_nonempty():
    defs = _good_axis_defs()
    defs["ear_size_ratio"]["plan_scope"] = []
    _expect_error(defs, _plan_defs(), "plan_scope")


def test_plan_scope_must_reference_known_plans():
    defs = _good_axis_defs()
    defs["ear_size_ratio"]["plan_scope"] = ["nonexistent_plan"]
    _expect_error(defs, _plan_defs(), "unknown")


def test_exactly_one_mass_axis_zero():
    defs = _good_axis_defs()
    defs["body_mass"]["unit"] = "dimensionless"       # now no mass axis
    _expect_error(defs, _plan_defs(), "unit=mass")


def test_exactly_one_mass_axis_two():
    defs = _good_axis_defs()
    defs["ear_size_ratio"]["unit"] = "mass"           # now two mass axes
    _expect_error(defs, _plan_defs(), "one mass axis")


def _weighted_set() -> dict:
    return {"block": "diet", "tier": "steady", "value_type": "weighted_set",
            "mutation": "weight_redraw", "sigma": 0.1,
            "states": ["grazer", "carnivore"], "plan_scope": "all",
            "consumers": ["pop", "tell"], "salience": 0.85,
            "grammar_role": "diet"}


def test_weighted_set_valid():
    defs = _good_axis_defs()
    defs["diet_spectrum"] = _weighted_set()
    reg = Registry.from_toml(defs, _plan_defs())
    assert reg.axis("diet_spectrum").mutable


def test_weighted_set_needs_weight_redraw():
    defs = _good_axis_defs()
    defs["diet_spectrum"] = _weighted_set()
    defs["diet_spectrum"]["mutation"] = "enum_redraw"
    _expect_error(defs, _plan_defs(), "weight_redraw or none")


def test_weight_redraw_needs_states():
    defs = _good_axis_defs()
    defs["diet_spectrum"] = _weighted_set()
    defs["diet_spectrum"]["states"] = []
    _expect_error(defs, _plan_defs(), "states")


def test_weight_redraw_needs_sigma():
    defs = _good_axis_defs()
    defs["diet_spectrum"] = _weighted_set()
    defs["diet_spectrum"]["sigma"] = 0.0
    _expect_error(defs, _plan_defs(), "sigma>0")


def test_coupling_triggers_must_resolve():
    defs = _good_axis_defs()
    defs["ear_size_ratio"]["coupling_triggers"] = ["domestication"]
    # coupling triggers are only checked when a coupling-id set is supplied;
    # an empty set means "domestication" is unresolved -> error
    with pytest.raises(RegistryError) as ei:
        Registry.from_toml(defs, _plan_defs(), coupling_ids=set())
    assert "coupling_trigger" in str(ei.value)
    # with the coupling id declared -> ok
    Registry.from_toml(defs, _plan_defs(),
                       coupling_ids={"domestication"})


# ──  TOML loader round-trip  ──────────────────────────────────────────────


def test_toml_loader(tmp_path):
    toml_text = """
[axis.body_mass]
block = "morphometrics"
tier = "steady"
value_type = "scalar"
mutation = "log_gaussian"
sigma = 0.3
bounds = [0.001, 100000.0]
unit = "mass"
plan_scope = "all"
consumers = ["stress", "pop", "name"]
salience = 0.9
grammar_role = "size"

[axis.foot_posture]
block = "morphometrics"
tier = "steady"
value_type = "enum"
mutation = "enum_redraw"
states = ["plantigrade", "digitigrade", "unguligrade"]
plan_scope = ["tetrapod"]
consumers = ["draw", "stress"]
salience = 0.5
grammar_role = "grade"

[plan.tetrapod]
medium = "land"
slots = ["head.cheek"]
[plan.tetrapod.generics]
locomotor = ["cursorial_limb_set", "flipper"]
"""
    p = tmp_path / "axes.toml"
    p.write_text(toml_text)
    reg = Registry.load(p)
    assert reg.mass_axis() == "body_mass"
    assert reg.axis("foot_posture").states == ["plantigrade", "digitigrade",
                                               "unguligrade"]
    assert reg.axis("foot_posture").grammar_role is GrammarRole.GRADE
    assert reg.axis("body_mass").tier is Tier.STEADY
    assert reg.axis("body_mass").value_type is ValueType.SCALAR
    assert reg.axis("body_mass").mutation_kind is MutationKind.LOG_GAUSSIAN
    assert reg.axis("body_mass").unit is Unit.MASS
    assert reg.axis("body_mass").block is Block.MORPHOMETRICS
    assert reg.plan_permissions("tetrapod") == {
        "locomotor": ["cursorial_limb_set", "flipper"]}


# ──  K1-only source audit  ────────────────────────────────────────────────


def test_no_nondeterministic_imports():
    src = (HERE / "registry.py").read_text()
    for line in src.splitlines():
        stripped = line.strip()
        for bad in ("import random", "from random", "import uuid",
                    "from uuid", "import time", "from time"):
            assert not stripped.startswith(bad), \
                f"registry.py: forbidden import: {stripped}"


# ──  reserved effects field (rounds hook; parsed, unconsumed)  ────────────


def test_effects_reserved_field():
    t = {"block": "morphometrics", "tier": "labile", "value_type": "scalar",
         "mutation": "gaussian", "sigma": 0.1, "bounds": [0.0, 1.0],
         "plan_scope": "all", "consumers": ["draw"],
         "effects": {"thermal": 0.8, "camouflage": -0.6, "warning": 0.9}}
    a = AxisSpec.from_toml("ear_size_ratio", t)
    assert a.effects == {"thermal": 0.8, "camouflage": -0.6, "warning": 0.9}
    assert a.validate() == []
    # bad shape is a validation error
    bad = AxisSpec.from_toml("x", {**t, "effects": {"thermal": "hot"}})
    assert any("effects" in e for e in bad.validate())
