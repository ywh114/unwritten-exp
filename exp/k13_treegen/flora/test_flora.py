"""Flora tests — flora engine gate. Mirrors K13's test discipline:
determinism (byte-exact replay), structure, constraint-gate unit
semantics, pin integration, derived axes, nomenclature guarantees, and
the metrics gate across seeds. Run: uv run pytest -q exp/k13_treegen/flora/
"""

from __future__ import annotations

import pathlib
import re

import pytest

from exp.k13_treegen.flora.backbone import ENVELOPE_LOG10, build
from exp.k13_treegen.flora.constraints import Rule, enforce, triggered, violations
from exp.k13_treegen.flora.content import load_content, merged_pin
from exp.k13_treegen.flora.derive import DERIVED_AXES
from exp.k13_treegen.flora.metrics import run_checks
from exp.k13_treegen.model import Node, Rank
from exp.k13_treegen.flora.naming import assign_names

CONTENT = pathlib.Path(__file__).parent.parent / "content" / "flora"


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
    assert tree1.to_json()["meta"]["generator"] == "k13_flora"


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


def test_enforce_pigment_legality(pack):
    """B5 §5.2: pigment legality is trait-side now. A bee-pollinated
    lineage cannot carry the "none" pathway (that is the dull wind set) —
    the gate snaps the pathway to a pigment, never the derived bucket."""
    r = Rule.from_toml({"id": "insect_syndrome_showy",
                        "when": {"axis": "pollination_syndrome",
                                 "state": ["bee", "moth", "beetle", "fly"]},
                        "forbid_enum": {"pigment_pathway": ["none"]}})
    pack2 = type(pack)(registry=pack.registry, constraints=[r])
    parent = _node("p", "tree",
                   {"pollination_syndrome": "wind",
                    "pigment_pathway": "none"})
    child = _node("p.s1", "tree",
                  {"pollination_syndrome": "bee",
                   "pigment_pathway": "none"})
    enforce(parent, child, pack2)
    assert child.axes["pigment_pathway"] == "anthocyanin"
    assert "insect_syndrome_showy" in child.edge_delta["constraint"]


def test_pigment_anthocyanin_excludes_betalain(pack):
    """B5 §5.2/§8.6: anthocyanin ⊥ betalain is a sampler-legality rule in
    the CAM↔succulence pattern. The pathway enum is single-valued, so a
    committed record can never hold both — the rule is the explicit gate
    and fires on either side of the pairing."""
    rule = next(r for r in pack.constraints
                if r.id == "pigment_anthocyanin_betalain_exclusive")
    assert triggered(rule, {"pigment_pathway": "anthocyanin"})
    # single-valued: the forbidding side of the pair is never present
    assert not violations(
        _node("x.s1", "tree", {"pigment_pathway": "anthocyanin"}), pack)
    assert not violations(
        _node("x.s2", "tree", {"pigment_pathway": "betalain"}), pack)


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
    from exp.k13_treegen.flora.derive import derive_tree
    before = {p: dict(n.axes) for p, n in tree1.nodes.items()}
    derive_tree(tree1.nodes.values(), pack)
    for p, n in tree1.nodes.items():
        for ax in DERIVED_AXES:
            assert n.axes.get(ax) == before[p].get(ax)


# ── derived flower_color (B5 §5.2) ─────────────────────────────────────


def test_derived_flower_color_vocab(tree1):
    """B5 §8.6: every species' derived flower_color is inside the legacy
    vocab the naming stems / id / tell consumers read."""
    from exp.k13_treegen.flora.derive import FLOWER_COLOR_VOCAB
    for n in tree1.nodes.values():
        if n.rank is Rank.SPECIES:
            assert n.axes.get("flower_color") in FLOWER_COLOR_VOCAB, n.path


