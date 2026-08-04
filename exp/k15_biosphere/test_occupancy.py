"""Fast-tier tests for the per-cell occupancy data model (ticket 0045;
spec B10 §1, B8).

Cells are built from REAL presets through the content loader + the
canonical view assembler (the only derive path): a canopy oak
(crown-driven coverage) and a grass sward (footprint-driven) are the
natural A/B-shaped pair, with a moss mat for the per-area (kg_m2) path.
Covers pool linearity in productivity (B8 numbers), geometric coverage
budgets per layer from B7 geometry, substrate multiplicativity,
remainder accounting through ordered painting (the A/B mechanism),
overshoot reported-but-never-clamped, conservation, and build
determinism.  Plain pytest, no marks — runs in milliseconds.
"""

from __future__ import annotations

import math
import pathlib

import pytest

from exp.k15_biosphere.content import load_content, merged_preset
from exp.k15_biosphere.flora.view import assemble_view
from exp.k15_biosphere.record import SpeciesRecord
from exp.k15_biosphere.occupancy import (
    CellInput,
    Lineage,
    OccupancyState,
    POOL_X_T_PER_HA,
)

# The real flora content pack lives in the frozen k13 reference; content
# is shared data, read IN PLACE from there (never copied).
CONTENT_DIR = pathlib.Path(__file__).parent.parent / "k13_treegen" \
    / "content" / "flora"

# Loaded once at module scope: the fixtures below are fast and share it.
_PACK = load_content(CONTENT_DIR)


# ──  fixture builders  ────────────────────────────────────────────────────


def _lineage(preset_id: str, ref: str, substrate_pref=None,
             demand_t: float = 0.0) -> Lineage:
    """A real-preset lineage: the committed record assembled to its
    canonical view (the only derive path), wrapped in a Lineage."""
    t = _PACK.presets[preset_id]
    axes, generics = merged_preset(t)
    rec = SpeciesRecord(sid="0" * 16, plan=t["preset"]["plan"],
                        preset=preset_id, axes=axes, generics=generics)
    return Lineage(ref=ref, view=assemble_view(rec, _PACK),
                   substrate_pref=substrate_pref or {}, demand_t=demand_t)


def _oak(**kw) -> Lineage:
    """tree.oak: canopy layer, 12 m crown — the A/B canopy actor."""
    return _lineage("tree.oak", "oak", **kw)


def _tussock(**kw) -> Lineage:
    """grass_sward.tussock: sward layer, footprint-driven — the
    understory actor."""
    return _lineage("grass_sward.tussock", "sward", **kw)


def _sphagnum(**kw) -> Lineage:
    """moss_grade.sphagnum: ground layer, kg_m2 (per-area) coverage."""
    return _lineage("moss_grade.sphagnum", "moss", **kw)


def _cell(productivity: float = 1.0, cell_ha: float = 1600.0,
          mix: dict | None = None) -> CellInput:
    """A 256²-resolution cell (1600 ha) at the default productivity,
    full-peat substrate unless the caller provides a mix."""
    return CellInput(productivity=productivity, cell_ha=cell_ha,
                     substrate_mix=mix or {"peat": 1.0})


# ──  the pool (B8)  ───────────────────────────────────────────────────────


def test_pool_linear_in_productivity_and_b8_numbers():
    """B8: C(c) = productivity · X · cell_ha with X = 400 t/ha per
    productivity unit — strictly linear in p, per-hectare so
    resolution-independent (1600 ha at 256², 100 ha at 1024²)."""
    st1 = OccupancyState(_cell(1.0), [_oak()])
    st_rich = OccupancyState(_cell(2.5), [_oak()])
    st_poor = OccupancyState(_cell(0.75), [_oak()])
    st_small = OccupancyState(_cell(1.0, cell_ha=100.0), [_oak()])
    assert st1.pool_t == pytest.approx(POOL_X_T_PER_HA * 1600.0)  # 640 000 t
    assert st_rich.pool_t == pytest.approx(2.5 * st1.pool_t)
    assert st_poor.pool_t == pytest.approx(0.75 * st1.pool_t)
    assert st_small.pool_t == pytest.approx(POOL_X_T_PER_HA * 100.0)
    assert st_poor.pool_t == pytest.approx(480_000.0)


