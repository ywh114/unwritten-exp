"""K14 derived axes & effective climate preference — same ruling as K13
(2026-07-29): axes that can be calculated ARE calculated. TRAITS are
stored and drift-and-commit; DERIVED parameters are pure functions of
the record, recomputed at consumption; climate preference is clade
METADATA (the preset's [niche] table) bundled with the stored tolerance
traits for the rounds' stress model (P7).

- derive_derived(): the mechanical axes — raunkiaer life form, the
  provision map (what this plant OFFERS the food web: mast / graze /
  browse / nectar / shelter, vocabulary §10 hook), clonality_class,
  silhouette (the Hallé tuple rendered for tree/shrub grades).
  Recomputed from the record at the end of every build / round;
  evolve() never drifts them.

- effective_climate(): niche-metadata baseline + stored tolerance
  traits (drought / salinity / waterlogging / growing-season /
  shade). Pure function of record + content, computed at consumption.
"""

from __future__ import annotations

from exp.k14_flora.content import ContentPack
from exp.k14_flora.model import Node

DERIVED_AXES = frozenset({
    "raunkiaer", "provision_mast", "provision_graze", "provision_browse",
    "provision_nectar", "provision_shelter", "clonality_class",
    "silhouette",
})

# raunkiaer thresholds (simplified life-form classification).
PHANERO_HEIGHT_M = 3.0     # buds above this -> phanerophyte
CHAMAE_HEIGHT_M = 0.25     # buds above this -> chamaephyte
GEOPHYTE_ORGANS = ("bulb", "tuber", "corm", "rhizome")
AQUATIC_LAYERS = ("aquatic_surface", "aquatic_benthic")

# provision map: what the food web can take (0..1 each).
MAST_FRUITS = ("berry", "drupe", "pome", "aggregate", "nut", "legume")
MAST_BASE = 0.8
MAST_ANIMAL_WEIGHT = 0.7   # animal dispersal channel amplifies reward
ANIMAL_SYNDROMES = ("bee", "moth", "bird", "bat", "beetle", "fly")
NECTAR_BASE = 0.7
NECTAR_SIZE_REF_MM = 20.0  # flower size for full nectar provision
DEFENSE_GRAZE_DISCOUNT = 0.6    # defense_potency scales palatability
CHEMICAL_GRAZE_MULT = 0.5       # any chemical defense halves it
SHELTER_HEIGHT_REF_M = 10.0

# clonality classes from clonal_spread_m. The sampler floor is 0.01
# (bounds [0.01, 100]; authored 0.0 = non-clonal is trusted), so "none"
# reaches just past the floor — anything at/below 0.02 is effectively
# non-clonal.
CLONAL_NONE_M = 0.02
CLONAL_LOCAL_M = 0.5
CLONAL_PATCH_M = 5.0


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _raunkiaer(node: Node) -> str:
    axes = node.axes
    if node.plan in ("fungus", "lichen"):
        return "N/A"     # decomposers sit outside the plant life-form key
    if axes.get("layer") in AQUATIC_LAYERS:
        return "hydrophyte"
    lon = axes.get("longevity_yr")
    if isinstance(lon, (int, float)) and lon < 1.0:
        return "therophyte"
    if axes.get("storage_organ") in GEOPHYTE_ORGANS:
        return "geophyte"
    h = axes.get("height_m")
    if isinstance(h, (int, float)):
        if h >= PHANERO_HEIGHT_M:
            return "phanerophyte"
        if h >= CHAMAE_HEIGHT_M:
            return "chamaephyte"
    return "hemicryptophyte"


def _palatability(node: Node) -> float:
    """Defense-discounted leaf palatability shared by graze/browse."""
    p = 1.0 - DEFENSE_GRAZE_DISCOUNT * float(
        node.axes.get("defense_potency") or 0.0)
    if node.axes.get("chemical_defense") not in (None, "none", "N/A"):
        p *= CHEMICAL_GRAZE_MULT
    return _clip01(p)


