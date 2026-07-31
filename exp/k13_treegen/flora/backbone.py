"""Flora backbone: the blind flora tree-build (mirrors K13 M7).

Assembles the committed Tree from the content pack. Kingdom root plantae
-> phyla (the seed / spore / decomposer lines, grouped by plan.phylum)
-> one class per growth-form plan -> one order per preset ->
families/genera/species evolved with the K13 evolve engine (flora
rebind tables, no fauna couplings) + the flora constraint gate + the
height envelope. Pins placed at authored ranks, byte-exact; radiations
seeded around authored targets. World-blind: benign Condition
throughout.

Differences from K13's backbone, all deliberate:
- size axis is height_m, so gen_time and the soft envelope key off
  height (ENVELOPE_LOG10/DAMP, same shape as K13's mass envelope);
- evolve runs with couplings=False (flora legality is the flora
  constraint gate, not the fauna M6 rule table) and the flora
  rebindable set (dispersal replaces locomotor);
- background radiation is thinner (BG_RADIATION 1-2): the authored
  genus-pin radiations dominate the census;
- phylum binomials are pre-committed here (the three lines have no
  per-plan class_name to compose from).
"""

from __future__ import annotations

import math

from exp.k13_treegen.forces import (
    Condition, evolve, gen_time_years, rate_multiplier)
from exp.k13_treegen.flora.constraints import enforce
from exp.k13_treegen.flora.content import ContentPack, merged_pin, merged_preset
from exp.k13_treegen.flora.derive import DERIVED_AXES, derive_tree
from exp.k13_treegen.model import Node, Rank, Tree
from exp.k13_treegen.flora.seeding import stage_stream

# dg budgets per rank step (generations, lognormal median): deep splits
# are older. Same shape as K13.
DG_ORDER_MEDIAN = 300.0
DG_FAMILY_MEDIAN = 150.0
DG_GENUS_MEDIAN = 60.0
DG_SIGMA = 0.3
# background radiation for orders without a radiation pin (no empty
# orders, but the authored radiations dominate the census).
BG_RADIATION_LO = 1
BG_RADIATION_HI = 2
# radiation counts scatter around their authored target.
RADIATION_SIGMA = 0.3
# generated sibling species per species-rank pin (no orphan pins).
RELATIVES_LO = 1
RELATIVES_HI = 2
# pin wiggle (K13 ruling): pinned records commit authored values plus a
# small seeded jitter (in axis-sigma units) so authored wholes don't sit
# suspiciously among generated neighbors. Enums/sets stay byte-exact;
# the metric tolerance is 6x this.
PIN_JITTER_Z = 0.05
# soft per-preset height envelope: no convergence anchor, but a leaky
# squash on sustained far-walks (same shape as K13's mass envelope).
ENVELOPE_LOG10 = 2.0
ENVELOPE_DAMP = 0.5
# gen_time from the size axis: years ~ COEFF * height_m^EXP (a 25 m oak
# clocks ~10 yr, a 0.6 m sedge ~1.5 yr).
GEN_TIME_COEFF = 2.0
GEN_TIME_EXP = 0.5
# flora generic rebinds (K13 forces.evolve hook): dispersal replaces
# locomotor; phenology/covering/signal/defense/storage/feeding_organ
# rebind within plan limits; sensor_array = tropism.
REBINDABLE = ("support", "feeding_organ", "signal", "dispersal",
              "defense", "storage", "covering", "phenology",
              "sensor_array")
UNBINDABLE = ("signal", "storage", "defense")
# authored latin for the three lines (pre-committed; nomenclature's
# phylum rule composes from plan.phylum only when unset).
PHYLUM_BINOMIAL = {"seed": "Spermatophyta", "spore": "Sporae",
                   "decomposer": "Mycota"}

_BENIGN = Condition()


def _sid(stream) -> str:
    return f"{stream.u64(0):016x}"


def _dg(stream, median: float, clock: int = 1) -> float:
    return median * math.exp(DG_SIGMA * stream.normal(clock))


