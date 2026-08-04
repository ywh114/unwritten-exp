"""Per-cell L3 dynamics: environmental stress, the one-channel stress
assembly, vital rates, vital suppression, and the equilibrium solver
(ticket 0049; spec B10 §2, §3, §5, §6 — environmental shapes per B5).

The L3 core, built on L2 (occupancy.py + crowding.py).  Every stress is
a scalar with provenance, a pure function of (species view, cell
fields, crowding fields) — probeable by nudge-and-recompute (B10 §2).
Stress has exactly TWO effects (B10 §3); this module implements effect
1, VITAL SUPPRESSION — birth down, death up, the population settles at
a LOWER EQUILIBRIUM, not a cap hit, not a kill-switch.  (Effect 2,
evolutionary pressure with provenance, is B10 §4 and lands with L4.)

The three families — environmental (B5 shapes), intrinsic (the view's
``intrinsic_stress`` block, B9 §4), competition (crowding.py) — sum
through ONE channel (B10 §2).  The derived cap (B10 §5) is the n=1
limit of the CROWDING equilibrium: growth zeroes at channel 1, so a
lone lineage settles at its own crowding equilibrium and no guardrail
can disagree with the mechanism.  This module reproduces that
calibration BY CONSTRUCTION: the net-growth function zeroes exactly at
channel 1 for any viable lineage, so the n=1 equilibrium solve equals
``crowding.self_crowding_equilibrium_t`` (the derived cap).

What lives here:

- ``CellClimate`` — the cell's climate/edaphic input (temp, moisture,
  ph, nutrient, salinity, rooting depth), a SEPARATE input from
  occupancy's ``CellInput``, composed at assembly level (B5 §3).
- ``environment_stress`` — per-axis environmental suitabilities: cell
  climate vs the view's derived climate envelope + tolerance
  passthroughs, shapes per B5 §4 — every axis reads f = 1 - sat(term)
  (one-/two-sided saturating distance), strata MULTIPLY (Liebig tail
  dominance), and the block composes to the signed s_env = 1 - 2F on
  [-1, +1]: s < 0 vigor, s = 0 the viability breakeven, s > 0 cost.
- ``total_stress`` — the one-channel assembly: max(0, s_env) (vigor
  does not suppress) + Σ intrinsic + Σ competition, per-term provenance
  preserved under its family key.
- ``vital_rates`` — birth / death / establish as PURE functions of the
  view: a REBUILD, not a port (see the constants' docstring).
- ``net_growth_rate`` — vital suppression: the channel discounts birth
  and amplifies death so net growth zeroes EXACTLY at channel 1 (B10
  §5's calibration) and both rates stay positive there (B10 §3's lower
  equilibrium, never a kill-switch).
- ``equilibrium_holdings`` — the per-cell, n-lineage equilibrium under
  crowding + vitals: a deterministic Gauss-Seidel solve (refs-sorted
  per-lineage bisection mirroring the reference's bracket/iteration/
  tolerance), closed-form in the "no ticks" sense — the equilibrium is
  solved directly from the algebraic stress equations, never ticked
  forward in time.  At n=1 with no env/intrinsic suppression it solves
  exactly ``crowding.self_crowding_equilibrium_t``.

Determinism hard rule: no randomness, no wall-clock; iteration over
terms / lineages / axes is sorted; float accumulation in sorted order;
two identical builds are byte-stable.

Deferred from B5 (documented scope cuts, all assembly/rounds-side):
the MONTHLY climate structure (growing season, phenology gating,
bloom-month frost — B5 §4.1) — this is the per-cell STATIONARY
climate; the waterlogging INVERSION to a wet requirement for
mangrove/wetland grades (B5 §4.2 — medium-dual-domain machinery, not
exercised by land-only content); and the deferred axes (fire, shade-as-
competition, land light — B5 §4.4).  The response wiring strings below
document each term's responder traits; the responder TABLE itself is
L3 content (B10 §4).
"""

from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Mapping

from exp.k15_biosphere.crowding import competition_stress, substrate_capacity_t
from exp.k15_biosphere.occupancy import OccupancyState

