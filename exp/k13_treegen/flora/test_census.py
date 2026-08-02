"""Census validation — 0012 interim (individual-track only).

The bundle-track pins and their validation were REMOVED 2026-08-02:
bundles were misimplemented as species-rank tree pins (the definition,
per rulings 9-14, is a SIM-SIDE envelope + anchor-clade entity, NOT a
tree node). The rework re-adds bundle + stub-scaffold validation; the
checks here enforce the individual-track census that remains.

Run: uv run pytest -q exp/k13_treegen/flora/test_census.py
"""

from __future__ import annotations

import pathlib

import pytest

from exp.k13_treegen.flora.backbone import build
from exp.k13_treegen.flora.constraints import violations
from exp.k13_treegen.flora.content import (
    load_content, merged_pin, merged_preset)
from exp.k13_treegen.flora.naming import assign_names
from exp.k13_treegen.model import Rank
from exp.k13_treegen.registry import ValueType

CONTENT = pathlib.Path(__file__).parent.parent / "content" / "flora"

# the seeded-lineage budget (owner ruling 2026-08-01: "<200 feasible").
MAX_LINEAGES = 200
# seeded-substrate floor (0012 coverage floor 2): >=2 SEEDED individual-
# track lineages whose tolerance envelope covers each B3 substrate
# class. Interim note: the old two-track census met some rows via
# bundles; with the misinterpreted bundle pins removed, a row that falls
# below the floor is xfailed as a documented interim gap until the
# rework lands.
SUBSTRATE_FLOOR = {
    "bog/fen":          {"waterlogging_tolerance": 0.8},
    "alluvium (rip.)":  {"waterlogging_tolerance": 0.5},
    "solonchak/tidal":  {"salinity_tolerance": 0.7},
    "coastal-sand":     {"salinity_tolerance": 0.5},
    "scree/bedrock":    {"drought_tolerance": 0.6},
    "till/outwash":     {"drought_tolerance": 0.4},
    "snow/glacier-margin": {"snow_adaptation": "margin"},
}


@pytest.fixture(scope="module")
def pack():
    return load_content(CONTENT)


@pytest.fixture(scope="module")
def records(pack):
    """Individual-track census view: the authored pin records with merged
    axes (bundles removed 2026-08-02; the rework re-adds them)."""
    return [{"pin": pin, "axes": merged_pin(pack, pin)[0]}
            for pin in pack.pins]


# ── census size ────────────────────────────────────────────────────────


def test_census_under_200_pins(records):
    """The authored individual-track census stays under the 200 budget."""
    assert len(records) < MAX_LINEAGES, len(records)


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_built_tree_under_200_lineages(pack, seed):
    """The lineage count the sim would seed (pins + radiations +
    background + relatives) stays < 200."""
    tree = build(seed, pack)
    assign_names(tree, pack, seed)
    sp = [n for n in tree.nodes.values() if n.rank is Rank.SPECIES]
    assert len(sp) < MAX_LINEAGES, f"seed {seed}: {len(sp)} species"


def test_sids_unique(pack):
    tree = build(1, pack)
    sids = [n.sid for n in tree.nodes.values()]
    assert len(sids) == len(set(sids))


def test_individual_track_count(records):
    """Individual track in [40, 70] (0012 Task A item 2)."""
    assert 40 <= len(records) <= 70, len(records)


# ── record coherence (the open-catalog gate) ───────────────────────────


def test_all_enum_values_legal(records, pack):
    """Every committed enum value in a pin record is a registry state
    — except the spore/decomposer "none" idiom (pre-existing: spore
    plans author `inflorescence = "none"`, outside the registry). The
    real legality gate is the constraint audit (next test)."""
    for rec in records:
        for ax, v in rec["axes"].items():
            spec = pack.registry.axes.get(ax)
            if spec is None or spec.value_type is not ValueType.ENUM:
                continue
            if str(v) == "none" and "none" not in spec.states:
                continue  # the pre-existing spore/decomposer idiom
            assert str(v) in spec.states, \
                f"{rec['pin']['label']}: {ax}={v!r} not in registry states"


def test_pin_records_pass_constraint_gate(records, pack):
    """A merged pin record must not breach a triggered constraint rule
    (the build-time trust caveat: pinned records are authored, so the
    author is responsible for legality)."""
    for rec in records:
        errs = violations_from_axes(pack, rec["axes"], rec["pin"])
        assert not errs, f"{rec['pin']['label']}: {errs[:2]}"


def violations_from_axes(pack, axes, pin):
    """Run the engine's constraint audit over a merged pin record."""
    from exp.k13_treegen.model import Node
    n = Node(path="x", rank=Rank.SPECIES, parent="p", sid="0" * 16,
             plan=pack.presets[pin["preset"]]["preset"]["plan"], axes=dict(axes))
    return violations(n, pack)


# ── seeded substrate floor (content-level proxy) ───────────────────────


def test_substrate_floor(records):
    """Each B3 substrate class has >=2 seeded individual-track lineages
    whose merged tolerance envelope covers it. Glacier MASK is not a
    substrate: the snow-margin row keys on the snow_adaptation margin
    forms instead (nothing roots on the mask)."""
    for substrate, req in SUBSTRATE_FLOOR.items():
        if "snow_adaptation" in req:
            margin = {"conical_shed", "flexible", "cushion_mat"}
            hit = [r for r in records
                   if r["axes"].get("snow_adaptation") in margin]
        else:
            ax, lo = next(iter(req.items()))
            hit = [r for r in records
                   if isinstance(r["axes"].get(ax), (int, float))
                   and r["axes"][ax] >= lo]
        assert len(hit) >= 2, \
            f"{substrate}: only {len(hit)} seeded lineages cover it " \
            f"({[r['pin']['label'] for r in hit]})"
