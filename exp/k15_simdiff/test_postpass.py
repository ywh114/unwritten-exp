"""K15 post pass (0032) — the demand function + single filling pass.

The post pass runs AFTER the sim: the default completion fills the
post-eligible nodes (stub genera, generated genera) per the decoded
factor, and each bundle issues a demand (envelope + magnitude + anchor
clades). It returns a STAGING set the caller commits into k15's store.
"""

from __future__ import annotations

import copy
from pathlib import Path

from kernel.hashrng import Stream

import pytest

from exp.k13_treegen.flora.backbone import build as build_backbone
from exp.k13_treegen.flora.content import load_content
from exp.k13_treegen.model import Rank
from exp.k15_simdiff.demand import demand, decode_factor, soft_cap
from exp.k15_simdiff.postpass import run_post

FLORA = Path("exp/k13_treegen/content/flora")


@pytest.fixture(scope="module")
def pack():
    return load_content(FLORA)


@pytest.fixture(scope="module")
def tree(pack):
    return build_backbone(1, pack)


@pytest.fixture(scope="module")
def post_tree(tree, pack):
    """The tree WITH the staging set committed (the post-sim store)."""
    staging = run_post(tree, pack, 1)
    t = copy.deepcopy(tree)
    for n in staging:
        t.add(n)
    return t


def _species(t):
    return [n for n in t.nodes.values() if n.rank is Rank.SPECIES]


def test_post_tree_reaches_flora_scale(post_tree):
    """The default completion + bundle demands push the tree toward the
    ~1k ('on the order of 1k') post-sim scale."""
    n = len(_species(post_tree))
    assert n >= 800, n


def test_default_completion_fills_empty_genera(tree, post_tree):
    """The previously-empty stub genera now carry species (the post
    pass's default completion)."""
    pre_empty = {n.path for n in tree.nodes.values()
                 if n.rank is Rank.GENUS and not any(
                     c.parent == n.path for c in tree.nodes.values())}
    assert pre_empty, "expected empty stub genera in the pre tree"
    for path in pre_empty:
        kids = [c for c in post_tree.nodes.values() if c.parent == path]
        assert kids, f"stub genus {path} still empty after the post pass"


def test_bundle_demand_creates_anchored_daughters(post_tree, pack):
    """A bundle demand creates daughters under its anchor clades, with
    the envelope's stress tolerances (the shared stress-interface axes)."""
    # the reef-stony-corals bundle anchors include Acropora (an authored
    # stub) — its genus should carry bundle daughters
    acro = [n for n in post_tree.nodes.values()
            if n.rank is Rank.GENUS and n.name.binomial == "Acropora"]
    assert acro, "Acropora stub missing from the post tree"
    daughters = [c for c in post_tree.nodes.values()
                 if c.parent == acro[0].path and c.rank is Rank.SPECIES]
    assert daughters
    # the daughters carry the marine envelope's salinity tolerance
    assert all(d.axes.get("salinity_tolerance", 0) >= 0.9 for d in daughters)


def test_determinism(tree, pack):
    """Same seed ⇒ byte-stable staging set (paths + sids identical)."""
    a = run_post(tree, pack, 1)
    b = run_post(tree, pack, 1)
    assert [n.path for n in a] == [n.path for n in b]
    assert [n.sid for n in a] == [n.sid for n in b]


def test_staging_not_committed(tree, pack):
    """The pass returns a staging set; the tree is unchanged until the
    caller commits it."""
    before = sorted(n.path for n in tree.nodes.values())
    staging = run_post(tree, pack, 1)
    assert staging
    after = sorted(n.path for n in tree.nodes.values())
    assert before == after


def test_demand_unit(pack, tree):
    """The demand function directly: creates ~magnitude species under a
    host with the type's traits (a defining pool drawn, tolerances
    copied), deterministic."""
    host = next(n for n in tree.nodes.values() if n.rank is Rank.GENUS)
    spec = dict(host.axes)
    spec.update({"plan": host.plan, "layer": host.axes.get("layer"),
                 "leaf_shape": ["lobed", "entire", "linear"],
                 "salinity_tolerance": 0.9})
    out = demand(pack, spec, 10.0, [host], Stream(1, "k15.demand.test"),
                 tree.nodes)
    assert 5 <= len(out) <= 20, len(out)
    # the defining pool drew one legal value; the tolerance copied
    assert out[0].axes["leaf_shape"] in ("lobed", "entire", "linear")
    assert out[0].axes["salinity_tolerance"] == 0.9
    # deterministic
    out2 = demand(pack, spec, 10.0, [host], Stream(1, "k15.demand.test"),
                  tree.nodes)
    assert [n.path for n in out] == [n.path for n in out2]


def test_soft_cap_and_decode():
    """The far-tail soft cap and the factor decode are bounded (no
    exploding clades)."""
    assert soft_cap(50.0) == 50.0
    assert soft_cap(1e6) <= 500.0          # the asymptote CAP_ONSET+HEADROOM
    assert 0 < decode_factor(Stream(7, "k15.demand.test")) <= 500.0
