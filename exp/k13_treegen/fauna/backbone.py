"""M7 — backbone: the blind tree-build (docs/m7-backbone.md).

Thin wrapper over the shared TreeBuilder (exp/k13_treegen/treebuilder.py)
with the ANIMALIA config — consolidated 2026-08-02 (0032 prereq,
absorbed from 0006); behavior byte-identical to the previous standalone
backbone. Assembles the committed Tree from the content pack: kingdom
root animalia (plantae hook reserved) -> phyla (authored frame map) ->
one class per plan -> one order per preset -> families/genera/species
evolved with M5/M6. Pins placed at authored ranks, byte-exact;
radiations seeded around authored targets. World-blind: benign Condition
throughout.
"""

from __future__ import annotations

from exp.k13_treegen.fauna.content import ContentPack, merged_pin, merged_preset
from exp.k13_treegen.fauna.derive import derive_tree
from exp.k13_treegen.forces import gen_time_years
from exp.k13_treegen.model import Tree
from exp.k13_treegen.fauna.seeding import stage_stream
from exp.k13_treegen.treebuilder import PIN_JITTER_Z, TreeBuilder


class _AnimaliaBuilder(TreeBuilder):
    GENERATOR = None            # model default is k13_treegen
    STAMP_COMMIT = False
    KINGDOM_FLAGS = ("animalia",)
    BG_RADIATION_LO = 2
    BG_RADIATION_HI = 4

    def stage_stream(self, seed, *path):
        return stage_stream(seed, *path)

    def merge_pin(self, pack, pin):
        return merged_pin(pack, pin)

    def preset_record(self, pack, preset):
        return merged_preset(pack, preset)

    def derive_tree(self, nodes, pack):
        derive_tree(nodes, pack)

    def gen_time(self, node, rate) -> None:
        mass = node.axes.get("body_mass")
        if isinstance(mass, (int, float)) and mass > 0:
            node.gen_time = gen_time_years(float(mass), rate)


_BUILDER = _AnimaliaBuilder()


def build(seed: int, pack: ContentPack) -> Tree:
    """Build the committed tree for *seed*."""
    return _BUILDER.build(seed, pack)
