"""Fast-tier tests for L3 dynamics — environmental stress, the one-channel
assembly, vital rates, vital suppression, and the equilibrium solver
(ticket 0049; spec B10 §2, §3, §5, §6 — environmental shapes per B5).

Cells are built from REAL presets through the content loader + the
canonical view assembler, following test_occupancy / test_crowding's
fixture style: the canopy oak (25 m — the A/B canopy actor), the 15 m
willow (a second, lower canopy stratum), the grass sward, and the moss
mat.  Covers:

- the B5 §4 environmental shapes: the T split (pressure:cold/heat —
  product = the symmetric envelope distance), the one-sided water /
  waterlogging / ph / fertility / salinity / rooting terms, the signed
  composition F = Π f, s_env = 1 - 2F (Liebig tail-dominance, the
  vigor gradient);
- the one-channel assembly (B10 §2): channel == max(0, s_env) +
  intrinsic + competition, per-term provenance preserved;
- vital rates as pure view functions (rebuild — the shapes and the
  presets' viability);
- vital suppression (B10 §3): zero stress = baseline rates, monotone
  birth-down / death-up, net = (b - d)(1 - σ), breakeven at channel 1;
- the equilibrium solver (B10 §5): n=1 reproduces
  self_crowding_equilibrium_t (the derived cap), lower equilibrium
  under stress, the A/B fixture, low-p near-monoculture, the quadrant
  shapes, and the GEOMETRIC partitioning equilibrium on mixed
  substrate cells (ticket 0050: specialists settle at their
  match-scaled cap, disjoint-preference lineages solve as isolated
  monocultures), determinism, and input purity.

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
    competition_stress,
    prodscale_f,
    self_crowding_equilibrium_t,
    substrate_capacity_t,
)
from exp.k15_biosphere.dynamics import (
    CellClimate,
    DEATH_MAX,
    DEATH_MIN,
    EQUILIBRIUM_SWEEP_BUDGET,
    PH_BREADTH,
    PH_OPT_LO,
    PH_OPT_SPAN,
    compose_suitabilities,
    environment_stress,
    equilibrium_holdings,
    net_growth_rate,
    total_stress,
    vital_rates,
)

# The real flora content pack lives in the frozen k13 reference; content
# is shared data, read IN PLACE from there (never copied).
CONTENT_DIR = pathlib.Path(__file__).parent.parent / "k13_treegen" \
    / "content" / "flora"

# Loaded once at module scope: the fixtures below are fast and share it.
_PACK = load_content(CONTENT_DIR)


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
    """tree.oak: 25 m canopy — the A/B canopy actor."""
    return _lineage("tree.oak", "oak", **kw)


def _willow(**kw) -> Lineage:
    """tree.willow: 15 m canopy — a second, lower canopy stratum."""
    return _lineage("tree.willow", "willow", **kw)


def _tussock(ref: str = "sward", **kw) -> Lineage:
    """grass_sward.tussock: sward layer, footprint-driven ground cover."""
    return _lineage("grass_sward.tussock", ref, **kw)


def _sphagnum(ref: str = "moss", **kw) -> Lineage:
    """moss_grade.sphagnum: ground layer, kg_m2 (per-area) cover."""
    return _lineage("moss_grade.sphagnum", ref, **kw)


def _cell(productivity: float = 1.0, cell_ha: float = 1600.0,
          mix: dict | None = None) -> CellInput:
    """A 256²-resolution cell (1600 ha) at the default productivity,
    full-peat substrate unless the caller provides a mix."""
    return CellInput(productivity=productivity, cell_ha=cell_ha,
                     substrate_mix=mix or {"peat": 1.0})


def _clean(ln: Lineage) -> Lineage:
    """The lineage with its intrinsic block ZEROED — the crowding-only
    calibration fixture (B10 §5's cap is the n=1 solution of the
    CROWDING system; intrinsic stress is a separate family that would
    pull the equilibrium slightly below the cap)."""
    view = dict(ln.view)
    zeroed = {}
    for key, term in (view.get("intrinsic_stress") or {}).items():
        zeroed[key] = dict(term, value=0.0, cause="zeroed (test fixture)")
    view["intrinsic_stress"] = zeroed
    return Lineage(ref=ln.ref, view=view, substrate_pref=ln.substrate_pref,
                   demand_t=ln.demand_t)


def _benign(view: dict, **overrides) -> CellClimate:
    """A climate in-envelope for the lineage: every axis reads its
    optimum, so s_env < 0 (vigor) — zero environmental suppression.
    (The oak's moisture_opt sits above its waterlogging tolerance, so
    its moisture is clamped to the tolerance — still vigor.)"""
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


# ──  CellClimate: the separate L3 input  ─────────────────────────────────


def test_cell_climate_is_a_separate_input():
    """CellClimate carries the cell's climate/edaphic fields (B5 §3) —
    a separate input from occupancy's CellInput (which is untouched)."""
    c = CellClimate(temp_c=10.0, moisture=0.5, ph=6.5,
                    nutrient=0.6, salinity=0.05, rooting_m=2.0)
    assert c.moisture == 0.5 and c.rooting_m == 2.0
    # CellInput carries no climate fields (its docstring: "NO climate
    # fields — those are L3's business")
    assert "temp_c" not in CellInput.__dataclass_fields__
    assert "moisture" not in CellInput.__dataclass_fields__