# ──  coverage budgets from B7 geometry (B10 §1)  ─────────────────────────


def test_canopy_layer_budget_from_crown_geometry():
    """The canopy layer packs ~cell_area / crown_area adults — a pure
    geometric budget (B10 §1), productivity-blind.  At full pack the
    p=1 pool binds first, so the paint reports a pool overshoot while
    coverage sits exactly on budget."""
    st = OccupancyState(_cell(1.0), [_oak()])
    oak = st.lineages[0]
    crown_area = math.pi * (oak.view["crown_spread_m"] / 2.0) ** 2
    budget_adults = st.cell_area_m2 / crown_area
    percap_t = oak.view["mass_total_kg"] / 1000.0

    rpt = st.paint("oak", budget_adults * percap_t)

    assert rpt.layer == "canopy"
    assert rpt.holdings_t == pytest.approx(budget_adults * percap_t)
    assert rpt.coverage == pytest.approx(1.0, rel=1e-6)
    assert st.coverage("canopy") == pytest.approx(1.0, rel=1e-6)
    assert st.coverage("sward") == 0.0          # other layers untouched
    assert rpt.overshoots == ("pool",)          # pool binds first at p=1
    assert rpt.overshoot_pool_t == pytest.approx(
        rpt.pool_used_t - st.pool_t)


def test_ground_layer_budget_from_footprint():
    """A sward's coverage bounds by its footprint (the view's
    mass_proportions footprint_m2, from B7 geometry) — at full cover
    its biomass sits far inside the p=1 pool, so nothing overshoots."""
    st = OccupancyState(_cell(1.0), [_tussock()])
    sw = st.lineages[0]
    fp = sw.view["mass_proportions"]["footprint_m2"]
    budget_adults = st.cell_area_m2 / fp
    percap_t = sw.view["mass_total_kg"] / 1000.0

    rpt = st.paint("sward", budget_adults * percap_t)

    assert rpt.layer == "sward"
    assert rpt.coverage == pytest.approx(1.0, rel=1e-6)
    assert rpt.overshoots == ()
    assert rpt.overshoot_pool_t == 0.0
    assert rpt.overshoot_coverage_m2 == 0.0


def test_per_area_mat_coverage_from_kg_m2():
    """Moss/mat per-area models carry kg_m2 (no footprint key): the
    per-individual area is recovered as percap_kg / kg_m2, so coverage
    stays consistent with the mass hook's own footprint."""
    st = OccupancyState(_cell(1.0), [_sphagnum()])
    moss = st.lineages[0]
    kg_m2 = moss.view["mass_proportions"]["kg_m2"]
    area = moss.view["mass_total_kg"] / kg_m2      # ≈ 0.196 m²
    budget_adults = st.cell_area_m2 / area
    percap_t = moss.view["mass_total_kg"] / 1000.0

    rpt = st.paint("moss", budget_adults * percap_t)

    assert rpt.layer == "ground"
    assert rpt.coverage == pytest.approx(1.0, rel=1e-6)


def test_layer_assignment_from_view_with_distinct_budgets():
    """The view's layer key drives layer assignment; each layer is an
    independent plane with its own geometric budget (B6 stratification:
    canopy and sward stack without double-counting)."""
    st = OccupancyState(_cell(1.0), [_oak(), _tussock()])
    assert st.layer_of("oak") == "canopy"
    assert st.layer_of("sward") == "sward"
    st.paint("oak", 100_000.0)
    assert st.coverage("canopy") > 0.0
    assert st.coverage("sward") == 0.0            # empty plane until painted
    rpt = st.paint("sward", 100.0)
    assert rpt.coverage > 0.0
    assert st.coverage("sward") == pytest.approx(rpt.coverage)
    assert st.layer_remainder_m2("sward") == pytest.approx(
        st.cell_area_m2 - st.layer_used_m2("sward"))
    assert st.layer_used_m2("canopy") + st.layer_used_m2("sward") \
        < st.cell_area_m2                          # stacked, not merged


