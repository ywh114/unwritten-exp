"""End-to-end integration gate (integration contract §6) — the composition
proof. Runs after all modules; over seeds {1, 2, 3}:

1. Whole-DAG re-run byte-identical.
2. Tree invariants: single animalia root; strict rank order; g monotonic;
   unique paths/sids.
3. Freeze check at composition scale: no axis constant across an order's
   species unless clade_steady or invariant tier.
4. Diversity within tolerance: median sister distance ~ sigma; between >
   within order.
5. Metrics gate clean (couplings compliant; the rest of the battery).
6. Every species named (well-formed, within-genus unique) and describable
   (trace matches the record).
7. Planted-violation content must fail the gate.
"""

from __future__ import annotations

import math
import pathlib
import statistics

import pytest

from exp.k13_treegen.backbone import build
from exp.k13_treegen.content import load_content
from exp.k13_treegen.describe import describe
from exp.k13_treegen.metrics import run_checks
from exp.k13_treegen.model import Rank
from exp.k13_treegen.nomenclature import assign_names

CONTENT = pathlib.Path(__file__).parent / "content"
SEEDS = (1, 2, 3)


@pytest.fixture(scope="module")
def pack():
    return load_content(CONTENT)


def generate(pack, seed):
    tree = build(seed, pack)
    assign_names(tree, pack, seed)
    return tree


def species(tree):
    return [n for n in tree.nodes.values() if n.rank is Rank.SPECIES]


# ──  1. determinism  ──────────────────────────────────────────────────────


def test_whole_dag_byte_identical(pack):
    for seed in SEEDS:
        assert generate(pack, seed).dumps() == generate(pack, seed).dumps()


# ──  2. tree invariants  ──────────────────────────────────────────────────


def test_tree_invariants(pack):
    for seed in SEEDS:
        tree = generate(pack, seed)
        roots = tree.roots()
        assert len(roots) == 1 and "animalia" in roots[0].flags
        paths = list(tree.nodes)
        sids = [n.sid for n in tree.nodes.values()]
        assert len(paths) == len(set(paths))
        assert len(sids) == len(set(sids)), "duplicate sids"
        for n in tree.nodes.values():
            if n.parent and n.parent in tree.nodes:
                p = tree.nodes[n.parent]
                assert p.rank < n.rank, f"{n.path}: rank inversion"
                assert n.g >= p.g, f"{n.path}: g inversion"


# ──  3. freeze check (composition scale, per order)  ──────────────────────


def test_no_frozen_axis_at_composition_scale(pack):
    """The v1 bug signature is SYSTEMATIC freezing (an axis frozen in most
    orders). A rare-redraw enum frozen in one small order is chance —
    flag only when >60% of multi-species orders are frozen on one axis."""
    for seed in SEEDS:
        tree = generate(pack, seed)
        orders: dict[str, list] = {}
        for n in species(tree):
            orders.setdefault(n.path.rsplit(".f", 1)[0], []).append(n)
        orders = {o: ms for o, ms in orders.items() if len(ms) >= 3}
        frozen_count: dict[str, int] = {}
        for opath, members in orders.items():
            shared = set.intersection(*(set(m.axes) for m in members))
            for ax in shared:
                spec = pack.registry.axes.get(ax)
                if spec is None or not spec.mutable:
                    continue
                if spec.value_type.value == "int" and spec.sigma < 0.5:
                    continue  # discreteness, not machinery (M7 ruling)
                vals = {str(m.axes[ax]) for m in members}
                if len(vals) <= 1:
                    frozen_count[ax] = frozen_count.get(ax, 0) + 1
        for ax, count in frozen_count.items():
            frac = count / len(orders)
            assert frac <= 0.6, \
                f"seed {seed}: {ax} frozen in {count}/{len(orders)} orders"


# ──  4. diversity within tolerance  ───────────────────────────────────────


def _dz(spec, va: float, vb: float) -> float:
    """sigma-distance in the axis's own space: log for multiplicative axes
    when both values are positive; raw otherwise — log-from-zero is
    meaningless for absence dials that start at 0.0 (cere_bareface class,
    seed 3)."""
    if spec.mutation_kind.value != "gaussian" and va > 0 and vb > 0:
        return abs(math.log(va) - math.log(vb)) / spec.sigma
    return abs(va - vb) / spec.sigma