# ══════════════════════════════════════════════════════════════════════
# ──  environmental-stress constants (B5 §4, §5.1)  ──────────────────────
# ══════════════════════════════════════════════════════════════════════

# pH: position-only tolerance (B5 §5.1) — pH optimum 4.0 + 5.0·ph_tolerance
# spanning the world's clip, breadth fixed ±1.0 pH unit, one-sided
# saturating distance outside.  Position drifts (radiation crosses the
# calcicole/calcifuge split); breadth is fixed (B5 §7 Q1).
PH_OPT_LO = 4.0
PH_OPT_SPAN = 5.0
PH_BREADTH = 1.0

# Saturating widths — the "ref" of the one-sided terms (B5 §4.2/§4.3:
# f = 1 - sat(term/ref)) — fixed constants on the field's own scale,
# calibrated so a near-unit deviation costs roughly half a suitability
# point.  They graduate to content tables when fauna lands (B9 §4
# idiom).
WL_REF = 0.3        # waterlogging: moisture units above the tolerance
FERT_REF = 0.2      # fertility: requirement units above the nutrient
SAL_REF = 0.1       # salinity: salinity units above the tolerance
ROOT_REF_M = 1.0    # rooting: metres of root depth above the substrate

# ── responder-wiring documentation (B10 §4; the responder TABLE is L3
# ── content, these strings are the per-term trait wiring, house style).
COLD_WIRING = (
    "responder traits: the temperature envelope (temp_opt_c / "
    "temp_breadth_c — a pure derived of the trait bundle: "
    "leaf_persistence, photosynthesis, pubescence, cuticle_thickness, "
    "leaf_size_cm, drought_tolerance, growing_season_req; B5 §4.1).  "
    "The responder TABLE is L3 content."
)
HEAT_WIRING = (
    "responder traits: the temperature envelope (temp_opt_c / "
    "temp_breadth_c — a pure derived of the trait bundle; B5 §4.1).  "
    "The responder TABLE is L3 content."
)
WATER_WIRING = (
    "responder traits: moisture_opt / moisture_breadth (a pure derived: "
    "drought_tolerance, succulence, photosynthesis, cuticle_thickness, "
    "leaf_size_cm — B5 §4.2; the envelope shapes drought response, "
    "nothing is double-counted).  The responder TABLE is L3 content."
)
WATERLOGGING_WIRING = (
    "responder traits: waterlogging_tolerance (the saturated-end limit; "
    "the B5 §4.2 inversion to a wet REQUIREMENT for mangrove/wetland "
    "grades is deferred — medium-dual-domain machinery).  The responder "
    "TABLE is L3 content."
)
PH_WIRING = (
    "responder traits: ph_tolerance (position — the calcicole/calcifuge "
    "split; breadth fixed ±1.0, B5 §5.1).  The responder TABLE is L3 "
    "content."
)
FERTILITY_WIRING = (
    "responder traits: fertility_requirement.  The responder TABLE is "
    "L3 content."
)
SALINITY_WIRING = (
    "responder traits: salinity_tolerance.  The responder TABLE is L3 "
    "content."
)
ROOTING_WIRING = (
    "responder traits: root_depth_m (the saturating-excess tail term, "
    "B5 §4.3 — never a cutoff).  The responder TABLE is L3 content."
)

# ══════════════════════════════════════════════════════════════════════
# ──  vital-rate constants (rebuild — view-input-only)  ──────────────────
# ══════════════════════════════════════════════════════════════════════

# The vital rates are a REBUILD, not a port (ticket 0049): pure
# functions of the assembled VIEW (B9 §3 — the only derive path), never
# of raw record axes.  The k13-era reference (FloraSim.vital,
# PROVISIONAL by its own docstring) read traits — longevity_yr,
# growth_rate, wood_density, clonal_spread_m — that the view does not
# carry, so it is NOT ported.  The structural ideas below ARE the k13
# research conclusions, restated for view inputs:
#
# - fecundity is a mass-driven inverse proxy — small propagules, many
#   offspring — (FECUNDITY_REF_MG / propagule_mass_mg)^FECUNDITY_EXP,
#   capped (FECUNDITY_CAP), annualized over the generation clock.
# - the generation clock runs on size: gen_time = GEN_TIME_COEFF ·
#   height_m^GEN_TIME_EXP (taller plants turn over more slowly).
# - establishment favors small propagules and is smoothed by clonal
#   spread and a persistent seed bank (B5's propagule-rain semantics).
# - death is 1/longevity with a woodiness discount; longevity is
#   REBUILT as a per-capita-mass power law (the view carries no
#   authored longevity): big organisms die slowly.
#
# The numbers are fresh constants: the k13 research values where the
# science is the same (mass-fecundity proxy, gen-time exponent,
# establishment exponents), new ones where the input changed (the
# longevity law, tuned so the tree presets land ~0.005-0.05/yr and the
# sward ~0.2/yr — the k13 research magnitudes).

