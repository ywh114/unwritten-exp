"""Fast-tier tests for crowding fields + competition stress + the
derived cap (ticket 0046; spec B10 §1, §2, §5, §6).

Cells are built from REAL presets through the content loader + the
canonical view assembler, following test_occupancy's fixture style: the
canopy oak (25 m, 12 m crown — the A/B canopy actor), the grass sward
(footprint-driven ground cover), the moss mat (kg_m2 ground cover), and
the 15 m willow for a second canopy stratum.  Covers:

- the prodscale target f and the crowding scalar's shape (B10 §5);
- the height-stratified canopy profile and the SHADE STEP — flat /
  steep / quiet vs the canopy top (B10 §4's benefit step);
- ground-cover and substrate share fields + share-based stress,
  including reciprocity (a growing lineage raises everyone's
  substrate contest — B10 §2's arms race);
- the n=1 calibration at the four anchor productivities (the lone
  lineage's self-crowding equilibrium == f(p) · L · matching-substrate
  ha) and the monoculture limit (the equilibrium reads as the derived
  cap);
- per-resource independence (the substrate contest does not leak into
  the canopy shade), probeability (nudge-and-recompute is
  deterministic, pure, and reads the landscape), and the determinism
  audit.  Plain pytest, no marks — runs in milliseconds.
"""

from __future__ import annotations

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
from exp.k15_biosphere.crowding import (
    PROVENANCE_TOP_N,
    LINEAGE_CAP_POOL_FRACTION,
    canopy_profile,
    competition_canopy,
    competition_ground_cover,
    competition_stress,
    competition_substrate,
    crowding,
    ground_cover_field,
    lineage_cap_scale_t,
    prodscale_f,
    self_crowding_equilibrium_t,
    substrate_capacity_t,
    substrate_field,
)

# The real flora content pack lives in the frozen k13 reference; content
# is shared data, read IN PLACE from there (never copied).
CONTENT_DIR = pathlib.Path(__file__).parent.parent / "k13_treegen" \
    / "content" / "flora"

# Loaded once at module scope: the fixtures below are fast and share it.
_PACK = load_content(CONTENT_DIR)

# The 1600 ha (256²-resolution) cell's p=1 pool — L's calibration frame.
_POOL_1_T = POOL_X_T_PER_HA * 1600.0


# ──  fixture builders (test_occupancy's house style)  ────────────────────


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
    """tree.oak: 25 m canopy, 12 m crown — the A/B canopy actor."""
    return _lineage("tree.oak", "oak", **kw)


def _willow(**kw) -> Lineage:
    """tree.willow: 15 m canopy — a second, lower canopy stratum."""
    return _lineage("tree.willow", "willow", **kw)


def _tussock(ref: str = "sward", **kw) -> Lineage:
    """grass_sward.tussock: sward layer, footprint-driven ground cover."""
    return _lineage("grass_sward.tussock", ref, **kw)


def _sphagnum(**kw) -> Lineage:
    """moss_grade.sphagnum: ground layer, kg_m2 (per-area) cover."""
    return _lineage("moss_grade.sphagnum", "moss", **kw)


def _probe(height_m: float) -> Lineage:
    """A zero-holding canopy lineage whose view is the oak's with the
    height nudged — the probe nudge-and-recompute pattern (B10 §4):
    the stress functions read the view; the probe never disturbs the
    field (zero holdings → zero cover)."""
    return Lineage(ref="probe", view=dict(_oak().view, height_m=height_m))


def _cell(productivity: float = 1.0, cell_ha: float = 1600.0,
          mix: dict | None = None) -> CellInput:
    """A 256²-resolution cell (1600 ha) at the default productivity,
    full-peat substrate unless the caller provides a mix."""
    return CellInput(productivity=productivity, cell_ha=cell_ha,
                     substrate_mix=mix or {"peat": 1.0})


def _cap_t(p: float, match: float = 1.0) -> float:
    """The derived cap f(p) · L · cell_ha · match at 1600 ha: the
    target the n=1 calibration must hit."""
    return prodscale_f(p) * LINEAGE_CAP_POOL_FRACTION * POOL_X_T_PER_HA \
        * 1600.0 * match


# ──  prodscale f + the crowding scalar (B10 §5)  ─────────────────────────


