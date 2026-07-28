"""M7 — backbone: the blind tree-build (docs/m7-backbone.md).

Assembles the committed Tree from the content pack. Kingdom root animalia
(plantae hook reserved) -> phyla (authored frame map) -> one class per
plan -> one order per preset -> families/genera/species evolved with
M5/M6. Pins placed at authored ranks, byte-exact; radiations seeded around
authored targets. World-blind: benign Condition throughout.
"""

from __future__ import annotations

import math

from exp.k13_treegen.content import ContentPack, merged_pin
from exp.k13_treegen.forces import (
    Condition, evolve, gen_time_years, rate_multiplier)
from exp.k13_treegen.model import Node, Rank, Tree
from exp.k13_treegen.seeding import stage_stream

# dg budgets per rank step (generations, lognormal median): deep splits are
# older. The seeded spread keeps sister clades from looking machined.
DG_ORDER_MEDIAN = 300.0
DG_FAMILY_MEDIAN = 150.0
DG_GENUS_MEDIAN = 60.0
DG_SIGMA = 0.3
# background radiation for orders without a radiation pin (no empty orders,
# but the authored radiations dominate the census).
BG_RADIATION_LO = 2
BG_RADIATION_HI = 4
# radiation counts scatter around their authored target.
RADIATION_SIGMA = 0.3
# generated sibling species per species-rank pin (no orphan pins).
RELATIVES_LO = 1
RELATIVES_HI = 2

_BENIGN = Condition()


def _sid(stream) -> str:
    return f"{stream.u64(0):016x}"


def _dg(stream, median: float, clock: int = 1) -> float:
    return median * math.exp(DG_SIGMA * stream.normal(clock))


def _radiation_count(stream, target: int) -> int:
    return max(1, round(target * math.exp(RADIATION_SIGMA
                                          * stream.normal(0))))


def _preset_axes(preset: dict) -> dict:
    return {**preset.get("knobs", {}), **preset.get("axes", {})}


def _apply_pin(node: Node, pack: ContentPack, pin: dict) -> None:
    """Commit the pin's authored record byte-exact onto an anchored node."""
    axes, generics = merged_pin(pack, pin)
    node.axes = axes
    node.generics = generics
    node.label = pin["label"]
    node.flags = list(pin.get("flags", []))


def _evolve_edge(parent: Node, pack: ContentPack, stream, dg: float,
                 path: str, rate: float, rdir: float,
                 rank: Rank) -> Node:
    return evolve(parent, pack, stream, dg, path=path, condition=_BENIGN,
                  runaway_dir=rdir, rate_mult=rate, rank=rank)


def _apply_drift(child: Node, pack: ContentPack, drift: dict) -> None:
    """M4 directional-drift: sigma-shift each drift axis on this speciation
    edge (the 'horse but more cursorial' bias)."""
    for ax, z in drift.items():
        v = child.axes.get(ax)
        spec = pack.registry.axes.get(ax)
        if isinstance(v, (int, float)) and spec is not None:
            child.axes[ax] = float(v) + z * spec.sigma
            d = child.edge_delta.setdefault(
                ax, {"drift": 0.0, "descent": 0.0, "runaway": 0.0})
            d["pin_drift"] = d.get("pin_drift", 0.0) + z


def build(seed: int, pack: ContentPack) -> Tree:
    """Build the committed tree for *seed*."""
    root_stream = stage_stream(seed, "backbone")
    tree = Tree(seed=seed)
    tree.add(Node(path="k1", rank=Rank.KINGDOM, parent=None,
                  sid=_sid(root_stream.child("k1")), flags=["animalia"]))

    # phyla in first-seen plan order (content order is authored)
    phyla: dict[str, list] = {}
    for plan in pack.registry.plans.values():
        phyla.setdefault(plan.phylum, []).append(plan)

    pins_by_preset: dict[str, list] = {}
    for pin in pack.pins:
        pins_by_preset.setdefault(pin.get("preset"), []).append(pin)

    for pi, (phylum, plans) in enumerate(phyla.items(), 1):
        ppath = f"k1.p{pi}"
        tree.add(Node(path=ppath, rank=Rank.PHYLUM, parent="k1",
                      sid=_sid(root_stream.child(ppath)),
                      flags=[plans[0].frame]))
        for ci, plan in enumerate(plans, 1):
            cpath = f"{ppath}.c{ci}"
            tree.add(Node(path=cpath, rank=Rank.CLASS, parent=ppath,
                          sid=_sid(root_stream.child(cpath)), plan=plan.id))
            presets = sorted(pid for pid, p in pack.presets.items()
                             if p["preset"]["plan"] == plan.id)
            for oi, pid in enumerate(presets, 1):
                _build_order(tree, root_stream, pack, cpath, oi, pid,
                             pins_by_preset.get(pid, []))
    return tree


