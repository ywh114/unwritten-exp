"""Fast-tier tests for exp/k15_biosphere constraints (ticket 0043).

The legality gate ported from k13 (``exp/k13_treegen/flora/
constraints.py``), adapted to SpeciesRecord: every one of the 26 real
rules fires on a crafted record and the snapping 24 snap to the exact
[old, new] pair the reference produces; snaps are audited as a return
value and never delete; enforce() is idempotent; all 29 real presets
pass the gate unmodified.  Plain pytest, no marks — runs in
milliseconds.
"""

from __future__ import annotations

import pathlib

import pytest

from exp.k15_biosphere.constraints import (
    ConstraintPack,
    Rule,
    enforce,
    load_palettes,
    load_rules,
    triggered,
    violations,
)
from exp.k15_biosphere.content import load_content, merged_preset
from exp.k15_biosphere.record import SpeciesRecord

# The real flora content pack lives in the frozen k13 reference; content
# is shared data, read IN PLACE from there (never copied).
CONTENT_DIR = pathlib.Path(__file__).parent.parent / "k13_treegen" \
    / "content" / "flora"


@pytest.fixture(scope="module")
def pack() -> ConstraintPack:
    """The real flora pack: 0041 registry + the real 26 rules + palettes."""
    return ConstraintPack(
        registry=load_content(CONTENT_DIR).registry,
        constraints=load_rules(CONTENT_DIR / "constraints.toml"),
        palettes=load_palettes(CONTENT_DIR / "palettes.toml"),
    )


def _rec(plan: str, axes: dict, sid: str = "0" * 16) -> SpeciesRecord:
    return SpeciesRecord(sid=sid, plan=plan, axes=dict(axes))


# ──  trigger forms / Rule schema  ──────────────────────────────────────────


def test_rule_trigger_forms():
    """The when-table trigger fires on enum state(s) and scalar above,
    and honors the plans scope."""
    r = Rule.from_toml({"id": "t1",
                        "when": {"axis": "photosynthesis", "state": "CAM"},
                        "require_min": {"succulence": 0.4}})
    assert triggered(r, {"photosynthesis": "CAM"})
    assert not triggered(r, {"photosynthesis": "C3"})
    r2 = Rule.from_toml({"id": "t2",
                         "when": {"axis": "leaf_size_cm", "above": 80.0},
                         "require_max": {"drought_tolerance": 0.6}})
    assert triggered(r2, {"leaf_size_cm": 90.0})
    assert not triggered(r2, {"leaf_size_cm": 50.0})
    r3 = Rule.from_toml({"id": "t3",
                         "when": {"axis": "leaf_trap",
                                  "state": ["pitcher", "snap"]}})
    assert triggered(r3, {"leaf_trap": "snap"})
    assert not triggered(r3, {"leaf_trap": "none"})


def test_rule_plans_scope(pack):
    """when.plans scopes the rule to those plans only (spinescence_aridity
    is a land-plant rule)."""
    rule = next(r for r in pack.constraints if r.id == "spinescence_aridity")
    axes = {"mechanical_defense": "spine"}
    assert triggered(rule, axes, "tree")
    assert triggered(rule, axes, "succulent")
    assert not triggered(rule, axes, "lichen")     # outside the scope
    assert not triggered(rule, axes, "fungus")     # outside the scope


# ──  enforce: snap semantics  ──────────────────────────────────────────────


def test_enforce_require_and_idempotent(pack):
    """B9 §8: enforce() snaps the offending dial and is idempotent — a
    second run over the same record returns zero snaps and changes
    nothing."""
    parent = _rec("succulent",
                  {"photosynthesis": "C3", "succulence": 0.1})
    child = _rec("succulent",
                 {"photosynthesis": "CAM", "succulence": 0.1})
    audit = enforce(parent, child, pack)
    assert child.axes["succulence"] == 0.4
    assert audit == [{"cam_succulence": {"succulence": [0.1, 0.4]}}]
    before = dict(child.axes)
    assert enforce(parent, child, pack) == []       # idempotent: no-op
    assert child.axes == before