def _radiation_count(stream, target: int) -> int:
    return max(1, round(target * math.exp(RADIATION_SIGMA
                                          * stream.normal(0))))


def _gen_time(node: Node, rate: float) -> None:
    h = node.axes.get("height_m")
    if isinstance(h, (int, float)) and h > 0:
        node.gen_time = gen_time_years(float(h), rate,
                                       coeff=GEN_TIME_COEFF,
                                       exponent=GEN_TIME_EXP)


def _apply_pin(node: Node, pack: ContentPack, pin: dict,
               stream=None) -> None:
    """Commit the pin's authored record onto an anchored node, plus the
    PIN_JITTER_Z wiggle on scalar axes (seeded from the node's own
    substream; enums and weighted sets stay byte-exact)."""
    from exp.k13_treegen.registry import MutationKind, ValueType
    axes, generics = merged_pin(pack, pin)
    if stream is not None:
        jitter = stream.child("pin_jitter")
        for clock, (ax, v) in enumerate(sorted(axes.items())):
            spec = pack.registry.axes.get(ax)
            if spec is None or not isinstance(v, (int, float)) \
                    or spec.value_type not in (ValueType.SCALAR,
                                               ValueType.INT) \
                    or spec.sigma <= 0:
                continue
            z = PIN_JITTER_Z * jitter.normal(clock)
            if spec.mutation_kind is not MutationKind.GAUSSIAN and v > 0:
                nv = v * math.exp(z * spec.sigma)
            else:
                nv = v + z * spec.sigma
            if spec.value_type is ValueType.INT:
                nv = int(round(nv))
            # NO clip: authored pin values are trusted even outside the
            # sampler bounds (the bound guides evolution, not curation).
            axes[ax] = nv
    node.axes = axes
    node.generics = generics
    node.label = pin["label"]
    node.flags = list(pin.get("flags", []))


def _evolve_edge(parent: Node, pack: ContentPack, stream, dg: float,
                 path: str, rate: float, rdir: float,
                 rank: Rank) -> Node:
    """One speciation edge: K13 evolve (flora tables) -> the height
    envelope -> the constraint gate (the final word — the envelope must
    run FIRST or it undoes legality snaps; the first seed-3 build had
    buttress snaps at 20 m damped back to 14 m) -> gen_time."""
    child = evolve(parent, pack, stream, dg, path=path, condition=_BENIGN,
                   runaway_dir=rdir, rate_mult=rate, rank=rank,
                   couplings=False, rebindable=REBINDABLE,
                   unbindable=UNBINDABLE, derived_axes=DERIVED_AXES)
    h = child.axes.get("height_m")
    if isinstance(h, (int, float)) and h > 0 and child.preset:
        ph = pack.preset_height(child.preset)
        if ph:
            dex = math.log10(h / ph)
            if abs(dex) > ENVELOPE_LOG10:
                excess = abs(dex) - ENVELOPE_LOG10
                new_dex = math.copysign(
                    ENVELOPE_LOG10 + excess * ENVELOPE_DAMP, dex)
                child.axes["height_m"] = ph * 10.0 ** new_dex
    enforce(parent, child, pack)
    _gen_time(child, rate)
    return child