def test_cell_climate_validates():
    """Fields validate on construction: moisture/nutrient/salinity on
    [0, 1], ph on [0, 14], rooting_m >= 0, everything finite."""
    with pytest.raises(ValueError):
        CellClimate(temp_c=10.0, moisture=1.5, ph=6.5,
                    nutrient=0.6, salinity=0.05, rooting_m=2.0)
    with pytest.raises(ValueError):
        CellClimate(temp_c=10.0, moisture=0.5, ph=15.0,
                    nutrient=0.6, salinity=0.05, rooting_m=2.0)
    with pytest.raises(ValueError):
        CellClimate(temp_c=10.0, moisture=0.5, ph=6.5,
                    nutrient=0.6, salinity=-0.1, rooting_m=2.0)
    with pytest.raises(ValueError):
        CellClimate(temp_c=10.0, moisture=0.5, ph=6.5,
                    nutrient=0.6, salinity=0.05, rooting_m=-1.0)
    with pytest.raises(ValueError):
        CellClimate(temp_c=float("nan"), moisture=0.5, ph=6.5,
                    nutrient=0.6, salinity=0.05, rooting_m=2.0)
    with pytest.raises(ValueError):
        CellClimate(temp_c="warm", moisture=0.5, ph=6.5,
                    nutrient=0.6, salinity=0.05, rooting_m=2.0)


# ──  environmental stress shapes (B5 §4)  ────────────────────────────────


def test_temperature_split_product_is_symmetric_distance():
    """B5 §4.1: the T requirement is SPLIT one-sided — pressure:cold
    (saturating shortfall below the optimum) and pressure:heat
    (saturating excess past it) — and their PRODUCT is the symmetric
    envelope distance (F unchanged by the split)."""
    view = _oak().view
    t_opt = view["temp_opt_c"]
    t_breadth = view["temp_breadth_c"]

    def product_at(temp: float) -> float:
        terms = environment_stress(view, _benign(
            view, temp_c=temp))
        return (terms["environment:cold"]["value"]
                * terms["environment:heat"]["value"])

    # at the optimum both read 1
    assert product_at(t_opt) == pytest.approx(1.0)
    # half a breadth below: cold 0.5, heat 1 — product 0.5, exactly
    # the two-sided distance 1 - sat(0.5)
    below = product_at(t_opt - 0.5 * t_breadth)
    above = product_at(t_opt + 0.5 * t_breadth)
    assert below == pytest.approx(0.5)
    assert above == pytest.approx(0.5)
    # saturating: one full breadth is lethal, further is flat at 0
    assert product_at(t_opt - t_breadth) == pytest.approx(0.0)
    assert product_at(t_opt + 2.0 * t_breadth) == pytest.approx(0.0)
    # symmetric: the split is orientation-blind
    assert below == pytest.approx(above)


def test_water_terms_one_sided():
    """B5 §4.2: pressure:water is the DRY end — one-sided shortfall of
    water_potential below the derived moisture need; pressure:
    waterlogging is the SATURATED end — one-sided excess above the
    waterlogging tolerance.  (drought_tolerance lives INSIDE the
    envelope — no double-counting.)"""
    view = _oak().view
    m_opt = view["moisture_opt"]
    m_breadth = view["moisture_breadth"]
    wl_tol = view["waterlogging_tolerance"]

    terms = environment_stress(view, _benign(view))
    # at the benign moisture the water term is ~1 (the oak's optimum
    # sits a hair above its waterlogging tolerance)
    assert terms["environment:water"]["value"] > 0.9
    assert terms["environment:waterlogging"]["value"] == pytest.approx(1.0)

    # dry end: water f = 1 - sat(shortfall/breadth), saturated beyond
    terms = environment_stress(view, _benign(view, moisture=0.0))
    assert terms["environment:water"]["value"] == pytest.approx(
        1.0 - min(1.0, m_opt / m_breadth))
    # wet end: waterlogging f = 1 - sat((moist - wl_tol)/WL_REF), one
    # WL_REF width of saturation above the tolerance is lethal
    terms = environment_stress(view, _benign(view, moisture=wl_tol + 0.3))
    assert terms["environment:waterlogging"]["value"] == 0.0
    terms = environment_stress(view, _benign(view, moisture=wl_tol + 0.15))
    assert terms["environment:waterlogging"]["value"] == pytest.approx(0.5)


