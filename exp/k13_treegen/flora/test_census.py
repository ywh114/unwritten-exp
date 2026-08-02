"""Census validation — 0012 Task A invariants (the open-catalog gate).

Every check is content-level (reads pins.toml + presets) except the
lineage count, which builds the tree the way genesis would. A new
species or bundle entry must keep these green; that is the entry
contract documented in CENSUS.md.

Run: uv run pytest -q exp/k13_treegen/flora/test_census.py
"""

from __future__ import annotations

import pathlib

import pytest

from exp.k13_treegen.flora.backbone import build
from exp.k13_treegen.flora.constraints import violations
from exp.k13_treegen.flora.content import (
    bundle_region, is_bundle, load_content, merged_pin, merged_preset)
from exp.k13_treegen.flora.naming import assign_names
from exp.k13_treegen.model import Rank
from exp.k13_treegen.registry import ValueType

CONTENT = pathlib.Path(__file__).parent.parent / "content" / "flora"

# the two-track budget (owner ruling 2026-08-01: "<200 feasible").
MAX_LINEAGES = 200
# seeded-substrate floor (0012 coverage floor 2): >=2 SEEDED lineages
# (individual pins + bundle pins) whose tolerance envelope covers each
# B3 substrate class. Content-level proxy for the Task C audit.
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
def census(pack):
    """Census view: the authored records with merged axes, split by
    track."""
    ind, bundles = [], []
    for pin in pack.pins:
        axes, generics = merged_pin(pack, pin)
        rec = {"pin": pin, "axes": axes, "generics": generics}
        (bundles if is_bundle(pin) else ind).append(rec)
    return {"individual": ind, "bundle": bundles, "pack": pack}


# ── census size ────────────────────────────────────────────────────────


def test_census_under_200_pins(census):
    """The authored census (both tracks) stays under the 200 budget."""
    total = len(census["individual"]) + len(census["bundle"])
    assert total < MAX_LINEAGES, total


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_built_tree_under_200_lineages(pack, seed):
    """The lineage count the sim would seed: the built tree's species
    (pins + radiations + background + relatives) stays < 200."""
    tree = build(seed, pack)
    assign_names(tree, pack, seed)
    sp = [n for n in tree.nodes.values() if n.rank is Rank.SPECIES]
    assert len(sp) < MAX_LINEAGES, f"seed {seed}: {len(sp)} species"


def test_sids_unique(pack):
    tree = build(1, pack)
    sids = [n.sid for n in tree.nodes.values()]
    assert len(sids) == len(set(sids))


# ── two-track partition ────────────────────────────────────────────────


def test_track_counts(census):
    """Individual track in [40, 70]; bundle track an order of 10s."""
    n_ind, n_bun = len(census["individual"]), len(census["bundle"])
    assert 40 <= n_ind <= 70, n_ind
    assert 30 <= n_bun <= 70, n_bun


def test_bundle_flag_shape(census):
    """A bundle record is a species-rank pin with `bundle = true`, a
    covered-region note, no radiation (frozen placeholder), no
    parent_pin (never nested in an individual genus clade), and a
    valid preset."""
    for rec in census["bundle"]:
        pin = rec["pin"]
        assert is_bundle(pin) is True
        assert pin.get("rank", "species") == "species", pin["label"]
        assert bundle_region(pin), f"{pin['label']}: covered_region missing"
        assert not pin.get("radiation"), \
            f"{pin['label']}: bundles are frozen, no radiation"
        assert not pin.get("parent_pin"), \
            f"{pin['label']}: bundle must not nest in an individual genus"
        assert pin["preset"] in census["pack"].presets, pin["preset"]


def test_disjoint_partition(census):
    """No individual-track species is also a bundle member: the two
    tracks' binomial genera are disjoint (an oak is never inside a
    woodland bundle), and no pin carries both flags."""
    ind_genera = set()
    for rec in census["individual"]:
        nm = rec["pin"].get("name", {})
        b = nm.get("binomial")
        if b:
            ind_genera.add(b.split()[0])
        assert not is_bundle(rec["pin"])
    for rec in census["bundle"]:
        nm = rec["pin"].get("name", {})
        g = nm.get("binomial", "").split()[0]
        assert g, rec["pin"]["label"]
        assert g not in ind_genera, \
            f"bundle {rec['pin']['label']} shares genus {g!r} with an individual-track lineage"


def test_clade_spread_co_window(census):
    """Bundles whose covered regions name the same biome-region window
    are spread across binomial genera (families) — no clade clones."""
    from collections import defaultdict
    by_region = defaultdict(list)
    for rec in census["bundle"]:
        region = bundle_region(rec["pin"]).split(";")[0].strip()
        g = rec["pin"]["name"]["binomial"].split()[0]
        by_region[region].append(g)
    for region, genera in sorted(by_region.items()):
        if len(genera) >= 2:
            assert len(set(genera)) == len(genera), \
                f"co-window bundles {region!r} share a genus: {genera}"


# ── record coherence (the open-catalog gate) ───────────────────────────


def test_all_enum_values_legal(census):
    """Every committed enum value in a pin record is a registry state
    — except the spore/decomposer "none" idiom (pre-existing: spore
    plans author `inflorescence = "none"`, outside the registry). The
    real legality gate is the constraint audit (next test)."""
    pack = census["pack"]
    for rec in list(census["individual"]) + list(census["bundle"]):
        for ax, v in rec["axes"].items():
            spec = pack.registry.axes.get(ax)
            if spec is None or spec.value_type is not ValueType.ENUM:
                continue
            if str(v) == "none" and "none" not in spec.states:
                continue  # the pre-existing spore/decomposer idiom
            assert str(v) in spec.states, \
                f"{rec['pin']['label']}: {ax}={v!r} not in registry states"


def test_pin_records_pass_constraint_gate(census):
    """A merged pin record must not breach a triggered constraint rule
    (the build-time trust caveat: pinned records are authored, so the
    author is responsible for legality)."""
    pack = census["pack"]
    for rec in list(census["individual"]) + list(census["bundle"]):
        errs = violations_from_axes(pack, rec["axes"], rec["pin"])
        assert not errs, f"{rec['pin']['label']}: {errs[:2]}"


def violations_from_axes(pack, axes, pin):
    """Run the engine's constraint audit over a merged pin record."""
    from exp.k13_treegen.model import Node
    n = Node(path="x", rank=Rank.SPECIES, parent="p", sid="0" * 16,
             plan=pack.presets[pin["preset"]]["preset"]["plan"], axes=dict(axes))
    return violations(n, pack)


# ── seeded substrate floor (content-level proxy) ───────────────────────


def test_substrate_floor(census):
    """Each B3 substrate class has >=2 seeded lineages (individual OR
    bundle) whose merged tolerance envelope covers it. Glacier MASK is
    not a substrate: the snow-margin row keys on the snow_adaptation
    margin forms instead (nothing roots on the mask)."""
    pool = [rec for rec in census["individual"] + census["bundle"]]
    for substrate, req in SUBSTRATE_FLOOR.items():
        if "snow_adaptation" in req:
            margin = {"conical_shed", "flexible", "cushion_mat"}
            hit = [r for r in pool
                   if r["axes"].get("snow_adaptation") in margin]
        else:
            ax, lo = next(iter(req.items()))
            hit = [r for r in pool
                   if isinstance(r["axes"].get(ax), (int, float))
                   and r["axes"][ax] >= lo]
        assert len(hit) >= 2, \
            f"{substrate}: only {len(hit)} seeded lineages cover it " \
            f"({[r['pin']['label'] for r in hit]})"