# ──  substrate-weighted demand (B10 §1)  ─────────────────────────────────


def test_substrate_weighted_demand_is_multiplicative():
    """Lineage demand × the cell's matching substrate fraction: a
    peat-preferring sward draws half its demand on a 50% peat cell,
    its full demand on a pure-peat cell (the unit-calibration anchor)."""
    pref = {"peat": 1.0, "sand": 0.0}
    half = OccupancyState(_cell(mix={"peat": 0.5, "sand": 0.5}),
                          [_tussock(substrate_pref=pref, demand_t=100.0)])
    full = OccupancyState(_cell(mix={"peat": 1.0}),
                          [_tussock(substrate_pref=pref, demand_t=100.0)])
    none = OccupancyState(_cell(mix={"peat": 0.5, "sand": 0.5}),
                          [_tussock(substrate_pref={}, demand_t=100.0)])
    assert half.substrate_match("sward") == pytest.approx(0.5)
    assert half.substrate_weighted_demand_t("sward") == pytest.approx(50.0)
    assert full.substrate_weighted_demand_t("sward") == pytest.approx(100.0)
    # an absent preference matches every substrate at full weight
    assert none.substrate_match("sward") == pytest.approx(1.0)
    assert none.substrate_weighted_demand_t("sward") == pytest.approx(100.0)


def test_substrate_mix_validated():
    """The substrate mix is a pmf over the synthetic vocabulary; a
    non-pmf or an unknown class is a construction error."""
    with pytest.raises(ValueError):
        _cell(mix={"peat": 0.5})                   # does not sum to 1
    with pytest.raises(ValueError):
        _cell(mix={"loam": 1.0})                   # outside the vocabulary


# ──  remainder accounting through ordered painting (the A/B mechanism) ───


def test_remainder_after_painting():
    """Each paint leaves the pool/coverage remainder the next stage
    sees: pool_used accumulates, pool_remainder tracks the A/B gap."""
    st = OccupancyState(_cell(2.5), [_oak()])
    assert st.pool_remainder_t == pytest.approx(st.pool_t)
    rpt = st.paint("oak", 400_000.0)
    assert rpt.holdings_t == pytest.approx(400_000.0)
    assert st.pool_used_t == pytest.approx(400_000.0)
    assert rpt.pool_used_t == pytest.approx(400_000.0)
    assert st.pool_remainder_t == pytest.approx(st.pool_t - 400_000.0)
    assert rpt.pool_remainder_t == pytest.approx(st.pool_t - 400_000.0)


def test_two_lineage_cell_painted_in_order_reports_remainder():
    """B10 §6.1 acceptance shape: cells A (rich) and B (poor) hold the
    SAME oak biomass; A's canopy leaves a large pool remainder for the
    understory, B's nearly exhausts the pool — emergent from the
    remainder + stage order, no understory penalty.  Coverage is
    productivity-blind (the geometric budget)."""
    def build(p):
        st = OccupancyState(_cell(p), [_oak(), _tussock()])
        r_oak = st.paint("oak", 400_000.0)         # stage 1: the canopy
        r_sward = st.paint("sward", 100.0)         # stage 2: the understory
        return st, r_oak, r_sward

    A, rA_oak, rA_sward = build(2.5)               # pool 1.6 Mt
    B, rB_oak, rB_sward = build(0.75)              # pool 480 kt

    # same canopy biomass, same coverage — only the pool differs
    assert rA_oak.holdings_t == pytest.approx(400_000.0)
    assert rB_oak.holdings_t == pytest.approx(400_000.0)
    assert rA_oak.coverage == pytest.approx(rB_oak.coverage)
    # A's canopy leaves ~1.2 Mt; B's leaves 80 kt
    assert rA_oak.pool_remainder_t == pytest.approx(A.pool_t - 400_000.0)
    assert rB_oak.pool_remainder_t == pytest.approx(80_000.0)
    assert rA_oak.pool_remainder_t > 10.0 * rB_oak.pool_remainder_t
    # each understory stage sees exactly what the canopy left it
    assert rA_sward.pool_remainder_t == pytest.approx(
        A.pool_t - 400_000.0 - 100.0)
    assert rB_sward.pool_remainder_t == pytest.approx(
        B.pool_t - 400_000.0 - 100.0)
    # the sward's own plane is unaffected by the canopy's (its own
    # geometric budget) — understory density is a pool story, not a
    # coverage story
    assert rA_sward.coverage == pytest.approx(rB_sward.coverage)


