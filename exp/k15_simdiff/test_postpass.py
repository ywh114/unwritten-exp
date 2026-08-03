"""K15 post pass (0032) — the demand function + single filling pass.

The post pass runs AFTER the sim: the default completion fills the
post-eligible nodes (stub genera, generated genera) per the decoded
factor, and each bundle issues a demand (envelope + magnitude + anchor
clades). It returns a STAGING set the caller commits into k15's store.
RANK-AWARE creation (0034): a post-eligible FAMILY fills with genera +
species (the rank being filled is GENUS); a GENUS still fills with
species — byte-identical to the pre-0034 genus-host shape (pinned
digest below).
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from kernel.hashrng import Stream

import pytest

from exp.k13_treegen.flora.backbone import build as build_backbone
from exp.k13_treegen.flora.content import load_content
from exp.k13_treegen.model import Rank
from exp.k15_simdiff.demand import demand, decode_factor, soft_cap
from exp.k15_simdiff.postpass import run_post

FLORA = Path("exp/k13_treegen/content/flora")


def _digest(nodes) -> str:
    """SHA-256 over (path, sid, sorted axes) — the byte-compat pin."""
    h = hashlib.sha256()
    for n in sorted(nodes, key=lambda n: n.path):
        h.update(json.dumps([n.path, n.sid, sorted(n.axes.items())],
                            sort_keys=True).encode())
    return h.hexdigest()


# the pre-0034 genus-host contract, captured from HEAD (see
# tmp/0034_head/digest_probe.py): species under PRE-EXISTING genera —
# the family-fill species (parents = demand-created genera) and the
# old family-attached species (the 0034 bug being fixed) are excluded.
GENUS_HOST_DIGEST = (
    "a3909e272e72c0ee014bd718dc98f53f68bcb50de5a085204ade703585468088")


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
    """Same seed ⇒ byte-stable staging set (paths, sids, ranks, and the
    0034 composed genus names all identical)."""
    a = run_post(tree, pack, 1)
    b = run_post(tree, pack, 1)
    assert [n.path for n in a] == [n.path for n in b]
    assert [n.sid for n in a] == [n.sid for n in b]
    assert [n.rank for n in a] == [n.rank for n in b]
    assert [n.name.binomial for n in a] == [n.name.binomial for n in b]


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


# ── 0034 rank-aware creation: families fill with genera + species ────────


def test_genus_host_demand_byte_identical(tree, pack):
    """Genus-host (bundle + genus default-completion) demands are
    byte-identical to the pre-0034 implementation — pinned digest over
    (path, sid, sorted axes) of the species staged under PRE-EXISTING
    genera (captured from HEAD via tmp/0034_head/digest_probe.py)."""
    staging = run_post(tree, pack, 1)
    genus_host = [n for n in staging
                  if n.rank is Rank.SPECIES
                  and n.parent in tree.nodes
                  and tree.nodes[n.parent].rank is Rank.GENUS]
    assert genus_host, "expected genus-host species in the staging set"
    assert _digest(genus_host) == GENUS_HOST_DIGEST


def test_family_fill_shape(tree, pack):
    """A post-eligible family host fills with genera (rank GENUS,
    parent = family path, named, g sane, radiate never), each carrying
    >= 1 species (rank SPECIES, parent = genus path)."""
    staging = run_post(tree, pack, 1)
    created = [n for n in staging if n.rank is Rank.GENUS]
    assert created, "expected demand-created genera (family fill)"
    fam_paths = {n.path for n in tree.nodes.values()
                 if n.rank is Rank.FAMILY}
    assert all(n.parent in fam_paths for n in created)
    assert all(n.radiate == "never" for n in created)   # the fill is terminal
    assert all(n.name.binomial for n in created)        # k13-composed names
    fam_g = {n.path: n.g for n in tree.nodes.values()
             if n.rank is Rank.FAMILY}
    assert all(n.g > fam_g[n.parent] for n in created)
    species = [n for n in staging
               if n.rank is Rank.SPECIES
               and n.parent in {c.path for c in created}]
    assert {s.parent for s in species} == {c.path for c in created}
    assert all(s.radiate == "never" for s in species)
    assert all(s.g > 0.0 for s in species)


def test_family_demand_magnitude_is_genus_count(tree, pack):
    """Magnitude = the count AT the filled rank: a family host with
    magnitude G yields exactly G genera, each with its own decoded
    species count (>= 1, the radiation-factor idiom)."""
    host = next(n for n in tree.nodes.values() if n.rank is Rank.FAMILY)
    spec = dict(host.axes)
    spec.update({"plan": host.plan, "layer": host.axes.get("layer")})
    out = demand(pack, spec, 5.0, [host], Stream(1, "k15.demand.test"),
                 tree.nodes)
    genera = [n for n in out if n.rank is Rank.GENUS]
    assert len(genera) == 5
    assert all(n.parent == host.path for n in genera)
    assert len({n.path for n in genera}) == 5        # distinct indices
    for g in genera:
        kids = [n for n in out
                if n.rank is Rank.SPECIES and n.parent == g.path]
        assert kids, f"created genus {g.path} carries no species"


def test_next_idx_family_collision(tree, pack):
    """Two demands on the same family (shared next_idx) never collide —
    the per-family genus index advances across calls."""
    host = next(n for n in tree.nodes.values() if n.rank is Rank.FAMILY)
    spec = dict(host.axes)
    spec.update({"plan": host.plan, "layer": host.axes.get("layer")})
    next_idx: dict = {}
    a = demand(pack, spec, 3.0, [host], Stream(1, "k15.demand.test"),
               tree.nodes, next_idx)
    b = demand(pack, spec, 3.0, [host], Stream(2, "k15.demand.test"),
               tree.nodes, next_idx)
    paths = [n.path for n in a + b]
    assert len(paths) == len(set(paths)), "duplicate staging paths"
    genera = [n for n in a + b if n.rank is Rank.GENUS]
    assert len(genera) == 6                          # 3 + 3, all distinct


def test_next_idx_family_and_genus(tree, pack):
    """A family demand and a demand on one of its PRE-EXISTING genera
    share the next_idx map without colliding (a family path tracks the
    genus index; a genus path the species index)."""
    fam = next(n for n in tree.nodes.values() if n.rank is Rank.FAMILY)
    genus_host = next((c for c in tree.nodes.values()
                       if c.parent == fam.path
                       and c.rank is Rank.GENUS), None)
    if genus_host is None:
        pytest.skip("no pre-existing genus under the first family")
    spec = dict(fam.axes)
    spec.update({"plan": fam.plan, "layer": fam.axes.get("layer")})
    next_idx: dict = {}
    a = demand(pack, spec, 3.0, [fam], Stream(1, "k15.demand.test"),
               tree.nodes, next_idx)
    b = demand(pack, spec, 5.0, [genus_host],
               Stream(2, "k15.demand.test"), tree.nodes, next_idx)
    paths = [n.path for n in a + b]
    assert len(paths) == len(set(paths)), "duplicate staging paths"
    assert all(n.rank is Rank.SPECIES for n in b)


def test_order_host_refused(tree, pack):
    """Demand NEVER creates orders or anything higher: an ORDER host
    asserts ('up to families, not orders' — 0032)."""
    order = next(n for n in tree.nodes.values() if n.rank is Rank.ORDER)
    spec = dict(order.axes)
    spec.update({"plan": order.plan, "layer": order.axes.get("layer")})
    with pytest.raises(AssertionError):
        demand(pack, spec, 5.0, [order], Stream(1, "k15.demand.test"),
               tree.nodes)
