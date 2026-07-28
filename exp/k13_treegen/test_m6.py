"""M6 tests — every active rule has an existence proof (must-fire +
must-not-fire); dormant rules are recorded-but-unbound; the 3 rejected
B1 §15 candidates are absent; weak bindings are seeded texture.

The must-fire cases call apply_couplings directly with synthetic
parent→child steps (deterministic), because the bug class under test is
the v1 identity-tradeoff: a coupling that never measurably moves output.
"""

from __future__ import annotations

import pathlib

import pytest

from exp.k13_treegen.content import load_content
from exp.k13_treegen.couplings import (
    GATE_PULL, ORNAMENT_PULL, WEAK_BIND_COUNT, apply_couplings,
    validate_couplings, weak_bindings)
from exp.k13_treegen.forces import Condition, evolve
from exp.k13_treegen.model import Node, Rank
from exp.k13_treegen.seeding import stage_stream

CONTENT = pathlib.Path(__file__).parent / "content"


@pytest.fixture(scope="module")
def pack():
    return load_content(CONTENT)


def node(path, plan="tetrapod", **axes) -> Node:
    return Node(path=path, rank=Rank.SPECIES, parent="k1", sid="0" * 16,
                plan=plan, preset="tetrapod.deer", axes=axes)


def run(pack, parent, child, condition=None, weak=None):
    apply_couplings(parent, child, pack, condition or Condition(),
                    stage_stream(1, "t", "c"), weak=weak)
    return child


# ──  gate: records validate  ──────────────────────────────────────────────


def test_rule_records_validate(pack):
    assert validate_couplings(pack) == []


# ──  R1 domestication package (bundle)  ───────────────────────────────────


def test_r1_must_fire_correlated_set(pack):
    """wariness drop >= 0.5 sigma fires the WHOLE package — one event."""
    p = node("a", wariness=0.8, ear_posture="erect", tail_carriage="level",
             snout_ratio=0.4, pattern_motif="uniform")
    c = node("b", wariness=0.1, ear_posture="erect", tail_carriage="level",
             snout_ratio=0.4, pattern_motif="uniform")
    run(pack, p, c)
    assert c.axes["ear_posture"] == "pendant"
    assert c.axes["tail_carriage"] == "curled"
    assert c.axes["snout_ratio"] < 0.4
    assert c.axes["pattern_motif"] == "spotted"
    # correlated: every effect recorded in edge_delta
    for ax in ("ear_posture", "tail_carriage", "snout_ratio",
               "pattern_motif"):
        assert c.edge_delta[ax]["coupling"] != 0


def test_r1_must_not_fire(pack):
    p = node("a", wariness=0.8, ear_posture="erect", pattern_motif="uniform")
    c = node("b", wariness=0.78, ear_posture="erect",
             pattern_motif="uniform")   # 0.2 sigma drop, below min_z
    run(pack, p, c)
    assert c.axes["ear_posture"] == "erect"
    assert "ear_posture" not in c.edge_delta


# ──  R2 size x fecundity (tradeoff)  ──────────────────────────────────────


def test_r2_must_fire(pack):
    p = node("a", body_mass=100.0, fecundity=4.0)
    c = node("b", body_mass=300.0, fecundity=4.0)   # mass up ~0.77 sigma
    run(pack, p, c)
    assert c.axes["fecundity"] < 4.0
    assert c.edge_delta["fecundity"]["coupling"] != 0.0


def test_r2_must_not_fire(pack):
    p = node("a", body_mass=100.0, fecundity=4.0)
    c = node("b", body_mass=100.0, fecundity=4.0)   # mass unchanged
    run(pack, p, c)
    assert c.axes["fecundity"] == 4.0
    assert "fecundity" not in c.edge_delta


# ──  R3 fast-slow life history (tradeoff)  ────────────────────────────────


def test_r3_must_fire(pack):
    p = node("a", lifespan_yr=10.0, fecundity=4.0)
    c = node("b", lifespan_yr=30.0, fecundity=4.0)
    run(pack, p, c)
    assert c.axes["fecundity"] < 4.0


