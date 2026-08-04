"""Fast-tier tests for the canonical species-view assembler + intrinsic
stress (ticket 0042; spec B9 §3, §4, §8).

View purity, the full carried-over key set on every flora plan's view
(driven from the real content pack), intrinsic stress: in-envelope zero
(≤ weak-leakage epsilon), strictly increasing with deviation, the
plateau-with-cliffs shape (no steering), decisive for the B8-probe
cactus, authored exception bubbles, and the describe hook smoke test.
Plain pytest, no marks — runs in milliseconds.
"""

from __future__ import annotations

import copy
import pathlib

import pytest

from exp.k15_biosphere.content import load_content, merged_preset
from exp.k15_biosphere.record import SpeciesRecord
from exp.k15_biosphere.flora.view import (
    CARRIED_KEYS,
    DECISIVE_STRESS,
    IN_ENVELOPE_EPSILON,
    StressBubble,
    WEAK_LEAK_RATE,
    assemble_view,
    energetics,
    mechanical_support,
)
from exp.k15_biosphere.describe import describe

# The real flora content pack lives in the frozen k13 reference; content
# is shared data, read IN PLACE from there (never copied).
CONTENT_DIR = pathlib.Path(__file__).parent.parent.parent / "k13_treegen" \
    / "content" / "flora"

# Loaded once at module scope: the 29-preset parametrizations below are
# fast and share the pack.
_PACK = load_content(CONTENT_DIR)
_PRESET_IDS = sorted(_PACK.presets)

# The keys the assembler adds on top of the carried-over k13 vocabulary.
_VIEW_EXTRA_KEYS = {"sid", "plan", "preset", "mass_total_kg",
                    "mass_agb_kg", "mass_proportions", "intrinsic_stress"}


def _preset_record(preset_id: str, **axis_overrides) -> SpeciesRecord:
    """The committed record of a real preset (with overrides winning)."""
    t = _PACK.presets[preset_id]
    axes, generics = merged_preset(t)
    axes = {**axes, **axis_overrides}
    return SpeciesRecord(sid="0" * 16, plan=t["preset"]["plan"],
                         preset=preset_id, axes=axes, generics=generics)


def _tree_view(height_m: float) -> dict:
    """A synthetic tree view whose support_ratio == height_m (dbh 1.0 m,
    crown_dbh_ratio at the broadleaf norm)."""
    return {"height_m": height_m, "crown_spread_m": 12.0,
            "mass_proportions": {"dbh_m": 1.0, "crown_dbh_ratio": 18.0}}


# ──  view purity (B9 §1, §8)  ────────────────────────────────────────────


def test_assembly_never_mutates_record_and_is_equal():
    """Assembling a view never mutates the record; two assemblies of the
    same record are equal (computed on read, never stored)."""
    rec = _preset_record("tree.oak")
    before = copy.deepcopy(rec)
    v1 = assemble_view(rec, _PACK)
    assert rec == before, "assembling the view mutated the record"
    v2 = assemble_view(rec, _PACK)
    assert v1 == v2


def test_view_snapshots_nested_record_state():
    """The view is an independent snapshot: nested dicts from the record
    (dispersal_channels) are copied, never aliased."""
    rec = _preset_record("tree.oak")
    v = assemble_view(rec, _PACK)
    assert v["dispersal_channels"] == rec.axes["dispersal_channels"]
    assert v["dispersal_channels"] is not rec.axes["dispersal_channels"]


# ──  the full carried-over key set (B9 §3, §8)  ─────────────────────────


@pytest.mark.parametrize("preset_id", _PRESET_IDS)
def test_carried_keys_present_on_every_preset_view(preset_id):
    """Every flora view carries the full k13 key set (plus the new block
    keys) — no pruning, no strays: the view is exactly CARRIED_KEYS ∪
    the identity/mass/stress block."""
    v = assemble_view(_preset_record(preset_id), _PACK)
    assert set(v) == CARRIED_KEYS | _VIEW_EXTRA_KEYS, (
        f"{preset_id}: view keys != carried set + block keys\n"
        f"  missing: {sorted(CARRIED_KEYS - set(v))}\n"
        f"  extra:   {sorted(set(v) - CARRIED_KEYS - _VIEW_EXTRA_KEYS)}")
    assert set(v["intrinsic_stress"]) == {"mechanical_support", "energetics"}


