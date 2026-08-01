"""Flora derived axes & effective climate preference — same ruling as K13
(2026-07-29): axes that can be calculated ARE calculated. TRAITS are
stored and drift-and-commit; DERIVED parameters are pure functions of
the record, recomputed at consumption.

- derive_derived(): the mechanical axes — raunkiaer life form, the
  provision map (what this plant OFFERS the food web: mast / graze /
  browse / nectar / shelter, vocabulary §10 hook), clonality_class,
  silhouette (the Hallé tuple rendered for tree/shrub grades), and the
  B5 §5.2 derived flower_color (pathway × expression × ph position).
  Recomputed from the record at the end of every build / round;
  evolve() never drifts them.

- effective_climate(): the climate ENVELOPE (temp_opt_c / temp_breadth_c
  / moisture_opt / moisture_breadth) as a pure DERIVED of the trait
  bundle — owner ruling 2026-08-01: the envelope is like every other
  derived, NOT clade metadata, so when stress pushes the traits (the
  backward pass) the envelope MOVES. The tolerance passthrough traits
  (drought / salinity / waterlogging / growing-season / ph / shade /
  fertility) ride the same view. Pure function of record, computed at
  consumption.
"""

from __future__ import annotations

import math

from exp.k13_treegen.flora.content import ContentPack
from exp.k13_treegen.model import Node

DERIVED_AXES = frozenset({
    "raunkiaer", "provision_mast", "provision_graze", "provision_browse",
    "provision_nectar", "provision_shelter", "clonality_class",
    "silhouette", "flower_color", "leaf_color", "autumn_color",
    "canopy_density",
})

# ── derived flower_color (B5 §5.2) ─────────────────────────────────────
# flower_color is no longer a drifted trait: it is computed from the
# pigment chemistry at derive time — pathway × expression × ph_tolerance
# position. The bucket names ARE the legacy enum vocabulary that the
# naming stems (stems_flora.toml color pools) and the id/tell consumers
# read; "black" is intentionally unreachable (no stem pool covers it).
FLOWER_COLOR_VOCAB = ("white", "cream", "yellow", "orange", "red", "pink",
                      "purple", "blue", "green", "brown")
PIGMENT_PATHWAYS = ("none", "anthocyanin", "carotenoid", "betalain")

# expression thresholds (shared 0..1 scale — the drift substrate for the
# runaway / F3 pollinator coupling).
EXPR_WHITE = 0.15          # at/below: petals effectively unpigmented
EXPR_CREAM = 0.35          # carotenoid low-mid: cream
EXPR_PINK_RED = 0.55       # acid anthocyanin pink<->red hinge
EXPR_PINK_PURPLE = 0.4     # neutral anthocyanin pink<->purple hinge
EXPR_ORANGE = 0.7          # carotenoid yellow<->orange hinge
EXPR_BET_ORANGE = 0.5      # betalain yellow<->orange hinge
EXPR_DEEP = 0.9            # carotenoid/betalain orange<->red hinge

# ph_tolerance zone hinges (pH optimum = 4.0 + 5.0 × value): below 0.35
# acid (opt < 5.75) -> red/pink, 0.35..0.65 neutral (5.75-7.25) ->
# purple, at/above 0.65 alkaline (opt > 7.25) -> blue (hydrangea logic).
PH_ACID_HI = 0.35
PH_ALKALINE_LO = 0.65

# The wind set (pathway none): green for woody wind plants and the
# green-flagged grades (moss sporophytes, submerged/self seed plants),
# brown for herbaceous chaff / spore-mass / fruiting-body grades.
DULL_GREEN_PLANS = {"moss_grade", "runner_meadow", "floater"}
DULL_WOODY_GREEN = 0.5     # woodiness at/above -> green

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

