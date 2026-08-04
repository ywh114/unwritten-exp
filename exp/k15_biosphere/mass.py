"""Per-capita allometric biomass for the K15 biosphere rewrite (ticket 0035).

Currency: kg DRY biomass per individual organism — ``total_kg`` includes
belowground, ``agb_kg`` is the aboveground split.  Pure scalar per-individual
functions; deterministic by construction (no randomness, no streams, no
wall-clock — AGENTS.md determinism hard rule), so no numpy is needed here.

Formula lock v1 (orchestrator-locked 2026-08-04): every constant below is
final and named as locked.  ``FLAGGED`` constants are acknowledged
order-of-magnitude estimates pending better published data — do not "fix"
them without a new lock.  ``MassEstimate.proportions`` exposes the per-group
intermediates for the future proportion-deviation penalty hook (ticket 0035
owner note).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

# ── formula lock v1 constants (2026-08-04, final) ───────────────────────

# --- trees ---------------------------------------------------------------
K_ASPECT_BROADLEAF = 18.0   # Hemery 2005 oak stand-grown crown:DBH, DOI 10.1016/j.foreco.2005.05.010
K_ASPECT_OPEN = 25.0        # Coombes 2019 open-grown crown:DBH, DOI 10.1016/j.ufug.2018.08.012
K_ASPECT_TROPICAL = 18.0    # FLAGGED weak (no clean published k; savanna k≈5 brackets low, Mugabowindekwe 2024)
K_ASPECT_PALM = 8.0         # FLAGGED weak
CHAVE_A = 0.0673
CHAVE_B = 0.976             # Chave 2014, DOI 10.1111/gcb.12629: AGB_kg = CHAVE_A·(ρ·DBH_cm²·H_m)^CHAVE_B
PALM_A = 0.0983
DMF_PALM = 0.45             # Goodman 2013, DOI 10.1371/journal.pone.0063337: AGB = PALM_A·DMF_PALM·DBH_cm²·H_m
R_TREE = 0.26               # Mokany 2006 individual-tree root:shoot, DOI 10.1111/j.1365-2486.2005.001043.x
# Conifer: Pretzsch crown:DBH cd = 0.289·d^0.75 (cd m, d cm) — inverted in
# _tree: DBH_cm = (crown_m / 0.289)^(4/3).

# --- shrubs --------------------------------------------------------------
SHRUB_WOOD_KG_M3 = 0.85
SHRUB_HERB_KG_M3 = 0.15     # effective tissue per crown volume (crown mostly air); anchored: 1.5 m H, 2 m crown, woodiness 0.35 → 1.9 kg
R_SHRUB = 0.40              # IPCC 2006 V4 T4.4 root:shoot

# --- herb_forb / fern_grade ----------------------------------------------
A_HERB = 0.05
HERB_EXP = 0.75             # Tadaki-family; sanity 0.5 m, 0.15 m² → 7 g
R_HERB = 3.0                # Jackson 1996 lower end, DOI 10.1007/BF00333714, FLAGGED

# --- grass_sward / runner_meadow (per-area model × footprint) ------------
GRASS_KG_M2_PER_M = 1.0
GRASS_CAP = 0.9             # Gill 2002, DOI 10.1046/j.1466-822x.2001.00267.x; sward_kg_m2 = min(GRASS_KG_M2_PER_M·H, GRASS_CAP)
SEAGRASS_KG_M2_PER_M = 1.5
SEAGRASS_CAP = 1.5          # Serrano 2016, DOI 10.5194/bg-13-491-2016; TOTAL incl. belowground folded in
R_GRASS = 3.0               # Jackson lower, FLAGGED

# --- succulents ----------------------------------------------------------
SUCC_FILL = 0.6
SUCC_FRESH_KG_M3 = 900.0
SUCC_DRY_FRAC = 0.12        # barrel sanity: 1 m × 0.5 m crown → ~100 kg fresh
R_SUCC = 0.3                # FLAGGED

# --- rosette_mat / moss_grade / lichen (per-area × cover, R = 0) ---------
MOSS_KG_M2_PER_M = 3.0
MOSS_CAP = 1.5              # Sphagnum carpets 0.2–1.5 kg/m²
LICHEN_KG_M2 = 0.05         # FLAGGED
ROSETTE_MAT_KG_M2 = 0.15    # FLAGGED

# --- floating_leaf / floater (per-area × cover) --------------------------
FLOATING_LEAF_KG_M2 = 0.08  # FLAGGED coarse
FLOATER_KG_M2 = 0.015       # FLAGGED coarse
R_FLOAT = 1.0               # FLAGGED

# --- macroalgae_holdfast (kelp) ------------------------------------------
KELP_WET_KG_PER_M = 0.39
KELP_BLADE_MULT = 1.3
KELP_DRY_FRAC = 0.12        # van Tamelen 2012 + Rassweiler 2018, DOI 10.1002/ecy.2229

# --- fungus (FLAGGED order-of-magnitude throughout) ----------------------
FUNGUS_DRY_FRAC = 0.10
MYCELIUM_KG_M2 = 0.03


PLANS = (
    "tree", "shrub", "herb_forb", "grass_sward", "rosette_mat", "succulent",
    "fern_grade", "moss_grade", "runner_meadow", "floating_leaf", "floater",
    "macroalgae_holdfast", "fungus", "lichen",
)

TREE_FORMS = ("broadleaf", "conifer", "tropical", "palm", "open")


@dataclass
class MassEstimate:
    """Dry per-individual biomass (kg).

    ``total_kg``: dry, incl. belowground; ``agb_kg``: aboveground dry.
    ``proportions``: per-group intermediates (dbh_m, crown_dbh_ratio,
    root_shoot, sward_kg_m2, …) for the future proportion-deviation
    penalty hook (ticket 0035 owner note).
    """

    total_kg: float
    agb_kg: float
    proportions: dict[str, float]


def footprint_m2(axes: Mapping[str, float], plan: str) -> float:
    """Cover/footprint area (m²) for per-area models and case densities.

    π·(spread/2)² when a spread is given — clonal spread overrides crown —
    else the group fallback: fungus → 1.0 m², everything else → (0.3·H)².
    """
    clonal = axes.get("clonal_spread_m", 0.0)
    crown = axes.get("crown_spread_m", 0.0)
    spread = clonal if clonal > 0.0 else crown
    if spread > 0.0:
        return math.pi * (spread / 2.0) ** 2
    if plan == "fungus":
        return 1.0
    h = max(0.0, axes.get("height_m", 0.0))
    return (0.3 * h) ** 2


def _tree(axes: Mapping[str, float], plan: str, form: str | None):
    h = axes.get("height_m", 0.0)
    crown = max(0.0, axes.get("crown_spread_m", 0.0))
    rho = max(0.0, axes.get("wood_density", 0.6))
    form = form or "broadleaf"
    if form == "broadleaf":
        dbh_cm = crown * 100.0 / K_ASPECT_BROADLEAF
        k = K_ASPECT_BROADLEAF
    elif form == "open":
        dbh_cm = crown * 100.0 / K_ASPECT_OPEN
        k = K_ASPECT_OPEN
    elif form == "tropical":
        dbh_cm = crown * 100.0 / K_ASPECT_TROPICAL
        k = K_ASPECT_TROPICAL
    elif form == "palm":
        dbh_cm = crown * 100.0 / K_ASPECT_PALM
        k = K_ASPECT_PALM
    elif form == "conifer":
        dbh_cm = (crown / 0.289) ** (4.0 / 3.0)
        k = crown / (dbh_cm / 100.0) if dbh_cm > 0.0 else 0.0
    else:
        raise ValueError(
            f"unknown tree form {form!r} (expected one of {TREE_FORMS})"
        )
    if form == "palm":
        # Goodman 2013: no woody stem — DMF (dry-matter fraction) folded in.
        agb = PALM_A * DMF_PALM * dbh_cm * dbh_cm * h
    else:
        agb = CHAVE_A * (rho * dbh_cm * dbh_cm * h) ** CHAVE_B
    total = agb * (1.0 + R_TREE)
    return total, agb, {
        "dbh_m": dbh_cm / 100.0,
        "crown_dbh_ratio": k,
        "root_shoot": R_TREE,
    }


def _shrub(axes: Mapping[str, float], plan: str, form: str | None):
    h = axes.get("height_m", 0.0)
    crown = max(0.0, axes.get("crown_spread_m", 0.0))
    woodiness = min(1.0, max(0.0, axes.get("woodiness", 0.0)))
    vol = math.pi * (crown / 2.0) ** 2 * h
    tissue = (
        woodiness * SHRUB_WOOD_KG_M3 + (1.0 - woodiness) * SHRUB_HERB_KG_M3
    )
    total = vol * tissue
    agb = total / (1.0 + R_SHRUB)
    return total, agb, {
        "crown_volume_m3": vol,
        "tissue_kg_m3": tissue,
        "root_shoot": R_SHRUB,
    }


def _herb(axes: Mapping[str, float], plan: str, form: str | None):
    """herb_forb and fern_grade share the Tadaki-family cover·H power model."""
    h = axes.get("height_m", 0.0)
    cover = footprint_m2(axes, plan)
    total = A_HERB * (cover * h) ** HERB_EXP
    agb = total / (1.0 + R_HERB)
    return total, agb, {"cover_m2": cover, "root_shoot": R_HERB}


def _grass(axes: Mapping[str, float], plan: str, form: str | None):
    h = axes.get("height_m", 0.0)
    fp = footprint_m2(axes, plan)
    sward = min(GRASS_KG_M2_PER_M * h, GRASS_CAP)
    total = sward * fp
    agb = total / (1.0 + R_GRASS)
    return total, agb, {
        "sward_kg_m2": sward,
        "footprint_m2": fp,
        "root_shoot": R_GRASS,
    }


def _runner_meadow(axes: Mapping[str, float], plan: str, form: str | None):
    h = axes.get("height_m", 0.0)
    fp = footprint_m2(axes, plan)
    if axes.get("medium") == "water":
        # Seagrass: Serrano 2016 totals already fold belowground in — do NOT
        # apply R on top.  agb = total/2.7 is the reference-only aboveground
        # split (documented as folded); root_shoot reported as 0.
        sward = min(SEAGRASS_KG_M2_PER_M * h, SEAGRASS_CAP)
        total = sward * fp
        agb = total / 2.7
        props = {"sward_kg_m2": sward, "footprint_m2": fp, "root_shoot": 0.0}
    else:
        sward = min(GRASS_KG_M2_PER_M * h, GRASS_CAP)
        total = sward * fp
        agb = total / (1.0 + R_GRASS)
        props = {"sward_kg_m2": sward, "footprint_m2": fp, "root_shoot": R_GRASS}
    return total, agb, props


def _succulent(axes: Mapping[str, float], plan: str, form: str | None):
    h = axes.get("height_m", 0.0)
    crown = max(0.0, axes.get("crown_spread_m", 0.0))
    woodiness = min(1.0, max(0.0, axes.get("woodiness", 0.0)))
    fresh = math.pi * (crown / 2.0) ** 2 * h * SUCC_FILL * SUCC_FRESH_KG_M3
    total = fresh * SUCC_DRY_FRAC * (1.0 + woodiness)
    agb = total / (1.0 + R_SUCC)
    return total, agb, {"fresh_kg": fresh, "root_shoot": R_SUCC}


def _rosette_mat(axes: Mapping[str, float], plan: str, form: str | None):
    cover = footprint_m2(axes, plan)
    total = ROSETTE_MAT_KG_M2 * cover
    return total, total, {"kg_m2": ROSETTE_MAT_KG_M2, "root_shoot": 0.0}


def _moss(axes: Mapping[str, float], plan: str, form: str | None):
    h = axes.get("height_m", 0.0)
    cover = footprint_m2(axes, plan)
    kg_m2 = min(MOSS_KG_M2_PER_M * h, MOSS_CAP)
    total = kg_m2 * cover
    return total, total, {"kg_m2": kg_m2, "root_shoot": 0.0}


def _lichen(axes: Mapping[str, float], plan: str, form: str | None):
    cover = footprint_m2(axes, plan)
    total = LICHEN_KG_M2 * cover
    return total, total, {"kg_m2": LICHEN_KG_M2, "root_shoot": 0.0}


def _floating(axes: Mapping[str, float], plan: str, form: str | None):
    cover = footprint_m2(axes, plan)
    kg_m2 = FLOATING_LEAF_KG_M2 if plan == "floating_leaf" else FLOATER_KG_M2
    total = kg_m2 * cover
    agb = total / (1.0 + R_FLOAT)
    return total, agb, {"kg_m2": kg_m2, "root_shoot": R_FLOAT}


def _kelp(axes: Mapping[str, float], plan: str, form: str | None):
    h = axes.get("height_m", 0.0)
    total = KELP_WET_KG_PER_M * h * KELP_BLADE_MULT * KELP_DRY_FRAC
    return total, total, {"wet_kg": total / KELP_DRY_FRAC, "root_shoot": 0.0}


def _fungus_fruitbody_fresh_kg(h: float) -> float:
    """Fruitbody fresh mass by fruitbody height (m); the lock's buckets:
    H<0.02 → 0.01 kg; 0.02–0.10 → 0.10 kg; >0.10 → 0.50 kg."""
    if h < 0.02:
        return 0.01
    if h <= 0.10:
        return 0.10
    return 0.50


def _fungus(axes: Mapping[str, float], plan: str, form: str | None):
    h = axes.get("height_m", 0.0)
    cover = footprint_m2(axes, plan)
    fruit_dry = _fungus_fruitbody_fresh_kg(h) * FUNGUS_DRY_FRAC
    mycelium = MYCELIUM_KG_M2 * cover
    total = fruit_dry + mycelium
    return total, fruit_dry, {
        "fruitbody_dry_kg": fruit_dry,
        "mycelium_kg": mycelium,
        "root_shoot": (mycelium / fruit_dry) if fruit_dry > 0.0 else 0.0,
    }


_DISPATCH = {
    "tree": _tree,
    "shrub": _shrub,
    "herb_forb": _herb,
    "grass_sward": _grass,
    "rosette_mat": _rosette_mat,
    "succulent": _succulent,
    "fern_grade": _herb,
    "moss_grade": _moss,
    "runner_meadow": _runner_meadow,
    "floating_leaf": _floating,
    "floater": _floating,
    "macroalgae_holdfast": _kelp,
    "fungus": _fungus,
    "lichen": _lichen,
}


def percap_biomass(
    axes: Mapping[str, float], plan: str, form: str | None = None
) -> MassEstimate:
    """Per-individual dry biomass (kg) for *plan* given *axes*.

    *form* refines trees only ("broadleaf" default / "conifer" / "tropical"
    / "palm" / "open"); None defaults per group.  Axes read with sane
    defaults: height_m (required-ish — 0 or missing ⇒ zero mass),
    crown_spread_m (0 ⇒ group fallback), woodiness (0), wood_density (0.6),
    clonal_spread_m (0).  Unknown plans raise ValueError.
    """
    if plan not in _DISPATCH:
        raise ValueError(f"unknown plan {plan!r} (expected one of {PLANS})")
    h = max(0.0, axes.get("height_m", 0.0))
    if h == 0.0:
        return MassEstimate(0.0, 0.0, {})
    total, agb, props = _DISPATCH[plan](axes, plan, form)
    return MassEstimate(total, agb, props)
