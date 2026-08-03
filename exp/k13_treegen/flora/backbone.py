"""Flora backbone: the blind flora tree-build (mirrors K13 M7).

Thin wrapper over the shared TreeBuilder (exp/k13_treegen/treebuilder.py)
with the PLANTAE config — consolidated 2026-08-02 (0032 prereq, absorbed
from 0006); behavior byte-identical to the previous standalone backbone.
All differences from K13's backbone are deliberate and live in the
_PlantaeBuilder hooks below:
- size axis is height_m, so gen_time and the soft envelope key off
  height (ENVELOPE_LOG10/DAMP, same shape as K13's mass envelope);
- evolve runs with couplings=False (flora legality is the flora
  constraint gate, not the fauna M6 rule table) and the flora
  rebindable set (dispersal replaces locomotor);
- background radiation is thinner (BG_RADIATION 1-2): the authored
  genus-pin radiations dominate the census;
- phylum binomials are pre-committed here (the three lines have no
  per-plan class_name to compose from).

Assembles the committed Tree from the content pack: kingdom root plantae
-> phyla (the seed / spore / decomposer lines, grouped by plan.phylum)
-> real classes (classes.toml; 0032) -> one order per preset ->
families/genera/species evolved with the K13 evolve engine (flora
rebind tables, no fauna couplings) + the flora constraint gate + the
height envelope. Pins placed at authored ranks, byte-exact; radiations
seeded around authored targets. World-blind: benign Condition
throughout.
"""

from __future__ import annotations

import math

from exp.k13_treegen.flora.constraints import enforce
from exp.k13_treegen.flora.content import (
    ContentPack, merged_pin, merged_preset)
from exp.k13_treegen.flora.derive import DERIVED_AXES, derive_tree
from exp.k13_treegen.flora.seeding import stage_stream
from exp.k13_treegen.forces import gen_time_years
from exp.k13_treegen.model import Tree
from exp.k13_treegen.treebuilder import PIN_JITTER_Z, TreeBuilder

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
# radiated singleton-tail sizing (0012 ruling 12/14, report §6): per
# order, a heavy-tailed draw around this mean — ~200-250 empty genera
# across the tree's ~34 orders.
STUB_RADIATION_MEAN = 6.0


class _PlantaeBuilder(TreeBuilder):
    GENERATOR = "k13_flora"
    STAMP_COMMIT = True
    KINGDOM_FLAGS = ("plantae",)

    def stage_stream(self, seed, *path):
        return stage_stream(seed, *path)

    def merge_pin(self, pack, pin):
        return merged_pin(pack, pin)

    def preset_record(self, pack, preset):
        return merged_preset(pack, preset)

    def derive_tree(self, nodes, pack):
        derive_tree(nodes, pack)

    def evolve_kwargs(self) -> dict:
        return dict(couplings=False, rebindable=REBINDABLE,
                    unbindable=UNBINDABLE, derived_axes=DERIVED_AXES)

    def post_evolve(self, child, parent, pack, rate) -> None:
        """The height envelope -> the constraint gate (the final word —
        the envelope must run FIRST or it undoes legality snaps; the
        first seed-3 build had buttress snaps at 20 m damped back to
        14 m) -> gen_time."""
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
        self.gen_time(child, rate)

    def gen_time(self, node, rate) -> None:
        h = node.axes.get("height_m")
        if isinstance(h, (int, float)) and h > 0:
            node.gen_time = gen_time_years(float(h), rate,
                                           coeff=GEN_TIME_COEFF,
                                           exponent=GEN_TIME_EXP)

    def phylum_flags(self, plans):
        return sorted({p.frame for p in plans})

    def phylum_binomial(self, phylum):
        return PHYLUM_BINOMIAL.get(phylum, phylum.capitalize())

    def class_groups(self, pack):
        """Real classes from the authored classes.toml table (0032): one
        class node per row, grouping the body plans that fall under it,
        in table order (seed -> spore -> decomposer)."""
        groups: dict[str, list[tuple[str, list[str]]]] = {}
        for cls in pack.classes:
            groups.setdefault(cls["phylum"], []).append(
                (cls["name"], list(cls["plans"])))
        return groups

    def stub_genera(self, pack, plan: str, preset: str) -> list[str]:
        """Authored stub genera for *plan* under *preset* from
        stubs.toml (0012): the empty (unseeded) genus nodes 0027 fills
        post-sim."""
        return [s["name"]["binomial"] for s in pack.stubs
                if s.get("parent") == preset
                and s.get("rank", "genus") == "genus"]

    def radiated_stub_count(self, pack, plan: str, preset: str,
                            stream) -> int:
        """The radiated singleton-tail count for this order: a
        deterministic heavy-tailed draw (report §6 hollow curve — most
        orders a handful of near-empty genera, some many), targeting
        ~200-250 total across the tree. Pinned stream: byte-stable per
        seed."""
        z = stream.child("rad_stubs").normal(0)
        return max(0, round(STUB_RADIATION_MEAN * math.exp(0.5 * z)))


_BUILDER = _PlantaeBuilder()


def build(seed: int, pack: ContentPack) -> Tree:
    """Build the committed tree for *seed*."""
    return _BUILDER.build(seed, pack)