def _apply_drift(child: Node, pack: ContentPack, drift: dict) -> None:
    """Directional-drift: sigma-shift each drift axis on this speciation
    edge (the 'oak but more drought-hardy' bias)."""
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
    tree.meta["generator"] = "k13_flora"   # model default is k13_treegen
    from exp.artifacts import current_commit
    tree.meta["commit"] = current_commit()  # provenance stamp
    tree.add(Node(path="k1", rank=Rank.KINGDOM, parent=None,
                  sid=_sid(root_stream.child("k1")), flags=["plantae"]))

    # phyla in first-seen plan order (content order is authored)
    phyla: dict[str, list] = {}
    for plan in pack.registry.plans.values():
        phyla.setdefault(plan.phylum, []).append(plan)

    pins_by_preset: dict[str, list] = {}
    for pin in pack.pins:
        pins_by_preset.setdefault(pin.get("preset"), []).append(pin)

    for pi, (phylum, plans) in enumerate(phyla.items(), 1):
        ppath = f"k1.p{pi}"
        pnode = Node(path=ppath, rank=Rank.PHYLUM, parent="k1",
                     sid=_sid(root_stream.child(ppath)),
                     flags=sorted({p.frame for p in plans}))
        pnode.name.binomial = PHYLUM_BINOMIAL.get(phylum,
                                                  phylum.capitalize())
        tree.add(pnode)
        for ci, plan in enumerate(plans, 1):
            cpath = f"{ppath}.c{ci}"
            tree.add(Node(path=cpath, rank=Rank.CLASS, parent=ppath,
                          sid=_sid(root_stream.child(cpath)),
                          plan=plan.id))
            presets = sorted(pid for pid, p in pack.presets.items()
                             if p["preset"]["plan"] == plan.id)
            for oi, pid in enumerate(presets, 1):
                _build_order(tree, root_stream, pack, cpath, oi, pid,
                             pins_by_preset.get(pid, []))
    # derived axes are a pure function of the committed record — one
    # pass at the end (rounds re-run it after their own evolves)
    derive_tree(tree.nodes.values(), pack)
    return tree


def _build_order(tree: Tree, root_stream, pack: ContentPack, cpath: str,
                 oi: int, preset_id: str, pins: list) -> None:
    opath = f"{cpath}.o{oi}"
    preset = pack.presets[preset_id]
    o_axes, o_generics = merged_preset(pack, preset)
    order = Node(path=opath, rank=Rank.ORDER, parent=cpath,
                 sid=_sid(root_stream.child(opath)),
                 plan=preset["preset"]["plan"], preset=preset_id,
                 axes=o_axes, generics=o_generics)
    _gen_time(order, 1.0)
    ostream = root_stream.child(opath)
    order_pin = next((p for p in pins
                      if p.get("rank", "species") == "order"), None)
    order_radiation = 0
    if order_pin:
        _apply_pin(order, pack, order_pin, ostream)
        order_radiation = order_pin.get("radiation", 0)
    tree.add(order)
    fam_pins = [p for p in pins if p.get("rank") == "family"]
    genus_pins = [p for p in pins if p.get("rank") == "genus"]
    # species pins with parent_pin are hosted inside that genus pin's
    # clade; the rest group by AUTHORED BINOMIAL GENUS — Quercus-hosted
    # species anchor a genus named Quercus and never sit beside an
    # unrelated pin in one composed genus (the K13 seals-beside-
    # anteaters ruling).
    hosted: dict[str, list] = {}
    by_genus: dict[str, list] = {}
    loose: list = []
    for sp in [p for p in pins if p.get("rank", "species") == "species"]:
        if sp.get("parent_pin"):
            hosted.setdefault(sp["parent_pin"], []).append(sp)
            continue
        binomial = (sp.get("name") or {}).get("binomial")
        genus_part = binomial.split()[0] if binomial else None
        if genus_part:
            by_genus.setdefault(genus_part, []).append(sp)
        else:
            loose.append(sp)
    # a group matching a genus pin's own binomial is hosted by that pin
    for gp in genus_pins:
        gb = (gp.get("name") or {}).get("binomial")
        if gb and gb in by_genus:
            hosted.setdefault(gp["label"], []).extend(by_genus.pop(gb))

    # families: default f1 (background + genus/species pins + order
    # radiation), then one per family pin.
    families: list[tuple[str, dict | None]] = [(None, None)]
    families += [(p["label"], p) for p in fam_pins]

    for fi, (_, fam_pin) in enumerate(families, 1):
        _build_family(tree, ostream, pack, order, fi, fam_pin,
                      genus_pins if fi == 1 else [],
                      loose if fi == 1 else [],
                      list(by_genus.items()) if fi == 1 else [],
                      order_radiation if fi == 1 else 0,
                      hosted if fi == 1 else {})