def test_snaps_audited_and_never_delete(pack):
    """B9 §8: a violated axis is snapped to the bound/enum, never
    removed — the key stays, its value is pulled to the threshold, and
    every move lands in the audit as [old, new]."""
    # bound snap: CAM pulls succulence UP to the threshold
    parent = _rec("succulent",
                  {"photosynthesis": "C3", "succulence": 0.1})
    child = _rec("succulent",
                 {"photosynthesis": "CAM", "succulence": 0.1})
    before = set(child.axes)
    audit = enforce(parent, child, pack)
    assert child.axes["succulence"] == 0.4          # pulled, not deleted
    assert set(child.axes) == before                # no key removed
    assert child.axes["photosynthesis"] == "CAM"    # untouched axis intact
    assert audit == [{"cam_succulence":
                      {"succulence": [0.1, 0.4]}}]
    # enum snap: the forbidden pathway is REPLACED, not deleted
    parent = _rec("tree", {"pollination_syndrome": "wind",
                           "pigment_pathway": "none"})
    child = _rec("tree", {"pollination_syndrome": "bee",
                          "pigment_pathway": "none"})
    enforce(parent, child, pack)
    assert child.axes["pigment_pathway"] == "anthocyanin"
    assert "pigment_pathway" in child.axes
    # parent-prior snap: the trap snaps to the parent's prior value
    parent = _rec("herb_forb", {"nutrient_package": "xerophyte",
                                "leaf_trap": "pitcher"})
    child = _rec("herb_forb", {"nutrient_package": "carnivore",
                               "leaf_trap": "none"})
    enforce(parent, child, pack)
    assert child.axes["leaf_trap"] == "pitcher"
    assert "leaf_trap" in child.axes


def test_enforce_state_plans_snap_back(pack):
    """state_plans legality: off-plan the trigger state snaps back to the
    parent's prior value; on-plan the requirements apply instead."""
    rule = next(r for r in pack.constraints
                if r.id == "buttress_emergent")
    # off-plan (lichen): the trigger state snaps back to the parent
    parent = _rec("lichen", {"root_special": "none", "height_m": 0.01})
    child = _rec("lichen",
                 {"root_special": "buttress", "height_m": 0.01})
    audit = enforce(parent, child, pack)
    assert child.axes["root_special"] == "none"
    assert child.axes["height_m"] == 0.01
    assert audit == [{"buttress_emergent":
                      {"root_special": ["buttress", "none"]}}]
    # on-plan (tree): requirements apply instead
    parent = _rec("tree", {"root_special": "none", "height_m": 25.0})
    child = _rec("tree",
                 {"root_special": "buttress", "height_m": 10.0})
    enforce(parent, child, pack)
    assert child.axes["root_special"] == "buttress"
    assert child.axes["height_m"] == 20.0


def test_enforce_pigment_legality(pack):
    """B5 §5.2: pigment legality is trait-side now.  A bee-pollinated
    lineage cannot carry the "none" pathway (that is the dull wind set) —
    the gate snaps the pathway to a pigment, never the derived bucket."""
    parent = _rec("tree",
                  {"pollination_syndrome": "wind",
                   "pigment_pathway": "none"})
    child = _rec("tree",
                 {"pollination_syndrome": "bee",
                  "pigment_pathway": "none"})
    audit = enforce(parent, child, pack)
    assert child.axes["pigment_pathway"] == "anthocyanin"
    assert audit == [{"insect_syndrome_showy":
                      {"pigment_pathway": ["none", "anthocyanin"]}}]


def test_pigment_anthocyanin_excludes_betalain(pack):
    """B5 §5.2/§8.6: anthocyanin ⊥ betalain is a sampler-legality rule in
    the CAM↔succulence pattern.  The pathway enum is single-valued, so a
    committed record can never hold both — the rule fires on either side
    and never has anything to snap."""
    rule = next(r for r in pack.constraints
                if r.id == "pigment_anthocyanin_betalain_exclusive")
    assert triggered(rule, {"pigment_pathway": "anthocyanin"})
    # single-valued: the forbidding side of the pair is never present
    assert not violations(_rec("tree", {"pigment_pathway": "anthocyanin"}),
                          pack)
    assert not violations(_rec("tree", {"pigment_pathway": "betalain"}),
                          pack)


def test_inflorescence_seed_plans_no_legal_replacement(pack):
    """A spore-grade plan redrawn into an inflorescence cannot be snapped:
    the inflorescence axis has no "none" state and every state is
    seed-plant-only, so snap-back finds no legal candidate — the record is
    left unchanged and the metrics gate reports the breach instead."""
    parent = _rec("moss_grade", {"inflorescence": "raceme"})
    child = _rec("moss_grade", {"inflorescence": "raceme"})
    assert enforce(parent, child, pack) == []
    assert child.axes == {"inflorescence": "raceme"}    # unchanged
    errs = violations(child, pack)
    assert any("inflorescence_seed_plans" in e for e in errs)


def test_violations_reports_breach(pack):
    """violations() audits the committed record; messages carry no node
    path prefix (the k15 record has no path — k13 prefixed every breach
    with ``node.path``)."""
    n = _rec("tree", {"photosynthesis": "CAM", "succulence": 0.1})
    errs = violations(n, pack)
    assert errs == ["cam_succulence: succulence 0.1 < require_min 0.4"]