# ──  overshoot: reported, never clamped (B10 §3)  ────────────────────────


def test_overshoot_reported_not_clamped():
    """Painting past the budgets APPLIES the delta in full and reports
    which budgets broke and by how much — nothing is silently clamped
    away (caps are guardrails; crowding stress is the mechanism)."""
    st = OccupancyState(_cell(1.0), [_oak()])
    rpt = st.paint("oak", 2.0 * st.pool_t)

    assert rpt.holdings_t == pytest.approx(2.0 * st.pool_t)
    assert st.pool_used_t == pytest.approx(2.0 * st.pool_t)
    assert rpt.overshoots == ("pool", "coverage")
    assert rpt.overshoot_pool_t == pytest.approx(st.pool_t)
    assert rpt.overshoot_coverage_m2 == pytest.approx(
        rpt.layer_used_m2 - st.cell_area_m2)
    assert rpt.overshoot_coverage_m2 > 0.0
    assert rpt.coverage > 1.0                      # the fraction may exceed 1


def test_paint_validation():
    """Painting an unknown ref or below-zero holdings is an error, not
    a report — data integrity, not capacity."""
    st = OccupancyState(_cell(1.0), [_oak()])
    with pytest.raises(ValueError):
        st.paint("nope", 1.0)
    with pytest.raises(ValueError):
        st.paint("oak", -1.0)


# ──  conservation + determinism  ─────────────────────────────────────────


def test_conservation_sum_of_lineage_biomass():
    """Σ lineage holdings == the cell total — the pool ledger never
    leaks (holdings are the stored primitive; pool_used is their sum)."""
    st = OccupancyState(_cell(1.0), [_oak(), _tussock()])
    st.paint("oak", 400_000.0)
    st.paint("sward", 100.0)
    assert st.pool_used_t == pytest.approx(sum(st.holdings_t.values()))
    assert st.pool_used_t == pytest.approx(400_100.0)
    for r in ("oak", "sward"):
        assert st.holdings_t[r] >= 0.0


def test_two_identical_builds_are_equal():
    """Determinism hard rule: two identical builds (same cell, same
    lineage views, same paint sequence) are equal — state and every
    report field."""
    def build():
        st = OccupancyState(
            _cell(2.5, mix={"peat": 0.5, "sand": 0.5}),
            [_oak(demand_t=500_000.0),
             _tussock(substrate_pref={"peat": 1.0}, demand_t=100.0)])
        r1 = st.paint("oak", 400_000.0)
        r2 = st.paint("sward", 100.0)
        return st, r1, r2

    s1, r1_oak, r1_sward = build()
    s2, r2_oak, r2_sward = build()
    assert s1 == s2
    assert r1_oak == r2_oak
    assert r1_sward == r2_sward


def test_no_nondeterministic_imports():
    """AGENTS.md determinism hard rule: no random/uuid/time/numpy in
    occupancy.py (same seed ⇒ byte-identical output)."""
    src = (pathlib.Path(__file__).parent / "occupancy.py").read_text()
    for line in src.splitlines():
        stripped = line.strip()
        for bad in ("import random", "from random", "import uuid",
                    "from uuid", "import time", "from time",
                    "import numpy"):
            assert not stripped.startswith(bad), \
                f"occupancy.py: forbidden import: {stripped}"