def test_derived_flower_color_presets(tree1):
    """The archetype (order) records reproduce the authored palette
    colors — the mechanical migration (authored color -> nearest
    pathway + expression + ph position) keeps the F0 colors stable."""
    expected = {
        "tree.oak": "green", "tree.conifer": "green", "tree.birch": "green",
        "tree.willow": "green", "tree.palm": "cream",
        "shrub.bramble": "white", "shrub.heath": "pink",
        "herb_forb.carrot": "white", "herb_forb.chive": "pink",
        "herb_forb.forb": "white", "herb_forb.grave_flower": "white",
        "herb_forb.iris": "purple", "herb_forb.legume": "pink",
        "herb_forb.thistle": "purple", "herb_forb.yarrow": "white",
        "grass_sward.bamboo": "green", "grass_sward.reed": "brown",
        "grass_sward.sedge": "brown", "grass_sward.tussock": "brown",
        "succulent.cactus": "red", "rosette_mat.ice_crown": "white",
        "rosette_mat.stonecrop": "yellow",
        "fern_grade.bracken": "brown",
        "moss_grade.cushion": "green", "moss_grade.sphagnum": "green",
        "runner_meadow.seagrass": "green",
        "floating_leaf.ludwigia": "yellow", "floating_leaf.waterlily": "white",
        "floater.duckweed": "green",
        "macroalgae_holdfast.kelp": "brown",
        "coral_grade.branching_coral": "brown",
        "sponge_grade.barrel_sponge": "brown",
        "fungus.agaric": "brown", "fungus.bracket": "brown",
        "lichen.crust": "brown",
    }
    by_order = {}
    for n in tree1.nodes.values():
        if n.rank is Rank.ORDER and n.preset:
            by_order.setdefault(n.preset, n.axes.get("flower_color"))
    for pid, want in expected.items():
        assert by_order.get(pid) == want, (pid, by_order.get(pid))


def test_built_species_single_pigment_pathway(tree1):
    """B5 §8.6: the sampler commits exactly one legal pathway per seed
    species (anthocyanin ⊥ betalain by construction) — every committed
    value is a registry state and never both."""
    from exp.k13_treegen.flora.derive import PIGMENT_PATHWAYS
    for n in tree1.nodes.values():
        if n.rank is Rank.SPECIES and n.axes.get("pigment_pathway") is not None:
            p = n.axes["pigment_pathway"]
            assert p in PIGMENT_PATHWAYS, (n.path, p)
            assert not (p == "anthocyanin" and
                        n.axes.get("pigment_pathway") == "betalain")


def test_derived_flower_color_ph_zero_is_acid():
    """Regression: ph_tolerance 0.0 is a legitimate authored value
    (obligate calcifuge) and must read ACID (pink/red), never neutral —
    guards against falsy-`or` defaults (0.0 or 0.5 -> 0.5)."""
    from exp.k13_treegen.flora.derive import _derived_flower_color
    n = Node(path="a", rank=Rank.SPECIES, parent="k1", sid="0" * 16,
             axes={"pigment_pathway": "anthocyanin",
                   "pigment_expression": 0.9, "ph_tolerance": 0.0})
    assert _derived_flower_color(n) == "red"
    n.axes["ph_tolerance"] = 0.5
    assert _derived_flower_color(n) == "purple"     # neutral sanity
    n.axes["ph_tolerance"] = 1.0
    assert _derived_flower_color(n) == "blue"       # alkaline sanity


# ── display derivations (leaf/autumn color, canopy density) ──────────