# ── the climate envelope (pure derived, owner ruling 2026-08-01) ──────
# The four envelope values are computed from the DRIFTABLE trait bundle
# — no [niche] metadata anywhere (the preset tables no longer carry it).
# When stress pushes the traits (select -> mutate, the backward pass),
# the envelope moves with them: a lineage pushed toward winter
# deciduousness / lower growing-season need / C4 runs a colder optimum;
# cuticle and smaller leaves (the HEAT-side continuous dials, owner
# ruling 2026-08-01 — the old heat side had only the discrete C4 switch
# gated at DISCRETE_THRESHOLD, unreachable at viable cells) run a hotter
# one; drought tolerance, succulence, cuticle, small leaves and
# waterlogging tolerance slide the moisture envelope. Numeric axes that
# a plan does not author read 0 (or the neutral value noted) — a missing
# axis is a neutral trait, not an error (a missing/non-numeric
# leaf_size_cm reads leaf_norm 1.0, so the (1 - leaf_norm) heat/arid
# dials vanish). All axis scales per axes_core.toml: succulence,
# pubescence, cuticle_thickness, drought_tolerance and
# waterlogging_tolerance are 0..1 normalized; leaf_size_cm is
# log-normalized over [0.05, 400.0] (wide bounds — the leaf economics
# spectrum is log-shaped); snow_adaptation and photosynthesis are enums.
T_BASE_C = 18.0          # neutral woody/C3 optimum
T_DECID_C = 8.0          # winter-deciduous optimum drop (leafless winter)
T_GS_C = 1.5             # per month of growing-season shortfall vs GS_REF
GS_REF_C = 6.0           # months; low requirement = cold-adapted
T_PUB_C = 3.0            # pubescence (0..1) -> silvery reflectance drop
T_SNOW_C = 4.0           # any snow_adaptation state -> cold-tolerant
T_C4_C = 6.0             # C4 runs hotter
T_CAM_C = 10.0           # CAM hotter still
T_SUCC_C = 4.0           # succulent tissue stores against heat
T_CUTICLE_C = 3.0        # cuticle (0..1) -> heat-dial shield/reflectance
T_LEAF_C = 4.0           # (1 - leaf_norm): small leaves shed heat
TEMP_OPT_LO, TEMP_OPT_HI = -30.0, 45.0

B_T_BASE = 20.0
B_T_DECID = 4.0          # deciduous = a wider seasonal band
B_T_TOL = 3.0            # drought tolerance widens the thermal band
TEMP_BREADTH_LO, TEMP_BREADTH_HI = 2.0, 20.0

P_BASE = 0.55            # neutral moisture optimum on the normalized scale
P_DROUGHT = 0.35         # drought tolerance buys a drier optimum
P_SUCC = 0.12            # succulence stores water: drier optimum
P_C4 = 0.08              # C4 water-efficiency: drier optimum
P_CAM = 0.15             # CAM most water-efficient
P_CUTICLE = 0.08         # cuticle trims transpiration: drier optimum
P_LEAF = 0.10            # (1 - leaf_norm): small leaves = arid adaptation
MOISTURE_OPT_LO, MOISTURE_OPT_HI = 0.02, 0.98

# leaf_size_cm axis bounds (axes_core.toml [0.05, 400.0]) — wide, so the
# normalized leaf dials run on a LOG scale (the leaf economics spectrum
# is log-shaped): leaf_norm 0 = smallest leaf (max heat/arid dial),
# 1 = largest (no dial).
LEAF_SIZE_LO_CM = 0.05
LEAF_SIZE_HI_CM = 400.0
LEAF_LOG_LO = math.log(LEAF_SIZE_LO_CM)
LEAF_LOG_SPAN = math.log(LEAF_SIZE_HI_CM) - LEAF_LOG_LO