def test_r3_must_not_fire(pack):
    p = node("a", lifespan_yr=10.0, fecundity=4.0)
    c = node("b", lifespan_yr=10.0, fecundity=4.0)
    run(pack, p, c)
    assert c.axes["fecundity"] == 4.0


# ──  R4 island flightlessness (gate)  ─────────────────────────────────────


def test_r4_must_fire(pack):
    p = node("a", plan="winged_biped", flight_style="soaring",
             aspect_ratio=12.0)
    c = node("b", plan="winged_biped", flight_style="flightless",
             aspect_ratio=12.0)
    run(pack, p, c)
    lo = pack.registry.axis("aspect_ratio").bounds[0]
    assert c.axes["aspect_ratio"] == pytest.approx(
        12.0 - GATE_PULL * (12.0 - lo))
    assert c.edge_delta["aspect_ratio"]["coupling"] != 0


def test_r4_must_not_fire(pack):
    p = node("a", plan="winged_biped", flight_style="soaring",
             aspect_ratio=12.0)
    c = node("b", plan="winged_biped", flight_style="soaring",
             aspect_ratio=12.0)
    run(pack, p, c)
    assert c.axes["aspect_ratio"] == 12.0


# ──  R8 ornament cost (condition gate)  ───────────────────────────────────


def test_r8_must_fire(pack):
    p = node("a", mane_ruff_extent=0.5)
    c = node("b", mane_ruff_extent=0.5)
    run(pack, p, c, condition=Condition(stress=1.0))
    assert c.axes["mane_ruff_extent"] == pytest.approx(
        0.5 * (1 - ORNAMENT_PULL))


def test_r8_proportional_to_stress(pack):
    """No step threshold: half stress = half pull (continuous, user ruling)."""
    p = node("a", mane_ruff_extent=0.5)
    c = node("b", mane_ruff_extent=0.5)
    run(pack, p, c, condition=Condition(stress=0.5))
    assert c.axes["mane_ruff_extent"] == pytest.approx(
        0.5 * (1 - 0.5 * ORNAMENT_PULL))


def test_r8_must_not_fire(pack):
    p = node("a", mane_ruff_extent=0.5)
    c = node("b", mane_ruff_extent=0.5)
    run(pack, p, c, condition=Condition(stress=0.0))
    assert c.axes["mane_ruff_extent"] == 0.5


# ──  Allen/Bergmann (symmetric ecogeographic couplings)  ──────────────────


def test_allen_fires_both_directions(pack):
    """Equal citizens: the niche axis drags the knob AND the knob drags
    the niche axis."""
    # colder-suited => smaller ears
    p = node("a", temp_opt_c=20.0, ear_size_ratio=0.15)
    c = node("b", temp_opt_c=10.0, ear_size_ratio=0.15)
    run(pack, p, c)
    assert c.axes["ear_size_ratio"] < 0.15
    # bigger ears => becomes warm-suited (reverse is equally real)
    p2 = node("a", temp_opt_c=20.0, ear_size_ratio=0.15)
    c2 = node("b", temp_opt_c=20.0, ear_size_ratio=0.24)
    run(pack, p2, c2)
    assert c2.axes["temp_opt_c"] > 20.0


def test_bergmann_must_fire(pack):
    """Colder-suited <=> larger body (opposite sign)."""
    p = node("a", temp_opt_c=20.0, body_mass=100.0)
    c = node("b", temp_opt_c=5.0, body_mass=100.0)
    run(pack, p, c)
    assert c.axes["body_mass"] > 100.0


def test_tradeoff_bidirectional_on_r2(pack):
    """R2 now also fires fecundity -> mass (equal citizens)."""
    p = node("a", body_mass=100.0, fecundity=4.0)
    c = node("b", body_mass=100.0, fecundity=8.0)   # fecundity up
    run(pack, p, c)
    assert c.axes["body_mass"] < 100.0              # mass pulled down