def test_prodscale_f_anchors():
    """f(p) = 5/4 − 4^(−p) for p<1, 39/40 + p/40 for p≥1, anchored
    f(1)=1 — the four anchor productivities from the ticket, with the
    real B2-scale numbers: f(2.5)≈1.04, f(0.75)≈0.90 (B10 §5)."""
    assert prodscale_f(0.25) == pytest.approx(1.25 - 4.0 ** -0.25)
    assert prodscale_f(0.75) == pytest.approx(0.8964, abs=1e-4)   # ≈0.90
    assert prodscale_f(1.0) == pytest.approx(1.0, abs=1e-12)      # both branches
    assert prodscale_f(2.5) == pytest.approx(1.0375, abs=1e-12)   # ≈1.04
    assert prodscale_f(0.0) == pytest.approx(0.25)
    # continuous across the p=1 hinge
    assert prodscale_f(1.0) == pytest.approx(1.25 - 4.0 ** -1.0, abs=1e-12)


def test_crowding_scalar_shape():
    """g(p̃) = min(1, p̃): no pressure → no crowding, g(1)=1 is the n=1
    calibration point (a pressure of one capacity zeroes net growth),
    and crowding saturates (full suppression, never oversuppression)."""
    assert crowding(0.0) == pytest.approx(0.0)
    assert crowding(0.5) == pytest.approx(0.5)
    assert crowding(1.0) == pytest.approx(1.0)
    assert crowding(2.0) == pytest.approx(1.0)


# ──  the height-stratified canopy profile (B10 §1)  ──────────────────────


def test_canopy_profile_is_height_stratified():
    """The canopy field carries HEIGHT structure: strata (ref, height,
    covered fraction) sorted height-descending, with the top and total
    cover; the shading function coverage_strictly_above steps through
    the strata."""
    st = OccupancyState(_cell(), [_oak(), _willow()])
    st.paint("oak", 400_000.0)            # cover ≈ 0.525
    st.paint("willow", 100_000.0)
    prof = canopy_profile(st)

    assert prof.top_height_m == pytest.approx(25.0)
    assert [s[0] for s in prof.strata] == ["oak", "willow"]   # height desc
    assert prof.strata[0][1] == pytest.approx(25.0)
    assert prof.strata[1][1] == pytest.approx(15.0)
    assert prof.covered_fraction == pytest.approx(
        st.coverage("canopy"), rel=1e-9)
    # the shading function: strictly above 20 m only the oak stands
    assert prof.coverage_strictly_above(20.0) == pytest.approx(
        prof.strata[0][2], rel=1e-9)
    # strictly above 10 m both strata shade
    assert prof.coverage_strictly_above(10.0) == pytest.approx(
        prof.covered_fraction, rel=1e-9)
    # at the top nothing is strictly above
    assert prof.coverage_strictly_above(25.0) == 0.0
    # zero-holding lineages (the probe) never appear in the profile
    assert all(s[0] != "probe" for s in canopy_profile(
        OccupancyState(_cell(), [_oak(), _probe(12.0)])).strata)


def test_canopy_profile_empty_without_canopy():
    """A cell with only ground cover has an empty canopy profile: top
    0, no cover, no shade."""
    prof = canopy_profile(OccupancyState(_cell(), [_tussock()]))
    assert prof.strata == ()
    assert prof.top_height_m == 0.0
    assert prof.covered_fraction == 0.0
    assert prof.coverage_strictly_above(0.0) == 0.0


# ──  the shade step (B10 §4 — the benefit step in competition:canopy) ────