def test_ground_and_tail_terms_one_sided():
    """B5 §4.2/§4.3: ph (position optimum 4 + 5·ph_tolerance, fixed ±1.0
    breadth), fertility (shortfall below the requirement), salinity
    (excess above the tolerance), rooting (saturating EXCESS of root
    depth over the substrate — never a cutoff)."""
    view = _oak().view
    ph_opt = PH_OPT_LO + PH_OPT_SPAN * view["ph_tolerance"]
    fert = view["fertility_requirement"]
    sal = view["salinity_tolerance"]
    root = view["root_depth_m"]

    assert environment_stress(view, _benign(view))["environment:ph"][
        "value"] == pytest.approx(1.0)
    terms = environment_stress(view, _benign(view, ph=ph_opt - PH_BREADTH))
    assert terms["environment:ph"]["value"] == 0.0
    # a neutral cell (pH 7) is within the oak's ±1 breadth at most
    terms = environment_stress(view, _benign(view, ph=7.0))
    assert 0.0 <= terms["environment:ph"]["value"] <= 1.0

    terms = environment_stress(view, _benign(view, nutrient=0.0))
    assert terms["environment:fertility"]["value"] == pytest.approx(
        1.0 - min(1.0, fert / 0.2))
    terms = environment_stress(view, _benign(view, nutrient=fert))
    assert terms["environment:fertility"]["value"] == pytest.approx(1.0)

    # salinity: oak tolerance 0.05; a coastal cell at 0.25 costs half
    terms = environment_stress(view, _benign(view, salinity=sal + 0.05))
    assert terms["environment:salinity"]["value"] == pytest.approx(0.5)
    terms = environment_stress(view, _benign(view, salinity=0.0))
    assert terms["environment:salinity"]["value"] == pytest.approx(1.0)

    # rooting: substrate one metre shallower than the roots is lethal;
    # deeper substrate is quiet
    terms = environment_stress(view, _benign(view, rooting_m=root - 1.0))
    assert terms["environment:rooting"]["value"] == 0.0
    terms = environment_stress(view, _benign(view, rooting_m=root))
    assert terms["environment:rooting"]["value"] == pytest.approx(1.0)


def test_composition_signed_scale_and_liebig():
    """B5 §4: F = Π strata, s_env = 1 - 2F on [-1, +1] — +1 lethal,
    0 the viability breakeven, -1 maximal vigor; the product keeps
    Liebig tail-dominance (one failed axis dominates), and the good end
    keeps its gradient (a merely acceptable cell reads closer to 0 than
    an ideal one, still < 0)."""
    # empty block: nothing is wrong anywhere
    assert compose_suitabilities({}) == (1.0, -1.0)
    # two strata: product and signed stress
    terms = {"a": {"value": 0.5}, "b": {"value": 1.0}}
    assert compose_suitabilities(terms) == (0.5, 0.0)     # breakeven
    terms = {"a": {"value": 1.0}, "b": {"value": 0.0}}
    assert compose_suitabilities(terms) == (0.0, 1.0)     # lethal

    # the real block: the benign oak climate is all-vigor (s_env < 0),
    # and one failed axis takes the block to ~lethal
    view = _oak().view
    benign = environment_stress(view, _benign(view))
    F, s = compose_suitabilities(benign)
    assert s < 0.0 and -1.0 < s      # vigor, but not maximal (0.91 water)
    hostile = environment_stress(
        view, _benign(view, temp_c=view["temp_opt_c"] + 2.0
                      * view["temp_breadth_c"]))
    F2, s2 = compose_suitabilities(hostile)
    assert F2 == pytest.approx(0.0)
    assert s2 == pytest.approx(1.0)   # one failed axis -> s ≈ +1

    # the vigor gradient: merely-acceptable (one axis mildly off) reads
    # closer to 0 than ideal, still below the breakeven
    mild = environment_stress(
        view, _benign(view, temp_c=view["temp_opt_c"]
                      + 0.25 * view["temp_breadth_c"]))
    _, s_mild = compose_suitabilities(mild)
    assert 0.0 > s_mild > s           # -0.82 < s_mild < 0


def test_environment_provenance():
    """Each environmental term carries its scalar suitability, the raw
    saturating distance, a human cause, the field read, and the
    responder wiring — probeable provenance per axis (B10 §2)."""
    view = _oak().view
    terms = environment_stress(view, _benign(view))
    assert set(terms) == {
        "environment:cold", "environment:heat", "environment:water",
        "environment:waterlogging", "environment:ph",
        "environment:fertility", "environment:salinity",
        "environment:rooting",
    }
    for key, term in terms.items():
        assert term["key"] == key
        assert 0.0 <= term["value"] <= 1.0
        assert term["distance"] >= 0.0
        assert isinstance(term["cause"], str) and term["cause"]
        assert isinstance(term["field"], dict)
        assert "wiring" in term and term["wiring"]
    # the provenance names the envelope read
    assert terms["environment:cold"]["field"]["temp_opt_c"] \
        == view["temp_opt_c"]
    assert terms["environment:ph"]["field"]["ph_opt"] \
        == PH_OPT_LO + PH_OPT_SPAN * view["ph_tolerance"]