FECUNDITY_REF_MG = 10.0
FECUNDITY_EXP = 0.5
FECUNDITY_CAP = 100.0
GEN_TIME_COEFF = 2.0
GEN_TIME_EXP = 0.3
BIRTH_GEN_RATE = 1.0      # offspring per generation per unit fecundity
BIRTH_MAX = 100.0         # per-year birth cap (per-capita)

ESTABLISH_REF_MG = 1.0
ESTABLISH_EXP = 0.35
CLONAL_ESTABLISH_MULT = 4.0   # any clonality_class beyond "none"
SEED_BANK_MULT = 1.5          # a persistent seed bank smooths the rain

LONGEVITY_COEFF = 8.0
LONGEVITY_EXP = 0.38          # longevity_yr = COEFF · percap_kg^EXP
DEATH_WOODY_DISCOUNT = 0.5    # wood lasts: x (1 - discount · woodiness)
DEATH_MIN = 1e-4              # floor so immortals still leak a little
DEATH_MAX = 1.0               # at most full replacement per year

# ══════════════════════════════════════════════════════════════════════
# ──  suppression + equilibrium solver constants (B10 §3, §5)  ───────────
# ══════════════════════════════════════════════════════════════════════

# The per-lineage bisection mirrors crowding.self_crowding_equilibrium_t
# (same bracket, iteration count, and tolerance) so the n=1 case — a
# lone lineage, benign climate, zero intrinsic stress — reproduces it
# and the derived cap to machine precision.
EQUILIBRIUM_BISECT_ITERS = 200
EQUILIBRIUM_TOL = 1e-9
EQUILIBRIUM_BRACKET_GUARD = 64
# The Gauss-Seidel sweep budget over the lineages (deterministic stop
# either way — tolerance break first, budget as the cap).
EQUILIBRIUM_SWEEP_BUDGET = 24


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _numeric(value: object) -> bool:
    return isinstance(value, (int, float))


def _num(view: Mapping, key: str, default: float = 0.0) -> float:
    v = view.get(key)
    return float(v) if _numeric(v) else default


# ══════════════════════════════════════════════════════════════════════
# ──  the cell's climate input (B5 §3)  ─────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class CellClimate:
    """The cell's climate/edaphic fields the environmental stress reads
    (B5 §3) — a SEPARATE L3 input, composed at assembly level;
    occupancy's ``CellInput`` is untouched (climate is not L2's
    business).

    ``temp_c`` the cell's temperature (°C); ``moisture`` the unified
    soil-water status ``water_potential`` on [0, 1] (retention-weighted
    monthly P vs T-driven demand, saturation end included — B5 §3);
    ``ph`` the cell's pH (the medium-dependent selection — land plans
    read ``ground_ph``, water plans ``water_ph``, B5 §4.2 — is resolved
    at assembly: the cell presents its effective pH); ``nutrient``
    ``eff_nutrient`` on [0, 1]; ``salinity`` the effective ionic
    salinity on [0, 1] (``eff_sal_add`` on land, ``h_salinity`` in
    water — assembly-resolved likewise); ``rooting_m`` ``eff_rooting_m``
    (m), the substrate's rootable depth.

    The B5 §4.1 MONTHLY structure (growing season, phenology gating,
    bloom-month frost) is deliberately out of scope here — this is the
    per-cell STATIONARY climate; monthly integration is the rounds'
    business (a later ticket).  Fields validate on construction.
    """

    temp_c: float
    moisture: float
    ph: float
    nutrient: float
    salinity: float
    rooting_m: float

    def __post_init__(self) -> None:
        for name, lo, hi, desc in (
                ("temp_c", None, None, "the cell temperature (°C)"),
                ("moisture", 0.0, 1.0, "water_potential [0, 1]"),
                ("ph", 0.0, 14.0, "the cell pH"),
                ("nutrient", 0.0, 1.0, "eff_nutrient [0, 1]"),
                ("salinity", 0.0, 1.0, "the effective salinity [0, 1]"),
                ("rooting_m", 0.0, None, "eff_rooting_m (m)")):
            v = getattr(self, name)
            if not _numeric(v):
                raise ValueError(
                    f"CellClimate.{name} must be numeric ({desc}; "
                    f"got {v!r})")
            if not math.isfinite(float(v)):
                raise ValueError(
                    f"CellClimate.{name} must be finite ({desc}; got {v:g})")
            if lo is not None and v < lo:
                raise ValueError(
                    f"CellClimate.{name} must be >= {lo} ({desc}; "
                    f"got {v:g})")
            if hi is not None and v > hi:
                raise ValueError(
                    f"CellClimate.{name} must be <= {hi} ({desc}; "
                    f"got {v:g})")


