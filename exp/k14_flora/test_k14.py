"""K14 tests — flora engine gate. Mirrors K13's test discipline:
determinism (byte-exact replay), structure, constraint-gate unit
semantics, pin integration, derived axes, nomenclature guarantees, and
the metrics gate across seeds. Run: uv run pytest -q exp/k14_flora/
"""

from __future__ import annotations

import pathlib
import re

import pytest

from exp.k14_flora.backbone import ENVELOPE_LOG10, build
from exp.k14_flora.constraints import Rule, enforce, triggered, violations
from exp.k14_flora.content import load_content, merged_pin
from exp.k14_flora.derive import DERIVED_AXES
from exp.k14_flora.metrics import run_checks
from exp.k14_flora.model import Node, Rank
from exp.k14_flora.naming import assign_names

CONTENT = pathlib.Path(__file__).parent / "content"


@pytest.fixture(scope="module")
def pack():
    return load_content(CONTENT)


def _generate(seed: int, pack):
    tree = build(seed, pack)
    assign_names(tree, pack, seed)
    return tree


@pytest.fixture(scope="module")
def tree1(pack):
    return _generate(1, pack)


# ── content / registry ─────────────────────────────────────────────────


def test_content_loads(pack):
    assert len(pack.registry.plans) == 16
    assert len(pack.presets) >= 30
    assert pack.pins
    assert pack.constraints
    # the flora size axis is height_m, unit=length (registry accepts it)
    spec = pack.registry.axes["height_m"]
    assert spec.unit.value == "length"


def test_stems_shape(pack):
    for key in ("axis_stem", "context_stem", "invent", "genus_suffix",
                "stem"):
        assert key in pack.stems, f"stems missing {key}"
    # genus suffix tables carry the parallel genders array
    for grade, tbl in pack.stems["genus_suffix"].items():
        assert len(tbl["genders"]) == len(tbl["suffixes"]), grade


# ── determinism ────────────────────────────────────────────────────────


def test_build_deterministic(pack):
    a, b = build(1, pack), build(1, pack)
    assert a.dumps() == b.dumps()


def test_full_generate_deterministic(pack, tree1):
    b = _generate(1, pack)
    assert tree1.dumps() == b.dumps()


# ── structure ──────────────────────────────────────────────────────────


def test_structure(tree1):
    roots = tree1.roots()
    assert len(roots) == 1 and roots[0].flags == ["plantae"]
    phyla = [n for n in tree1.nodes.values() if n.rank is Rank.PHYLUM]
    assert len(phyla) == 3
    assert all(n.name.binomial for n in phyla)
    classes = [n for n in tree1.nodes.values() if n.rank is Rank.CLASS]
    assert len(classes) == 16
    species = [n for n in tree1.nodes.values() if n.rank is Rank.SPECIES]
    assert len(species) >= 100
    # no empty orders
    spaths = [n.path for n in species]
    for n in tree1.nodes.values():
        if n.rank is Rank.ORDER:
            assert any(s.startswith(n.path + ".") for s in spaths), n.path


def test_meta_generator(tree1):
    assert tree1.to_json()["meta"]["generator"] == "k14_flora"


# ── constraint gate (unit semantics) ───────────────────────────────────


def _node(path: str, plan: str, axes: dict) -> Node:
    return Node(path=path, rank=Rank.SPECIES, parent=None, sid="0" * 16,
                plan=plan, axes=dict(axes))


def test_rule_trigger_forms():
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


def test_enforce_require_and_idempotent(pack):
    r = Rule.from_toml({"id": "cam_succulence",
                        "when": {"axis": "photosynthesis", "state": "CAM"},
                        "require_min": {"succulence": 0.4}})
    parent = _node("p", "succulent",
                   {"photosynthesis": "C3", "succulence": 0.1})
    child = _node("p.s1", "succulent",
                  {"photosynthesis": "CAM", "succulence": 0.1})
    pack2 = type(pack)(registry=pack.registry, constraints=[r])
    enforce(parent, child, pack2)
    assert child.axes["succulence"] == 0.4
    assert "cam_succulence" in child.edge_delta["constraint"]
    before = dict(child.axes)
    enforce(parent, child, pack2)          # idempotent: second run no-op
    assert child.axes == before


def test_enforce_state_plans_snap_back(pack):
    r = Rule.from_toml({"id": "buttress_emergent",
                        "when": {"axis": "root_special",
                                 "state": "buttress"},
                        "state_plans": ["tree", "shrub"],
                        "require_min": {"height_m": 20.0}})
    pack2 = type(pack)(registry=pack.registry, constraints=[r])
    # off-plan (lichen): the trigger state snaps back to the parent
    parent = _node("p", "lichen", {"root_special": "none", "height_m": 0.01})
    child = _node("p.s1", "lichen",
                  {"root_special": "buttress", "height_m": 0.01})
    enforce(parent, child, pack2)
    assert child.axes["root_special"] == "none"
    assert child.axes["height_m"] == 0.01
    # on-plan (tree): requirements apply instead
    parent = _node("q", "tree", {"root_special": "none", "height_m": 25.0})
    child = _node("q.s1", "tree",
                  {"root_special": "buttress", "height_m": 10.0})
    enforce(parent, child, pack2)
    assert child.axes["root_special"] == "buttress"
    assert child.axes["height_m"] == 20.0