def test_palette_filtered_candidates(pack):
    """Palette filtering (k13 _candidates): a snap onto a color axis may
    not paint a plan a color its palette forbids — fern_grade's palette is
    green/brown/yellow/cream, so the red/blue/green candidate set narrows
    to green."""
    r = Rule.from_toml({"id": "palette_test",
                        "when": {"axis": "flower_symmetry",
                                 "state": "radial"},
                        "require_enum": {"flower_color":
                                         ["red", "blue", "green"]}})
    pack2 = ConstraintPack(registry=pack.registry, constraints=[r],
                           palettes=pack.palettes)
    parent = _rec("fern_grade", {"flower_color": "white"})
    child = _rec("fern_grade",
                 {"flower_symmetry": "radial", "flower_color": "white"})
    enforce(parent, child, pack2)
    assert child.axes["flower_color"] == "green"     # palette-filtered
    # full palette (tree): registry order wins
    parent = _rec("tree", {"flower_color": "white"})
    child = _rec("tree",
                 {"flower_symmetry": "radial", "flower_color": "white"})
    enforce(parent, child, pack2)
    assert child.axes["flower_color"] == "red"


# ──  the full real rule table  ─────────────────────────────────────────────

# (rule_id, plan, child_axes, parent_axes, expected_snaps): one crafted
# record per rule that triggers it and violates its requirements.  The
# expected snaps were verified against the frozen k13 reference
# (exp/k13_treegen/flora/constraints.py) — same pack, same moves.
# Excluded here: pigment_anthocyanin_betalain_exclusive and
# inflorescence_seed_plans, which can never snap (see their tests above).
RULE_CASES = [
    ("cam_succulence", "succulent",
     {"photosynthesis": "CAM", "succulence": 0.1},
     {"photosynthesis": "C3", "succulence": 0.1},
     {"succulence": [0.1, 0.4]}),
    ("c4_warm_open", "tree",
     {"photosynthesis": "C4", "drought_tolerance": 0.1},
     {},
     {"drought_tolerance": [0.1, 0.4]}),
    ("wind_poll_inconspicuous", "tree",
     {"pollination_syndrome": "wind", "flower_size_mm": 20.0,
      "pigment_pathway": "anthocyanin"},
     {},
     {"flower_size_mm": [20.0, 5.0],
      "pigment_pathway": ["anthocyanin", "none"]}),
    ("bird_syndrome_red", "tree",
     {"pollination_syndrome": "bird", "flower_size_mm": 5.0,
      "pigment_expression": 0.1, "pigment_pathway": "none"},
     {},
     {"flower_size_mm": [5.0, 10.0],
      "pigment_expression": [0.1, 0.5],
      "pigment_pathway": ["none", "anthocyanin"]}),
    ("serotiny_fire", "tree",
     {"serotiny": "yes", "fire_strategy": "avoider"},
     {},
     {"fire_strategy": ["avoider", "resprouter"]}),
    ("spinescence_aridity", "tree",
     {"mechanical_defense": "spine", "drought_tolerance": 0.1},
     {},
     {"drought_tolerance": [0.1, 0.4]}),
    ("large_leaves_warmwet", "tree",
     {"leaf_size_cm": 100.0, "drought_tolerance": 0.9},
     {},
     {"drought_tolerance": [0.9, 0.6]}),
    ("toothed_cold", "tree",
     {"leaf_margin": "toothed", "leaf_size_cm": 200.0},
     {},
     {"leaf_size_cm": [200.0, 100.0]}),
    ("pneumatophores_waterlogging", "tree",
     {"root_special": "pneumatophores", "waterlogging_tolerance": 0.1},
     {},
     {"waterlogging_tolerance": [0.1, 0.7]}),
    ("buttress_emergent", "tree",
     {"root_special": "buttress", "height_m": 5.0, "root_depth_m": 5.0},
     {},
     {"height_m": [5.0, 20.0], "root_depth_m": [5.0, 2.0]}),
    ("stilt_roots_woody", "lichen",
     {"root_special": "stilt"},
     {"root_special": "none"},
     {"root_special": ["stilt", "none"]}),
    ("knee_roots_woody", "lichen",
     {"root_special": "knee"},
     {"root_special": "none"},
     {"root_special": ["knee", "none"]}),
    ("nutrient_carnivore_plans", "tree",
     {"nutrient_package": "carnivore"},
     {"nutrient_package": "none"},
     {"nutrient_package": ["carnivore", "none"]}),
    ("trap_carnivory", "herb_forb",
     {"nutrient_package": "carnivore", "leaf_trap": "none"},
     {"leaf_trap": "pitcher"},
     {"leaf_trap": ["none", "pitcher"]}),
    ("trap_plans", "tree",
     {"leaf_trap": "pitcher"},
     {"leaf_trap": "none"},
     {"leaf_trap": ["pitcher", "none"]}),
    ("aquatic_layer", "tree",
     {"waterlogging_tolerance": 0.9, "layer": "canopy"},
     {},
     {"layer": ["canopy", "aquatic_surface"]}),
    ("aquatic_surface_needs_tolerance", "tree",
     {"layer": "aquatic_surface", "waterlogging_tolerance": 0.1},
     {},
     {"waterlogging_tolerance": [0.1, 0.7]}),
    ("aquatic_benthic_needs_tolerance", "tree",
     {"layer": "aquatic_benthic", "waterlogging_tolerance": 0.1},
     {},
     {"waterlogging_tolerance": [0.1, 0.7]}),
    ("flowers_seed_plans", "moss_grade",
     {"flower_symmetry": "radial"},
     {"flower_symmetry": "none"},
     {"flower_symmetry": ["radial", "none"]}),
    ("pollination_seed_plans", "moss_grade",
     {"pollination_syndrome": "wind"},
     {"pollination_syndrome": "none"},
     {"pollination_syndrome": ["wind", "none"]}),
    ("fruit_seed_plans", "moss_grade",
     {"fruit_type": "berry"},
     {"fruit_type": "none"},
     {"fruit_type": ["berry", "none"]}),
    ("sorus_plans", "moss_grade",
     {"fruit_type": "sorus"},
     {"fruit_type": "none"},
     {"fruit_type": ["sorus", "none"]}),
    ("sporangium_plans", "fern_grade",
     {"fruit_type": "sporangium"},
     {"fruit_type": "none"},
     {"fruit_type": ["sporangium", "none"]}),
    ("insect_syndrome_showy", "tree",
     {"pollination_syndrome": "bee", "pigment_pathway": "none"},
     {"pigment_pathway": "none"},
     {"pigment_pathway": ["none", "anthocyanin"]}),
]