# ══════════════════════════════════════════════════════════════════════
# ──  environmental stress (B5 §4 — shapes per B5)  ─────────────────────
# ══════════════════════════════════════════════════════════════════════

def _env_term(key: str, f: float, distance: float, cause: str,
              field: dict, wiring: str) -> dict:
    """Assemble one environmental term: the stratum's SUITABILITY ``f``
    in [0, 1] (1 optimal, 0 lethal — B5 §4: the factor vector IS the
    provenance), the raw saturating ``distance``, the human ``cause``,
    the ``field`` read (cell + envelope values), and the responder
    ``wiring`` — mirroring the crowding/intrinsic term shapes."""
    return dict(key=key, value=f, distance=distance, cause=cause,
                field=field, wiring=wiring)


def environment_stress(view: Mapping, climate: CellClimate) -> dict:
    """The B5 §4 environmental block: one suitability stratum per axis —
    the climate terms (pressure:cold / pressure:heat, B5 §4.1, SPLIT
    one-sided so their product is the symmetric envelope distance) and
    the ground/tail terms (pressure:water / pressure:waterlogging /
    ph / fertility / salinity / rooting, B5 §4.2/§4.3) — each a PURE
    function of (view, CellClimate), shapes per B5: every axis reads
    f = 1 - sat(term) with a one- or two-sided saturating distance, and
    strata MULTIPLY (Liebig tail-dominance; ``compose_suitabilities``
    does the product).

    Returns the per-axis terms keyed ``environment:<axis>``.  Probeable
    (B10 §4): nudge a view trait or the climate, recompute, read the
    difference — pure, never mutates.  Missing view keys read the
    documented neutral (an absent envelope/tolerance means no cost on
    that axis — f = 1, per B9 §3's "every key is always written" the
    canonical view never exercises this).
    """
    out: dict = {}

    # ── the climate stratum: T split one-sided (B5 §4.1).  The two
    # ── terms' product is the symmetric envelope distance, so the
    # ── composed F is unchanged by the split.
    t_opt = view.get("temp_opt_c")
    t_breadth = view.get("temp_breadth_c")
    if _numeric(t_opt) and _numeric(t_breadth) and t_breadth > 0.0:
        cold = max(0.0, t_opt - climate.temp_c) / t_breadth
        out["environment:cold"] = _env_term(
            "environment:cold", 1.0 - _clip01(cold), cold,
            cause=(f"temp {climate.temp_c:.3g}°C is {cold:.3g} breadths "
                   f"below the {t_opt:.3g}°C optimum "
                   f"(breadth {t_breadth:.3g}°C)"),
            field=dict(temp_c=climate.temp_c, temp_opt_c=t_opt,
                       temp_breadth_c=t_breadth, shortfall=cold),
            wiring=COLD_WIRING)
        heat = max(0.0, climate.temp_c - t_opt) / t_breadth
        out["environment:heat"] = _env_term(
            "environment:heat", 1.0 - _clip01(heat), heat,
            cause=(f"temp {climate.temp_c:.3g}°C is {heat:.3g} breadths "
                   f"above the {t_opt:.3g}°C optimum "
                   f"(breadth {t_breadth:.3g}°C)"),
            field=dict(temp_c=climate.temp_c, temp_opt_c=t_opt,
                       temp_breadth_c=t_breadth, excess=heat),
            wiring=HEAT_WIRING)
    else:
        for key, cause in (("environment:cold",
                            "no temperature envelope (neutral)"),
                           ("environment:heat",
                            "no temperature envelope (neutral)")):
            out[key] = _env_term(
                key, 1.0, 0.0, cause,
                field=dict(temp_c=climate.temp_c),
                wiring=COLD_WIRING if key.endswith("cold")
                else HEAT_WIRING)

    # ── pressure:water — the dry end, one-sided shortfall of
    # ── water_potential below the derived moisture need (B5 §4.2).
    # ── drought_tolerance is already INSIDE the envelope (it moves
    # ── moisture_opt drier and widens moisture_breadth) — no
    # ── double-counting.
    m_opt = view.get("moisture_opt")
    m_breadth = view.get("moisture_breadth")
    if _numeric(m_opt) and _numeric(m_breadth) and m_breadth > 0.0:
        water = max(0.0, m_opt - climate.moisture) / m_breadth
        out["environment:water"] = _env_term(
            "environment:water", 1.0 - _clip01(water), water,
            cause=(f"water potential {climate.moisture:.3g} is "
                   f"{water:.3g} breadths below the {m_opt:.3g} moisture "
                   f"need (breadth {m_breadth:.3g})"),
            field=dict(moisture=climate.moisture, moisture_opt=m_opt,
                       moisture_breadth=m_breadth, shortfall=water),
            wiring=WATER_WIRING)
    else:
        out["environment:water"] = _env_term(
            "environment:water", 1.0, 0.0,
            "no moisture envelope (neutral)",
            field=dict(moisture=climate.moisture), wiring=WATER_WIRING)

    # ── pressure:waterlogging — the saturated end, one-sided excess
    # ── above the tolerance (B5 §4.2; the inversion for mangrove/
    # ── wetland grades is deferred — see the module docstring).
    wl_tol = _clip01(_num(view, "waterlogging_tolerance", 0.0))
    waterlog = max(0.0, climate.moisture - wl_tol) / WL_REF
    out["environment:waterlogging"] = _env_term(
        "environment:waterlogging", 1.0 - _clip01(waterlog), waterlog,
        cause=(f"water potential {climate.moisture:.3g} is "
               f"{waterlog:.3g} widths above the {wl_tol:.3g} "
               f"waterlogging tolerance (width {WL_REF:.3g})"),
        field=dict(moisture=climate.moisture,
                   waterlogging_tolerance=wl_tol, width=WL_REF,
                   excess=waterlog),
        wiring=WATERLOGGING_WIRING)

    # ── pH — the calcicole/calcifuge split (B5 §5.1): position-only
    # ── optimum 4 + 5·ph_tolerance, fixed ±1.0 breadth.
    ph_tol = _clip01(_num(view, "ph_tolerance", 0.5))
    ph_opt = PH_OPT_LO + PH_OPT_SPAN * ph_tol
    ph_d = abs(climate.ph - ph_opt) / PH_BREADTH
    out["environment:ph"] = _env_term(
        "environment:ph", 1.0 - _clip01(ph_d), ph_d,
        cause=(f"cell pH {climate.ph:.3g} is {ph_d:.3g} pH units from "
               f"the {ph_opt:.3g} optimum (breadth {PH_BREADTH:.3g})"),
        field=dict(ph=climate.ph, ph_opt=ph_opt,
                   ph_tolerance=ph_tol, breadth=PH_BREADTH),
        wiring=PH_WIRING)

    # ── fertility — one-sided shortfall below the requirement.
    fert_req = _clip01(_num(view, "fertility_requirement", 0.0))
    fert = max(0.0, fert_req - climate.nutrient) / FERT_REF
    out["environment:fertility"] = _env_term(
        "environment:fertility", 1.0 - _clip01(fert), fert,
        cause=(f"nutrient {climate.nutrient:.3g} is {fert:.3g} widths "
               f"below the {fert_req:.3g} requirement "
               f"(width {FERT_REF:.3g})"),
        field=dict(nutrient=climate.nutrient,
                   fertility_requirement=fert_req, width=FERT_REF,
                   shortfall=fert),
        wiring=FERTILITY_WIRING)

    # ── salinity — one-sided excess above the tolerance.
    sal_tol = _clip01(_num(view, "salinity_tolerance", 0.0))
    sal = max(0.0, climate.salinity - sal_tol) / SAL_REF
    out["environment:salinity"] = _env_term(
        "environment:salinity", 1.0 - _clip01(sal), sal,
        cause=(f"salinity {climate.salinity:.3g} is {sal:.3g} widths "
               f"above the {sal_tol:.3g} tolerance (width {SAL_REF:.3g})"),
        field=dict(salinity=climate.salinity,
                   salinity_tolerance=sal_tol, width=SAL_REF, excess=sal),
        wiring=SALINITY_WIRING)

    # ── rooting — the saturating-excess tail term (B5 §4.3): the
    # ── plant's root depth vs the substrate's rootable depth, never a
    # ── cutoff.
    root_need = _num(view, "root_depth_m", 0.0)
    root = max(0.0, root_need - climate.rooting_m) / ROOT_REF_M
    out["environment:rooting"] = _env_term(
        "environment:rooting", 1.0 - _clip01(root), root,
        cause=(f"root depth {root_need:.3g} m is {root:.3g} widths above "
               f"the {climate.rooting_m:.3g} m substrate "
               f"(width {ROOT_REF_M:.3g} m)"),
        field=dict(rooting_m=climate.rooting_m, root_depth_m=root_need,
                   width=ROOT_REF_M, excess=root),
        wiring=ROOTING_WIRING)

    return out