def test_environment_is_pure_and_probeable():
    """The environmental block never mutates (view, climate), recomputes
    identically, and is probeable by nudge-and-recompute (B10 §4)."""
    view = _oak().view
    climate = _benign(view)
    before = dict(view)
    first = environment_stress(view, climate)
    second = environment_stress(view, climate)
    assert first == second                 # deterministic recompute
    assert view == before                  # pure: nothing mutated
    # nudge a view trait: deeper roots read a cost where there was none
    nudged = dict(view, root_depth_m=view["root_depth_m"] + 1.0)
    assert environment_stress(nudged, climate)["environment:rooting"][
        "value"] == 0.0
    assert environment_stress(view, climate)["environment:rooting"][
        "value"] == 1.0
    # nudge the climate: hotter cell moves the heat term
    hotter = environment_stress(
        view, _benign(view, temp_c=view["temp_opt_c"]
                      + 0.5 * view["temp_breadth_c"]))
    assert hotter["environment:heat"]["value"] \
        != first["environment:heat"]["value"]
    # missing keys read the neutral (f = 1) — a degenerate probe view on
    # a trait-neutral cell (dry, neutral pH, no salinity, deep substrate)
    neutral = environment_stress(
        {"plan": "tree"},
        CellClimate(temp_c=15.0, moisture=0.0, ph=6.5, nutrient=0.5,
                    salinity=0.0, rooting_m=2.0))
    assert all(t["value"] == 1.0 for t in neutral.values())


# ──  the one-channel assembly (B10 §2)  ──────────────────────────────────


def test_total_stress_one_channel_with_provenance():
    """total_stress sums the three families through ONE channel:
    channel == max(0, s_env) + Σ intrinsic + Σ competition, with every
    term's provenance preserved under its family key (B10 §2)."""
    st = OccupancyState(_cell(), [_oak(), _tussock()])
    st.paint("oak", 200_000.0)
    st.paint("sward", 20_000.0)
    view = _oak().view
    climate = _benign(view)

    verdict = total_stress(view, st, climate)
    # the channel is the closed-form sum, independently recomputed
    env = environment_stress(view, climate)
    _, s_env = compose_suitabilities(env)
    intrinsic = sum(t["value"] for t in verdict["intrinsic"].values())
    competition = sum(t["value"] for t in verdict["competition"].values())
    assert verdict["channel"] == pytest.approx(
        max(0.0, s_env) + intrinsic + competition, rel=1e-12)
    assert verdict["s_env"] == pytest.approx(s_env)
    assert verdict["environment"] == env
    # provenance: the view's intrinsic block rides through untouched
    assert verdict["intrinsic"] == view["intrinsic_stress"]
    # competition block from crowding
    assert verdict["competition"] == competition_stress(view, st)
    # a benign climate contributes no suppression (vigor)
    assert max(0.0, s_env) == 0.0
    assert verdict["channel"] > 0.0       # intrinsic + competition only


def test_total_stress_vigor_does_not_suppress():
    """Vigor (s_env < 0) floors to zero in the channel: a favorable
    lineage's environmental block suppresses nothing (B10 §5 — the cap
    is the crowding equilibrium)."""
    view = _oak().view
    st = OccupancyState(_cell(), [_oak()])
    verdict = total_stress(view, st, _benign(view))
    assert verdict["s_env"] < 0.0
    assert max(0.0, verdict["s_env"]) == 0.0
    # the same cell, hostile: the channel gains the environmental cost
    hostile = total_stress(
        view, st, _benign(view, temp_c=view["temp_opt_c"]
                          + view["temp_breadth_c"]))
    assert hostile["s_env"] > 0.0
    assert hostile["channel"] > verdict["channel"]


# ──  vital rates (rebuild — pure view functions)  ────────────────────────


def test_vital_rates_shapes():
    """Birth falls with propagule mass (small seeds, many offspring),
    death falls with per-capita mass (big organisms die slowly — the
    rebuilt longevity law), establishment falls with propagule mass and
    stays in [0, 1]; everything bounded."""
    view = dict(_oak().view)
    small = vital_rates(dict(view, propagule_mass_mg=0.01))
    big = vital_rates(dict(view, propagule_mass_mg=5000.0))
    assert small.birth > big.birth
    assert small.establish > big.establish
    assert big.establish <= 1.0

    light = vital_rates(dict(view, mass_total_kg=0.1))
    heavy = vital_rates(dict(view, mass_total_kg=1e5))
    assert light.death > heavy.death
    assert DEATH_MIN <= heavy.death <= DEATH_MAX
    assert light.birth == vital_rates(view).birth     # mass does not
    assert light.establish == vital_rates(view).establish  # touch these

    # pure: same view, same rates; a nudge changes them
    assert vital_rates(view) == vital_rates(view)
    assert vital_rates(view) != vital_rates(dict(view, height_m=5.0))


@pytest.mark.parametrize("preset,ref", [
    ("tree.oak", "oak"), ("tree.willow", "willow"),
    ("grass_sward.tussock", "sward"), ("moss_grade.sphagnum", "moss"),
])
def test_presets_are_viable(preset, ref):
    """The four content presets' rebuilt vital rates are VIABLE (birth >
    death at zero stress — they can establish) and bounded."""
    rates = vital_rates(_lineage(preset, ref).view)
    assert 0.0 < rates.birth <= 100.0
    assert DEATH_MIN <= rates.death <= DEATH_MAX
    assert 0.0 < rates.establish <= 1.0
    assert rates.birth > rates.death


# ──  vital suppression (B10 §3 effect 1)  ────────────────────────────────


