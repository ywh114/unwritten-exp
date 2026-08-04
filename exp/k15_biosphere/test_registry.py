"""Fast-tier tests for exp/k15_biosphere registry + record + content
(ticket 0041).

The three spec B9 §8 registry rejections (mutable axis without sigma,
consumer outside the closed vocabulary, second size axis), the real flora
content pack loads and validates clean against the ported registry, the
species record round-trips, and the plan permission tables / plan_scope
resolution.  Plain pytest, no marks — runs in milliseconds.
"""

from __future__ import annotations

import pathlib

import pytest

from exp.k15_biosphere.content import (
    ContentPack,
    load_content,
    merged_pin,
    merged_preset,
)
from exp.k15_biosphere.record import SpeciesRecord
from exp.k15_biosphere.registry import (
    Block,
    MutationKind,
    Registry,
    RegistryError,
    Tier,
    Unit,
    ValueType,
    VALID_CONSUMERS,
)

# The real flora content pack lives in the frozen k13 reference; content
# is shared data, read IN PLACE from there (never copied).
CONTENT_DIR = pathlib.Path(__file__).parent.parent / "k13_treegen" \
    / "content" / "flora"


# ──  fixture builders  ────────────────────────────────────────────────────


def _size_axis() -> dict:
    """The flora size axis (unit=length): the one non-dimensionless axis
    every valid registry in these tests needs."""
    return {"block": "morphometrics", "tier": "steady", "value_type": "scalar",
            "mutation": "log_gaussian", "sigma": 0.5, "bounds": [0.005, 200.0],
            "unit": "length", "plan_scope": "all",
            "consumers": ["stress", "id", "pop"], "salience": 0.7}


def _labile_scalar() -> dict:
    return {"block": "morphometrics", "tier": "labile", "value_type": "scalar",
            "mutation": "ratio", "sigma": 0.1, "bounds": [0.0, 1.0],
            "plan_scope": ["tree"], "consumers": ["draw", "name"],
            "salience": 0.3}


def _good_axis_defs() -> dict:
    return {"height_m": _size_axis(), "woodiness": _labile_scalar()}


def _plan_defs() -> dict:
    return {"tree": {"medium": "land", "slots": ["trunk", "crown"],
                     "generics": {"dispersal": ["gravity_drop", "wind_winged"],
                                  "support": ["trunk_single"]}},
            "fungus": {"medium": "land",
                       "generics": {"dispersal": ["spore_wind"]}}}


def _expect_error(axis_defs: dict, plan_defs: dict | None = None,
                  substring: str = "") -> None:
    with pytest.raises(RegistryError) as ei:
        Registry.from_toml(axis_defs, plan_defs)
    if substring:
        assert substring in str(ei.value)


# ──  spec B9 §8 rejections  ───────────────────────────────────────────────


def test_mutable_axis_without_sigma_rejected():
    """Vary-by-default: a mutable (non-invariant, non-steady-blacklisted)
    axis must carry sigma>0 — the freeze-bug lint."""
    defs = _good_axis_defs()
    defs["woodiness"]["sigma"] = 0.0
    _expect_error(defs, _plan_defs(), "sigma>0")


def test_consumer_outside_closed_vocabulary_rejected():
    """Rent audit: every axis must name consumers from the closed
    vocabulary; unknown consumers are a validation error."""
    defs = _good_axis_defs()
    defs["woodiness"]["consumers"] = ["vibes"]
    _expect_error(defs, _plan_defs(), "unknown consumers")


def test_second_size_axis_rejected():
    """Single-size-axis lint: exactly one non-dimensionless axis."""
    defs = _good_axis_defs()
    defs["woodiness"]["unit"] = "length"        # now two size axes
    _expect_error(defs, _plan_defs(), "one mass axis")


def test_no_size_axis_rejected():
    defs = _good_axis_defs()
    defs["height_m"]["unit"] = "dimensionless"  # now no size axis
    _expect_error(defs, _plan_defs(), "unit=mass")


# ──  plan permission tables / plan_scope resolution  ─────────────────────


def test_plan_permissions_feed_bindings():
    reg = Registry.from_toml(_good_axis_defs(), _plan_defs())
    perms = reg.plan_permissions("tree")
    assert perms["dispersal"] == ["gravity_drop", "wind_winged"]
    assert reg.plan_permissions("no_such_plan") == {}


def test_plan_scope_resolution():
    reg = Registry.from_toml(_good_axis_defs(), _plan_defs())
    assert reg.axis("woodiness").applies_to("tree")     # tree-scoped
    assert not reg.axis("woodiness").applies_to("fungus")
    assert reg.axis("height_m").applies_to("fungus")    # "all"
    assert {a.name for a in reg.applicable_axes("fungus")} == {"height_m"}


# ──  the real flora pack  ─────────────────────────────────────────────────