def compose_suitabilities(terms: Mapping[str, Mapping]) -> tuple[float, float]:
    """B5 §4: F = Π stratum suitabilities (accumulated over the sorted
    keys — determinism hard rule), s_env = 1 - 2F on [-1, +1]: +1
    lethal, 0 the viability breakeven, -1 maximal vigor.  The product
    keeps Liebig tail-dominance: one failed non-compensable axis takes
    F to ~0.  An empty block reads F = 1, s_env = -1 (nothing is wrong
    anywhere)."""
    F = 1.0
    for key in sorted(terms):
        F *= terms[key]["value"]
    return F, 1.0 - 2.0 * F


# ══════════════════════════════════════════════════════════════════════
# ──  the one-channel assembly (B10 §2)  ────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

def total_stress(view: Mapping, state: OccupancyState,
                 climate: CellClimate) -> dict:
    """The B10 §2 one-channel assembly: the environmental block (B5
    shapes, composed) + the intrinsic block (read from the view's
    ``intrinsic_stress`` — B9 §4) + the competition block (crowding.py)
    — every term's provenance preserved under its family key.

    ``channel`` is the summed stress scalar: max(0, s_env) (vigor does
    not suppress — a favorable lineage reaches its full derived cap,
    B10 §5) + Σ intrinsic values + Σ competition values, accumulated in
    sorted key order.  Net growth zeroes at channel 1 (B10 §5's
    calibration), so a stressed lineage settles at a LOWER EQUILIBRIUM,
    never a kill-switch (B10 §3).  Returns the channel, the composed
    s_env and F, and the three family term dicts."""
    env = environment_stress(view, climate)
    F, s_env = compose_suitabilities(env)
    intrinsic = dict(view.get("intrinsic_stress") or {})
    competition = competition_stress(view, state)
    channel = (max(0.0, s_env)
               + sum(intrinsic[k]["value"] for k in sorted(intrinsic))
               + sum(competition[k]["value"] for k in sorted(competition)))
    return dict(channel=channel, s_env=s_env, F=F,
                environment=env, intrinsic=intrinsic,
                competition=competition)