def test_enforce_palette_aware_snap(pack):
    """bird_syndrome_red on a moss: red/orange are outside the moss
    palette, so there is no legal candidate — the trigger (bird
    syndrome) must snap back instead of committing a palette breach."""
    r = Rule.from_toml({"id": "bird_syndrome_red",
                        "when": {"axis": "pollination_syndrome",
                                 "state": "bird"},
                        "require_min": {"flower_size_mm": 10.0},
                        "require_enum": {"flower_color": ["red",
                                                          "orange"]}})
    pack2 = type(pack)(registry=pack.registry, palettes=pack.palettes,
                       constraints=[r])
    parent = _node("p", "moss_grade",
                   {"pollination_syndrome": "none", "flower_color": "green",
                    "flower_size_mm": 1.0})
    child = _node("p.s1", "moss_grade",
                  {"pollination_syndrome": "bird", "flower_color": "green",
                   "flower_size_mm": 1.0})
    enforce(parent, child, pack2)
    assert child.axes["flower_color"] in pack.palettes["moss_grade"]
    assert child.axes["pollination_syndrome"] == "none"  # snapped back


def test_violations_reports_breach(pack):
    n = _node("x.s1", "tree", {"photosynthesis": "CAM", "succulence": 0.1})
    pack2 = type(pack)(registry=pack.registry, constraints=[
        Rule.from_toml({"id": "cam_succulence",
                        "when": {"axis": "photosynthesis", "state": "CAM"},
                        "require_min": {"succulence": 0.4}})])
    errs = violations(n, pack2)
    assert errs and "cam_succulence" in errs[0]


# ── pins ───────────────────────────────────────────────────────────────


def test_pins_present_at_rank(tree1, pack):
    by_label = {n.label: n for n in tree1.nodes.values() if n.label}
    for pin in pack.pins:
        n = by_label.get(pin["label"])
        assert n is not None, f"pin {pin['label']!r} missing"
        assert n.rank is Rank[pin.get("rank", "species").upper()]
        assert "pinned" in n.flags


def test_pin_enums_byte_exact(tree1, pack):
    by_label = {n.label: n for n in tree1.nodes.values() if n.label}
    for pin in pack.pins:
        n = by_label[pin["label"]]
        axes, _ = merged_pin(pack, pin)
        for ax, v0 in axes.items():
            if isinstance(v0, str):
                assert str(n.axes.get(ax)) == v0, (pin["label"], ax)


def test_binomial_genus_anchoring(tree1):
    """Pinned species sit under a genus bearing their authored binomial
    genus (Achillea millefolium under Achillea, never a composed name)."""
    for n in tree1.nodes.values():
        if n.label == "yarrow":
            genus = tree1.nodes[n.parent]
            assert genus.name.binomial == "Achillea"
            assert n.name.binomial == "Achillea millefolium"
            return
    raise AssertionError("yarrow pin missing")


# ── derived axes ───────────────────────────────────────────────────────


def test_derived_populated(tree1):
    for n in tree1.nodes.values():
        if n.rank is Rank.SPECIES:
            for ax in DERIVED_AXES:
                assert ax in n.axes, (n.path, ax)
            assert n.axes["raunkiaer"]


def test_derived_recompute_is_pure(tree1, pack):
    """Derived axes never drift: re-running derive reproduces them."""
    from exp.k14_flora.derive import derive_tree
    before = {p: dict(n.axes) for p, n in tree1.nodes.items()}
    derive_tree(tree1.nodes.values(), pack)
    for p, n in tree1.nodes.items():
        for ax in DERIVED_AXES:
            assert n.axes.get(ax) == before[p].get(ax)


# ── nomenclature ───────────────────────────────────────────────────────

_SID_FALLBACK = re.compile(r"^sp[0-9a-f]{4,16}$")


def test_all_species_named(tree1):
    for n in tree1.nodes.values():
        if n.rank is Rank.SPECIES:
            assert n.name.binomial, n.path
            ep = n.name.binomial.split()[-1]
            assert not _SID_FALLBACK.match(ep), (n.path, n.name.binomial)


def test_latin_ranks(tree1):
    for n in tree1.nodes.values():
        if n.rank in (Rank.KINGDOM, Rank.PHYLUM, Rank.CLASS):
            assert n.name.binomial, (n.path, n.rank)
    k1 = tree1.nodes["k1"]
    assert k1.name.binomial == "Plantae"


# ── envelope ───────────────────────────────────────────────────────────


def test_height_envelope_leaky(tree1, pack):
    """No species sits absurdly far from its preset anchor (the envelope
    is leaky, not a cap — but 6 dex is beyond any damped walk)."""
    for n in tree1.nodes.values():
        if n.rank is not Rank.SPECIES or not n.preset:
            continue
        ph = pack.preset_height(n.preset)
        h = n.axes.get("height_m")
        if ph and isinstance(h, (int, float)) and h > 0:
            import math
            assert abs(math.log10(h / ph)) < ENVELOPE_LOG10 * 3, n.path


# ── the metrics gate ───────────────────────────────────────────────────


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_metrics_clean(pack, seed):
    tree = _generate(seed, pack)
    report = run_checks(tree, pack)
    assert report.ok, report.text()