P_B_BASE = 0.26
P_B_DROUGHT = 0.10       # drought tolerance widens the moisture band
P_B_WLOG = 0.06          # waterlogging tolerance too
MOISTURE_BREADTH_LO, MOISTURE_BREADTH_HI = 0.03, 0.5
# Breadth calibration 2026-08-01 (T0001, viable-range collapse): the
# genesis-range audit (tmp/k15_range_check.py, seed 1) measured 7
# presets at ZERO cells under the unit-weight T terms — the derived
# breadths (B_T_BASE 6.0, P_B_BASE 0.08) were too narrow for the
# authored optima on this world's temperature range. Both bases were
# RAISED (6 -> 20, 0.08 -> 0.26) until every preset cleared 50 cells;
# the residual failures were trait re-authors (stonecrop/cactus CAM ->
# C3, duckweed/ludwigia winter-deciduous, sphagnum cushion_mat) —
# documented in biosphere-addendum-b6-flora-wiring.md §4. GENESIS_F and
# the factor product were NOT softened.


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _leaf_norm(axes: dict) -> float:
    """leaf_size_cm normalized 0..1 on a LOG scale over the axis bounds
    [0.05, 400.0] (wide — see LEAF_LOG_*). Small leaves -> 0 (the max
    heat/arid dial), largest leaves -> 1 (no dial). Missing /
    non-numeric / nonpositive reads 1.0: a neutral trait, so the
    (1 - leaf_norm) heat/arid terms vanish."""
    v = axes.get("leaf_size_cm")
    if not isinstance(v, (int, float)) or v <= 0.0:
        return 1.0
    return _clip01((math.log(float(v)) - LEAF_LOG_LO) / LEAF_LOG_SPAN)


def _dull_color(node: Node) -> str:
    """The wind set for pigment_pathway none: green on woody wind plants
    and the green-flagged grades, brown on herbaceous chaff / spore-mass
    / fruiting-body grades (matches the authored dull palette)."""
    wood = node.axes.get("woodiness")
    if isinstance(wood, (int, float)) and wood >= DULL_WOODY_GREEN:
        return "green"
    if node.plan in DULL_GREEN_PLANS:
        return "green"
    return "brown"


def _anthocyanin_color(expr: float, ph: float) -> str:
    """Hue slides with the pH optimum (acid red/pink, neutral purple,
    alkaline blue); expression scales saturation white↔deep."""
    if expr < EXPR_WHITE:
        return "white"
    if ph < PH_ACID_HI:
        return "pink" if expr < EXPR_PINK_RED else "red"
    if ph < PH_ALKALINE_LO:
        return "pink" if expr < EXPR_PINK_PURPLE else "purple"
    return "blue"


def _carotenoid_color(expr: float) -> str:
    """Yellow/orange/red, pH-stable (low expression reads cream)."""
    if expr < EXPR_WHITE:
        return "white"
    if expr < EXPR_CREAM:
        return "cream"
    if expr < EXPR_ORANGE:
        return "yellow"
    if expr < EXPR_DEEP:
        return "orange"
    return "red"


def _betalain_color(expr: float) -> str:
    """Red/yellow, pH-stable — never blue/purple (Caryophyllales)."""
    if expr < EXPR_WHITE:
        return "white"
    if expr < EXPR_BET_ORANGE:
        return "yellow"
    if expr < EXPR_DEEP:
        return "orange"
    return "red"


def _derived_flower_color(node: Node) -> str:
    """B5 §5.2: pathway × expression × ph_tolerance position -> the
    legacy named bucket. None (or ~0 expression) is the dull wind set.
    (No falsy-`or` defaults: 0.0 is a legitimate authored value on both
    scalars — an obligate calcifuge at ph 0.0 must not read neutral.)"""
    pathway = str(node.axes.get("pigment_pathway") or "none")
    expr_v = node.axes.get("pigment_expression")
    expr = _clip01(float(expr_v)) if isinstance(expr_v, (int, float)) \
        else 0.0
    if pathway == "none" or expr < EXPR_WHITE:
        return _dull_color(node) if pathway == "none" else "white"
    ph_v = node.axes.get("ph_tolerance")
    ph = _clip01(float(ph_v)) if isinstance(ph_v, (int, float)) else 0.5
    if pathway == "anthocyanin":
        return _anthocyanin_color(expr, ph)
    if pathway == "carotenoid":
        return _carotenoid_color(expr)
    if pathway == "betalain":
        return _betalain_color(expr)
    return _dull_color(node)   # unknown pathway: the wind set