@pytest.mark.parametrize("preset_id", _PRESET_IDS)
def test_real_presets_are_not_intrinsically_stressed(preset_id):
    """Every authored preset sits inside both viable envelopes (stress ≤
    the weak-leakage bound): real species are not intrinsically stressed
    at their authored proportions — the 200 m cactus exception is the
    whole point of the channel."""
    v = assemble_view(_preset_record(preset_id), _PACK)
    for key, term in sorted(v["intrinsic_stress"].items()):
        assert term["value"] <= IN_ENVELOPE_EPSILON, (
            f"{preset_id} {key}: {term['value']:.4f} > "
            f"{IN_ENVELOPE_EPSILON} ({term['cause']})")


# ──  intrinsic stress: the acceptance case (B9 §4, §8)  ─────────────────


def test_cactus_at_height_ceiling_is_decisively_stressed():
    """The B8-probe cactus: succulent.cactus with height_m at the
    registry ceiling (200 m) while its crown stays at 0.6 m — a 200 m
    cactus must be chronically self-stressed through the mechanical
    support channel ALONE."""
    rec = _preset_record("succulent.cactus", height_m=200.0)
    v = assemble_view(rec, _PACK)
    mech = v["intrinsic_stress"]["mechanical_support"]
    ener = v["intrinsic_stress"]["energetics"]
    sr = mech["knobs"]["support_ratio"]
    assert sr["value"] == pytest.approx(200.0 / 0.6)
    assert mech["value"] >= DECISIVE_STRESS, (
        f"support stress {mech['value']:.3f} < DECISIVE_STRESS "
        f"{DECISIVE_STRESS}: {mech['cause']}")
    assert ener["value"] <= IN_ENVELOPE_EPSILON, (
        "the decisive signal must come from the support channel alone")


def test_support_stress_strictly_increasing_with_deviation():
    """Outside the envelope the penalty rises strictly with deviation —
    below the floor (approaching it lowers stress) and above the
    ceiling (moving away raises it)."""
    lo, hi = 8.0, 120.0   # the tree support_ratio envelope
    below = [mechanical_support(_tree_view(h), "tree")["value"]
             for h in (2.0, 4.0, 6.0, 7.5, 8.0)]
    above = [mechanical_support(_tree_view(h), "tree")["value"]
             for h in (120.0, 176.0, 232.0, 288.0, 344.0)]
    assert all(a > b for a, b in zip(below, below[1:])), below
    assert all(a < b for a, b in zip(above, above[1:])), above


def test_plateau_flat_inside_envelope():
    """Inside the envelope the stress is at most the weak leakage, with
    ~zero gradient — drift inside the viable region is free (the
    anti-carcinisation ruling: no gradient steering normal body plans)."""
    interior = [mechanical_support(_tree_view(h), "tree")["value"]
                for h in (20.0, 40.0, 60.0, 80.0, 100.0)]
    assert all(x <= WEAK_LEAK_RATE for x in interior), interior
    assert max(interior) - min(interior) <= WEAK_LEAK_RATE


def test_energetics_fires_on_root_shoot_deviation():
    """The energetics channel reads root_shoot (the storage/size split;
    fungus's mycelium/fruitbody ratio is the variable knob today): a
    tree carrying a herb-like root:shoot is decisively stressed, a
    normal tree is not."""
    normal = {"height_m": 25.0, "crown_spread_m": 12.0,
              "mass_proportions": {"root_shoot": 0.26}}
    lopsided = {"height_m": 25.0, "crown_spread_m": 12.0,
                "mass_proportions": {"root_shoot": 1.5}}
    assert energetics(normal, "tree")["value"] <= IN_ENVELOPE_EPSILON
    assert energetics(lopsided, "tree")["value"] > IN_ENVELOPE_EPSILON
    assert mechanical_support(normal, "tree")["value"] \
        <= IN_ENVELOPE_EPSILON


def test_zero_height_record_is_neutral():
    """Height 0 (or missing) means no organism: no proportions, no
    intrinsic stress — the knobs read neutral."""
    rec = _preset_record("tree.oak", height_m=0.0)
    v = assemble_view(rec, _PACK)
    assert v["mass_total_kg"] == 0.0
    assert v["mass_proportions"] == {}
    for term in v["intrinsic_stress"].values():
        assert term["value"] == 0.0
        assert "no measurable proportions" in term["cause"]


