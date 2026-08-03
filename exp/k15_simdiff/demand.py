"""K15 demand function (0032) — post-radiate creates children of a TYPE.

The demand function is the post-sim creation mechanism: given a type
(the shared vocabulary — body plan/layer + defining features + stress
tolerance profile), a magnitude (the count target), and post-eligible
hosts to attach under, it creates ~magnitude children and returns them
as a STAGING SET (the caller commits them into k15's store).

RANK-AWARE creation (0034, owner-settled 2026-08-03): demand fills the
rank being filled, taxonomically complete —
- GENUS host: ~magnitude SPECIES under it (the bundle-demand shape);
- FAMILY host: magnitude GENERA under it, then species under each
  created genus (the radiation-factor idiom per genus). Orders and
  anything higher are refused ("up to families, not orders" — 0032
  bounds the CREATED rank, not the host rank).
Created genera are TERMINAL (radiate never — they are the fill, not a
source of further post draws), carry deterministic k13-composed names
(the treebuilder's radiated-genus naming idiom) and the treebuilder's
genus-edge g increment.

Trait generation (owner-approved 2026-08-02):
- defining features: deterministic draws from feature POOLS (a value
  that is a list draws one entry) + a small seeded jitter on scalars;
- survival traits: the envelope's stress tolerance profile — the axes
  the sim's stress interface consumes (req_flora/stress_adapter), i.e.
  the stress -> provenance -> traits reuse;
- plan/layer committed on the node.

A demand result IS a lineage — where it attaches is not the sim's
concern. Determinism: every draw from the passed pinned stream.
"""

from __future__ import annotations

import math

from exp.k13_treegen.flora.naming import PLAN_SUFFIX_GRADE
from exp.k13_treegen.forces import gen_time_years
from exp.k13_treegen.model import Node, Rank
from exp.k13_treegen.nomenclature import _compose_genus
from exp.k13_treegen.treebuilder import (
    CAP_HEADROOM, CAP_ONSET, DECODE_MEDIAN, DG_FAMILY_MEDIAN, DG_SIGMA,
    RADIATION_TAIL_SIGMA)

# a "try to match" scatter around the magnitude (the dollar-bill ladder
# for bundles, a continuous factor for the default completion).
MAGNITUDE_SIGMA = 0.3
# scalar jitter for the generated daughters (variants of the envelope).
DAUGHTER_JITTER = 0.02


def _sid(stream) -> str:
    return f"{stream.u64(0):016x}"


def soft_cap(x: float) -> float:
    """The far-tail soft cap (same shape as the treebuilder's): values
    above CAP_ONSET squash toward the asymptote, harder than a log."""
    if x <= CAP_ONSET:
        return x
    return CAP_ONSET + CAP_HEADROOM * math.tanh(
        (x - CAP_ONSET) / CAP_HEADROOM)


def decode_factor(stream) -> float:
    """A generated child's own radiation factor (0032): independent, on
    a 'few to very many' log scale, soft-capped (same as the
    treebuilder's _decode_factor)."""
    return soft_cap(DECODE_MEDIAN * math.exp(RADIATION_TAIL_SIGMA
                                             * stream.normal(0)))


def _draw(value, stream, clock: int):
    """A defining feature: a POOL (list) draws one entry; a single value
    passes through."""
    if isinstance(value, list) and value:
        return value[stream.randrange(len(value), clock, 0)]
    return value


def _daughter_axes(base: dict, overrides: dict, stream) -> dict:
    """The daughter's axes: the type's full base record, overlaid with
    the envelope's defining features + tolerances, pools drawn, scalars
    jittered (EXCEPT the stress-interface tolerance axes — those are the
    survival profile, copied from the envelope)."""
    out = dict(base)
    j = stream.child("jit")
    no_jitter = {"drought_tolerance", "waterlogging_tolerance",
                 "salinity_tolerance", "ph_tolerance",
                 "fertility_requirement", "growing_season_req"}
    for i, (ax, v) in enumerate(sorted(overrides.items())):
        if ax in ("plan", "layer"):
            out[ax] = v
            continue
        drawn = _draw(v, stream.child(f"f{ax}"), 0)
        if isinstance(drawn, (int, float)) and not isinstance(drawn, bool) \
                and ax not in ("height_m",) and ax not in no_jitter:
            drawn = drawn * (1.0 + DAUGHTER_JITTER * j.normal(i))
        out[ax] = drawn
    return out