# ── display derivations (leaf/autumn color, canopy density) ──────────
# leaf_color precedence thresholds (0..1 authored scales; sla on the
# 1..60 economics spectrum).
LEAF_RED_EXPR = 0.55         # pigment expression for red foliage
LEAF_GRAY_PUB = 0.6          # pubescence at/above -> silvery gray
LEAF_GLAUCOUS_CUT = 0.6      # cuticle wax at/above -> glaucous blue
LEAF_LIGHT_SLA = 20.0        # thin cheap leaves -> light green
LEAF_DARK_SLA = 8.0          # thick expensive leaves -> dark green
# autumn: expression floors per pathway (below: unpigmented -> brown)
AUTUMN_RED_EXPR = 0.35
# canopy density (P9 provisional): base by woodiness, adjusted by the
# leaf economics spectrum, evergreen cover and succulence.
CD_WOODY_BASE = 0.55
CD_HERB_BASE = 0.3
CD_WOODY_T = 0.5             # woodiness at/above -> woody base
CD_SLA_LOW = 8.0
CD_SLA_LOW_ADD = 0.2         # sclerophyll foliage packs dense
CD_SLA_HIGH = 20.0
CD_SLA_HIGH_SUB = 0.1        # thin leaves = open canopy
CD_EVERGREEN_ADD = 0.1       # year-round cover
CD_SUCC_T = 0.5
CD_SUCC_ADD = 0.1


def _deciduous(node: Node) -> bool:
    """Winter- or drought-shedding by either the persistence state or
    the trigger (the sim's winter_deciduous/drought_deciduous flags)."""
    lp = str(node.axes.get("leaf_persistence") or "evergreen")
    dt = str(node.axes.get("deciduous_trigger") or "none")
    return lp in ("winter_deciduous", "drought_deciduous") \
        or dt in ("winter", "drought")


def _num(axes: dict, key: str, default: float) -> float:
    v = axes.get(key)
    return float(v) if isinstance(v, (int, float)) else default


def _derived_leaf_color(node: Node) -> str:
    """Display bucket, precedence: leafless -> red pigment -> gray
    pubescence -> glaucous wax -> sla economics -> green."""
    axes = node.axes
    if str(axes.get("leaf_shape") or "none") == "none":
        return "none"
    pathway = str(axes.get("pigment_pathway") or "none")
    expr = _clip01(_num(axes, "pigment_expression", 0.0))
    if pathway in ("anthocyanin", "betalain") and expr >= LEAF_RED_EXPR:
        return "red"
    if _num(axes, "pubescence", 0.0) >= LEAF_GRAY_PUB:
        return "gray"
    if _num(axes, "cuticle_thickness", 0.0) >= LEAF_GLAUCOUS_CUT:
        return "glaucous"
    sla = _num(axes, "leaf_sla", 10.0)
    if sla >= LEAF_LIGHT_SLA:
        return "light_green"
    if sla <= LEAF_DARK_SLA:
        return "dark_green"
    return "green"


def _derived_autumn_color(node: Node) -> str:
    """Display bucket for the shedding season: evergreens and leafless
    plans read none; the pathway sets the hue, expression the floor."""
    axes = node.axes
    if str(axes.get("leaf_shape") or "none") == "none" \
            or not _deciduous(node):
        return "none"
    pathway = str(axes.get("pigment_pathway") or "none")
    expr = _clip01(_num(axes, "pigment_expression", 0.0))
    if pathway in ("anthocyanin", "betalain"):
        return "red" if expr >= AUTUMN_RED_EXPR else "brown"
    if pathway == "carotenoid":
        if expr >= EXPR_ORANGE:
            return "orange"
        if expr >= EXPR_WHITE:
            return "yellow"
        return "brown"
    return "brown"