# ══════════════════════════════════════════════════════════════════════
# ──  vital rates (rebuild — pure functions of the view)  ───────────────
# ══════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class VitalRates:
    """Base per-year rates at zero stress, derived from the view — the
    k13 interface contract's VitalRates shape (birth / death /
    establish), defined here since dynamics is L3's home (the frozen
    reference is never imported)."""

    birth: float = 0.0
    death: float = 0.0
    establish: float = 0.0    # propagule-rain -> established conversion


def vital_rates(view: Mapping) -> VitalRates:
    """Birth / death / establish as a PURE function of the view (B9 §3 —
    the only derive path; no record axes, no k13 imports).  Rebuild, not
    port — see the constants' docstring for the shapes, the inputs, and
    why the k13 reference does not carry over."""
    prop = view.get("propagule_mass_mg")
    prop_mg = float(prop) if _numeric(prop) and prop > 0.0 \
        else FECUNDITY_REF_MG
    fecundity = min(FECUNDITY_CAP,
                    (FECUNDITY_REF_MG / prop_mg) ** FECUNDITY_EXP)

    h = view.get("height_m")
    height = float(h) if _numeric(h) and h > 0.0 else 1e-6
    gen_time = GEN_TIME_COEFF * height ** GEN_TIME_EXP
    birth = min(BIRTH_MAX, fecundity * BIRTH_GEN_RATE / gen_time)

    est = min(1.0, (ESTABLISH_REF_MG / prop_mg) ** ESTABLISH_EXP)
    if str(view.get("clonality_class") or "none") != "none":
        est *= CLONAL_ESTABLISH_MULT
    if str(view.get("seed_bank") or "") == "persistent":
        est *= SEED_BANK_MULT
    est = min(1.0, est)

    percap = view.get("mass_total_kg")
    percap_kg = float(percap) if _numeric(percap) and percap > 0.0 \
        else height
    longevity = LONGEVITY_COEFF * max(percap_kg, 1e-6) ** LONGEVITY_EXP
    wood = _clip01(_num(view, "woodiness", 0.0))
    death = max(DEATH_MIN, min(DEATH_MAX,
                (1.0 / longevity) * (1.0 - DEATH_WOODY_DISCOUNT * wood)))
    return VitalRates(birth=birth, death=death, establish=est)