def _next_index(host: Node, tree_nodes: dict,
                rank: Rank = Rank.SPECIES) -> int:
    """The next child index (1-based, sorted by path) of *rank* under
    *host* — the genus index within a family, the species index within a
    genus (default: species, the genus-host demand shape)."""
    n = 1
    for child in tree_nodes.values():
        if child.parent == host.path and child.rank is rank:
            n += 1
    return n


def _committed_genus_names(tree_nodes: dict) -> set[str]:
    """The committed binomials' genus parts — the 'used' seed the k13
    naming idiom redraws against (a demand-created genus must not
    collide with a committed name)."""
    return {n.name.binomial.split()[0] for n in tree_nodes.values()
            if n.name.binomial}


def _set_gen_time(node: Node) -> None:
    """gen_time from the size axis (the flora idiom — orders and evolved
    genera get it from post_evolve; demand children from height)."""
    h = node.axes.get("height_m")
    if isinstance(h, (int, float)) and h > 0:
        from exp.k13_treegen.flora.backbone import (
            GEN_TIME_COEFF, GEN_TIME_EXP)
        node.gen_time = gen_time_years(float(h), 1.0,
                                       coeff=GEN_TIME_COEFF,
                                       exponent=GEN_TIME_EXP)


def _species_node(host: Node, spath: str, sstream, type_spec: dict,
                  base: dict, overrides: dict, plan) -> Node:
    """One demand species under *host* (the genus-host record shape):
    type record via _daughter_axes, the species-edge g increment, radiate
    never, gen_time from height."""
    axes = _daughter_axes(base, overrides, sstream)
    if plan is not None:
        axes.setdefault("layer", type_spec.get("layer"))
    g = host.g + 60.0 * math.exp(0.3 * sstream.normal(0))
    species = Node(path=spath, rank=Rank.SPECIES, parent=host.path,
                   sid=_sid(sstream), plan=plan or host.plan,
                   preset=host.preset, g=g, axes=axes,
                   radiate="never")
    _set_gen_time(species)
    return species


def _demand_family(pack, type_spec: dict, plan, base: dict,
                   overrides: dict, magnitude: float, hosts: list,
                   stream, tree_nodes: dict, next_idx: dict,
                   used: set[str]) -> list[Node]:
    """FAMILY host: fill the rank being filled — *magnitude* genera
    under the family, then species under each created genus (the
    radiation-factor idiom per genus: heavy-tailed decode, soft-capped).
    Created genera are terminal (radiate never — the fill is complete,
    no further post draws ride them), carry k13-composed names (the
    treebuilder's radiated-genus naming idiom) and the genus-edge g
    increment (DG_FAMILY_MEDIAN * exp(DG_SIGMA * z))."""
    G = max(1, round(magnitude))
    out: list[Node] = []
    for k in range(G):
        host = hosts[k % len(hosts)]
        idx = next_idx.get(host.path,
                           _next_index(host, tree_nodes, Rank.GENUS))
        next_idx[host.path] = idx + 1
        gstream = stream.child(f"g{k}")
        gpath = f"{host.path}.g{idx}"
        # this genus's own radiation factor -> its species count (0032:
        # a generated child's 'few to very many' decode, heavy-tailed
        # and soft-capped — same idiom as the treebuilder)
        n_species = max(1, round(decode_factor(gstream.child("factor"))))
        g_axes = _daughter_axes(base, overrides, gstream)
        if plan is not None:
            g_axes.setdefault("layer", type_spec.get("layer"))
        # k13 naming idiom for radiated genera: composed (seeded style
        # mix), redrawn on collision with committed names
        name, _ = _compose_genus(gstream.child("name"), pack,
                                 plan or host.plan, used,
                                 plan_grades=PLAN_SUFFIX_GRADE)
        used.add(name)
        g = host.g + DG_FAMILY_MEDIAN * math.exp(DG_SIGMA
                                                 * gstream.normal(0))
        genus = Node(path=gpath, rank=Rank.GENUS, parent=host.path,
                     sid=_sid(gstream), plan=plan or host.plan,
                     preset=host.preset, g=g, axes=g_axes,
                     radiate="never")   # the fill is terminal
        genus.name.binomial = name
        _set_gen_time(genus)
        out.append(genus)
        for s in range(1, n_species + 1):
            sidx = next_idx.get(gpath, _next_index(genus, tree_nodes,
                                                   Rank.SPECIES))
            next_idx[gpath] = sidx + 1
            out.append(_species_node(genus, f"{gpath}.s{sidx}",
                                     gstream.child(f"s{s}"),
                                     type_spec, base, overrides, plan))
    return out