def test_shade_step_flat_steep_quiet():
    """competition:canopy as a function of the lineage's height RELATIVE
    to the canopy profile: high and FLAT well below the top (small
    height gains buy zero marginal relief — the shade trap), STEEP just
    below the canopy top (a nudge crosses the top stratum's coverage —
    strong marginal relief), QUIET at/above the top."""
    def shade_at(h: float) -> float:
        st = OccupancyState(_cell(), [_oak(), _probe(h)])
        st.paint("oak", 400_000.0)
        return competition_canopy(_probe(h).view, st)["value"]

    # the oak's painted cover — the shade the probe reads at its feet
    st0 = OccupancyState(_cell(), [_oak()])
    st0.paint("oak", 400_000.0)
    c_oak = canopy_profile(st0).covered_fraction
    assert c_oak > 0.0

    # FLAT deep understory: 12 m vs 13 m read the same shade
    assert shade_at(12.0) == pytest.approx(c_oak)
    assert shade_at(13.0) == pytest.approx(c_oak)
    assert shade_at(13.0) == pytest.approx(shade_at(12.0), abs=1e-12)
    # STEEP just below the top: the full top-stratum coverage is
    # crossed by a nudge through 25 m
    assert shade_at(24.9) == pytest.approx(c_oak)
    assert shade_at(25.5) == 0.0
    assert shade_at(24.9) - shade_at(25.5) == pytest.approx(c_oak)
    # QUIET at/above the top
    assert shade_at(25.0) == 0.0
    assert shade_at(26.0) == 0.0
    # monotone nonincreasing in height (never deeper shade higher up)
    hs = [12.0, 20.0, 24.0, 24.9, 25.0, 25.5, 26.0]
    vals = [shade_at(h) for h in hs]
    assert all(vals[i] >= vals[i + 1] - 1e-12 for i in range(len(vals) - 1))
    assert vals[0] > 0.0 and vals[-1] == 0.0


def test_canopy_self_is_quiet():
    """A lone canopy lineage's own canopy never shades it — nothing
    stands strictly above its crown — so competition:canopy reads 0
    (quiet): its crowding comes from the substrate, not its own shade."""
    st = OccupancyState(_cell(), [_oak()])
    st.paint("oak", 400_000.0)
    term = competition_canopy(_oak().view, st)
    assert term["value"] == 0.0
    assert "quiet" in term["cause"]
    # provenance names the canopy field's occupant — the oak dominates
    # the resource even though nothing shades it
    assert term["dominant_refs"] == ("oak",)
    # provenance: the field read
    assert term["field"]["top_height_m"] == pytest.approx(25.0)
    assert term["field"]["covered_fraction"] == pytest.approx(
        st.coverage("canopy"), rel=1e-9)


# ──  ground-cover share field + stress  ──────────────────────────────────


def test_ground_cover_field_and_stress():
    """The ground-cover field is the ground-class lineages' shares of
    the cell plane; the stress is the contest level (crowding of the
    total share) for ground dwellers, and 0 for a canopy lineage (no
    claim on the ground plane)."""
    st = OccupancyState(_cell(), [_oak(), _tussock(), _sphagnum()])
    st.paint("oak", 400_000.0)
    st.paint("sward", 20_000.0)            # cover 0.3906
    st.paint("moss", 2_000.0)              # cover 0.2083
    fld = ground_cover_field(st)

    assert [r for r, _ in fld.shares] == ["moss", "sward"]     # ref order
    assert fld.total_share == pytest.approx(
        st.coverage("sward") + st.coverage("ground"), rel=1e-9)

    sward_term = competition_ground_cover(_tussock().view, st)
    moss_term = competition_ground_cover(_sphagnum().view, st)
    assert sward_term["value"] == pytest.approx(
        crowding(fld.total_share))
    # reciprocal: both ground dwellers read the same contest level
    assert moss_term["value"] == pytest.approx(sward_term["value"])
    # provenance: dominance is by covered fraction desc — moss (0.42)
    # edges out the sward (0.39)
    assert sward_term["dominant_refs"] == ("moss", "sward")

    oak_term = competition_ground_cover(_oak().view, st)
    assert oak_term["value"] == 0.0
    assert "no ground plane" in oak_term["cause"]


def test_ground_cover_saturates_at_full_contest():
    """An overshooting ground plane (shares beyond 1.0) reads full
    crowding — reported, never clamped."""
    st = OccupancyState(_cell(), [_tussock()])
    st.paint("sward", 60_000.0)            # cover 1.17 — overshoot
    assert ground_cover_field(st).total_share > 1.0
    assert competition_ground_cover(_tussock().view, st)["value"] == 1.0


# ──  substrate share field + stress  ─────────────────────────────────────


