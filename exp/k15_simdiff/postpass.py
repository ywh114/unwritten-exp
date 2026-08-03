"""K15 post pass (0032) — ONE single filling pass at the end.

After the sim, the post pass completes the tree on k15's OWN store:
1. DEFAULT COMPLETION: every post-eligible node (radiate in (post,
   both) — the stub genera, the generated genera under shallow pre
   orders, the authored stubs, the post families) fills the rank being
   filled per the decoded factor (0034): a FAMILY radiates GENERA then
   species per genus, a GENUS its species — the "children of shallow
   pre nodes are allowed to radiate during post" rule.
2. BUNDLE DEMANDS: every bundle issues a demand — its envelope + a
   ladder magnitude + hosts = its anchor clades present in the tree.

The pass returns a STAGING SET; the caller commits it into the tree
(k15's store). k13 content stays pristine. Determinism: all draws from
pinned k15.post / k15.demand streams, hosts processed in sorted order.
"""

from __future__ import annotations

from kernel.hashrng import Stream
from exp.k13_treegen.flora.content import merged_preset
from exp.k13_treegen.model import Rank
from exp.k15_simdiff.demand import (
    _committed_genus_names, demand, decode_factor)

# the ladder default for bundle demands (dollar-bill amounts, 0032).
# 0027's differentiation will size per-bundle from the sim outcome; this
# is the mechanism's default.
BUNDLE_MAGNITUDE = 50


def _post_eligible(tree) -> list:
    return sorted((n for n in tree.nodes.values()
                   if n.radiate in ("post", "pre-and-post")),
                  key=lambda n: n.path)


def _node_envelope(node) -> dict:
    """The default-completion type: the node's own full record (plan +
    axes) — its daughters are variants of it."""
    spec = {"plan": node.plan, "layer": node.axes.get("layer")}
    spec.update(node.axes)
    return spec


def _bundle_spec(pack, bundle) -> dict:
    """The bundle demand type: the plan's full base record overlaid with
    the bundle's envelope (defining features + stress tolerances)."""
    spec = {"plan": bundle["plan"], "layer": bundle["layer"],
            "_base": _bundle_base(pack, bundle)}
    spec.update(bundle["envelope"])
    return spec


def _bundle_base(pack, bundle) -> dict:
    """The plan's base axes (the first preset of the bundle's plan) the
    envelope overrides sit on — so the daughters carry the plan's full
    axis set."""
    plan = bundle["plan"]
    pid = next((pid for pid in pack.presets
                if pack.presets[pid]["preset"]["plan"] == plan), None)
    if pid is None:
        return {}
    axes, _ = merged_preset(pack, pack.presets[pid])
    return dict(axes)


def _anchor_hosts(tree, bundle) -> list:
    """The bundle's anchor genera that exist in the tree and are
    POST-eligible (the stub genera; a pre'd genus is stable against
    post-draws), sorted by path."""
    anchors = set(bundle.get("anchor_genera", []))
    hosts = [n for n in tree.nodes.values()
             if n.rank is Rank.GENUS and n.name.binomial in anchors
             and n.radiate in ("post", "pre-and-post")]
    return sorted(hosts, key=lambda n: n.path)


def run_post(tree, pack, seed: int) -> list:
    """The single post filling pass. Returns the staging set (uncommitted
    genera + species nodes); the caller adds them to the tree."""
    stream = Stream(seed, "k15.post")
    staging: list = []
    # shared across demands (the staging set isn't in the tree yet): the
    # per-host next-index map (genus index per family, species index per
    # genus — 0034) and the k13-composed genus names already used
    next_idx: dict[str, int] = {}
    used: set[str] = _committed_genus_names(tree.nodes)
    # 1. default completion — post-eligible nodes radiate per factor
    for i, node in enumerate(_post_eligible(tree)):
        factor = decode_factor(stream.child(f"fill{i}"))
        spec = _node_envelope(node)
        staging += demand(pack, spec, factor, [node],
                          stream.child(f"fill{i}d"), tree.nodes, next_idx,
                          used)
    # 2. bundle demands
    for j, bundle in enumerate(pack.bundles):
        spec = _bundle_spec(pack, bundle)
        hosts = _anchor_hosts(tree, bundle)
        if not hosts:
            continue   # no anchors stubbed yet (a content follow-up)
        staging += demand(pack, spec, BUNDLE_MAGNITUDE, hosts,
                          stream.child(f"bundle{j}"), tree.nodes, next_idx,
                          used)
    return staging