def demand(pack, type_spec: dict, magnitude: float, hosts: list,
           stream, tree_nodes: dict,
           next_idx: dict[str, int] | None = None,
           used: set[str] | None = None) -> list[Node]:
    """Create children of *type_spec* under *hosts* at the RANK BEING
    FILLED (0034): a GENUS host gets ~magnitude species (the bundle-
    demand shape — byte-compat contract); a FAMILY host gets magnitude
    genera + species per genus. Orders and anything higher are refused.

    *type_spec*: the shared-vocabulary envelope — plan/layer + defining
    features (values or pools) + the stress tolerance profile (the axes
    the stress adapter reads); optional ``_base`` = the plan's full
    record the overrides sit on. *hosts*: post-eligible nodes to attach
    under (anchor clades for bundles; the node itself for the default
    completion). *next_idx*: a SHARED per-host next-index map across
    demand calls, tracking BOTH ranks — the genus index within a family
    AND the species index within a genus (the staging set isn't in the
    tree yet, so indices must be tracked here — otherwise the default
    completion and a bundle demand on the same host, or two demands on
    one family, collide). *used*: the shared set of committed genus
    names the k13 naming idiom redraws against (deterministic across
    demand calls in one pass). Returns the staging set.
    """
    if magnitude <= 0 or not hosts:
        return []
    rank = hosts[0].rank
    assert all(h.rank is rank for h in hosts), \
        "demand hosts must all share one rank"
    # creation respects post permissions; demand NEVER creates orders or
    # anything higher ("up to families, not orders" — 0032 bounds the
    # CREATED rank). Subspecies are sim-side (0010), not demand children.
    assert rank in (Rank.FAMILY, Rank.GENUS), \
        f"demand cannot create below rank {rank.name}"
    plan = type_spec.get("plan")
    base = type_spec.get("_base", {})
    overrides = {k: v for k, v in type_spec.items()
                 if k not in ("_base", "plan", "layer")}
    next_idx = next_idx if next_idx is not None else {}
    if used is None:
        used = _committed_genus_names(tree_nodes)
    if rank is Rank.FAMILY:
        return _demand_family(pack, type_spec, plan, base, overrides,
                              magnitude, hosts, stream, tree_nodes,
                              next_idx, used)
    # genus host: ~magnitude species (the bundle-demand shape) — the
    # existing byte-compat contract (draws unchanged)
    z = stream.normal(0)
    count = max(1, round(magnitude * math.exp(MAGNITUDE_SIGMA * z)))
    out: list[Node] = []
    # distribute the count round-robin over the hosts (pinned order)
    for k in range(count):
        host = hosts[k % len(hosts)]
        idx = next_idx.get(host.path, _next_index(host, tree_nodes))
        next_idx[host.path] = idx + 1
        sstream = stream.child(f"s{k}")
        out.append(_species_node(host, f"{host.path}.s{idx}", sstream,
                                 type_spec, base, overrides, plan))
    return out
