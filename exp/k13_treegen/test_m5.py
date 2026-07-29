"""M5 tests — clock & forces acceptance battery (rebuild plan M5 gates).

Everything runs directly on evolve() over synthetic lineages; no backbone
needed. Seeded determinism throughout (K1 streams).
"""

from __future__ import annotations

import pathlib
import statistics

import pytest

from exp.k13_treegen.content import load_content
from exp.k13_treegen.forces import (
    Condition, classify, evolve, g_star, gen_time_years, rate_multiplier,
    share_ratios, step_scale, _tier_gate, G_STEADY_ONSET,
    G_STEADY_RAMP, STRESS_G_BOOST)
from exp.k13_treegen.model import Node, Rank
from exp.k13_treegen.seeding import stage_stream

CONTENT = pathlib.Path(__file__).parent / "content"


@pytest.fixture(scope="module")
def pack():
    return load_content(CONTENT)


def parent_node(g: float = 0.0, **axes) -> Node:
    base = dict(body_mass=100.0, base_color="rufous", ear_size_ratio=0.1,
                intermembral_index=100, vibrissae_prominence=0.1,
                diet_spectrum={"grazer": 1.0},
                horn_cover_texture="N/A")
    base.update(axes)
    return Node(path="k1.p1.c1.o1.f1.g1.s1", rank=Rank.SPECIES,
                parent="k1.p1.c1.o1.f1.g1", sid="0" * 16,
                plan="tetrapod", preset="tetrapod.deer", g=g, axes=base)


# ──  clock  ───────────────────────────────────────────────────────────────


def test_gen_time_ordering():
    """Megafauna run slower clocks than small taxa, by construction."""
    assert gen_time_years(100000.0) > gen_time_years(0.1)
    assert gen_time_years(100.0) > gen_time_years(1.0)


def test_rate_multiplier_both_tails():
    """Lognormal lineage rates: fast radiators AND living fossils."""
    s = stage_stream(1, "test", "rate")
    draws = [rate_multiplier(s.child(f"lin{i}")) for i in range(200)]
    assert min(draws) < 0.7 and max(draws) > 1.5


def test_g_monotonic(pack):
    s = stage_stream(1, "test", "mono")
    p = parent_node()
    c1 = evolve(p, pack, s.child("e1"), 10.0, path="x.1")
    c2 = evolve(c1, pack, s.child("e2"), 10.0, path="x.2")
    assert p.g < c1.g < c2.g


def test_stress_raises_g_accrual(pack):
    """Sign test: stressed lineages accrue more g for the same base Δg."""
    p = parent_node()
    benign = evolve(p, pack, stage_stream(2, "t", "b"), 10.0, path="x.b",
                    condition=Condition(stress=0.0))
    stressed = evolve(p, pack, stage_stream(2, "t", "b"), 10.0, path="x.s",
                      condition=Condition(stress=1.0))
    assert stressed.g - p.g == pytest.approx(
        (benign.g - p.g) * (1 + STRESS_G_BOOST))


def test_g_star_boundary():
    s = stage_stream(1, "test", "gstar")
    star = g_star(s)
    assert classify(star - 1, star) == "subspecies"
    assert classify(star + 1, star) == "species"


# ──  mutation magnitude ∝ f(g) — the novelty tail  ───────────────────────


def test_tier_gate_planted(pack):
    """Low-g lineage: steady axes frozen, labile axes move. High-g: the
    novelty tail opens and steady axes move too."""
    low = parent_node(g=0.0)
    moved_low = set()
    for i in range(30):
        c = evolve(low, pack, stage_stream(3, "tg", f"l{i}"), 5.0,
                   path=f"x.l{i}")
        for ax in ("intermembral_index", "vibrissae_prominence"):
            if c.axes[ax] != low.axes[ax]:
                moved_low.add(ax)
    assert "intermembral_index" not in moved_low    # steady, still locked
    assert "vibrissae_prominence" in moved_low       # labile, moves

    high = parent_node(g=G_STEADY_ONSET * 10)
    moved_high = {ax for i in range(30)
                  for ax in ("intermembral_index",)
                  if evolve(high, pack, stage_stream(3, "tg", f"h{i}"),
                            5.0, path=f"x.h{i}").axes[ax]
                  != high.axes[ax]}
    assert "intermembral_index" in moved_high       # unlocked at high g


