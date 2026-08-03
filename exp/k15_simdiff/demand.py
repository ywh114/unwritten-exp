"""K15 demand function (0032) — post-radiate creates species of a TYPE.

The demand function is the post-sim creation mechanism: given a type
(the shared vocabulary — body plan/layer + defining features + stress
tolerance profile), a magnitude (the count target), and post-eligible
hosts to attach under, it creates ~magnitude new species and returns
them as a STAGING SET (the caller commits them into k15's store).

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

from exp.k13_treegen.forces import gen_time_years
from exp.k13_treegen.model import Node, Rank
from exp.k13_treegen.treebuilder import (
    CAP_HEADROOM, CAP_ONSET, DECODE_MEDIAN, RADIATION_TAIL_SIGMA)

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


def _next_index(host: Node, tree_nodes: dict) -> int:
    """The next species index under *host* (1-based, sorted by path)."""
    n = 1
    for child in tree_nodes.values():
        if child.parent == host.path and child.rank is Rank.SPECIES:
            n += 1
    return n


def demand(pack, type_spec: dict, magnitude: float, hosts: list,
           stream, tree_nodes: dict,
           next_idx: dict[str, int] | None = None) -> list[Node]:
    """Create ~magnitude species of *type_spec* under *hosts*.

    *type_spec*: the shared-vocabulary envelope — plan/layer + defining
    features (values or pools) + the stress tolerance profile (the axes
    the stress adapter reads); optional ``_base`` = the plan's full
    record the overrides sit on. *hosts*: post-eligible nodes to attach
    under (anchor clades for bundles; the genus itself for the default
    completion). *next_idx*: a SHARED per-host next-species-index map
    across demand calls (the staging set isn't in the tree yet, so
    indices must be tracked here — otherwise the default completion and
    a bundle demand on the same host collide). Returns the staging set.
    """
    if magnitude <= 0 or not hosts:
        return []
    plan = type_spec.get("plan")
    base = type_spec.get("_base", {})
    overrides = {k: v for k, v in type_spec.items()
                 if k not in ("_base", "plan", "layer")}
    z = stream.normal(0)
    count = max(1, round(magnitude * math.exp(MAGNITUDE_SIGMA * z)))
    out: list[Node] = []
    next_idx = next_idx if next_idx is not None else {}
    # distribute the count round-robin over the hosts (pinned order)
    for k in range(count):
        host = hosts[k % len(hosts)]
        idx = next_idx.get(host.path, _next_index(host, tree_nodes))
        next_idx[host.path] = idx + 1
        sstream = stream.child(f"s{k}")
        axes = _daughter_axes(base, overrides, sstream)
        if plan is not None:
            axes.setdefault("layer", type_spec.get("layer"))
        spath = f"{host.path}.s{idx}"
        g = host.g + 60.0 * math.exp(0.3 * sstream.normal(0))
        species = Node(path=spath, rank=Rank.SPECIES, parent=host.path,
                       sid=_sid(sstream), plan=plan or host.plan,
                       preset=host.preset, g=g, axes=axes,
                       radiate="never")
        h = axes.get("height_m")
        if isinstance(h, (int, float)) and h > 0:
            from exp.k13_treegen.flora.backbone import (
                GEN_TIME_COEFF, GEN_TIME_EXP)
            species.gen_time = gen_time_years(float(h), 1.0,
                                              coeff=GEN_TIME_COEFF,
                                              exponent=GEN_TIME_EXP)
        out.append(species)
    return out