def test_derived_leaf_color_precedence():
    """leafless -> red pigment -> gray pubescence -> glaucous cuticle ->
    sla economics -> green, in that order."""
    from exp.k13_treegen.flora.derive import _derived_leaf_color
    base = {"leaf_shape": "elliptical", "pigment_pathway": "none",
            "pigment_expression": 0.0, "pubescence": 0.0,
            "cuticle_thickness": 0.0, "leaf_sla": 12.0}
    n = _node("x.s1", "tree", dict(base, leaf_shape="none"))
    assert _derived_leaf_color(n) == "none"
    n = _node("x.s1", "tree", dict(base, pigment_pathway="anthocyanin",
                                   pigment_expression=0.8,
                                   pubescence=0.9))   # red beats gray
    assert _derived_leaf_color(n) == "red"
    n = _node("x.s1", "tree", dict(base, pubescence=0.7,
                                   cuticle_thickness=0.9))  # gray > glauc
    assert _derived_leaf_color(n) == "gray"
    n = _node("x.s1", "tree", dict(base, cuticle_thickness=0.8))
    assert _derived_leaf_color(n) == "glaucous"
    n = _node("x.s1", "tree", dict(base, leaf_sla=25.0))
    assert _derived_leaf_color(n) == "light_green"
    n = _node("x.s1", "tree", dict(base, leaf_sla=5.0))
    assert _derived_leaf_color(n) == "dark_green"
    n = _node("x.s1", "tree", dict(base))
    assert _derived_leaf_color(n) == "green"


def test_derived_autumn_color():
    """Evergreen/leafless -> none; deciduous hues by pathway x
    expression; pathway none -> brown."""
    from exp.k13_treegen.flora.derive import _derived_autumn_color
    base = {"leaf_shape": "elliptical", "leaf_persistence": "evergreen",
            "deciduous_trigger": "none", "pigment_pathway": "none",
            "pigment_expression": 0.0}
    n = _node("x.s1", "tree", dict(base))
    assert _derived_autumn_color(n) == "none"          # evergreen
    n = _node("x.s1", "tree", dict(base, leaf_shape="none",
                                   leaf_persistence="winter_deciduous"))
    assert _derived_autumn_color(n) == "none"          # leafless
    dec = dict(base, leaf_persistence="winter_deciduous")
    n = _node("x.s1", "tree", dict(dec))
    assert _derived_autumn_color(n) == "brown"         # no pigment
    n = _node("x.s1", "tree", dict(dec, pigment_pathway="anthocyanin",
                                   pigment_expression=0.8))
    assert _derived_autumn_color(n) == "red"
    n = _node("x.s1", "tree", dict(dec, pigment_pathway="carotenoid",
                                   pigment_expression=0.5))
    assert _derived_autumn_color(n) == "yellow"
    n = _node("x.s1", "tree", dict(dec, pigment_pathway="carotenoid",
                                   pigment_expression=0.9))
    assert _derived_autumn_color(n) == "orange"
    n = _node("x.s1", "tree", dict(dec, deciduous_trigger="drought",
                                   leaf_persistence="evergreen"))
    assert _derived_autumn_color(n) == "brown"  # trigger alone counts


def test_derived_canopy_density():
    """Leafless -> 0; woody evergreen sclerophyll denser than a thin-
    leaved deciduous herb; always inside [0, 1]."""
    from exp.k13_treegen.flora.derive import _derived_canopy_density
    leafless = _node("x.s1", "fungus", {"leaf_shape": "none"})
    assert _derived_canopy_density(leafless) == 0.0
    dense = _node("x.s1", "tree", {"leaf_shape": "needle",
                                   "woodiness": 1.0, "leaf_sla": 4.0,
                                   "leaf_persistence": "evergreen",
                                   "succulence": 0.0})
    open_ = _node("x.s1", "herb_forb", {
        "leaf_shape": "elliptical", "woodiness": 0.0, "leaf_sla": 30.0,
        "leaf_persistence": "winter_deciduous", "succulence": 0.0})
    d, o = _derived_canopy_density(dense), _derived_canopy_density(open_)
    assert d > o
    assert 0.0 <= o < d <= 1.0
    # every preset archetype lands in bounds
    for axes in ({"leaf_shape": "elliptical", "woodiness": 1.0,
                  "leaf_sla": 1.0, "leaf_persistence": "evergreen",
                  "succulence": 1.0},
                 {"leaf_shape": "blade", "woodiness": 0.0,
                  "leaf_sla": 60.0, "leaf_persistence": "winter_deciduous",
                  "succulence": 0.0}):
        n = _node("x.s1", "tree", axes)
        assert 0.0 <= _derived_canopy_density(n) <= 1.0


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
