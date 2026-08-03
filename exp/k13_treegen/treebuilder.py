"""TreeBuilder — the shared blind tree-build (M7), serving both kingdoms.

Consolidated 2026-08-02 (0032 prereq, absorbed from 0006): the fauna
backbone (exp/k13_treegen/fauna/backbone.py) and the flora backbone
(exp/k13_treegen/flora/backbone.py) were near-identical copies of the
same build — same spine (kingdom -> phylum -> one class per plan (flora: real
order per preset -> families/genera/species), same pin/radiation/
relative machinery — differing only in per-kingdom constants and hooks
(content module, evolve kwargs, height-vs-mass gen_time, phylum
binomials, background radiation, meta stamping).

One parameterized TreeBuilder + one subclass per kingdom replaces both.

RADIATE MODEL (0032, owner-settled 2026-08-02): every node carries a
radiate permission (never / pre / post / pre-and-post) — WHEN radiation
may create children below it — and a radiate_to level (the DEEPEST rank
pre-radiation may create; PRE only — post creation handles its own
depth via the demand function). Defaults per rank (model.RADIATE_DEFAULT
/ RADIATE_TO_DEFAULT), overridable per node via the pin record
(``radiate`` / ``radiate_to`` keys).

The pre pass ("add pinned things, radiate allowed"):
- pinned nodes at every rank are created regardless of radiation;
- a node with radiate in (pre, both) creates its children down to its
  radiate_to, respecting pins (a pinned child slot is not radiated
  over);
- children created AT the radiate_to depth are marked post (they
  complete after the sim); intermediates propagate the chain target;
- species never radiates (terminal; subspecies are sim-side 0010).

World-blind: benign Condition throughout.
"""

from __future__ import annotations

import math

from exp.k13_treegen.forces import Condition, evolve, rate_multiplier
from exp.k13_treegen.model import (
    RADIATE_BOTH, RADIATE_DEFAULT, RADIATE_NEVER, RADIATE_POST,
    RADIATE_PRE, RADIATE_TO_DEFAULT, Node, Rank, Tree)
from exp.k13_treegen.registry import MutationKind, ValueType

# dg budgets per rank step (generations, lognormal median): deep splits
# are older. The seeded spread keeps sister clades from looking machined.
DG_ORDER_MEDIAN = 300.0
DG_FAMILY_MEDIAN = 150.0
DG_GENUS_MEDIAN = 60.0
DG_SIGMA = 0.3
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

_BENIGN = Condition()