def test_zero_stress_is_baseline_rates():
    """At zero channel (clean view, benign climate, zero holdings) the
    effective rates ARE the baseline rates: birth_eff == birth,
    death_eff == death, net == birth - death."""
    ln = _clean(_oak())
    st = OccupancyState(_cell(), [ln])
    ledger = net_growth_rate(ln.view, st, _benign(ln.view))
    assert ledger["sigma"] == 0.0          # exactly: no env, no
                                           # intrinsic, no crowding
    rates = vital_rates(ln.view)
    assert ledger["birth"] == rates.birth
    assert ledger["death"] == rates.death
    assert ledger["birth_eff"] == pytest.approx(rates.birth)
    assert ledger["death_eff"] == pytest.approx(rates.death)
    assert ledger["net"] == pytest.approx(rates.birth - rates.death)
    assert ledger["net"] > 0.0             # a viable lineage grows


def test_suppression_monotone_in_stress():
    """Raising the channel discounts birth, amplifies death, and lowers
    net growth — strictly monotone (B10 §3: birth down, death up)."""
    ln = _clean(_oak())
    view = ln.view
    st = OccupancyState(_cell(), [ln])

    def ledger_at(temp_offset_breadths: float) -> dict:
        climate = _benign(
            view, temp_c=view["temp_opt_c"]
            + temp_offset_breadths * view["temp_breadth_c"])
        return net_growth_rate(view, st, climate)

    l0 = ledger_at(0.0)                    # sigma 0 (benign)
    l1 = ledger_at(0.6)                    # heat stress, s_env > 0
    l2 = ledger_at(0.8)
    assert 0.0 == l0["sigma"] < l1["sigma"] < l2["sigma"]
    assert l0["birth_eff"] > l1["birth_eff"] > l2["birth_eff"]
    assert l0["death_eff"] < l1["death_eff"] < l2["death_eff"]
    assert l0["net"] > l1["net"] > l2["net"]


def test_suppression_net_formula_and_breakeven():
    """The suppression's closed form: net = (b - d)(1 - σ), and net
    growth zeroes EXACTLY at channel 1 — where birth_eff = death_eff =
    2bd/(b+d), the harmonic mean: a lower equilibrium, never a
    kill-switch (B10 §3, §5)."""
    ln = _clean(_oak())
    view = ln.view
    st = OccupancyState(_cell(), [ln])
    rates = vital_rates(view)

    # across stress levels the net identity holds
    for offset in (0.0, 0.4, 0.7, 0.9):
        climate = _benign(view, temp_c=view["temp_opt_c"]
                          + offset * view["temp_breadth_c"])
        ledger = net_growth_rate(view, st, climate)
        assert ledger["net"] == pytest.approx(
            (rates.birth - rates.death) * (1.0 - ledger["sigma"]), abs=1e-12)

    # at the equilibrium the channel is 1 (to the solver's 1e-9
    # tolerance) and net is zero
    eq = equilibrium_holdings(st, _benign(view))["oak"]
    st2 = OccupancyState(_cell(), [ln])
    st2.paint("oak", eq)
    at_eq = net_growth_rate(view, st2, _benign(view))
    assert at_eq["sigma"] == pytest.approx(1.0, abs=1e-8)
    assert at_eq["net"] == pytest.approx(0.0, abs=1e-8)
    harmonic = 2.0 * rates.birth * rates.death / (rates.birth + rates.death)
    assert at_eq["birth_eff"] == pytest.approx(harmonic, abs=1e-8)
    assert at_eq["death_eff"] == pytest.approx(harmonic, abs=1e-8)
    # both rates stay positive at the breakeven — never a kill-switch
    assert at_eq["birth_eff"] > 0.0
    assert at_eq["death_eff"] > 0.0


def test_suppression_never_a_kill_switch():
    """At any finite channel the effective rates stay non-negative and
    the net declines smoothly — no instant-death threshold (B10 §3)."""
    ln = _clean(_oak())
    view = ln.view
    # extreme environmental stress: a fully lethal cell (s_env = +1)
    extreme = _benign(view, temp_c=view["temp_opt_c"]
                      + 2.0 * view["temp_breadth_c"])
    st = OccupancyState(_cell(), [ln])
    ledger = net_growth_rate(view, st, extreme)
    assert ledger["s_env"] == pytest.approx(1.0)
    assert ledger["sigma"] == pytest.approx(1.0)   # the breakeven, exactly
    assert ledger["net"] == pytest.approx(0.0, abs=1e-12)
    assert ledger["birth_eff"] > 0.0     # both rates positive — no
    assert ledger["death_eff"] > 0.0     # kill-switch at the breakeven
    # with holdings the channel passes 1: declining, rates still positive
    st2 = OccupancyState(_cell(), [ln])
    st2.paint("oak", 200_000.0)
    ledger2 = net_growth_rate(view, st2, extreme)
    assert ledger2["sigma"] > 1.0
    assert ledger2["net"] < 0.0
    assert ledger2["birth_eff"] > 0.0
    assert ledger2["death_eff"] > 0.0


# ──  the equilibrium solver (B10 §5 — the derived cap)  ──────────────────