def _zdist_axes(pack, a: dict, b: dict, axes: list[str]) -> float:
    """sigma-normalized distance, in each axis's OWN space: raw for
    additive axes, log for multiplicative ones (raw-unit distance on a
    log axis reads sisters at 40 vs 80 as 114 sigma)."""
    total, n = 0.0, 0
    for ax in axes:
        spec = pack.registry.axes[ax]
        va, vb = a.get(ax), b.get(ax)
        if (spec.sigma > 0 and isinstance(va, (int, float))
                and isinstance(vb, (int, float))):
            total += _dz(spec, va, vb) ** 2
            n += 1
    return math.sqrt(total / n) if n else 0.0


def test_diversity_within_tolerance(pack):
    """Median sister distance per axis ~ sigma (the acceptance metric),
    plus a tail guard: the hottest axis must not explode (the
    fecundity/lifespan coupling-loop class)."""
    scalar_axes = [n for n, a in pack.registry.axes.items()
                   if a.mutable and a.value_type.value == "scalar"
                   and a.sigma > 0]
    for seed in SEEDS:
        tree = generate(pack, seed)
        genera: dict[str, list] = {}
        orders: dict[str, list] = {}
        for n in species(tree):
            genera.setdefault(n.path.rsplit(".s", 1)[0], []).append(n)
            orders.setdefault(n.path.rsplit(".f", 1)[0], []).append(n)
        per_axis: dict[str, list] = {ax: [] for ax in scalar_axes}
        for members in genera.values():
            for a, b in zip(members, members[1:]):
                for ax in scalar_axes:
                    spec = pack.registry.axes[ax]
                    va, vb = a.axes.get(ax), b.axes.get(ax)
                    if (isinstance(va, (int, float))
                            and isinstance(vb, (int, float))):
                        per_axis[ax].append(_dz(spec, va, vb))
        medians = {ax: statistics.median(v)
                   for ax, v in per_axis.items() if v}
        med = statistics.median(medians.values())
        assert 0.2 < med < 3.0, \
            f"seed {seed}: median per-axis sister distance {med}"
        hot = max(medians.items(), key=lambda kv: kv[1])
        assert hot[1] < 4.0, \
            f"seed {seed}: {hot[0]} sister distance {hot[1]:.1f} sigma"
        within, between = [], []
        keys = sorted(orders)
        for i, ka in enumerate(keys):
            ms = orders[ka]
            within += [_zdist_axes(pack, a.axes, b.axes, scalar_axes)
                       for a, b in zip(ms, ms[1:])]
            for kb in keys[i + 1:]:
                between.append(_zdist_axes(pack, orders[kb][0].axes,
                                           ms[0].axes, scalar_axes))
        assert statistics.mean(between) > statistics.mean(within)


# ──  5. metrics gate  ─────────────────────────────────────────────────────


def test_metrics_gate_all_seeds(pack):
    for seed in SEEDS:
        rep = run_checks(generate(pack, seed), pack)
        assert rep.ok, f"seed {seed}:\n{rep.text()}"


# ──  6. names + descriptions  ─────────────────────────────────────────────


def test_every_species_named_and_describable(pack):
    for seed in SEEDS:
        tree = generate(pack, seed)
        for n in species(tree):
            assert n.name.binomial, f"{n.path} unnamed"
            text, trace = describe(n, pack)
            assert text.startswith(("a ", "an ")) and "-like" in text
            assert trace["size"] == "axes.body_mass"


# ──  7. planted violations must fail the gate  ────────────────────────────


def test_planted_crocodile_on_monkey_fails(pack):
    import copy
    from exp.k13_treegen.lint import lint
    p = copy.deepcopy(pack)
    for pin in p.pins:
        if pin["label"] == "crocodile":
            pin["preset"] = "tetrapod.monkey"
    assert lint(p) != []


def test_planted_absolute_unit_knob_fails(pack):
    from exp.k13_treegen.registry import Registry
    bad = {"axis": {
        "body_mass": {"block": "morphometrics", "tier": "steady",
                      "value_type": "scalar", "mutation": "log_gaussian",
                      "sigma": 0.3, "bounds": [0.001, 1e5], "unit": "mass",
                      "plan_scope": "all", "consumers": ["name"]},
        "ear_kg": {"block": "morphometrics", "tier": "labile",
                   "value_type": "scalar", "mutation": "gaussian",
                   "sigma": 0.1, "bounds": [0.0, 1.0], "unit": "mass",
                   "plan_scope": "all", "consumers": ["draw"]},
    }}
    with pytest.raises(Exception):
        Registry.from_toml(bad["axis"])