def test_substrate_field_per_class_and_pressure():
    """The substrate field: per-class claimed fractions (claims =
    holdings × preference over the class's capacity f(p)·L·cell_ha·mix)
    and the total contested pressure Q = Σ holdings/C(ref) — the
    matching-substrate capacity (B10 §5: a lineage on half its
    preferred substrate caps at half)."""
    st = OccupancyState(_cell(mix={"peat": 0.5, "sand": 0.5}),
                        [_tussock(substrate_pref={"peat": 1.0})])
    st.paint("sward", 100_000.0)
    fld = substrate_field(st)

    # match 0.5 → capacity f(1)·L·1600·0.5 = 200 000 t; pressure 0.5
    assert st.substrate_match("sward") == pytest.approx(0.5)
    assert substrate_capacity_t(st, "sward") == pytest.approx(
        _cap_t(1.0, match=0.5))
    assert fld.total_pressure == pytest.approx(100_000.0 / 200_000.0)
    # per-class: the full claim lands on peat (capacity 200 000 t)
    assert dict(fld.per_class)["peat"] == pytest.approx(0.5)
    assert dict(fld.per_class)["sand"] == pytest.approx(0.0)

    term = competition_substrate(_tussock().view, st)
    assert term["value"] == pytest.approx(0.5)
    assert term["dominant_refs"] == ("sward",)


def test_substrate_stress_is_reciprocal():
    """The substrate stress reads the TOTAL contested level Q — the same
    for every lineage — so when one lineage grows, everyone's substrate
    stress grows (B10 §2's arms race: A crowds better, B's crowding
    worsens)."""
    st = OccupancyState(_cell(), [_tussock(ref="a"), _tussock(ref="b")])
    st.paint("a", 50_000.0)
    st.paint("b", 50_000.0)
    q1 = substrate_field(st).total_pressure
    assert q1 == pytest.approx(2 * 50_000.0 / _cap_t(1.0))
    a_view = next(ln.view for ln in st.lineages if ln.ref == "a")
    b_view = next(ln.view for ln in st.lineages if ln.ref == "b")
    v1 = competition_substrate(a_view, st)["value"]
    assert v1 == pytest.approx(crowding(q1))
    assert competition_substrate(b_view, st)["value"] == pytest.approx(v1)

    st.paint("b", 300_000.0)               # b crowds the substrate harder
    v2 = competition_substrate(a_view, st)["value"]
    assert v2 > v1                          # a's stress rose because of b
    assert v2 == pytest.approx(crowding(substrate_field(st).total_pressure))


# ──  per-resource independence  ──────────────────────────────────────────


def test_per_resource_independence():
    """competition:canopy is a pure function of the canopy field: a
    different substrate contest in the cell leaves the canopy shade
    untouched (the substrate does not leak into the canopy), while the
    substrate stress moves with it."""
    def build(sward_t: float):
        st = OccupancyState(_cell(), [_oak(), _tussock(), _probe(12.0)])
        st.paint("oak", 200_000.0)         # oak pressure 0.5 — room to move
        st.paint("sward", sward_t)
        return st

    A, B = build(100.0), build(100_000.0)
    probe_view = _probe(12.0).view

    canopy_A = competition_canopy(probe_view, A)
    canopy_B = competition_canopy(probe_view, B)
    assert canopy_A["value"] > 0.0          # the oak shades the probe
    assert canopy_A["value"] == pytest.approx(canopy_B["value"], abs=0.0)
    assert canopy_A["dominant_refs"] == canopy_B["dominant_refs"]
    assert canopy_A["field"] == canopy_B["field"]

    assert competition_substrate(probe_view, A)["value"] \
        != competition_substrate(probe_view, B)["value"]
    assert competition_substrate(probe_view, B)["value"] > \
        competition_substrate(probe_view, A)["value"]


# ──  the n=1 calibration + monoculture limit (B10 §5)  ───────────────────


@pytest.mark.parametrize("p", [0.25, 0.75, 1.0, 2.5])
def test_n1_calibration_matches_f_at_anchor_productivities(p):
    """A lone canopy lineage's self-crowding equilibrium — bisected from
    the crowding system, not read off any formula — equals the prodscale
    target f(p) × L × matching-substrate ha (B10 §5; L = 0.625 of the
    p=1 cell pool, match 1 on full peat)."""
    st = OccupancyState(_cell(p), [_oak()])
    eq = self_crowding_equilibrium_t(st, "oak")
    assert eq == pytest.approx(_cap_t(p), rel=1e-7)
    # the n=1 equation solved is the crowding one: holdings where the
    # lone lineage's own total crowding reaches 1
    st2 = OccupancyState(_cell(p), [_oak()])
    st2.paint("oak", eq)
    total = sum(t["value"]
                for t in competition_stress(_oak().view, st2).values())
    assert total == pytest.approx(1.0, rel=1e-6)