@pytest.mark.parametrize("p", [0.25, 0.75, 1.0, 2.5])
def test_n1_equilibrium_reproduces_crowding_cap(p):
    """The n=1 equilibrium — a lone canopy lineage, benign climate, zero
    intrinsic stress — reproduces crowding.self_crowding_equilibrium_t
    and the derived cap f(p)·L·matching-substrate ha at the four anchor
    productivities (B10 §5: the cap is the n=1 solution of the SAME
    crowding function; no guardrail can disagree with it)."""
    ln = _clean(_oak())
    st = OccupancyState(_cell(p), [ln])
    eq = equilibrium_holdings(st, _benign(ln.view))["oak"]
    assert eq == pytest.approx(substrate_capacity_t(st, "oak"), rel=1e-7)
    assert eq == pytest.approx(_cap_t(p), rel=1e-7)
    assert eq == pytest.approx(self_crowding_equilibrium_t(st, "oak"),
                               rel=1e-9)


def test_intrinsic_leakage_pulls_slightly_below_cap():
    """With the REAL (uncleaned) view, the intrinsic block is a separate
    family in the channel, so the equilibrium sits slightly BELOW the
    crowding cap — the plateau's weak leakage, by design (B9 §4)."""
    ln = _oak()
    st = OccupancyState(_cell(1.0), [ln])
    eq = equilibrium_holdings(st, _benign(ln.view))["oak"]
    cap = substrate_capacity_t(st, "oak")
    assert 0.0 < eq < cap
    assert eq > 0.98 * cap                # leakage ≤ ~2%


def test_equilibrium_lower_under_stress():
    """Environmental stress lowers the equilibrium monotonically —
    x* = C·(1 - σ_env) for a canopy lineage — and it never hits zero at
    finite stress (B10 §3: a stressed lineage settles at a LOWER
    EQUILIBRIUM, not a kill-switch)."""
    ln = _clean(_oak())
    view = ln.view
    st = OccupancyState(_cell(1.0), [ln])
    cap = substrate_capacity_t(st, "oak")

    def eq_at(offset_breadths: float) -> float:
        climate = _benign(view, temp_c=view["temp_opt_c"]
                          + offset_breadths * view["temp_breadth_c"])
        return equilibrium_holdings(st, climate)["oak"]

    eq0 = eq_at(0.0)
    assert eq0 == pytest.approx(cap, rel=1e-7)      # favorable: full cap
    chain = [eq0]
    # past the oak's viability breakeven (s_env > 0 from ~0.45 breadths
    # of heat, given its 0.91 water stratum) the equilibrium falls
    for offset in (0.5, 0.6, 0.8, 0.9):
        eq = eq_at(offset)
        chain.append(eq)
        # the closed-form identity: x* = C·(1 - max(0, s_env))
        s_env = total_stress(view, st, _benign(
            view, temp_c=view["temp_opt_c"]
            + offset * view["temp_breadth_c"]))["s_env"]
        assert eq == pytest.approx(cap * (1.0 - max(0.0, s_env)),
                                   rel=1e-6)
    assert all(chain[i] > chain[i + 1] for i in range(len(chain) - 1))
    assert chain[-1] > 0.0                 # still positive, never zero


def test_ab_fixture_nearly_equal_holdings_different_remainders():
    """The A/B fixture (B10 §6.1): the same canopy lineage at p=2.5 vs
    p=0.75 settles at the same NEARLY-productivity-flat cap — the
    holding ratio tracks f (≈1.157), not the pool (×3.33) — while the
    pool remainders differ enormously: A leaves a rich remainder
    (understory headroom), B's canopy nearly exhausts the pool."""
    def solve(p: float) -> tuple[float, float]:
        ln = _clean(_oak())
        st = OccupancyState(_cell(p), [ln])
        eq = equilibrium_holdings(st, _benign(ln.view))["oak"]
        return eq, st.pool_t - eq

    eq_rich, rem_rich = solve(2.5)
    eq_poor, rem_poor = solve(0.75)
    # equal holdings in the B10 sense: the cap ratio is the f ratio,
    # nowhere near the pool ratio (productivity buys lineage count,
    # never lineage size)
    assert eq_rich / eq_poor == pytest.approx(
        prodscale_f(2.5) / prodscale_f(0.75), rel=1e-7)
    assert eq_rich / eq_poor == pytest.approx(1.157, abs=1e-3)
    # the pool ratio, for contrast
    pool_rich, pool_poor = rem_rich + eq_rich, rem_poor + eq_poor
    assert pool_rich / pool_poor == pytest.approx(3.333, rel=1e-3)
    # different remainders: A's canopy leaves ~1.2M t of pool, B's
    # nearly exhausts it
    assert rem_rich > 1.0e6
    assert rem_poor < 2.0e5
    assert rem_rich / rem_poor > 5.0
    # shares of the pool: a quarter (rich, room for more lineages) vs
    # three quarters (poor, near-monoculture binding)
    assert eq_rich / pool_rich == pytest.approx(0.2594, rel=1e-3)
    assert eq_poor / pool_poor == pytest.approx(0.7470, rel=1e-3)