def _build_order(tree: Tree, root_stream, pack: ContentPack, cpath: str,
                 oi: int, preset_id: str, pins: list) -> None:
    opath = f"{cpath}.o{oi}"
    preset = pack.presets[preset_id]
    order = Node(path=opath, rank=Rank.ORDER, parent=cpath,
                 sid=_sid(root_stream.child(opath)), plan=preset["preset"]
                 ["plan"], preset=preset_id,
                 axes=_preset_axes(preset),
                 generics=dict(preset.get("generics", {})))
    mass = order.axes.get("body_mass")
    if isinstance(mass, (int, float)) and mass > 0:
        order.gen_time = gen_time_years(float(mass))
    order_pin = next((p for p in pins
                      if p.get("rank", "species") == "order"), None)
    order_radiation = 0
    if order_pin:
        _apply_pin(order, pack, order_pin)
        order_radiation = order_pin.get("radiation", 0)
    tree.add(order)

    ostream = root_stream.child(opath)
    fam_pins = [p for p in pins if p.get("rank") == "family"]
    genus_pins = [p for p in pins if p.get("rank") == "genus"]
    # species pins with parent_pin are hosted inside that genus pin's
    # clade (horse -> equines); the rest go to the default genus.
    hosted: dict[str, list] = {}
    species_pins = []
    for sp in [p for p in pins if p.get("rank", "species") == "species"]:
        if sp.get("parent_pin"):
            hosted.setdefault(sp["parent_pin"], []).append(sp)
        else:
            species_pins.append(sp)

    # families: default f1 (background + genus/species pins + order
    # radiation), then one per family pin.
    families: list[tuple[str, dict | None]] = [(None, None)]
    families += [(p["label"], p) for p in fam_pins]

    # distribute the order pin's radiation into the default family
    for fi, (_, fam_pin) in enumerate(families, 1):
        _build_family(tree, ostream, pack, order, fi, fam_pin,
                      genus_pins if fi == 1 else [],
                      species_pins if fi == 1 else [],
                      order_radiation if fi == 1 else 0,
                      hosted if fi == 1 else {})


def _family_streams(ostream, fi: int):
    fam_stream = ostream.child(f"f{fi}")
    rate = rate_multiplier(fam_stream.child("rate"))
    rdir = 1.0 if fam_stream.child("rdir").bernoulli(0.5, 0) else -1.0
    return fam_stream, rate, rdir


def _build_family(tree: Tree, ostream, pack: ContentPack, order: Node,
                  fi: int, fam_pin: dict | None, genus_pins: list,
                  species_pins: list, order_radiation: int,
                  hosted: dict[str, list]) -> None:
    fam_stream, rate, rdir = _family_streams(ostream, fi)
    fpath = f"{order.path}.f{fi}"
    family = _evolve_edge(order, pack, fam_stream.child("node"),
                          _dg(fam_stream, DG_ORDER_MEDIAN), fpath,
                          rate, rdir, Rank.FAMILY)
    radiation = 0
    drift: dict = {}
    if fam_pin:
        _apply_pin(family, pack, fam_pin)
        radiation = fam_pin.get("radiation", 0)
    if fi == 1:
        radiation = order_radiation
    tree.add(family)

    # genera: the default genus g1 takes the first radiation share (never
    # left empty), genus pins anchor their own, then spread genera.
    if radiation:
        count = _radiation_count(fam_stream.child("rad"), radiation)
        n_spread = max(1, round(math.sqrt(count)))
        per_genus = [count // n_spread] * n_spread
        for i in range(count % n_spread):
            per_genus[i] += 1
    else:
        n_spread, per_genus = 0, []

    genera: list[tuple[dict | None, int]] = [
        (None, per_genus[0] if per_genus else 0)]
    genera += [(p, p.get("radiation", 0)) for p in genus_pins]
    genera += [(None, per_genus[i]) for i in range(1, n_spread)]

    bg = (BG_RADIATION_LO + fam_stream.child("bg").randrange(
        BG_RADIATION_HI - BG_RADIATION_LO + 1, 0)) if fi == 1 else 0

    for gi, (gen_pin, gen_radiation) in enumerate(genera, 1):
        hosted_here = hosted.get(gen_pin["label"], []) if gen_pin else []
        _build_genus(tree, fam_stream, pack, family, gi, gen_pin,
                     gen_radiation, rate, rdir,
                     (species_pins if gi == 1 else []) + hosted_here,
                     bg if gi == 1 else 0)


def _build_genus(tree: Tree, fam_stream, pack: ContentPack, family: Node,
                 gi: int, gen_pin: dict | None, radiation: int,
                 rate: float, rdir: float, species_pins: list,
                 background: int) -> None:
    gen_stream = fam_stream.child(f"g{gi}")
    gpath = f"{family.path}.g{gi}"
    genus = _evolve_edge(family, pack, gen_stream.child("node"),
                         _dg(gen_stream, DG_FAMILY_MEDIAN), gpath,
                         rate, rdir, Rank.GENUS)
    drift: dict = {}
    if gen_pin:
        _apply_pin(genus, pack, gen_pin)
        drift = gen_pin.get("drift", {})
    tree.add(genus)

    n_species = background
    if radiation:
        n_species += _radiation_count(gen_stream.child("rad"), radiation)
    n_rel = 0
    if species_pins:
        n_rel = (RELATIVES_LO + gen_stream.child("rel").randrange(
            RELATIVES_HI - RELATIVES_LO + 1, 0))

    si = 0
    for pin in species_pins:          # pinned species: byte-exact commits
        si += 1
        spath = f"{gpath}.s{si}"
        sstream = gen_stream.child(f"s{si}")
        species = Node(path=spath, rank=Rank.SPECIES, parent=gpath,
                       sid=_sid(sstream), plan=genus.plan,
                       preset=genus.preset, g=genus.g +
                       _dg(sstream, DG_GENUS_MEDIAN))
        _apply_pin(species, pack, pin)
        mass = species.axes.get("body_mass")
        if isinstance(mass, (int, float)) and mass > 0:
            species.gen_time = gen_time_years(float(mass), rate)
        tree.add(species)
    for _ in range(n_species + n_rel):  # generated radiation + relatives
        si += 1
        spath = f"{gpath}.s{si}"
        sstream = gen_stream.child(f"s{si}")
        species = _evolve_edge(genus, pack, sstream,
                               _dg(sstream, DG_GENUS_MEDIAN), spath,
                               rate, rdir, Rank.SPECIES)
        if drift:
            _apply_drift(species, pack, drift)
        tree.add(species)