def _derived_canopy_density(node: Node) -> float:
    """P9 provisional: how much light the canopy blocks, 0..1 — the
    field the understory will read (never a direct pressure term)."""
    axes = node.axes
    if str(axes.get("leaf_shape") or "none") == "none":
        return 0.0
    d = CD_WOODY_BASE if _num(axes, "woodiness", 0.0) >= CD_WOODY_T \
        else CD_HERB_BASE
    sla = _num(axes, "leaf_sla", 10.0)
    if sla <= CD_SLA_LOW:
        d += CD_SLA_LOW_ADD
    elif sla >= CD_SLA_HIGH:
        d -= CD_SLA_HIGH_SUB
    if not _deciduous(node):
        d += CD_EVERGREEN_ADD
    if _num(axes, "succulence", 0.0) >= CD_SUCC_T:
        d += CD_SUCC_ADD
    return _clip01(d)


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
    axes["flower_color"] = _derived_flower_color(node)
    axes["leaf_color"] = _derived_leaf_color(node)
    axes["autumn_color"] = _derived_autumn_color(node)
    axes["canopy_density"] = _derived_canopy_density(node)

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
    """The climate envelope as a pure DERIVED of the trait bundle (owner
    ruling 2026-08-01): no [niche] metadata anywhere — when stress moves
    the traits, the envelope moves with them. Returns the four envelope
    values plus the tolerance passthrough traits the rounds' stress
    model (stress_adapter) reads. Pure function of record + content,
    computed at consumption."""
    axes = node.axes

    def _num(key: str, default: float = 0.0) -> float:
        v = axes.get(key)
        return float(v) if isinstance(v, (int, float)) else default

    lp = str(axes.get("leaf_persistence") or "evergreen")
    dt = str(axes.get("deciduous_trigger") or "none")
    winter_dec = int(lp == "winter_deciduous" or dt == "winter")
    photo = str(axes.get("photosynthesis") or "C3")
    drought = _num("drought_tolerance")
    succ = _num("succulence")
    pub = _num("pubescence")
    cuticle = _num("cuticle_thickness")
    wlog = _num("waterlogging_tolerance")
    snow = int(str(axes.get("snow_adaptation") or "none") != "none")
    gs_req = _num("growing_season_req", GS_REF_C)   # months; missing -> ref
    leaf_norm = _leaf_norm(axes)   # log-normalized; missing -> neutral 1.0

    temp_opt = (T_BASE_C
                - T_DECID_C * winter_dec
                - T_GS_C * max(0.0, GS_REF_C - gs_req)
                - T_PUB_C * pub
                - T_SNOW_C * snow
                + T_C4_C * int(photo == "C4")
                + T_CAM_C * int(photo == "CAM")
                + T_SUCC_C * succ
                + T_CUTICLE_C * cuticle
                + T_LEAF_C * (1.0 - leaf_norm))
    temp_opt = min(TEMP_OPT_HI, max(TEMP_OPT_LO, temp_opt))
    temp_breadth = min(TEMP_BREADTH_HI,
                       max(TEMP_BREADTH_LO,
                           B_T_BASE + B_T_DECID * winter_dec
                           + B_T_TOL * drought))
    moisture_opt = min(MOISTURE_OPT_HI,
                       max(MOISTURE_OPT_LO,
                           P_BASE - P_DROUGHT * drought - P_SUCC * succ
                           - P_C4 * int(photo == "C4")
                           - P_CAM * int(photo == "CAM")
                           - P_CUTICLE * cuticle
                           - P_LEAF * (1.0 - leaf_norm)))
    moisture_breadth = min(MOISTURE_BREADTH_HI,
                           max(MOISTURE_BREADTH_LO,
                               P_B_BASE + P_B_DROUGHT * drought
                               + P_B_WLOG * wlog))
    return {
        "temp_opt_c": temp_opt,
        "temp_breadth_c": temp_breadth,
        "moisture_opt": moisture_opt,
        "moisture_breadth": moisture_breadth,
        "drought_tolerance": axes.get("drought_tolerance"),
        "salinity_tolerance": axes.get("salinity_tolerance"),
        "waterlogging_tolerance": axes.get("waterlogging_tolerance"),
        "ph_tolerance": axes.get("ph_tolerance"),
        "growing_season_req": axes.get("growing_season_req"),
        "shade_tolerance": axes.get("shade_tolerance"),
        "fertility_requirement": axes.get("fertility_requirement"),
    }