def test_real_rule_count(pack):
    """The real table has 26 rules, all loaded (the sweep must not go
    stale as content evolves)."""
    assert len(pack.constraints) == 26


@pytest.mark.parametrize("rule_id,plan,axes,parent_axes,expected",
                         RULE_CASES, ids=[c[0] for c in RULE_CASES])
def test_enforce_snaps_each_real_rule(pack, rule_id, plan, axes,
                                      parent_axes, expected):
    """Every snapping real rule fires on its crafted record and pulls the
    offending dial to the exact [old, new] pair the k13 reference
    produces; after the snap the record is compliant."""
    parent = _rec(plan, parent_axes) if parent_axes else None
    child = _rec(plan, axes, sid=rule_id)
    audit = enforce(parent, child, pack)
    assert audit == [{rule_id: expected}]
    assert violations(child, pack) == []


def test_all_real_rules_trigger(pack):
    """Drive the FULL table: every one of the 26 real rules fires on a
    crafted record (the trigger gate, not just the snapping subset)."""
    for rule_id, plan, axes, parent_axes, _expected in RULE_CASES:
        rule = next(r for r in pack.constraints if r.id == rule_id)
        assert triggered(rule, axes, plan), rule_id
    for rule_id, plan, axes in [
            ("inflorescence_seed_plans", "moss_grade",
             {"inflorescence": "raceme"}),
            ("pigment_anthocyanin_betalain_exclusive", "tree",
             {"pigment_pathway": "anthocyanin"})]:
        rule = next(r for r in pack.constraints if r.id == rule_id)
        assert triggered(rule, axes, plan), rule_id


# ──  the real presets pass the gate  ───────────────────────────────────────


def test_all_presets_pass_gate_unmodified(pack):
    """All 29 real presets commit clean: enforce() returns zero snaps and
    violations() is empty — the authored pack is legal as written."""
    pack_full = load_content(CONTENT_DIR)
    assert len(pack_full.presets) == 29
    for pid, preset in sorted(pack_full.presets.items()):
        plan = preset["preset"].get("plan")
        assert plan is not None, pid
        axes, generics = merged_preset(preset)
        rec = SpeciesRecord(sid=pid, plan=plan, preset=pid,
                            axes=axes, generics=generics)
        assert enforce(None, rec, pack) == [], pid
        assert violations(rec, pack) == [], pid


# ──  determinism audit  ────────────────────────────────────────────────────


def test_no_nondeterministic_imports():
    """AGENTS.md determinism hard rule: no random/uuid/time/numpy in the
    new module (same seed ⇒ byte-identical output)."""
    src = (pathlib.Path(__file__).parent / "constraints.py").read_text()
    for line in src.splitlines():
        stripped = line.strip()
        for bad in ("import random", "from random", "import uuid",
                    "from uuid", "import time", "from time",
                    "import numpy"):
            assert not stripped.startswith(bad), \
                f"constraints.py: forbidden import: {stripped}"