def test_unknown_plan_raises():
    """The assembler is for species records of a registry plan; a record
    without one (or with a plan outside the pack) is an error, not a
    silent view."""
    rec = _preset_record("tree.oak")
    rec.plan = "dragon"
    with pytest.raises(ValueError):
        assemble_view(rec, _PACK)
    rec.plan = None
    with pytest.raises(ValueError):
        assemble_view(rec, _PACK)


# ──  authored exception bubbles (B9 §4)  ────────────────────────────────


def test_bubble_exempts_and_cliff_applies_beyond_its_edge():
    """A record inside an authored bubble reads as in-envelope; beyond
    the bubble edge the normal cliff applies (and the bubble must HELP
    versus no bubble at the same point)."""
    view = _tree_view(25.0)
    bub = [StressBubble("mechanical_support", "support_ratio", 200.0, 10.0,
                        note="test exemption")]
    at_bub = mechanical_support({**view, "height_m": 200.0}, "tree", bub)
    beyond = mechanical_support({**view, "height_m": 250.0}, "tree", bub)
    plain = mechanical_support({**view, "height_m": 250.0}, "tree")
    assert at_bub["value"] <= IN_ENVELOPE_EPSILON
    assert at_bub["knobs"]["support_ratio"]["direction"] == "none"
    assert beyond["value"] > IN_ENVELOPE_EPSILON
    assert beyond["value"] < plain["value"], "the bubble must help"


def test_bubbles_are_per_type_and_per_knob():
    """A bubble exempts only its own stress type × knob — a support
    bubble implies no exemption elsewhere (B9 §4)."""
    view = _tree_view(200.0)   # support_ratio 200: outside the tree envelope
    wrong_type = [StressBubble("energetics", "support_ratio", 200.0, 10.0)]
    wrong_knob = [StressBubble("mechanical_support", "root_shoot", 200.0, 10.0)]
    assert mechanical_support(view, "tree", wrong_type)["value"] \
        > IN_ENVELOPE_EPSILON
    assert mechanical_support(view, "tree", wrong_knob)["value"] \
        > IN_ENVELOPE_EPSILON


def test_bubbles_thread_through_the_assembler():
    """The assembler accepts bubbles and threads them into the stress
    block — the cactus at the ceiling, with an authored support bubble
    around its pinned proportions, reads in-envelope again."""
    rec = _preset_record("succulent.cactus", height_m=200.0)
    bub = [StressBubble("mechanical_support", "support_ratio", 333.3, 20.0,
                        note="the B8 cactus — authored exemption")]
    v = assemble_view(rec, _PACK, bubbles=bub)
    assert v["intrinsic_stress"]["mechanical_support"]["value"] \
        <= IN_ENVELOPE_EPSILON


def test_bubble_zero_radius_rejected():
    view = _tree_view(200.0)
    bad = [StressBubble("mechanical_support", "support_ratio", 200.0, 0.0)]
    with pytest.raises(ValueError):
        mechanical_support(view, "tree", bad)


# ──  describe hook (B9 §6, §8)  ─────────────────────────────────────────


def test_describe_output_smoke():
    """The describe hook renders the full view in human terms: the
    binomial slot, mass, every intrinsic-stress term with its cause,
    provisions, dispersal."""
    text = describe(_preset_record("tree.oak"), _PACK)
    for needle in ("binomial", "plan", "climate", "mass", "proportions",
                   "mechanical_support", "energetics", "provisions",
                   "dispersal", "wiring"):
        assert needle in text, f"{needle!r} missing from describe output"


def test_describe_cactus_shows_the_decisive_cause():
    text = describe(_preset_record("succulent.cactus", height_m=200.0),
                    _PACK)
    assert "envelope-widths ABOVE" in text
    assert "mechanical_support" in text


# ──  determinism audit  ─────────────────────────────────────────────────


def test_no_nondeterministic_imports():
    """AGENTS.md determinism hard rule: no random/uuid/time/numpy in the
    new modules (same seed ⇒ byte-identical output)."""
    for mod in ("flora/view.py", "describe.py"):
        src = (pathlib.Path(__file__).parent.parent / mod).read_text()
        for line in src.splitlines():
            stripped = line.strip()
            for bad in ("import random", "from random", "import uuid",
                        "from uuid", "import time", "from time",
                        "import numpy"):
                assert not stripped.startswith(bad), \
                    f"{mod}: forbidden import: {stripped}"