# ──  dormant + rejected enumeration  ──────────────────────────────────────


def test_dormant_rules_recorded_but_unbound(pack):
    dormant = {r.id: r.raw.get("dormant_reason")
               for r in pack.couplings if r.status == "dormant"}
    assert set(dormant) == {"cancer_suppression",
                            "sensory_modality_tradeoff",
                            "melanism_aggression",
                            "glogers_rule"}
    assert all(dormant.values())     # every dormancy has a reason


def test_rejected_candidates_absent(pack):
    """B1 §15's three rejected candidates must not exist as rules."""
    text = " ".join(str(r.raw) + r.id for r in pack.couplings).lower()
    for rejected in ("expensive_tissue", "brain_gut", "armor_speed",
                     "venom"):
        assert rejected not in text


# ──  per-world weak bindings  ─────────────────────────────────────────────


def test_weak_bindings_seeded(pack):
    a = weak_bindings(1, pack)
    b = weak_bindings(1, pack)
    c = weak_bindings(2, pack)
    assert a == b                       # deterministic per seed
    assert a != c                       # differs across seeds
    assert len(a) == WEAK_BIND_COUNT
    for wb in a:
        assert 0.1 <= abs(wb.coeff) <= 0.3
        assert wb.a != wb.b


def test_weak_bindings_applied(pack):
    wb = weak_bindings(1, pack)[0]
    p = node("a", **{wb.a: 1.0, wb.b: 1.0})
    c = node("b", **{wb.a: 2.0, wb.b: 1.0})   # a moved
    run(pack, p, c, weak=[wb])
    assert c.axes[wb.b] != 1.0


# ──  env-gate hook (world-conditioned couplings, rounds seam)  ────────────


def test_env_gate_hook(pack):
    """The rounds hook: an env-gated rule is silent without env data
    (world-blind backbone) and fires when the rounds populate it."""
    import copy

    from exp.k13_treegen.couplings import Rule
    rule = Rule.from_toml({
        "id": "hook_allen", "kind": "gate", "status": "active",
        "scope": ["all"], "source": "hook test",
        "trigger": {"env": "temp_c", "below": -10.0, "toward": "min"},
        "targets": ["ear_size_ratio"]})
    p2 = copy.deepcopy(pack)
    p2.couplings = [rule]
    p = node("a", ear_size_ratio=0.2)
    # world-blind: no env data -> gate stays silent
    c1 = run(p2, p, node("b", ear_size_ratio=0.2), condition=Condition())
    assert c1.axes["ear_size_ratio"] == 0.2
    # rounds populated env, below threshold -> fires toward min
    c2 = run(p2, p, node("b", ear_size_ratio=0.2),
             condition=Condition(env={"temp_c": -20.0}))
    lo = pack.registry.axis("ear_size_ratio").bounds[0]
    assert c2.axes["ear_size_ratio"] == pytest.approx(
        0.2 - GATE_PULL * (0.2 - lo))
    # above threshold -> silent
    c3 = run(p2, p, node("b", ear_size_ratio=0.2),
             condition=Condition(env={"temp_c": 5.0}))
    assert c3.axes["ear_size_ratio"] == 0.2


# ──  end-to-end: couplings change evolve output  ──────────────────────────


def test_evolve_couplings_on_off_differs(pack):
    base = dict(body_mass=100.0, fecundity=4.0, wariness=0.5,
                ear_posture="erect", tail_carriage="level",
                snout_ratio=0.4, pattern_motif="uniform",
                base_color="rufous", vibrissae_prominence=0.1)
    p = node("a", **base)
    on = evolve(p, pack, stage_stream(5, "e2e", "s"), 500.0, path="x.on",
                couplings=True)
    off = evolve(p, pack, stage_stream(5, "e2e", "s"), 500.0, path="x.off",
                 couplings=False)
    # same stream, same mutation draws — any difference is coupling-forced
    assert on.axes != off.axes or on.edge_delta != off.edge_delta