class TreeBuilder:
    """Shared blind tree-build. One subclass per kingdom supplies the
    hooks; the machinery below is common to both."""

    # -- per-kingdom hooks (override in subclasses) --
    GENERATOR: str | None = None   # meta["generator"]; None = model default
    STAMP_COMMIT: bool = False     # stamp meta["commit"] = current_commit()
    KINGDOM_FLAGS = ("animalia",)
    BG_RADIATION_LO = 2
    BG_RADIATION_HI = 4

    def stage_stream(self, seed, *path):
        raise NotImplementedError

    def merge_pin(self, pack, pin):
        raise NotImplementedError

    def preset_record(self, pack, preset):
        raise NotImplementedError

    def derive_tree(self, nodes, pack):
        raise NotImplementedError

    def evolve_kwargs(self) -> dict:
        return {}

    def post_evolve(self, child, parent, pack, rate) -> None:
        pass

    def gen_time(self, node, rate) -> None:
        pass

    def phylum_flags(self, plans):
        return [plans[0].frame]

    def phylum_binomial(self, phylum):
        return None

    def class_groups(self, pack) -> dict[str, list[tuple[str, list[str]]]]:
        """phylum -> [(class_name, [plan_ids])] in tree order. Default
        (fauna): one class per plan, named from plan.class_name. Flora
        overrides with the authored classes.toml table (real classes
        grouping several plans)."""
        groups: dict[str, list[tuple[str, list[str]]]] = {}
        for plan in pack.registry.plans.values():
            groups.setdefault(plan.phylum, []).append(
                (plan.class_name or plan.id, [plan.id]))
        return groups

    # -- radiate model (0032) ----------------------------------------------

    def _radiate_flag(self, node, pin=None, propagated=None) -> str:
        """Resolve a node's radiate permission: pin override > propagated
        chain target > rank default."""
        if pin is not None and pin.get("radiate"):
            return str(pin["radiate"])
        if propagated is not None:
            return propagated
        return RADIATE_DEFAULT.get(node.rank, RADIATE_NEVER)

    def _radiate_to(self, node, pin=None, propagated=None) -> Rank:
        """Resolve radiate_to (deepest rank PRE may create below a node):
        pin override > propagated chain target > rank default."""
        if pin is not None and pin.get("radiate_to"):
            return Rank[str(pin["radiate_to"]).upper()]
        if propagated is not None:
            return propagated
        return RADIATE_TO_DEFAULT.get(node.rank)

    # -- shared machinery -------------------------------------------------

    def _sid(self, stream) -> str:
        return f"{stream.u64(0):016x}"

    def _dg(self, stream, median: float, clock: int = 1) -> float:
        return median * math.exp(DG_SIGMA * stream.normal(clock))

    def _radiation_count(self, stream, target: int) -> int:
        return max(1, round(target * math.exp(RADIATION_SIGMA
                                              * stream.normal(0))))

    def _apply_pin(self, node, pack, pin, stream=None) -> None:
        """Commit the pin's authored record onto an anchored node, plus
        the PIN_JITTER_Z wiggle on scalar axes (seeded from the node's
        own substream; enums and weighted sets stay byte-exact)."""
        axes, generics = self.merge_pin(pack, pin)
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
                # NO clip: authored pin values are trusted even outside
                # the sampler bounds (the bound guides evolution, not
                # curation).
                axes[ax] = nv
        node.axes = axes
        node.generics = generics
        node.label = pin["label"]
        node.flags = list(pin.get("flags", []))

    def _evolve_edge(self, parent, pack, stream, dg: float,
                     path: str, rate: float, rdir: float,
                     rank: Rank) -> Node:
        """One speciation edge: K13 evolve (per-kingdom tables) -> the
        per-kingdom post hook (flora: height envelope -> constraint gate
        -> gen_time; fauna: none)."""
        child = evolve(parent, pack, stream, dg, path=path,
                       condition=_BENIGN, runaway_dir=rdir,
                       rate_mult=rate, rank=rank, **self.evolve_kwargs())
        self.post_evolve(child, parent, pack, rate)
        return child

    def _apply_drift(self, child, pack, drift) -> None:
        """Directional-drift: sigma-shift each drift axis on this
        speciation edge (the 'oak but more drought-hardy' bias)."""
        for ax, z in drift.items():
            v = child.axes.get(ax)
            spec = pack.registry.axes.get(ax)
            if isinstance(v, (int, float)) and spec is not None:
                child.axes[ax] = float(v) + z * spec.sigma
                d = child.edge_delta.setdefault(
                    ax, {"drift": 0.0, "descent": 0.0, "runaway": 0.0})
                d["pin_drift"] = d.get("pin_drift", 0.0) + z

    def _is_pre(self, radiate: str) -> bool:
        return radiate in (RADIATE_PRE, RADIATE_BOTH)

    def build(self, seed: int, pack) -> Tree:
        """Build the committed tree for *seed* (the PRE pass: pinned
        things + pre-radiation to each node's radiate_to)."""
        root_stream = self.stage_stream(seed, "backbone")
        tree = Tree(seed=seed)
        if self.GENERATOR is not None:
            tree.meta["generator"] = self.GENERATOR
        if self.STAMP_COMMIT:
            from exp.artifacts import current_commit
            tree.meta["commit"] = current_commit()  # provenance stamp
        kingdom = Node(path="k1", rank=Rank.KINGDOM, parent=None,
                       sid=self._sid(root_stream.child("k1")),
                       flags=list(self.KINGDOM_FLAGS))
        kingdom.radiate = RADIATE_DEFAULT.get(Rank.KINGDOM, RADIATE_NEVER)
        tree.add(kingdom)

        # phyla in class-table order (content order is authored); each
        # phylum carries one class node per authored class (real classes
        # group several plans — flora classes.toml; fauna stays one
        # class per plan).
        groups = self.class_groups(pack)
        pins_by_preset: dict[str, list] = {}
        for pin in pack.pins:
            pins_by_preset.setdefault(pin.get("preset"), []).append(pin)

        for pi, (phylum, classes) in enumerate(groups.items(), 1):
            ppath = f"k1.p{pi}"
            phylum_plans = [pack.registry.plans[pid]
                            for _, plans in classes for pid in plans]
            pnode = Node(path=ppath, rank=Rank.PHYLUM, parent="k1",
                         sid=self._sid(root_stream.child(ppath)),
                         flags=self.phylum_flags(phylum_plans))
            pnode.radiate = RADIATE_DEFAULT.get(Rank.PHYLUM, RADIATE_NEVER)
            binomial = self.phylum_binomial(phylum)
            if binomial is not None:
                pnode.name.binomial = binomial
            tree.add(pnode)
            for ci, (class_name, plans) in enumerate(classes, 1):
                cpath = f"{ppath}.c{ci}"
                cnode = Node(path=cpath, rank=Rank.CLASS, parent=ppath,
                             sid=self._sid(root_stream.child(cpath)),
                             plan=plans[0])
                cnode.name.binomial = class_name  # pre-committed (nomenclature skips)
                cnode.radiate = RADIATE_DEFAULT.get(Rank.CLASS, RADIATE_NEVER)
                cnode.radiate_to = RADIATE_TO_DEFAULT.get(Rank.CLASS)
                tree.add(cnode)
                presets = sorted(pid for pid, p in pack.presets.items()
                                 if p["preset"]["plan"] in plans)
                for oi, pid in enumerate(presets, 1):
                    self._build_order(tree, root_stream, pack, cpath, oi,
                                      pid, pins_by_preset.get(pid, []))
        # derived axes are a pure function of the committed record — one
        # pass at the end (rounds re-run it after their own evolves)
        self.derive_tree(tree.nodes.values(), pack)
        return tree

    def _build_order(self, tree, root_stream, pack, cpath: str,
                     oi: int, preset_id: str, pins: list) -> None:
        opath = f"{cpath}.o{oi}"
        preset = pack.presets[preset_id]
        o_axes, o_generics = self.preset_record(pack, preset)
        order = Node(path=opath, rank=Rank.ORDER, parent=cpath,
                     sid=self._sid(root_stream.child(opath)),
                     plan=preset["preset"]["plan"], preset=preset_id,
                     axes=o_axes, generics=o_generics)
        self.gen_time(order, 1.0)
        ostream = root_stream.child(opath)
        order_pin = next((p for p in pins
                          if p.get("rank", "species") == "order"), None)
        order_radiation = 0
        if order_pin:
            self._apply_pin(order, pack, order_pin, ostream)
            order_radiation = order_pin.get("radiation", 0)
        order.radiate = self._radiate_flag(order, order_pin)
        order.radiate_to = self._radiate_to(order, order_pin)
        tree.add(order)
        fam_pins = [p for p in pins if p.get("rank") == "family"]
        genus_pins = [p for p in pins if p.get("rank") == "genus"]
        # species pins with parent_pin are hosted inside that genus pin's
        # clade; the rest group by AUTHORED BINOMIAL GENUS — Quercus-
        # hosted species anchor a genus named Quercus and never sit
        # beside an unrelated pin in one composed genus (the K13 seals-
        # beside-anteaters ruling).
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
        # radiation), then one per family pin. Created only if the order
        # pre-radiates (the skeleton); the family's own radiate decides
        # whether genera follow pre or post.
        families: list[tuple[str, dict | None]] = [(None, None)]
        families += [(p["label"], p) for p in fam_pins]

        if not self._is_pre(order.radiate):
            return
        for fi, (_, fam_pin) in enumerate(families, 1):
            self._build_family(tree, ostream, pack, order, fi, fam_pin,
                               genus_pins if fi == 1 else [],
                               loose if fi == 1 else [],
                               list(by_genus.items()) if fi == 1 else [],
                               order_radiation if fi == 1 else 0,
                               hosted if fi == 1 else {},
                               parent_rt=order.radiate_to)

    def _family_streams(self, ostream, fi: int):
        fam_stream = ostream.child(f"f{fi}")
        rate = rate_multiplier(fam_stream.child("rate"))
        rdir = 1.0 if fam_stream.child("rdir").bernoulli(0.5, 0) else -1.0
        return fam_stream, rate, rdir

    def _build_family(self, tree, ostream, pack, order: Node, fi: int,
                      fam_pin, genus_pins, loose, pin_genera,
                      order_radiation: int, hosted,
                      parent_rt: Rank | None = None) -> None:
        fam_stream, rate, rdir = self._family_streams(ostream, fi)
        fpath = f"{order.path}.f{fi}"
        # drift-and-commit (user ruling): children drift from the
        # parent's committed record — NO convergence to far-back clade
        # anchors, and clade ranks carry no convergence requirements of
        # their own.
        family = self._evolve_edge(order, pack, fam_stream.child("node"),
                                   self._dg(fam_stream, DG_ORDER_MEDIAN),
                                   fpath, rate, rdir, Rank.FAMILY)
        radiation = 0
        if fam_pin:
            self._apply_pin(family, pack, fam_pin, fam_stream)
            radiation = fam_pin.get("radiation", 0)
        if fi == 1:
            radiation = order_radiation
        # generated families (children of the order's pre pass): terminal
        # at the order's radiate_to -> post; intermediate -> pre with the
        # propagated chain target.
        if fam_pin is None:
            if parent_rt is not None and parent_rt > Rank.FAMILY:
                family.radiate = RADIATE_PRE
                family.radiate_to = parent_rt
            else:
                family.radiate = RADIATE_POST
                family.radiate_to = None
        else:
            family.radiate = self._radiate_flag(family, fam_pin)
            family.radiate_to = self._radiate_to(family, fam_pin)
        tree.add(family)
        # genera: PINNED genera (genus pins + binomial-anchored groups +
        # the default g1 hosting loose species pins) are authored and
        # always created; the GENERATED spread genera (radiation shares
        # + background) exist only if the family pre-radiates to genus.
        pre_genus = self._is_pre(family.radiate) \
            and family.radiate_to is not None \
            and family.radiate_to >= Rank.GENUS
        if pre_genus and radiation:
            count = self._radiation_count(fam_stream.child("rad"),
                                          radiation)
            n_spread = max(1, round(math.sqrt(count)))
            per_genus = [count // n_spread] * n_spread
            for i in range(count % n_spread):
                per_genus[i] += 1
        else:
            n_spread, per_genus = 0, []

        genera: list[tuple[dict | None, int, str | None, list]] = []
        if loose or per_genus:
            genera.append((None, per_genus[0] if per_genus else 0,
                           None, loose))
        genera += [(p, p.get("radiation", 0), None,
                    hosted.get(p["label"], [])) for p in genus_pins]
        genera += [(None, 0, gname, grp) for gname, grp in pin_genera]
        if pre_genus:
            genera += [(None, per_genus[i], None, [])
                       for i in range(1, n_spread)]

        bg = (self.BG_RADIATION_LO + fam_stream.child("bg").randrange(
            self.BG_RADIATION_HI - self.BG_RADIATION_LO + 1, 0)) \
            if (fi == 1 and pre_genus) else 0

        for gi, (gen_pin, gen_radiation, gname, gspecies) in \
                enumerate(genera, 1):
            self._build_genus(tree, fam_stream, pack, family, gi, gen_pin,
                              gen_radiation, rate, rdir, gspecies,
                              bg if gi == 1 else 0, name_hint=gname,
                              parent_rt=family.radiate_to)

    def _build_genus(self, tree, fam_stream, pack, family: Node, gi: int,
                     gen_pin, radiation: int, rate: float, rdir: float,
                     species_pins: list, background: int,
                     name_hint: str | None = None,
                     parent_rt: Rank | None = None) -> None:
        gen_stream = fam_stream.child(f"g{gi}")
        gpath = f"{family.path}.g{gi}"
        genus = self._evolve_edge(family, pack, gen_stream.child("node"),
                                  self._dg(gen_stream, DG_FAMILY_MEDIAN),
                                  gpath, rate, rdir, Rank.GENUS)
        drift: dict = {}
        if gen_pin:
            self._apply_pin(genus, pack, gen_pin, gen_stream)
            drift = gen_pin.get("drift", {})
        else:
            if name_hint:
                # binomial-anchored genus (from its pinned species): the
                # name is committed NOW so nomenclature never composes
                # over it (Achillea millefolium must sit under Achillea,
                # not under a composed Veladra).
                genus.name.binomial = name_hint
            if species_pins:
                # drift origin (user ruling): a genus hosting a pin
                # takes the pin's record as its local drift reference
                # when the file offers no genus-rank metadata.
                axes, generics = self.merge_pin(pack, species_pins[0])
                genus.axes = dict(axes)
                genus.generics = dict(generics)
                self.gen_time(genus, rate)
        # generated genera (children of a family pre pass): terminal at
        # the family's radiate_to -> post; intermediate -> pre.
        if gen_pin is None:
            if parent_rt is not None and parent_rt > Rank.GENUS:
                genus.radiate = RADIATE_PRE
                genus.radiate_to = parent_rt
            else:
                genus.radiate = RADIATE_POST
                genus.radiate_to = None
        else:
            genus.radiate = self._radiate_flag(genus, gen_pin)
            genus.radiate_to = self._radiate_to(genus, gen_pin)
        tree.add(genus)

        # species: pinned species are byte-exact commits and exist
        # regardless of radiation; GENERATED species (radiation +
        # relatives + background) happen only if the genus pre-radiates
        # to species.
        si = 0
        for pin in species_pins:  # pinned species: byte-exact commits
            si += 1
            spath = f"{gpath}.s{si}"
            sstream = gen_stream.child(f"s{si}")
            species = Node(path=spath, rank=Rank.SPECIES, parent=gpath,
                           sid=self._sid(sstream), plan=genus.plan,
                           preset=genus.preset, g=genus.g +
                           self._dg(sstream, DG_GENUS_MEDIAN))
            self._apply_pin(species, pack, pin, sstream)
            species.radiate = RADIATE_DEFAULT.get(Rank.SPECIES,
                                                  RADIATE_NEVER)
            self.gen_time(species, rate)
            tree.add(species)
        if not self._is_pre(genus.radiate) \
                or genus.radiate_to is None \
                or genus.radiate_to < Rank.SPECIES:
            return

        n_species = background
        if radiation:
            n_species += self._radiation_count(gen_stream.child("rad"),
                                               radiation)
        n_rel = 0
        if species_pins:
            n_rel = (RELATIVES_LO + gen_stream.child("rel").randrange(
                RELATIVES_HI - RELATIVES_LO + 1, 0))
        for _ in range(n_species + n_rel):  # generated radiation + relatives
            si += 1
            spath = f"{gpath}.s{si}"
            sstream = gen_stream.child(f"s{si}")
            species = self._evolve_edge(genus, pack, sstream,
                                        self._dg(sstream, DG_GENUS_MEDIAN),
                                        spath, rate, rdir, Rank.SPECIES)
            species.radiate = RADIATE_DEFAULT.get(Rank.SPECIES,
                                                  RADIATE_NEVER)
            if drift:
                self._apply_drift(species, pack, drift)
            tree.add(species)
