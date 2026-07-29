"""Derived axes & effective climate preference (user ruling, 2026-07-29:
"axes that can be calculated ARE calculated — how else would a sim round
work if there is no stress pressure?").

The partition: TRAITS are stored and drift-and-commit; DERIVED
parameters are pure functions of the record, recomputed at consumption
(neither stored originals nor drift targets); climate preference is
clade METADATA (the [niche] table) modulated by organs.

- derive_derived(): the mechanical axes — niche_breadth (diet entropy),
  maturity (allometry x metabolism), parental_care, territoriality,
  dimorphism. Recomputed from the record at the end of every build /
  round; evolve() never drifts them. wariness is deliberately NOT here:
  it is a trait and drifts with no predator pressure. Authored-only
  axes (engineer_impact, mutualist_links) are content [niche] traits
  and drift like any other.

- effective_climate(): organ-modulated temperature/moisture preference
  for the rounds' stress model. Baseline = the preset's [niche]
  metadata; organs say what the body can actually back it with.
  Blubber shifts down, ectothermy narrows, evaporative cooling widens
  hot-side. Idempotent: computed from record + content, never stored.
"""

from __future__ import annotations

import math

from exp.k13_treegen.content import ContentPack
from exp.k13_treegen.model import Node

DERIVED_AXES = frozenset({
    "niche_breadth", "maturity_age_yr", "parental_care",
    "territoriality", "dimorphism_direction", "size_dimorphism_ratio",
})
# NOT derived: wariness is a trait (user ruling: it drifts with no
# predator pressure — deriving it from mass/trophic would pin it).

# parental care enum from fecundity (r/K): breeders of many guard less.
CARE_FEC_GUARD = 30.0     # above -> "none"
CARE_FEC_PROVISION = 10.0  # above -> "guard"
CARE_FEC_EXTENDED = 3.0    # above -> "provision"; below -> "extended"
# territoriality by dominant diet guild; solitary amplifies.
TERR_PREDATOR = 0.75
TERR_OTHER = 0.2
TERR_SOLITARY_MULT = 1.2
# dimorphism: ornament-driven; herd social organization is the
# polygyny-grade signal in the current social_system vocabulary.
DIMORPH_RATIO_CAP = 3.0
DIMORPH_SIGNAL_BONUS = 0.3
DIMORPH_DIRECTION_MIN = 1.15   # ratio above this -> direction "male"
# maturity: years ~ MATURE_COEFF x mass^0.25 (x1.5 for ectotherms).
MATURE_COEFF = 2.0
MATURE_ECTOTHERM_MULT = 1.5

# effective_climate organ modifiers (rounds' stress model).
BLUBBER_OPT_SHIFT_C = -4.0       # per unit blubber_thickness
ENDOTHERM_BREADTH_MULT = 1.3
ECTOTHERM_BREADTH_MULT = 0.6
COOLING_BREADTH_BONUS = 0.15     # evaporative cooling widens hot side
FUR_MOISTURE_BREADTH_MULT = 0.8  # fur/f eathers handle wet+dry better
PERMEABLE_MOISTURE_BREADTH_MULT = 0.6


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _dominant_guild(node: Node) -> str | None:
    spec = node.axes.get("diet_spectrum")
    if not isinstance(spec, dict) or not spec:
        return None
    return max(spec.items(), key=lambda kv: kv[1])[0]