# ══════════════════════════════════════════════════════════════════════
# ──  vital suppression (B10 §3 effect 1)  ──────────────────────────────
# ══════════════════════════════════════════════════════════════════════

def net_growth_rate(view: Mapping, state: OccupancyState,
                    climate: CellClimate) -> dict:
    """Vital suppression (B10 §3 effect 1): the one-channel stress
    discounts birth and amplifies death into a net-growth rate.

    With baseline rates (b, d) and channel σ:

        φ(σ)    = σ · (b − d) / (b + d)    (rate-normalized suppression;
                                          0 for non-viable lineages)
        birth_eff = b · (1 − φ)            (floored at 0 — rates never
        death_eff = d · (1 + φ)             go negative)
        net       = birth_eff − death_eff  = (b − d) · (1 − σ)

    Properties (the design contract): zero stress → baseline rates
    (φ = 0); monotone — stress discounts birth, amplifies death, and
    lowers net growth; net growth zeroes EXACTLY at channel 1 for any
    viable lineage (B10 §5's calibration — the n=1 equilibrium
    reproduces ``crowding.self_crowding_equilibrium_t``); at the
    breakeven birth_eff = death_eff = 2bd/(b+d) (the harmonic mean —
    both rates stay positive: a stressed lineage settles at a LOWER
    EQUILIBRIUM, never a kill-switch, B10 §3).  Birth_eff reaches 0
    only at σ = (b+d)/(b−d) > 1 — beyond the breakeven, in the
    exclusion regime.  Vigor (s_env < 0) does not suppress (the channel
    floors at 0).

    Returns the ledger dict: sigma, s_env, the baseline
    birth/death/establish, the effective birth_eff/death_eff, and net."""
    verdict = total_stress(view, state, climate)
    sigma = verdict["channel"]
    rates = vital_rates(view)
    b, d = rates.birth, rates.death
    span = b + d
    phi = sigma * (b - d) / span if span > 0.0 and b > d else 0.0
    birth_eff = max(0.0, b * (1.0 - phi))
    death_eff = d * (1.0 + phi)
    net = birth_eff - death_eff
    return dict(sigma=sigma, s_env=verdict["s_env"],
                birth=b, death=d, establish=rates.establish,
                birth_eff=birth_eff, death_eff=death_eff, net=net)


