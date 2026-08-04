"""Fast-tier tests for L3 evolutionary pressure with provenance —
the B10 §4 probe machinery and the §6 acceptance cases (ticket 0051).

Pressure is stress's second effect (B10 §3): the trait backprop through
the responder wiring, the trace recording WHY.  This file covers:

- the probe itself: nudge the committed record axis ± one relative
  probe step (PROBE_REL_STEP), REASSEMBLE the view through the one
  assembler (nudges ripple through derived quantities honestly —
  height changes shade AND mass AND support ratio), recompute the
  term, read the relief; pressure = stress × marginal relief, signed
  toward relief, STRICT ZERO on zero relief, ∝ stress (low stress →
  no pull);
- the machine wiring table (WIRING_TABLE) mirroring the human wiring
  texts in crowding.py and flora/view.py;
- the TraitPressure provenance shape, purity, and determinism;
- the B10 §6 acceptance cases through the FULL stack (content → view →
  occupancy → crowding → dynamics → pressure): A/B, rainforest ≈
  temperate, low-p monoculture, and the shade trap (strict zero deep
  under the canopy, strong pressure through the step).

Cells are built from REAL presets through the content loader + the
canonical view assembler (test_dynamics' fixture style) — and, unlike
test_dynamics, the lineages are deliberately NOT intrinsic-cleaned:
pressure is a property of the record's real landscape (the intrinsic
block rides through the probe's reassembly), so the acceptance cases
run with the real intrinsic leakage.

One documented boundary (orchestrator answer to the bubbled question,
2026-08-04): the shade-trap acceptance's "shade_tolerance pressure
positive" is implemented via the B5 idiom — shade_tolerance ATTENUATES
the canopy competition stress (effective = shade × (1 − tolerance),
crowding.competition_canopy), so tolerance genuinely relieves the
shade term and the probe reads a positive pressure for it.  The
tolerance is wired direction "+" only.

Plain pytest, no marks — runs in milliseconds.
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
    LINEAGE_CAP_POOL_FRACTION,
    prodscale_f,
)
from exp.k15_biosphere.dynamics import (
    CellClimate,
    PH_OPT_LO,
    PH_OPT_SPAN,
    equilibrium_holdings,
)
from exp.k15_biosphere.pressure import (
    PROBE_REL_STEP,
    WIRING_TABLE,
    TraitPressure,
    pressure_probe,
    probe_trait,
)

# The real flora content pack lives in the frozen k13 reference; content
# is shared data, read IN PLACE from there (never copied).
CONTENT_DIR = pathlib.Path(__file__).parent.parent / "k13_treegen" \
    / "content" / "flora"

# Loaded once at module scope: the fixtures below are fast and share it.
_PACK = load_content(CONTENT_DIR)


# ──  fixture builders (test_dynamics' house style)  ──────────────────────


def _record(preset_id: str, **axes_overrides) -> SpeciesRecord:
    """A committed record at the real preset, with optional axis
    overrides (the shade-trap lineages re-author height/crown)."""
    t = _PACK.presets[preset_id]
    axes, generics = merged_preset(t)
    axes = dict(axes)
    axes.update(axes_overrides)
    return SpeciesRecord(sid="0" * 16, plan=t["preset"]["plan"],
                         preset=preset_id, axes=axes, generics=generics)


def _pair(preset_id: str, ref: str, substrate_pref=None,
          **axes_overrides) -> tuple[SpeciesRecord, Lineage]:
    """A (record, lineage) pair: the lineage's view is assembled from
    the record (the only derive path), so pressure_probe's reassembly
    matches the state lineage exactly."""
    rec = _record(preset_id, **axes_overrides)
    return rec, Lineage(ref=ref, view=assemble_view(rec, _PACK),
                        substrate_pref=substrate_pref or {})


def _lineage(preset_id: str, ref: str, **kw) -> Lineage:
    _, ln = _pair(preset_id, ref, **kw)
    return ln


def _cell(productivity: float = 1.0, cell_ha: float = 1600.0,
          mix: dict | None = None) -> CellInput:
    return CellInput(productivity=productivity, cell_ha=cell_ha,
                     substrate_mix=mix or {"peat": 1.0})


def _benign(view: dict, **overrides) -> CellClimate:
    """A climate in-envelope for the lineage (test_dynamics' helper)."""
    wl = float(view.get("waterlogging_tolerance") or 0.0)
    kw = dict(
        temp_c=view.get("temp_opt_c", 15.0),
        moisture=min(float(view.get("moisture_opt") or 0.5), wl),
        ph=PH_OPT_LO + PH_OPT_SPAN * float(view.get("ph_tolerance") or 0.5),
        nutrient=max(float(view.get("fertility_requirement") or 0.0), 0.5),
        salinity=min(float(view.get("salinity_tolerance") or 0.0), 0.05),
        rooting_m=max(float(view.get("root_depth_m") or 0.0), 1.0),
    )
    kw.update(overrides)
    return CellClimate(**kw)


def _cap_t(p: float, match: float = 1.0) -> float:
    """The derived cap f(p) · L · cell_ha · match at 1600 ha."""
    return prodscale_f(p) * LINEAGE_CAP_POOL_FRACTION * POOL_X_T_PER_HA \
        * 1600.0 * match


def _pressures(rec, st: OccupancyState, ref: str
               ) -> dict[str, tuple[TraitPressure, ...]]:
    """pressure_probe wrapped with the fixture pack."""
    return pressure_probe(rec, _PACK, st, ref)


def _entry(pr: dict, stress_key: str, trait: str) -> TraitPressure:
    """The one TraitPressure for (stress key, trait) — the acceptance
    tests index the block this way."""
    for e in pr[stress_key]:
        if e.trait == trait:
            return e
    raise AssertionError(f"no {trait} entry under {stress_key} "
                         f"(have {[e.trait for e in pr[stress_key]]})")


# ──  the probe step and the wiring table (B10 §4)  ───────────────────────


def test_probe_step_constant_documented():
    """The probe step is a small named constant (B10 §4's "one small
    probe step"), RELATIVE to the committed trait value: wired traits
    span orders of magnitude, so an absolute step cannot be marginal
    everywhere."""
    assert isinstance(PROBE_REL_STEP, float)
    assert 0.0 < PROBE_REL_STEP < 1.0


def test_wiring_table_mirrors_the_human_texts():
    """The L3 responder table mirrors the human wiring texts in
    crowding.py and flora/view.py (ticket brief): CANOPY → height_m /
    crown_spread_m / shade_tolerance (the tolerance attenuates the
    shade stress, direction "+" only — B10 §6.4); MECHANICAL →
    crown_spread_m / height_m / wood_density; ENERGETICS →
    root_depth_m / root_spread_m; GROUND_COVER → height_m /
    crown_spread_m / footprint (the mass-hook π·max(clonal, crown)²
    geometry — clonal_spread_m is its second driver); SUBSTRATE →
    root_depth_m / substrate preference (the preference axis is a
    deferred B2 addendum — root_depth_m is the only probeable responder
    today)."""
    canopy = dict(WIRING_TABLE["competition:canopy"])
    assert set(canopy) == {"height_m", "crown_spread_m", "shade_tolerance"}
    assert canopy["shade_tolerance"] == ("+",)   # more tolerance always
                                                 # attenuates more
    mech = {t for t, _ in WIRING_TABLE["mechanical_support"]}
    assert mech == {"crown_spread_m", "height_m", "wood_density"}
    energy = {t for t, _ in WIRING_TABLE["energetics"]}
    assert energy == {"root_depth_m", "root_spread_m"}
    ground = {t for t, _ in WIRING_TABLE["competition:ground_cover"]}
    assert {"height_m", "crown_spread_m", "clonal_spread_m"} <= ground
    substrate = [t for t, _ in WIRING_TABLE["competition:substrate"]]
    assert substrate == ["root_depth_m"]
    # every wired trait lists non-empty allowed directions within ±
    for key, entries in WIRING_TABLE.items():
        for trait, directions in entries:
            assert directions, f"{key}.{trait} has no allowed directions"
            assert set(directions) <= {"+", "-"}, \
                f"{key}.{trait} has invalid directions {directions}"


def test_wiring_keys_are_real_stress_terms():
    """Every machine-wired stress key is a real term the dynamics
    channel reads: the three competition terms from crowding, the two
    intrinsic terms from the view's intrinsic_stress block (B10 §2's
    one channel)."""
    rec, ln = _pair("tree.oak", "oak")
    st = OccupancyState(_cell(), [ln])
    st.paint("oak", 100_000.0)
    comp = {"competition:canopy", "competition:ground_cover",
            "competition:substrate"}
    assert comp <= set(WIRING_TABLE)
    assert set(ln.view["intrinsic_stress"]) <= set(WIRING_TABLE)
    pr = _pressures(rec, st, "oak")
    assert set(pr) == set(WIRING_TABLE)


# ──  the probe: shape, identity, purity, determinism  ────────────────────


def test_trait_pressure_shape_and_identity():
    """Each TraitPressure carries the full provenance (stress term,
    trait, direction, base stress/value, probe step, relief, marginal
    relief, pressure, cause) and satisfies the B10 §4 identity:
    pressure == ±stress × marginal_relief, signed toward relief, and
    direction "none" ⇔ relief == 0 ⇔ pressure == 0."""
    rec, ln = _pair("tree.oak", "oak")
    st = OccupancyState(_cell(), [ln])
    st.paint("oak", 100_000.0)
    for key, entries in _pressures(rec, st, "oak").items():
        for e in entries:
            assert e.stress_key == key and e.trait in dict(WIRING_TABLE[key])
            assert e.probe_step == PROBE_REL_STEP * abs(e.base_value)
            assert e.marginal_relief == pytest.approx(e.relief / e.probe_step
                                                      if e.probe_step else 0.0)
            sign = 1.0 if e.direction == "+" \
                else (-1.0 if e.direction == "-" else 0.0)
            assert e.pressure == pytest.approx(sign * e.stress
                                               * e.marginal_relief)
            assert e.relief >= 0.0
            if e.direction == "none":
                assert e.relief == 0.0 and e.pressure == 0.0
            else:
                assert e.relief > 0.0
                assert (e.pressure > 0.0) == (e.direction == "+")
            assert isinstance(e.cause, str) and e.cause


def test_probe_is_pure_and_deterministic():
    """pressure_probe never mutates the record or the state, and two
    identical probes are byte-stable (determinism hard rule)."""
    rec, ln = _pair("tree.oak", "oak")
    st = OccupancyState(_cell(), [ln])
    st.paint("oak", 100_000.0)
    axes_before = dict(rec.axes)
    holdings_before = dict(st.holdings_t)
    first = _pressures(rec, st, "oak")
    assert rec.axes == axes_before and st.holdings_t == holdings_before
    assert _pressures(rec, st, "oak") == first


def test_probe_trait_rejects_uncommitted_axis():
    """A wired trait the record does not commit (wood_density is not an
    axis of the grass-sward presets) has nothing to probe — the trait
    is not expressed."""
    rec, ln = _pair("grass_sward.tussock", "sward")
    st = OccupancyState(_cell(), [ln])
    st.paint("sward", 10_000.0)
    assert "wood_density" not in rec.axes
    # omitted from the block, not fabricated
    pr = _pressures(rec, st, "sward")
    assert all(e.trait != "wood_density" for e in pr["mechanical_support"])
    with pytest.raises(ValueError):
        probe_trait(rec, _PACK, st, "sward", "mechanical_support",
                    "wood_density")


# ──  the semantics on today's landscape (B10 §4)  ────────────────────────


def test_low_stress_no_pull_top_canopy():
    """A canopy lineage at the top reads canopy stress 0 (nothing above
    it — crowding's quiet) — pressure ∝ stress, so its canopy pressures
    are EXACTLY 0.0: no pull toward height, crown, or shade tolerance
    (B10 §4 low stress → no pull)."""
    rec, ln = _pair("tree.oak", "oak")
    st = OccupancyState(_cell(), [ln])
    st.paint("oak", 200_000.0)
    pr = _pressures(rec, st, "oak")
    for trait in ("height_m", "crown_spread_m", "shade_tolerance"):
        e = _entry(pr, "competition:canopy", trait)
        assert e.stress == 0.0
        assert e.pressure == 0.0 and e.direction == "none"


def test_ground_cover_canopy_lineage_quiet():
    """A canopy-class lineage claims no ground plane: its
    ground_cover stress is 0 and every wired ground-cover pressure is
    exactly 0 (stress ∝ pressure — no pull)."""
    rec, ln = _pair("tree.oak", "oak")
    st = OccupancyState(_cell(), [ln])
    st.paint("oak", 200_000.0)
    pr = _pressures(rec, st, "oak")
    for e in pr["competition:ground_cover"]:
        assert e.stress == 0.0 and e.pressure == 0.0 \
            and e.direction == "none"


def test_substrate_relieved_by_partitioning_not_root_depth():
    """competition:substrate reads holdings + substrate preference, not
    root depth (crowding.SUBSTRATE_WIRING: "substrate → roots", relieved
    by PARTITIONING — B10 §2's only true escape).  The probe reads zero
    marginal relief for root_depth_m, so its pressure is EXACTLY 0.0
    (strict zero) even under a heavy substrate contest."""
    rec, ln = _pair("tree.oak", "oak")
    st = OccupancyState(_cell(), [ln])
    st.paint("oak", 300_000.0)       # substrate stress 0.75
    e = _entry(_pressures(rec, st, "oak"), "competition:substrate",
               "root_depth_m")
    assert e.stress == pytest.approx(0.75)
    assert e.relief == 0.0 and e.pressure == 0.0 \
        and e.direction == "none"


def test_mechanical_directions_from_the_landscape():
    """The mechanical probe reads the real support-ratio landscape, not
    a hand-shaped rule: the oak (support_ratio 37.5 in [8, 120]) relieves
    by growing taller OR spreading its crown (both move the ratio toward
    the envelope center — the plateau's weak leakage), so height reads
    "+" and crown reads "−"; wood_density does not enter the
    support-ratio metric, so it reads strict zero."""
    rec, ln = _pair("tree.oak", "oak")
    st = OccupancyState(_cell(), [ln])
    st.paint("oak", 100_000.0)
    pr = _pressures(rec, st, "oak")
    h = _entry(pr, "mechanical_support", "height_m")
    c = _entry(pr, "mechanical_support", "crown_spread_m")
    w = _entry(pr, "mechanical_support", "wood_density")
    assert h.stress == pytest.approx(0.0094643, rel=1e-4)
    assert h.direction == "+" and 0.0 < h.pressure < 1e-4
    assert c.direction == "-" and -1e-4 < c.pressure < 0.0
    assert w.direction == "none" and w.relief == 0.0 and w.pressure == 0.0


def test_energetics_knobs_locked_per_plan():
    """The energetics proportion knobs (root_shoot) are locked
    per-plan constants in mass.py today — wired root_depth_m /
    root_spread_m move nothing, so both read strict zero (the honest
    landscape; the wiring graduates with content)."""
    rec, ln = _pair("tree.oak", "oak")
    st = OccupancyState(_cell(), [ln])
    st.paint("oak", 100_000.0)
    pr = _pressures(rec, st, "oak")
    for trait in ("root_depth_m", "root_spread_m"):
        e = _entry(pr, "energetics", trait)
        assert e.relief == 0.0 and e.pressure == 0.0 \
            and e.direction == "none"


def test_sward_height_relieves_ground_contest():
    """A sward's ground-cover contest is relieved by its own geometry:
    the per-area mass model makes a TALLER sward carry the same biomass
    on less area (fewer individuals, less covered fraction → less
    contest), so height reads a real "+" pressure; crown/clonal moves
    leave the per-area cover invariant (mass ∝ area), reading strict
    zero.  (The ground contest itself is relieved by partitioning — the
    probe measures what the landscape actually pays.)"""
    rec, ln = _pair("grass_sward.tussock", "sward")
    st = OccupancyState(_cell(), [ln])
    st.paint("sward", 20_000.0)
    pr = _pressures(rec, st, "sward")
    h = _entry(pr, "competition:ground_cover", "height_m")
    assert h.stress > 0.0
    assert h.direction == "+" and 0.0 < h.pressure < 1.0
    for trait in ("crown_spread_m", "clonal_spread_m"):
        e = _entry(pr, "competition:ground_cover", trait)
        assert e.relief == 0.0 and e.pressure == 0.0


# ──  B10 §6 acceptance cases — the full stack  ───────────────────────────


def test_ab_equilibrium_and_pressure():
    """B10 §6.1 THROUGH THE FULL STACK (content → view → occupancy →
    crowding → dynamics → pressure): the same oak at p=2.5 vs p=0.75
    settles at the nearly-productivity-flat derived cap — the holding
    ratio tracks f (≈1.157), never the pool (×3.33) — while the pool
    remainders contrast enormously: A leaves ~1.19M t (rich
    understory headroom), B's canopy leaves ~126k t (near-exhaustion).
    The pressure block at each equilibrium reads the lineage's real
    landscape: canopy stress 0 (it IS the top — no pull), substrate
    contest ≈ 1 − intrinsic (the channel ≈ 1 at equilibrium) with zero
    relief on root_depth_m, and the mechanical plateau's weak leakage
    toward taller/shorter."""
    def solve(p: float) -> tuple[dict, OccupancyState]:
        rec, ln = _pair("tree.oak", "oak")
        st = OccupancyState(_cell(p), [ln])
        eq = equilibrium_holdings(st, _benign(ln.view))
        st.paint("oak", eq["oak"])
        return rec, st

    rec_rich, st_rich = solve(2.5)
    rec_poor, st_poor = solve(0.75)
    eq_rich = st_rich.holdings_t["oak"]
    eq_poor = st_poor.holdings_t["oak"]
    rem_rich = st_rich.pool_remainder_t
    rem_poor = st_poor.pool_remainder_t

    # holdings track the f-ratio (≈1.157), nowhere near the pool ratio
    assert eq_rich / eq_poor == pytest.approx(
        prodscale_f(2.5) / prodscale_f(0.75), rel=1e-6)
    assert eq_rich / eq_poor == pytest.approx(1.157, abs=1e-3)
    assert (rem_rich + eq_rich) / (rem_poor + eq_poor) \
        == pytest.approx(3.333, rel=1e-3)        # the pool ratio, for contrast
    # magnitudes: ~1.2M vs ~80–120k
    assert eq_rich == pytest.approx(4.098e5, rel=1e-3)
    assert eq_poor == pytest.approx(3.541e5, rel=1e-3)
    assert rem_rich == pytest.approx(1.19e6, rel=2e-2)
    assert rem_poor == pytest.approx(1.26e5, rel=2e-2)
    assert rem_rich / rem_poor > 5.0

    # the pressure block at each equilibrium (full-stack read)
    for rec, st in ((rec_rich, st_rich), (rec_poor, st_poor)):
        pr = _pressures(rec, st, "oak")
        for trait in ("height_m", "crown_spread_m", "shade_tolerance"):
            e = _entry(pr, "competition:canopy", trait)
            assert e.stress == 0.0 and e.pressure == 0.0
        sub = _entry(pr, "competition:substrate", "root_depth_m")
        assert sub.stress == pytest.approx(0.9875, abs=1e-3)
        assert sub.pressure == 0.0               # partitioning, not roots
        h = _entry(pr, "mechanical_support", "height_m")
        assert h.direction == "+" and 0.0 < h.pressure < 1e-4


def test_rainforest_equals_temperate():
    """B10 §6.2 THROUGH THE FULL STACK: a moist tropical cell (p=2.5,
    several canopy lineages partitioning the substrate classes) and a
    temperate cell (p=0.75, few) pack ROUGHLY EQUAL total adult canopy
    biomass — within the f-ratio (≈1.157), nowhere near the pool ratio
    (×3.33) — with MORE lineages each holding FEWER at high p
    (partitioning splits the geometric per-class caps; productivity
    buys lineage count, never lineage size).  Each lineage settles at
    its ISOLATED match-scaled cap (B10 §5: f(p)·L·cell_ha·match[s]).

    DEFERRED (ticket note): the sapling-count half of §6.2 needs age
    structure (the L2/L3 occupancy holds biomass only) — noted, not
    tested."""
    # rainforest: 3 same-species canopy lineages, each on its own third
    # of a clay/sand/silt cell — disjoint preferences partition the cell
    mix3 = {"clay": 1 / 3, "sand": 1 / 3, "silt": 1 / 3}
    lins = [_lineage("tree.oak", f"oak_{s}", substrate_pref={s: 1.0})
            for s in ("clay", "sand", "silt")]
    st_hi = OccupancyState(_cell(2.5, mix=mix3), lins)
    eq_hi = equilibrium_holdings(st_hi, _benign(lins[0].view))
    tot_hi = sum(eq_hi.values())

    # temperate: one broadleaf canopy on the uniform cell
    rec_lo, ln_lo = _pair("tree.oak", "oak")
    st_lo = OccupancyState(_cell(0.75), [ln_lo])
    eq_lo = equilibrium_holdings(st_lo, _benign(ln_lo.view))
    tot_lo = eq_lo["oak"]

    # roughly equal totals: within the f-ratio, nowhere near ×3.33
    assert tot_hi / tot_lo == pytest.approx(
        prodscale_f(2.5) / prodscale_f(0.75), rel=1e-6)
    assert tot_hi / tot_lo == pytest.approx(1.157, abs=1e-3)
    # more lineages each holding fewer at high p: each rainforest
    # lineage holds ~its per-class cap (total/3), each < the temperate
    # monoculture's holding
    assert eq_hi["oak_clay"] == pytest.approx(tot_hi / 3, rel=1e-9)
    # each settles at its ISOLATED match-scaled cap, pulled ~1.25%
    # below it by the real intrinsic leakage (not the cleaned fixture —
    # the substrate factor 0.9875 is pinned in the A/B test)
    assert eq_hi["oak_clay"] == pytest.approx(
        _cap_t(2.5, match=1 / 3), rel=1.5e-2)
    assert eq_hi["oak_clay"] < eq_lo["oak"]
    assert len(eq_hi) == 3 and len(eq_lo) == 1
    # the pressure block on one rainforest lineage at its equilibrium
    rec_hi, _ = _pair("tree.oak", "oak_clay", substrate_pref={"clay": 1.0})
    for ref, x in eq_hi.items():
        st_hi.paint(ref, x)
    pr = _pressures(rec_hi, st_hi, "oak_clay")
    e = _entry(pr, "competition:canopy", "height_m")
    assert e.stress == 0.0 and e.pressure == 0.0   # top of its class
    sub = _entry(pr, "competition:substrate", "root_depth_m")
    assert sub.stress == pytest.approx(0.9875, abs=1e-3)


def test_low_p_favorable_monoculture_pressure():
    """B10 §6.3 THROUGH THE FULL STACK: at low p with a favorable
    climate the well-adapted canopy lineage settles at its derived cap
    and the sward is EXCLUDED (over-constrained at zero — shade + full
    substrate contest) — near-monoculture, the pool binds.  The
    pressure block at the equilibrium reads the surviving lineage's
    landscape (canopy quiet at the top; substrate contest ≈ 1 −
    intrinsic with no root-depth relief)."""
    rec_oak, oak = _pair("tree.oak", "oak")
    sward = _lineage("grass_sward.tussock", "sward")
    st = OccupancyState(_cell(0.75), [oak, sward])
    eq = equilibrium_holdings(st, _benign(oak.view))
    st.paint("oak", eq["oak"])
    assert eq["sward"] == 0.0                       # excluded exactly
    assert eq["oak"] == pytest.approx(_cap_t(0.75), rel=2e-2)
    assert eq["oak"] / st.pool_t > 0.7              # the pool binds
    pr = _pressures(rec_oak, st, "oak")
    e = _entry(pr, "competition:canopy", "height_m")
    assert e.stress == 0.0 and e.pressure == 0.0
    sub = _entry(pr, "competition:substrate", "root_depth_m")
    assert sub.stress == pytest.approx(0.9875, abs=1e-3)
    assert sub.pressure == 0.0


def test_shade_trap_strict_zero_and_step():
    """B10 §6.4 — THE SHADE TRAP, probed: a lineage deep under a high
    canopy reads STRICTLY ZERO height pressure (the shade is high but
    FLAT in its neighbourhood — an evolutionary leap with no benefit in
    the middle — so it is NOT pulled toward height; exact 0.0, not
    epsilon) and a POSITIVE shade_tolerance pressure (tolerance
    attenuates the shade term — effective = shade × (1 − tolerance) —
    so adapting toward tolerance pays immediately: the shade-trap
    escape).  A lineage one probe step below the canopy top feels the
    step: nudging height crosses the top stratum's coverage, the shade
    drops to zero, and the height pressure is STRONG (relief == the
    shade itself), while its shade_tolerance pressure is ~zero relative
    to it (at the base the top is right above its crown — the
    tolerance channel is negligible next to the height step).  The
    near-top move is exactly the time-reversal-local case: every
    intermediate step from just-below to through is motivated (B10 §4)."""
    # the shared canopy: a 25 m oak at 200 kt — raw shade ≈ 0.263,
    # attenuated by the oak-record's 0.35 tolerance → effective 0.171
    _, oak = _pair("tree.oak", "oak")
    raw_shade = 0.2626
    tol = 0.35
    effective = raw_shade * (1.0 - tol)

    # deep understory: a 5 m tree under the oak
    rec_deep, deep = _pair("tree.oak", "understory",
                           height_m=5.0, crown_spread_m=8.0)
    st = OccupancyState(_cell(), [oak, deep])
    st.paint("oak", 200_000.0)
    st.paint("understory", 10_000.0)
    pr = _pressures(rec_deep, st, "understory")
    h = _entry(pr, "competition:canopy", "height_m")
    assert h.stress > 0.0                    # genuinely shaded (not vacuous)
    assert h.stress == pytest.approx(effective, abs=1e-3)
    assert h.relief == 0.0                   # flat benefit zone: no relief
    assert h.pressure == 0.0                 # STRICTLY zero — exact, not
                                             # epsilon (B10 §4)
    assert h.direction == "none"
    c = _entry(pr, "competition:canopy", "crown_spread_m")
    assert c.pressure == 0.0
    # the shade-trap escape: shade_tolerance pressure is POSITIVE —
    # tolerance genuinely relieves the shade term (B10 §6.4): the
    # marginal relief is the RAW shade per unit tolerance, so
    # pressure = effective × raw > 0
    t = _entry(pr, "competition:canopy", "shade_tolerance")
    assert t.direction == "+"
    assert t.stress == pytest.approx(effective, abs=1e-3)
    raw_actual = t.stress / (1.0 - tol)      # back out the raw shade
    assert t.marginal_relief == pytest.approx(raw_actual, rel=1e-9)
    assert t.pressure > 0.0
    assert t.pressure == pytest.approx(t.stress * t.marginal_relief,
                                       rel=1e-9)

    # just below the canopy top: a 24.99 m tree under the same oak —
    # +0.1% of 24.99 (PROBE_REL_STEP) clears the 25 m top stratum
    rec_near, near = _pair("tree.oak", "near_top", height_m=24.99)
    st2 = OccupancyState(_cell(), [oak, near])
    st2.paint("oak", 200_000.0)
    st2.paint("near_top", 10_000.0)
    pr2 = _pressures(rec_near, st2, "near_top")
    h2 = _entry(pr2, "competition:canopy", "height_m")
    assert h2.stress == pytest.approx(effective, abs=1e-3)
    assert h2.direction == "+"
    assert h2.relief == h2.stress            # shade drops to zero exactly
    assert h2.pressure > 1.0                 # strong — dragged through
    assert h2.pressure == pytest.approx(h2.stress * h2.stress
                                        / h2.probe_step, rel=1e-9)
    # ~zero shade_tolerance pressure next to the height step: the
    # canopy top is right above its crown, so tolerance still pays a
    # little (the oak above it) — but an order of magnitude below the
    # height channel (a lineage AT the top reads exactly 0, asserted in
    # test_low_stress_no_pull_top_canopy)
    t2 = _entry(pr2, "competition:canopy", "shade_tolerance")
    assert t2.pressure == pytest.approx(t2.stress * t2.marginal_relief,
                                        rel=1e-9)
    assert 0.0 < t2.pressure < 0.05 * h2.pressure


# ──  determinism audit  ──────────────────────────────────────────────────


def test_no_nondeterministic_imports():
    """AGENTS.md determinism hard rule: no random/uuid/time/numpy in
    pressure.py (same seed ⇒ byte-identical output)."""
    src = (pathlib.Path(__file__).parent / "pressure.py").read_text()
    for line in src.splitlines():
        stripped = line.strip()
        for bad in ("import random", "from random", "import uuid",
                    "from uuid", "import time", "from time",
                    "import numpy"):
            assert not stripped.startswith(bad), \
                f"pressure.py: forbidden import: {stripped}"