def derive_derived(node: Node, pack: ContentPack) -> None:
    """Recompute the mechanical derived axes from the record in place."""
    if not node.axes:
        return   # kingdom/phylum/class carry no record to derive from
    axes = node.axes
    axes["raunkiaer"] = _raunkiaer(node)

    # ── provision map (vocabulary §10: what the plant offers) ──
    animal_w = 0.0
    channels = axes.get("dispersal_channels")
    if isinstance(channels, dict):
        animal_w = float(channels.get("animal", 0.0))
    mast = (MAST_BASE * (1.0 - MAST_ANIMAL_WEIGHT
                         + MAST_ANIMAL_WEIGHT * animal_w)
            if axes.get("fruit_type") in MAST_FRUITS else 0.0)
    axes["provision_mast"] = _clip01(mast)

    layer = axes.get("layer")
    graze_base = {"sward": 0.8, "ground": 0.8, "shrub": 0.5,
                  "subcanopy": 0.2, "canopy": 0.1,
                  "aquatic_surface": 0.3, "aquatic_benthic": 0.3}.get(
                      layer, 0.0)
    browse_base = {"shrub": 0.6, "subcanopy": 0.7, "canopy": 0.7}.get(
        layer, 0.1)
    pal = _palatability(node)
    axes["provision_graze"] = _clip01(graze_base * pal)
    axes["provision_browse"] = _clip01(browse_base * pal)

    syndrome = axes.get("pollination_syndrome")
    size = axes.get("flower_size_mm")
    nectar = NECTAR_BASE if syndrome in ANIMAL_SYNDROMES else 0.0
    if isinstance(size, (int, float)):
        nectar *= min(1.0, size / NECTAR_SIZE_REF_MM)
    axes["provision_nectar"] = _clip01(nectar)

    h = axes.get("height_m")
    wood = axes.get("woodiness")
    if isinstance(h, (int, float)) and isinstance(wood, (int, float)):
        axes["provision_shelter"] = _clip01(
            wood * min(1.0, h / SHELTER_HEIGHT_REF_M))

    spread = axes.get("clonal_spread_m")
    if isinstance(spread, (int, float)):
        axes["clonality_class"] = (
            "none" if spread <= CLONAL_NONE_M else
            "local" if spread < CLONAL_LOCAL_M else
            "patch" if spread < CLONAL_PATCH_M else "landscape")

    if node.plan in ("tree", "shrub"):
        parts = [str(axes.get(k)) for k in
                 ("halle_axes", "halle_growth", "halle_branching",
                  "halle_orientation")]
        axes["silhouette"] = "/".join(parts)
    else:
        axes["silhouette"] = str(node.plan)


def derive_tree(nodes, pack: ContentPack) -> None:
    """One pass over every node (end of build / end of round)."""
    for n in nodes:
        derive_derived(n, pack)


def effective_climate(node: Node, pack: ContentPack) -> dict:
    """Niche-metadata baseline + stored tolerance traits, for the
    rounds' stress model (P7). The baseline is clade METADATA (the
    preset's [niche] table — not a stored trait); the tolerances ARE
    traits and drift. Pure function of record + content, computed at
    consumption."""
    axes = node.axes
    meta = pack.presets.get(node.preset or "", {}).get("niche", {})
    return {
        "temp_opt_c": meta.get("temp_opt_c"),
        "temp_breadth_c": meta.get("temp_breadth_c"),
        "moisture_opt": meta.get("moisture_opt"),
        "moisture_breadth": meta.get("moisture_breadth"),
        "drought_tolerance": axes.get("drought_tolerance"),
        "salinity_tolerance": axes.get("salinity_tolerance"),
        "waterlogging_tolerance": axes.get("waterlogging_tolerance"),
        "growing_season_req": axes.get("growing_season_req"),
        "shade_tolerance": axes.get("shade_tolerance"),
        "fertility_requirement": axes.get("fertility_requirement"),
    }