# ══════════════════════════════════════════════════════════════════════
# ──  the equilibrium solver (B10 §3, §5 — closed-form, no ticks)  ───────
# ══════════════════════════════════════════════════════════════════════

def equilibrium_holdings(state: OccupancyState, climate: CellClimate,
                         *, sweep_budget: int = EQUILIBRIUM_SWEEP_BUDGET
                         ) -> dict[str, float]:
    """The per-cell, n-lineage equilibrium under crowding + vitals (B10
    §3, §5): the holdings at which every lineage's net growth is zero —
    or it is EXCLUDED (holdings 0, with net growth ≤ 0 at zero: not
    viable — birth ≤ death or no substrate capacity — or already
    over-constrained by the fixed + others' stress).

    Method: a deterministic Gauss-Seidel over the refs-sorted lineages —
    each lineage's holding is bisected to its net-growth root (channel
    = 1, the B10 §5 calibration) with the others at their current
    iterates, sweeping until the holdings stabilize (or the sweep
    budget is exhausted).  Closed-form, no ticks: the equilibrium is
    solved directly from the algebraic stress equations, never ticked
    forward in time.  The per-lineage bisection mirrors
    ``crowding.self_crowding_equilibrium_t``'s bracket / iterations /
    tolerance exactly, so the n=1 case (a lone lineage, benign climate,
    zero intrinsic stress) reproduces it — and the derived cap — to
    machine precision.

    Pure: solves on a deep copy of the occupancy reset to ZERO holdings
    (the equilibrium is the attractor from the empty-cold start — a
    property of the cell + lineages + climate, not of the starting
    holdings — which also resolves any degenerate symmetric case
    deterministically by ref order); the input state is never mutated.
    Deterministic: sorted iteration, fixed budgets, tolerance stop;
    identical inputs → identical holdings."""
    st = copy.deepcopy(state)
    for ref in st.holdings_t:
        st.holdings_t[ref] = 0.0
    refs = [ln.ref for ln in st.lineages]          # already ref-sorted
    views = {ln.ref: ln.view for ln in st.lineages}
    for _ in range(sweep_budget):
        max_delta = 0.0
        for ref in refs:
            rates = vital_rates(views[ref])
            cap = substrate_capacity_t(state, ref)
            if rates.birth <= rates.death or cap <= 0.0:
                x = 0.0
            else:
                x = _stress_root(views[ref], st, climate, ref, cap)
            max_delta = max(max_delta, abs(x - st.holdings_t[ref]))
            st.holdings_t[ref] = x
        scale = max(1.0, max(st.holdings_t.values()))
        if max_delta <= EQUILIBRIUM_TOL * scale:
            break
    return dict(st.holdings_t)


def _stress_root(view: Mapping, st: OccupancyState, climate: CellClimate,
                 ref: str, cap: float) -> float:
    """The holdings at which the lineage's own total stress (channel)
    reaches 1 — net growth zeroes (B10 §5) — with the other lineages'
    holdings fixed at their current iterates.  0.0 when the lineage is
    already over-constrained at zero holdings (excluded).  Bisection
    mirroring ``crowding.self_crowding_equilibrium_t``: the same
    bracket (current + max(cap, 1), doubled until the crossing is
    inside), the same 200 iterations, the same tolerance."""
    def channel(x: float) -> float:
        st.holdings_t[ref] = x
        return total_stress(view, st, climate)["channel"]

    lo = 0.0
    if channel(lo) >= 1.0:
        return 0.0
    hi = max(cap, 1.0)
    guard = 0
    while channel(hi) < 1.0 and guard < EQUILIBRIUM_BRACKET_GUARD:
        hi *= 2.0
        guard += 1
    scale = max(1.0, hi)
    for _ in range(EQUILIBRIUM_BISECT_ITERS):
        mid = (lo + hi) / 2.0
        if channel(mid) < 1.0:
            lo = mid
        else:
            hi = mid
        if hi - lo <= EQUILIBRIUM_TOL * scale:
            break
    return (lo + hi) / 2.0