def test_monoculture_limit_is_derived_cap():
    """The monoculture limit: the lone oak's equilibrium is exactly its
    derived cap (substrate_capacity_t — f(p)·L·matching-substrate ha),
    with zero canopy and zero ground-cover contributions: the cap is
    the substrate term's n=1 solution, no separate guardrail."""
    st = OccupancyState(_cell(2.5), [_oak()])
    eq = self_crowding_equilibrium_t(st, "oak")
    assert eq == pytest.approx(substrate_capacity_t(st, "oak"), rel=1e-7)

    st2 = OccupancyState(_cell(2.5), [_oak()])
    st2.paint("oak", eq)
    terms = competition_stress(_oak().view, st2)
    assert terms["competition:canopy"]["value"] == 0.0
    assert terms["competition:ground_cover"]["value"] == 0.0
    assert terms["competition:substrate"]["value"] == pytest.approx(
        1.0, rel=1e-6)
    # the derived cap is nearly productivity-flat above unit: the pool
    # is ×2.5 at p=2.5 while the cap is ×1.04 — productivity buys
    # lineage count, never lineage size (B10 §5)
    assert _cap_t(2.5) / _cap_t(1.0) == pytest.approx(prodscale_f(2.5))
    assert _cap_t(2.5) / _cap_t(1.0) == pytest.approx(1.0375, abs=1e-6)


def test_equilibrium_solver_is_deterministic():
    """Two identical builds solve to the same equilibrium (determinism
    hard rule — the bisection accumulates no randomness)."""
    def solve():
        st = OccupancyState(_cell(0.75), [_oak()])
        return self_crowding_equilibrium_t(st, "oak")
    assert solve() == solve()


# ──  probeability (B10 §4) + purity  ─────────────────────────────────────


def test_stress_is_pure_and_probe_deterministic():
    """The stress functions never mutate the occupancy, and recomputing
    the same probe reads the same landscape (probeable by
    nudge-and-recompute — deterministic and cheap)."""
    st = OccupancyState(_cell(), [_oak(), _tussock(), _probe(12.0)])
    st.paint("oak", 400_000.0)
    st.paint("sward", 20_000.0)
    holdings_before = dict(st.holdings_t)
    pool_before = st.pool_used_t

    probe_view = _probe(12.0).view
    first = competition_stress(probe_view, st)
    second = competition_stress(probe_view, st)

    assert first == second                 # deterministic recompute
    assert st.holdings_t == holdings_before   # pure: nothing mutated
    assert st.pool_used_t == pytest.approx(pool_before)
    # nudging the probe's height recomputes a DIFFERENT landscape
    nudge = competition_canopy(
        dict(probe_view, height_m=25.5), st)
    assert nudge["value"] != first["competition:canopy"]["value"]
    assert nudge["value"] == 0.0
    assert st.holdings_t == holdings_before   # still pure after the nudge


def test_provenance_lists_are_bounded_and_deterministic():
    """Provenance names at most PROVENANCE_TOP_N lineages, ordered by
    field dominance (covered fraction / pressure desc, ties by ref) —
    bounded and deterministic."""
    st = OccupancyState(_cell(),
                        [_oak(), _tussock(), _sphagnum(), _willow()])
    st.paint("oak", 400_000.0)
    st.paint("willow", 200_000.0)
    st.paint("sward", 20_000.0)
    st.paint("moss", 2_000.0)
    view = _oak().view
    first = competition_stress(view, st)
    second = competition_stress(view, st)
    for key, term in first.items():
        assert len(term["dominant_refs"]) <= PROVENANCE_TOP_N
        # deterministic: recomputing reads the same provenance
        assert term["dominant_refs"] == second[key]["dominant_refs"]
        assert len(term["dominant_refs"]) == len(set(term["dominant_refs"]))


# ──  determinism audit  ──────────────────────────────────────────────────


def test_no_nondeterministic_imports():
    """AGENTS.md determinism hard rule: no random/uuid/time/numpy in
    crowding.py (same seed ⇒ byte-identical output)."""
    src = (pathlib.Path(__file__).parent / "crowding.py").read_text()
    for line in src.splitlines():
        stripped = line.strip()
        for bad in ("import random", "from random", "import uuid",
                    "from uuid", "import time", "from time",
                    "import numpy"):
            assert not stripped.startswith(bad), \
                f"crowding.py: forbidden import: {stripped}"