def derive_derived(node: Node, pack: ContentPack) -> None:
    """Recompute the mechanical derived axes from the record in place."""
    axes = node.axes

    spec = axes.get("diet_spectrum")
    if isinstance(spec, dict) and spec:
        total = sum(spec.values()) or 1.0
        ent = -sum((w / total) * math.log(w / total)
                   for w in spec.values() if w > 0)
        axes["niche_breadth"] = (ent / math.log(len(spec))
                                 if len(spec) > 1 else 0.0)

    mass = axes.get("body_mass")
    if isinstance(mass, (int, float)) and mass > 0:
        ecto = node.generics.get("metabolism") == "ectotherm"
        axes["maturity_age_yr"] = (MATURE_COEFF * mass ** 0.25
                                   * (MATURE_ECTOTHERM_MULT
                                      if ecto else 1.0))

    fec = axes.get("fecundity")
    if isinstance(fec, (int, float)) and fec > 0:
        if node.generics.get("social") == "eusocial" or \
                axes.get("social_system") == "eusocial":
            axes["parental_care"] = "guard"   # colony care
        elif fec > CARE_FEC_GUARD:
            axes["parental_care"] = "none"
        elif fec > CARE_FEC_PROVISION:
            axes["parental_care"] = "guard"
        elif fec > CARE_FEC_EXTENDED:
            axes["parental_care"] = "provision"
        else:
            axes["parental_care"] = "extended"

    guild = _dominant_guild(node)
    terr = TERR_PREDATOR if guild in ("carnivore", "piscivore",
                                      "insectivore") else TERR_OTHER
    if axes.get("social_system") == "solitary":
        terr *= TERR_SOLITARY_MULT
    axes["territoriality"] = _clip01(terr)

    ornament = 0.0
    if node.generics.get("covering") == "fur":
        mr = axes.get("mane_ruff_extent")
        if isinstance(mr, (int, float)):
            ornament += mr
    if node.generics.get("signal") in ("antlers", "horns_keratin", "mane"):
        ornament += DIMORPH_SIGNAL_BONUS
    ratio = min(DIMORPH_RATIO_CAP, 1.0 + ornament)
    axes["size_dimorphism_ratio"] = ratio
    axes["dimorphism_direction"] = ("male"
                                    if ratio > DIMORPH_DIRECTION_MIN
                                    else "none")


def derive_tree(nodes, pack: ContentPack) -> None:
    """One pass over every node (end of build / end of round)."""
    for n in nodes:
        derive_derived(n, pack)


def effective_climate(node: Node, pack: ContentPack) -> dict:
    """Organ-modulated climate preference for the rounds' stress model.

    The baseline is clade METADATA (the preset's [niche] table — not a
    stored trait); the organs say what the body can actually back it
    with. Pure function of record + content, computed at consumption.
    """
    axes = node.axes
    meta = pack.presets.get(node.preset or "", {}).get("niche", {})
    opt = meta.get("temp_opt_c")
    breadth = meta.get("temp_breadth_c")
    m_opt = meta.get("moisture_opt")
    m_breadth = meta.get("moisture_breadth")

    opt_eff = float(opt) if isinstance(opt, (int, float)) else None
    br_eff = float(breadth) if isinstance(breadth, (int, float)) else None

    if opt_eff is not None:
        blub = axes.get("blubber_thickness")
        if isinstance(blub, (int, float)):
            opt_eff += BLUBBER_OPT_SHIFT_C * blub
    if br_eff is not None:
        metab = node.generics.get("metabolism")
        if metab == "endotherm":
            br_eff *= ENDOTHERM_BREADTH_MULT
        elif metab == "ectotherm":
            br_eff *= ECTOTHERM_BREADTH_MULT
        if axes.get("cooling_mode") not in (None, "none", "N/A"):
            br_eff += COOLING_BREADTH_BONUS

    mbr_eff = float(m_breadth) \
        if isinstance(m_breadth, (int, float)) else None
    if mbr_eff is not None:
        covering = node.generics.get("covering")
        if covering in ("fur", "feathers", "keratin_scales",
                        "osteoderm_armor", "chitin_cuticle_sclerotized"):
            mbr_eff *= FUR_MOISTURE_BREADTH_MULT
        # permeable skin (bare "skinned") narrows moisture tolerance
        elif covering in (None, "skinned"):
            mbr_eff *= PERMEABLE_MOISTURE_BREADTH_MULT

    return {"temp_opt_c": opt_eff, "temp_breadth_c": br_eff,
            "moisture_opt": m_opt, "moisture_breadth": mbr_eff}