def _family_streams(ostream, fi: int):
    fam_stream = ostream.child(f"f{fi}")
    rate = rate_multiplier(fam_stream.child("rate"))
    rdir = 1.0 if fam_stream.child("rdir").bernoulli(0.5, 0) else -1.0
    return fam_stream, rate, rdir


def _build_family(tree: Tree, ostream, pack: ContentPack, order: Node,
                  fi: int, fam_pin: dict | None, genus_pins: list,
                  loose: list, pin_genera: list, order_radiation: int,
                  hosted: dict[str, list]) -> None:
    fam_stream, rate, rdir = _family_streams(ostream, fi)
    fpath = f"{order.path}.f{fi}"
    # drift-and-commit (user ruling): children drift from the parent's
    # committed record — NO convergence to far-back clade anchors, and
    # clade ranks carry no convergence requirements of their own.
    family = _evolve_edge(order, pack, fam_stream.child("node"),
                          _dg(fam_stream, DG_ORDER_MEDIAN), fpath,
                          rate, rdir, Rank.FAMILY)
    radiation = 0
    if fam_pin:
        _apply_pin(family, pack, fam_pin, fam_stream)
        radiation = fam_pin.get("radiation", 0)
    if fi == 1:
        radiation = order_radiation
    tree.add(family)

    if radiation:
        count = _radiation_count(fam_stream.child("rad"), radiation)
        n_spread = max(1, round(math.sqrt(count)))
        per_genus = [count // n_spread] * n_spread
        for i in range(count % n_spread):
            per_genus[i] += 1
    else:
        n_spread, per_genus = 0, []

    genera: list[tuple[dict | None, int, str | None, list]] = [
        (None, per_genus[0] if per_genus else 0, None, loose)]
    genera += [(p, p.get("radiation", 0), None,
                hosted.get(p["label"], [])) for p in genus_pins]
    genera += [(None, 0, gname, grp) for gname, grp in pin_genera]
    genera += [(None, per_genus[i], None, []) for i in range(1, n_spread)]

    bg = (BG_RADIATION_LO + fam_stream.child("bg").randrange(
        BG_RADIATION_HI - BG_RADIATION_LO + 1, 0)) if fi == 1 else 0

    for gi, (gen_pin, gen_radiation, gname, gspecies) in \
            enumerate(genera, 1):
        _build_genus(tree, fam_stream, pack, family, gi, gen_pin,
                     gen_radiation, rate, rdir, gspecies,
                     bg if gi == 1 else 0, name_hint=gname)


def _build_genus(tree: Tree, fam_stream, pack: ContentPack, family: Node,
                 gi: int, gen_pin: dict | None, radiation: int,
                 rate: float, rdir: float, species_pins: list,
                 background: int,
                 name_hint: str | None = None) -> None:
    gen_stream = fam_stream.child(f"g{gi}")
    gpath = f"{family.path}.g{gi}"
    genus = _evolve_edge(family, pack, gen_stream.child("node"),
                         _dg(gen_stream, DG_FAMILY_MEDIAN), gpath,
                         rate, rdir, Rank.GENUS)
    drift: dict = {}
    if gen_pin:
        _apply_pin(genus, pack, gen_pin, gen_stream)
        drift = gen_pin.get("drift", {})
    else:
        if name_hint:
            # binomial-anchored genus (from its pinned species): the
            # name is committed NOW so nomenclature never composes over
            # it (Achillea millefolium must sit under Achillea, not
            # under a composed Veladra).
            genus.name.binomial = name_hint
        if species_pins:
            # drift origin (user ruling): a genus hosting a pin takes
            # the pin's record as its local drift reference when the
            # file offers no genus-rank metadata.
            axes, generics = merged_pin(pack, species_pins[0])
            genus.axes = dict(axes)
            genus.generics = dict(generics)
            _gen_time(genus, rate)
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
        _apply_pin(species, pack, pin, sstream)
        _gen_time(species, rate)
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