def test_ab_fixture_mixed_substrate_cell():
    """The A/B shape holds through dynamics on a MIXED substrate cell
    (ticket 0050): a generalist canopy on clay+sand still settles at
    its match-1 derived cap, and the rich/poor holding ratio tracks f
    (≈1.157), not the pool (×3.33) — the per-class geometry does not
    disturb the productivity-flat cap."""
    def solve(p: float) -> tuple[float, float]:
        ln = _clean(_oak())
        st = OccupancyState(_cell(p, mix={"clay": 0.5, "sand": 0.5}), [ln])
        eq = equilibrium_holdings(st, _benign(ln.view))["oak"]
        return eq, st.pool_t - eq

    eq_rich, rem_rich = solve(2.5)
    eq_poor, rem_poor = solve(0.75)
    assert eq_rich / eq_poor == pytest.approx(
        prodscale_f(2.5) / prodscale_f(0.75), rel=1e-7)
    assert eq_rich / eq_poor == pytest.approx(1.157, abs=1e-3)
    # the match-1 cap still binds (the generalist spreads with the mix)
    assert eq_rich == pytest.approx(_cap_t(2.5), rel=1e-7)
    assert eq_poor == pytest.approx(_cap_t(0.75), rel=1e-7)
    assert rem_rich > 1.0e6 and rem_poor < 2.0e5


def test_equilibrium_specialist_on_mixed_cell():
    """A substrate-specialist canopy on a mixed cell settles at its
    match-SCALED derived cap through the dynamics solver (ticket
    0050): f(p)·L·cell_ha·match with match the preferred class's
    share — the geometric per-class equilibrium reproduces the cap
    exactly (no guardrail disagrees)."""
    ln = _clean(_oak(substrate_pref={"clay": 1.0}))
    st = OccupancyState(_cell(1.0, mix={"clay": 0.5, "sand": 0.5}), [ln])
    eq = equilibrium_holdings(st, _benign(ln.view))["oak"]
    assert eq == pytest.approx(substrate_capacity_t(st, "oak"), rel=1e-7)
    assert eq == pytest.approx(_cap_t(1.0, match=0.5), rel=1e-7)


def test_equilibrium_partition_relief_dynamics():
    """Through the dynamics solver, disjoint-preference lineages settle
    at their ISOLATED per-class equilibria — neither's stress ever
    includes the other's claims (ticket 0050: partitioning relieves
    competition geometrically, so the pair solves exactly as two
    monocultures sharing the cell).  Two same-preset swards partition
    the cell's clay/sand classes under a shared climate — the same
    species, different substrate niche (B10 §2's partitioning is the
    only true escape)."""
    clay = _clean(_tussock(ref="clay_sward",
                           substrate_pref={"clay": 1.0}))
    sand = _clean(_tussock(ref="sand_sward",
                           substrate_pref={"sand": 1.0}))
    cell = _cell(1.0, mix={"clay": 0.5, "sand": 0.5})
    climate = _benign(clay.view)           # identical envelopes

    def solve_pair() -> dict:
        st = OccupancyState(cell, [clay, sand])
        return equilibrium_holdings(st, climate)

    def solve_alone(ref: str, ln: Lineage) -> float:
        st = OccupancyState(cell, [ln])
        return equilibrium_holdings(st, climate)[ref]

    eq = solve_pair()
    assert eq["clay_sward"] == pytest.approx(
        solve_alone("clay_sward", clay), rel=1e-7)
    assert eq["sand_sward"] == pytest.approx(
        solve_alone("sand_sward", sand), rel=1e-7)
    assert eq["clay_sward"] > 0.0 and eq["sand_sward"] > 0.0
    # and neither is excluded — both survive at their own equilibria
    # (determinism: identical builds, identical holdings)
    assert solve_pair() == eq


def test_low_p_favorable_near_monoculture():
    """B10 §6.3: at low p with a favorable climate the well-adapted
    canopy lineage settles at its derived cap and the sward is excluded
    — near-monoculture, the pool binds (the oak holds ~3/4 of it)."""
    p = 0.75
    oak = _clean(_oak())
    sward = _clean(_tussock())
    st = OccupancyState(_cell(p), [oak, sward])
    eq = equilibrium_holdings(st, _benign(oak.view))
    cap = substrate_capacity_t(st, "oak")
    assert eq["oak"] == pytest.approx(cap, rel=1e-7)
    assert eq["sward"] == 0.0              # excluded exactly
    assert eq["oak"] / st.pool_t > 0.7     # binds most of the pool