def test_real_flora_pack_loads_clean():
    """The settled flora pack loads and validates against the ported
    registry: 84 axes, 14 plans, 29 presets, non-empty pins/bundles/
    classes (bundle envelope + class open-catalog checks included)."""
    pack = load_content(CONTENT_DIR)
    assert isinstance(pack, ContentPack)
    assert len(pack.registry.axes) == 84
    assert len(pack.registry.plans) == 14
    assert len(pack.presets) == 29
    assert pack.pins and pack.bundles and pack.classes


def test_flora_size_axis_is_height_m():
    """Flora's single size axis is height_m (unit=length); mass_axis()
    (the fauna lookup) is None by the ported k13 contract."""
    pack = load_content(CONTENT_DIR)
    sizes = [a.name for a in pack.registry.axes.values()
             if a.unit is not Unit.DIMENSIONLESS]
    assert sizes == ["height_m"]
    assert pack.registry.axes["height_m"].unit is Unit.LENGTH
    assert pack.registry.mass_axis() is None


def test_real_axis_spec_enum_coercion():
    """The content TOML strings coerce to the schema enums when the real
    pack parses — nothing stays a raw string."""
    pack = load_content(CONTENT_DIR)
    h = pack.registry.axes["height_m"]
    assert h.block is Block.MORPHOMETRICS
    assert h.tier is Tier.STEADY
    assert h.value_type is ValueType.SCALAR
    assert h.mutation_kind is MutationKind.LOG_GAUSSIAN
    assert pack.registry.axes["halle_axes"].tier is Tier.INVARIANT
    assert pack.registry.axes["layer"].value_type is ValueType.ENUM
    assert (pack.registry.axes["dispersal_channels"].value_type
            is ValueType.WEIGHTED_SET)


def test_plan_permissions_real_flora():
    pack = load_content(CONTENT_DIR)
    perms = pack.registry.plan_permissions("tree")
    assert "gravity_drop" in perms["dispersal"]
    assert "trunk_single" in perms["support"]
    assert pack.registry.plan_permissions("tree") != \
        pack.registry.plan_permissions("fungus")


def test_consumer_vocabulary_covers_flora_content():
    """The extended vocabulary keeps every consumer the real flora
    content uses, plus the new L2 consumers (spec B9 §2)."""
    pack = load_content(CONTENT_DIR)
    used = {c for a in pack.registry.axes.values() for c in a.consumers}
    assert used <= VALID_CONSUMERS
    assert used == {"stress", "id", "name", "tell", "pop", "draw",
                    "runaway"}
    assert {"biomass", "occupancy"} <= VALID_CONSUMERS


def test_merged_preset_committed_shape():
    """A preset merges to the flat committed axes+generics a species
    record stores."""
    pack = load_content(CONTENT_DIR)
    axes, generics = merged_preset(pack.presets["tree.conifer"])
    assert axes["height_m"] == 30.0
    assert generics["support"] == "trunk_single"
    assert generics["dispersal"] == "wind_winged"


def test_merged_pin_pin_wins_over_preset():
    """The pin's committed record: merged preset with pin overrides
    winning (pin > preset) — every pin-declared axis/generic survives the
    merge verbatim, over whatever the preset authored."""
    pack = load_content(CONTENT_DIR)
    assert pack.pins
    for pin in pack.pins:
        assert pin["preset"] in pack.presets
        axes, generics = merged_pin(pack, pin)
        assert axes and generics
        for k, v in pin.get("axes", {}).items():
            assert axes[k] == v
        for k, v in pin.get("generics", {}).items():
            assert generics[k] == v


# ──  species record round-trip  ───────────────────────────────────────────


def test_record_round_trips():
    rec = SpeciesRecord(
        sid="0123456789abcdef", plan="tree", preset="tree.oak",
        g=4.2, gen_time=12.5,
        axes={"height_m": 25.0, "leaf_shape": "lobed",
              "dispersal_channels": {"local": 0.3, "wind": 0.7}},
        generics={"dispersal": "gravity_drop", "support": "trunk_single"},
    )
    assert SpeciesRecord.from_json(rec.to_json()) == rec


def test_record_defaults():
    rec = SpeciesRecord.from_json({"sid": "0123456789abcdef"})
    assert rec.plan is None and rec.preset is None
    assert rec.g == 0.0 and rec.gen_time == 0.0
    assert rec.axes == {} and rec.generics == {}


# ──  determinism audit  ───────────────────────────────────────────────────


def test_no_nondeterministic_imports():
    """AGENTS.md determinism hard rule: no random/uuid/time in the new
    modules (same seed ⇒ byte-identical output)."""
    for mod in ("registry.py", "record.py", "content.py"):
        src = (pathlib.Path(__file__).parent / mod).read_text()
        for line in src.splitlines():
            stripped = line.strip()
            for bad in ("import random", "from random", "import uuid",
                        "from uuid", "import time", "from time",
                        "import numpy"):
                assert not stripped.startswith(bad), \
                    f"{mod}: forbidden import: {stripped}"