def test_steady_gate_is_leaky_ramp(pack):
    """No hard unlock: the steady gate is a smooth 0->1 ramp (user ruling:
    processes are continuous and leaky)."""
    from exp.k13_treegen.registry import Tier
    spec = pack.registry.axis("intermembral_index")
    assert spec.tier is Tier.STEADY
    assert _tier_gate(spec, 0.0) == 0.0                    # frozen at low g
    assert _tier_gate(spec, G_STEADY_ONSET) == 0.0         # still ~frozen
    mid = _tier_gate(spec, G_STEADY_ONSET + G_STEADY_RAMP)
    assert 0.5 < mid < 0.75                                # ~0.63, opening
    assert _tier_gate(spec, G_STEADY_ONSET + 10 * G_STEADY_RAMP) > 0.99
    # monotonic, never a step
    gs = [_tier_gate(spec, float(g)) for g in range(0, 4000, 100)]
    assert all(b >= a for a, b in zip(gs, gs[1:]))


def test_magnitude_grows_with_g(pack):
    """Mean |Δ| of a labile scalar is larger at high g than low g."""
    def mean_step(g):
        p = parent_node(g=g)
        steps = [abs(evolve(p, pack, stage_stream(4, "mg", str(i)), 5.0,
                            path="x").axes["ear_size_ratio"]
                     - p.axes["ear_size_ratio"]) for i in range(60)]
        return statistics.mean(steps)
    assert mean_step(0.0) < mean_step(G_STEADY_ONSET * 10)


def test_step_scale_leaky_linear():
    assert step_scale(0.0) == 1.0
    assert step_scale(1000.0) == 2.0
    assert step_scale(10000.0) > 5.0     # no cap


# ──  force attribution (edge_delta decomposition)  ───────────────────────


def test_drift_mean_zero(pack):
    """Benign condition, no center, no ornaments moved: drift-only steps
    average to zero."""
    p = parent_node()
    deltas = [evolve(p, pack, stage_stream(5, "dm", str(i)), 5.0,
                     path="x").edge_delta["vibrissae_prominence"]["drift"]
              for i in range(80)]
    assert abs(statistics.mean(deltas)) < 0.2 * statistics.pstdev(deltas) \
        or abs(statistics.mean(deltas)) < 0.05


def test_descent_moves_toward_center(pack):
    """Stressed lineage with a clade center: adaptive axes converge."""
    p = parent_node(ear_size_ratio=0.1)
    center = {"ear_size_ratio": 0.3}
    cur = p
    for i in range(20):
        cur = evolve(cur, pack, stage_stream(6, "dc", str(i)), 20.0,
                     path=f"x.{i}", condition=Condition(stress=1.0),
                     clade_center=center)
    assert cur.axes["ear_size_ratio"] > p.axes["ear_size_ratio"]
    assert cur.edge_delta["ear_size_ratio"]["descent"] != 0


def test_runaway_targets_ornaments_only(pack):
    """Runaway contributions land only on adapt_weight == 0 axes."""
    p = parent_node(mane_ruff_extent=0.5)  # adapt_weight 0.0 ornament
    c = evolve(p, pack, stage_stream(7, "rw", "0"), 50.0, path="x",
               condition=Condition(stress=0.0, isolation=0.0),
               runaway_dir=1.0)
    assert c.edge_delta["mane_ruff_extent"]["runaway"] > 0
    for ax, d in c.edge_delta.items():
        if ax != "mane_ruff_extent":
            assert d["runaway"] == 0.0


def test_share_ratios_condition_table(pack):
    """RFC §4: stressed → descent-dominated; isolate → drift-dominated;
    benign → slow mixed."""
    s_stress = share_ratios(Condition(stress=1.0))
    s_iso = share_ratios(Condition(isolation=1.0))
    s_benign = share_ratios(Condition())
    assert s_stress.descent > s_stress.drift
    assert s_iso.drift > s_iso.descent + s_iso.runaway
    # benign: drift dominates, but descent has a baseline share (OU-style
    # mean reversion — a zero-descent benign walk gave 0.1 g .. 6 kg
    # "beetles" in one genus).
    assert 0.0 < s_benign.descent < s_benign.drift
    assert s_benign.drift > s_benign.runaway


# ──  stickiness  ──────────────────────────────────────────────────────────


def test_na_sticky(pack):
    p = parent_node()
    for i in range(10):
        c = evolve(p, pack, stage_stream(8, "na", str(i)), 50.0, path="x")
        assert c.axes["horn_cover_texture"] == "N/A"


def test_determinism(pack):
    p = parent_node()
    a = evolve(p, pack, stage_stream(9, "det", "s"), 10.0, path="x")
    b = evolve(p, pack, stage_stream(9, "det", "s"), 10.0, path="x")
    assert a.to_json() == b.to_json()
    c = evolve(p, pack, stage_stream(10, "det", "s"), 10.0, path="x")
    assert a.to_json() != c.to_json()       # different seed differs