def test_quadrant_shapes():
    """The B10 §5 owner quadrants, per cell: favorable × high-p — the
    lineage at its full cap with large pool headroom (room for more
    lineages); unfavorable × high-p — suppressed, the pool headroom
    unused as pure potential; favorable × low-p — the cap binds most of
    the pool; unfavorable × low-p — sparse."""
    def solve(p: float, hostile: bool) -> tuple[float, float]:
        ln = _clean(_oak())
        view = ln.view
        st = OccupancyState(_cell(p), [ln])
        climate = _benign(view) if not hostile else _benign(
            view, temp_c=view["temp_opt_c"]
            + 0.8 * view["temp_breadth_c"])
        eq = equilibrium_holdings(st, climate)["oak"]
        return eq, st.pool_t - eq

    cap_hi, cap_lo = _cap_t(2.5), _cap_t(0.75)
    eq_hi_fav, rem_hi_fav = solve(2.5, hostile=False)
    eq_hi_unf, rem_hi_unf = solve(2.5, hostile=True)
    eq_lo_fav, rem_lo_fav = solve(0.75, hostile=False)
    eq_lo_unf, rem_lo_unf = solve(0.75, hostile=True)

    # favorable: the full derived cap either way
    assert eq_hi_fav == pytest.approx(cap_hi, rel=1e-7)
    assert eq_lo_fav == pytest.approx(cap_lo, rel=1e-7)
    # unfavorable: suppressed below the cap
    assert eq_hi_unf < eq_hi_fav and eq_lo_unf < eq_lo_fav
    # headroom: the high-p cell keeps ~1.2M t of pool untouched under
    # stress — pure potential
    assert rem_hi_fav > 1.0e6 and rem_hi_unf > 1.0e6
    # low-p favorable: the cap binds most of the pool (monoculture);
    # low-p unfavorable: sparse
    assert eq_lo_fav / (rem_lo_fav + eq_lo_fav) > 0.7
    assert eq_lo_unf < eq_lo_fav


def test_n2_shaded_lineage_is_excluded():
    """Under an at-cap canopy the lower canopy stratum reads shade +
    full substrate contest — over-constrained at zero holdings — so it
    is excluded while the top canopy holds its cap (B10 §2's
    competition:canopy; the shade is WHY, per the provenance)."""
    oak = _clean(_oak())
    willow = _clean(_willow())
    st = OccupancyState(_cell(1.0), [oak, willow])
    eq = equilibrium_holdings(st, _benign(oak.view))
    assert eq["oak"] == pytest.approx(substrate_capacity_t(st, "oak"),
                                      rel=1e-7)
    assert eq["willow"] == 0.0             # excluded exactly
    # the provenance at the equilibrium: the willow's shade > 0
    st2 = OccupancyState(_cell(1.0), [oak, willow])
    st2.paint("oak", eq["oak"])
    shade = competition_stress(willow.view, st2)["competition:canopy"]
    assert shade["value"] > 0.0
    assert shade["dominant_refs"] == ("oak",)


def test_equilibrium_uses_vitals_viability_gate():
    """The vitals gate viability: a lineage whose birth ≤ death (an
    enormous, huge-seeded tree) settles at ZERO — never establishes —
    even at a favorable climate and empty cell."""
    view = dict(_oak().view, propagule_mass_mg=1.0e9, mass_total_kg=1.0e12)
    rates = vital_rates(view)
    assert rates.birth <= rates.death      # non-viable by construction
    ln = Lineage(ref="oak", view=view)
    st = OccupancyState(_cell(1.0), [ln])
    eq = equilibrium_holdings(st, _benign(view))["oak"]
    assert eq == 0.0
    # the viable control settles at its cap
    control = _clean(_oak())
    st2 = OccupancyState(_cell(1.0), [control])
    assert equilibrium_holdings(st2, _benign(control.view))["oak"] > 0.0


def test_equilibrium_solver_is_deterministic():
    """Two identical builds solve to identical holdings (determinism
    hard rule — the bisection + Gauss-Seidel accumulate no randomness)."""
    def solve() -> dict:
        st = OccupancyState(_cell(0.75), [_clean(_oak()), _tussock()])
        return equilibrium_holdings(st, _benign(_oak().view))
    assert solve() == solve()


def test_equilibrium_solver_is_pure():
    """equilibrium_holdings never mutates the input occupancy (solves on
    a deep copy); the climate and views are untouched."""
    ln = _clean(_oak())
    sward = _tussock()
    st = OccupancyState(_cell(1.0), [ln, sward])
    st.paint("sward", 5_000.0)
    holdings_before = dict(st.holdings_t)
    view_before = dict(ln.view)
    climate = _benign(ln.view)
    eq = equilibrium_holdings(st, climate)
    assert st.holdings_t == holdings_before   # input untouched
    assert ln.view == view_before
    assert eq == equilibrium_holdings(st, climate)   # deterministic


def test_sweep_budget_constant_documented():
    """The Gauss-Seidel budget is a named constant (deterministic stop —
    tolerance first, budget as the cap)."""
    assert isinstance(EQUILIBRIUM_SWEEP_BUDGET, int)
    assert EQUILIBRIUM_SWEEP_BUDGET > 0


# ──  determinism audit  ──────────────────────────────────────────────────


def test_no_nondeterministic_imports():
    """AGENTS.md determinism hard rule: no random/uuid/time/numpy in
    dynamics.py (same seed ⇒ byte-identical output)."""
    src = (pathlib.Path(__file__).parent / "dynamics.py").read_text()
    for line in src.splitlines():
        stripped = line.strip()
        for bad in ("import random", "from random", "import uuid",
                    "from uuid", "import time", "from time",
                    "import numpy"):
            assert not stripped.startswith(bad), \
                f"dynamics.py: forbidden import: {stripped}"
