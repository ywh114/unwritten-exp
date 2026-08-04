"""The canonical species-view assembler for the K15 biosphere rewrite
(ticket 0042; spec B9 §3, §4).

THIS IS THE ONLY DERIVE PATH in exp/k15_biosphere (B9 §8: one assembler).
``assemble_view`` turns a committed ``SpeciesRecord`` into the full
derived view — climate envelope, morphology (mechanical deriveds), plan
descriptors, dispersal equipment, per-individual biomass, and the
intrinsic-stress block — and every other layer (occupancy L2, dynamics
L3, the game layer's spawn decisions) reads the view and computes
nothing itself.  The view is COMPUTED ON READ, never stored: the record
holds committed traits only, and assembling a view never mutates it
(B9 §1).  Nothing in k15_biosphere re-derives these fields.

The k13-era mirror pair this replaces — ``FloraSim.derive``
(exp/k13_treegen/flora/sim.py) and ``stress_adapter._view_from_record``
(exp/k15_simdiff/stress_adapter.py), kept in sync by comments, with
``ANCHOR_REF_M`` literally defined twice — is NOT ported; the full
~49-key carried vocabulary lives here once (owner ruling: pruning is
easier than adding — the whole k13 key set rides over, and new fields
only ever get added to this one assembler).

The derived logic itself is ported from the frozen k13 reference
(exp/k13_treegen/flora/derive.py — climate envelope + mechanical
deriveds, spec B9 §2) with two adaptations: helpers take ``(axes,
plan)`` instead of a k13 ``Node``, and every key is always written
(missing axes read the neutral value documented at each helper, so the
full key set is present on every flora view; the k13 habit of omitting
a key when its input axis is missing dies).

Intrinsic stress (B9 §4) is the only novelty: a family of stress types
— mechanical support, energetics, and successors — each an ordinary
SCALAR stress in the stress → derived → trait paradigm, reading ONLY
the view's derived proportions (never the record's raw axes).  Each
type carries a plan-aware viable envelope, a plateau-with-cliffs
penalty curve (flat + very weak leakage inside, cliff outside — the
anti-carcinisation ruling), a vital-cost scalar (the stress value
itself), and responder-wiring documentation.  Envelopes and curves are
module-level NAMED CONSTANTS here; they graduate to content tables when
fauna lands (spec §13 idiom, B9 §4).  Authored exception bubbles are
supported in the function signatures (the assembler and the stress
functions accept them); wiring bubble DATA into the pin/preset loader
is a later ticket.

Determinism hard rule: no randomness, no wall-clock; iteration over
proportion knobs is sorted; two assemblies of the same record are
equal and byte-stable.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping, Sequence

from exp.k15_biosphere.content import ContentPack
from exp.k15_biosphere.flora.mass import percap_biomass
from exp.k15_biosphere.record import SpeciesRecord

# ══════════════════════════════════════════════════════════════════════
# ──  the carried-over k13 view vocabulary (B9 §3, owner ruling)  ──────
# ══════════════════════════════════════════════════════════════════════

# Every key the k13 view carried (climate envelope + tolerance
# passthroughs + mechanical deriveds + plan descriptors + B6 hand-wiring
# + dispersal keys), minus the in-place derived writes that died (B9 §1).
# The §8 acceptance test asserts this set on every flora plan's view.
CARRIED_KEYS = frozenset({
    # climate envelope + tolerance passthroughs (effective_climate)
    "temp_opt_c", "temp_breadth_c", "moisture_opt", "moisture_breadth",
    "drought_tolerance", "salinity_tolerance", "waterlogging_tolerance",
    "ph_tolerance", "growing_season_req", "shade_tolerance",
    "fertility_requirement",
    # mechanical deriveds (derive_derived)
    "raunkiaer", "flower_color", "leaf_color", "autumn_color",
    "canopy_density", "provision_mast", "provision_graze",
    "provision_browse", "provision_nectar", "provision_shelter",
    "clonality_class", "silhouette",
    # plan descriptors (FloraSim.derive block)
    "root_depth_m", "height_m", "woodiness", "photosynthesis",
    "winter_deciduous", "leafout_month", "drought_deciduous",
    "bloom_start_month", "bloom_length_months", "medium",
    "anchoring_need", "holdfast", "submerged",
    # B6 hand-wiring keys
    "mycorrhizal", "n_fixation", "nutrient_package", "drip_tips",
    "leaf_margin", "snow_adaptation", "layer",
    # engine-side dispersal keys + per-capita space demand
    "dispersal_channels", "propagule_mass_mg", "propagule_count",
    "seed_bank", "jump_rate", "crown_spread_m",
})

# ── the locked anchoring constant, defined ONCE (the k13-era duplicate
# ── in stress_adapter.py/FloraSim.derive dies with this module).
ANCHOR_REF_M = 25.0     # full anchoring need for woody land plants

# ── tree mass form by committed preset grade (stopgap).  The mass hook
# ── (flora/mass.py, lock v1.1) refines trees by *form* — broadleaf /
# ── conifer / tropical / palm / open — but the record commits a grade
# ── (via the preset), not a form trait; this mapping is the only bridge
# ── until the record carries form explicitly.  Unknown grades → None →
# ── the mass hook's per-plan default (broadleaf).
TREE_FORM_BY_GRADE = {
    "conifer": "conifer",
    "palm": "palm",
    "tropical": "tropical",
    "mangrove": "tropical",      # prop-rooted tropical tree; k≈18 either way
    "oak": "broadleaf",
    "willow": "broadleaf",
    "sandalwood": "broadleaf",
}


# ══════════════════════════════════════════════════════════════════════
# ──  mechanical deriveds (ported from k13 derive.py, B9 §2)  ───────────
# ══════════════════════════════════════════════════════════════════════

# flower_color (B5 §5.2): pathway × expression × ph_tolerance position
# -> the legacy named bucket.  "black" is intentionally unreachable (no
# stem pool covers it).
EXPR_WHITE = 0.15          # at/below: petals effectively unpigmented
EXPR_CREAM = 0.35          # carotenoid low-mid: cream
EXPR_PINK_RED = 0.55       # acid anthocyanin pink<->red hinge
EXPR_PINK_PURPLE = 0.4     # neutral anthocyanin pink<->purple hinge
EXPR_ORANGE = 0.7          # carotenoid yellow<->orange hinge
EXPR_BET_ORANGE = 0.5      # betalain yellow<->orange hinge
EXPR_DEEP = 0.9            # carotenoid/betalain orange<->red hinge
PH_ACID_HI = 0.35          # below: acid (opt < 5.75) -> red/pink
PH_ALKALINE_LO = 0.65      # at/above: alkaline (opt > 7.25) -> blue
DULL_GREEN_PLANS = {"moss_grade", "runner_meadow", "floater"}
DULL_WOODY_GREEN = 0.5     # woodiness at/above -> green (wind set)

# raunkiaer thresholds.
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

# clonality classes from clonal_spread_m.
CLONAL_NONE_M = 0.02
CLONAL_LOCAL_M = 0.5
CLONAL_PATCH_M = 5.0

# display derivations (leaf/autumn color, canopy density).
LEAF_RED_EXPR = 0.55         # pigment expression for red foliage
LEAF_GRAY_PUB = 0.6          # pubescence at/above -> silvery gray
LEAF_GLAUCOUS_CUT = 0.6      # cuticle wax at/above -> glaucous blue
LEAF_LIGHT_SLA = 20.0        # thin cheap leaves -> light green
LEAF_DARK_SLA = 8.0          # thick expensive leaves -> dark green
AUTUMN_RED_EXPR = 0.35       # autumn: expression floor per pathway
CD_WOODY_BASE = 0.55         # canopy density (P9 provisional)
CD_HERB_BASE = 0.3
CD_WOODY_T = 0.5
CD_SLA_LOW = 8.0
CD_SLA_LOW_ADD = 0.2
CD_SLA_HIGH = 20.0
CD_SLA_HIGH_SUB = 0.1
CD_EVERGREEN_ADD = 0.1
CD_SUCC_T = 0.5
CD_SUCC_ADD = 0.1


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _num(axes: Mapping, key: str, default: float) -> float:
    v = axes.get(key)
    return float(v) if isinstance(v, (int, float)) else default


def _deciduous(axes: Mapping) -> bool:
    """Winter- or drought-shedding by either the persistence state or
    the trigger (the sim's winter_deciduous/drought_deciduous flags)."""
    lp = str(axes.get("leaf_persistence") or "evergreen")
    dt = str(axes.get("deciduous_trigger") or "none")
    return lp in ("winter_deciduous", "drought_deciduous") \
        or dt in ("winter", "drought")


def _dull_color(axes: Mapping, plan: str) -> str:
    """The wind set for pigment_pathway none: green on woody wind plants
    and the green-flagged grades, brown on herbaceous chaff / spore-mass
    / fruiting-body grades."""
    wood = axes.get("woodiness")
    if isinstance(wood, (int, float)) and wood >= DULL_WOODY_GREEN:
        return "green"
    if plan in DULL_GREEN_PLANS:
        return "green"
    return "brown"


def _anthocyanin_color(expr: float, ph: float) -> str:
    if expr < EXPR_WHITE:
        return "white"
    if ph < PH_ACID_HI:
        return "pink" if expr < EXPR_PINK_RED else "red"
    if ph < PH_ALKALINE_LO:
        return "pink" if expr < EXPR_PINK_PURPLE else "purple"
    return "blue"


def _carotenoid_color(expr: float) -> str:
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


def _derived_flower_color(axes: Mapping, plan: str) -> str:
    """B5 §5.2: pathway × expression × ph_tolerance position -> the
    legacy named bucket.  (No falsy-`or` defaults: 0.0 is a legitimate
    authored value on both scalars.)"""
    pathway = str(axes.get("pigment_pathway") or "none")
    expr_v = axes.get("pigment_expression")
    expr = _clip01(float(expr_v)) if isinstance(expr_v, (int, float)) \
        else 0.0
    if pathway == "none" or expr < EXPR_WHITE:
        return _dull_color(axes, plan) if pathway == "none" else "white"
    ph_v = axes.get("ph_tolerance")
    ph = _clip01(float(ph_v)) if isinstance(ph_v, (int, float)) else 0.5
    if pathway == "anthocyanin":
        return _anthocyanin_color(expr, ph)
    if pathway == "carotenoid":
        return _carotenoid_color(expr)
    if pathway == "betalain":
        return _betalain_color(expr)
    return _dull_color(axes, plan)   # unknown pathway: the wind set


def _derived_leaf_color(axes: Mapping) -> str:
    """Display bucket, precedence: leafless -> red pigment -> gray
    pubescence -> glaucous wax -> sla economics -> green."""
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


def _derived_autumn_color(axes: Mapping) -> str:
    """Display bucket for the shedding season: evergreens and leafless
    plans read none; the pathway sets the hue, expression the floor."""
    if str(axes.get("leaf_shape") or "none") == "none" \
            or not _deciduous(axes):
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


def _derived_canopy_density(axes: Mapping) -> float:
    """P9 provisional: how much light the canopy blocks, 0..1 — the
    field the understory will read (never a direct pressure term)."""
    if str(axes.get("leaf_shape") or "none") == "none":
        return 0.0
    d = CD_WOODY_BASE if _num(axes, "woodiness", 0.0) >= CD_WOODY_T \
        else CD_HERB_BASE
    sla = _num(axes, "leaf_sla", 10.0)
    if sla <= CD_SLA_LOW:
        d += CD_SLA_LOW_ADD
    elif sla >= CD_SLA_HIGH:
        d -= CD_SLA_HIGH_SUB
    if not _deciduous(axes):
        d += CD_EVERGREEN_ADD
    if _num(axes, "succulence", 0.0) >= CD_SUCC_T:
        d += CD_SUCC_ADD
    return _clip01(d)


def _raunkiaer(axes: Mapping, plan: str) -> str:
    if plan in ("fungus", "lichen"):
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


def _palatability(axes: Mapping) -> float:
    """Defense-discounted leaf palatability shared by graze/browse."""
    p = 1.0 - DEFENSE_GRAZE_DISCOUNT * float(
        axes.get("defense_potency") or 0.0)
    if axes.get("chemical_defense") not in (None, "none", "N/A"):
        p *= CHEMICAL_GRAZE_MULT
    return _clip01(p)


def _mechanical_deriveds(axes: Mapping, plan: str) -> dict:
    """The mechanical derived axes as view fields (k13 derive_derived,
    B9 §2) — raunkiaer life form, provision map (what this plant OFFERS
    the food web: mast / graze / browse / nectar / shelter), clonality
    class, silhouette, and the display colors + canopy density.

    Every key is always written; missing axes read the documented
    neutral (clonality_class "none", provisions 0.0, ...) so the full
    key set rides on every flora view."""
    out: dict = {
        "raunkiaer": _raunkiaer(axes, plan),
        "flower_color": _derived_flower_color(axes, plan),
        "leaf_color": _derived_leaf_color(axes),
        "autumn_color": _derived_autumn_color(axes),
        "canopy_density": _derived_canopy_density(axes),
    }

    # ── provision map (vocabulary §10: what the plant offers) ──
    animal_w = 0.0
    channels = axes.get("dispersal_channels")
    if isinstance(channels, dict):
        animal_w = float(channels.get("animal", 0.0))
    mast = (MAST_BASE * (1.0 - MAST_ANIMAL_WEIGHT
                         + MAST_ANIMAL_WEIGHT * animal_w)
            if axes.get("fruit_type") in MAST_FRUITS else 0.0)
    out["provision_mast"] = _clip01(mast)

    layer = axes.get("layer")
    graze_base = {"sward": 0.8, "ground": 0.8, "shrub": 0.5,
                  "subcanopy": 0.2, "canopy": 0.1,
                  "aquatic_surface": 0.3, "aquatic_benthic": 0.3}.get(
                      layer, 0.0)
    browse_base = {"shrub": 0.6, "subcanopy": 0.7, "canopy": 0.7}.get(
        layer, 0.1)
    pal = _palatability(axes)
    out["provision_graze"] = _clip01(graze_base * pal)
    out["provision_browse"] = _clip01(browse_base * pal)

    syndrome = axes.get("pollination_syndrome")
    size = axes.get("flower_size_mm")
    nectar = NECTAR_BASE if syndrome in ANIMAL_SYNDROMES else 0.0
    if isinstance(size, (int, float)):
        nectar *= min(1.0, size / NECTAR_SIZE_REF_MM)
    out["provision_nectar"] = _clip01(nectar)

    h = axes.get("height_m")
    wood = axes.get("woodiness")
    if isinstance(h, (int, float)) and isinstance(wood, (int, float)):
        out["provision_shelter"] = _clip01(
            wood * min(1.0, h / SHELTER_HEIGHT_REF_M))
    else:
        out["provision_shelter"] = 0.0

    spread = axes.get("clonal_spread_m")
    if isinstance(spread, (int, float)):
        out["clonality_class"] = (
            "none" if spread <= CLONAL_NONE_M else
            "local" if spread < CLONAL_LOCAL_M else
            "patch" if spread < CLONAL_PATCH_M else "landscape")
    else:
        out["clonality_class"] = "none"

    if plan in ("tree", "shrub"):
        parts = [str(axes.get(k)) for k in
                 ("halle_axes", "halle_growth", "halle_branching",
                  "halle_orientation")]
        out["silhouette"] = "/".join(parts)
    else:
        out["silhouette"] = str(plan)
    return out


# ══════════════════════════════════════════════════════════════════════
# ──  the climate envelope (ported from k13 effective_climate)  ─────────
# ══════════════════════════════════════════════════════════════════════

# The four envelope values are computed from the DRIFTABLE trait bundle
# — no [niche] metadata anywhere (owner ruling 2026-08-01; presets carry
# no [niche] table).  When stress pushes the traits, the envelope moves
# with them.  Numeric axes a plan does not author read 0 (or the neutral
# noted) — a missing axis is a neutral trait, not an error.  All scales
# per axes_core.toml; leaf_size_cm is log-normalized over [0.05, 400.0].
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

LEAF_SIZE_LO_CM = 0.05
LEAF_SIZE_HI_CM = 400.0
LEAF_LOG_LO = math.log(LEAF_SIZE_LO_CM)
LEAF_LOG_SPAN = math.log(LEAF_SIZE_HI_CM) - LEAF_LOG_LO

P_B_BASE = 0.26
P_B_DROUGHT = 0.10       # drought tolerance widens the moisture band
P_B_WLOG = 0.06          # waterlogging tolerance too
MOISTURE_BREADTH_LO, MOISTURE_BREADTH_HI = 0.03, 0.5


def _leaf_norm(axes: Mapping) -> float:
    """leaf_size_cm normalized 0..1 on a LOG scale over the axis bounds
    [0.05, 400.0].  Small leaves -> 0 (the max heat/arid dial), largest
    leaves -> 1 (no dial).  Missing / non-numeric / nonpositive reads
    1.0: a neutral trait, so the (1 - leaf_norm) dials vanish."""
    v = axes.get("leaf_size_cm")
    if not isinstance(v, (int, float)) or v <= 0.0:
        return 1.0
    return _clip01((math.log(float(v)) - LEAF_LOG_LO) / LEAF_LOG_SPAN)


def _effective_climate(axes: Mapping) -> dict:
    """The climate envelope as a pure DERIVED of the trait bundle (owner
    ruling 2026-08-01): the four envelope values plus the tolerance
    passthrough traits the rounds' stress model reads.  Pure function of
    the committed axes, computed at consumption."""
    def _num_(key: str, default: float = 0.0) -> float:
        v = axes.get(key)
        return float(v) if isinstance(v, (int, float)) else default

    lp = str(axes.get("leaf_persistence") or "evergreen")
    dt = str(axes.get("deciduous_trigger") or "none")
    winter_dec = int(lp == "winter_deciduous" or dt == "winter")
    photo = str(axes.get("photosynthesis") or "C3")
    drought = _num_("drought_tolerance")
    succ = _num_("succulence")
    pub = _num_("pubescence")
    cuticle = _num_("cuticle_thickness")
    wlog = _num_("waterlogging_tolerance")
    snow = int(str(axes.get("snow_adaptation") or "none") != "none")
    gs_req = _num_("growing_season_req", GS_REF_C)   # months; missing -> ref
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


# ══════════════════════════════════════════════════════════════════════
# ──  plan descriptors (the FloraSim.derive block, B9 §2)  ──────────────
# ══════════════════════════════════════════════════════════════════════

def _plan_descriptors(axes: Mapping, plan: str, pack: ContentPack) -> dict:
    """Plan / phenology / B6 hand-wiring / dispersal descriptors — the
    FloraSim.derive block minus the climate envelope and canopy_density
    (both land under their own headers above)."""
    p = pack.registry.plans.get(plan)
    medium = p.medium if p is not None else "land"
    lp = str(axes.get("leaf_persistence") or "evergreen")
    dt = str(axes.get("deciduous_trigger") or "none")
    height = float(axes.get("height_m") or 0.0)
    wood = float(axes.get("woodiness") or 0.0)
    return {
        "root_depth_m": axes.get("root_depth_m"),
        "height_m": height,
        "woodiness": wood,
        "photosynthesis": str(axes.get("photosynthesis") or "C3"),
        "winter_deciduous": int(lp == "winter_deciduous"
                                or dt == "winter"),
        "leafout_month": axes.get("leafout_month"),
        "drought_deciduous": int(lp == "drought_deciduous"
                                 or dt == "drought"),
        "bloom_start_month": axes.get("bloom_start_month"),
        "bloom_length_months": axes.get("bloom_length_months"),
        "medium": medium,
        "anchoring_need": min(1.0, max(0.0,
                                       height * wood / ANCHOR_REF_M)),
        "holdfast": int(str(axes.get("root_type") or "") == "holdfast"),
        "submerged": int(str(axes.get("layer") or "")
                         == "aquatic_benthic"),
        # ── B6 hand-wiring keys (biosphere-addendum-b6; the stress
        # ── strata read them).
        "mycorrhizal": str(axes.get("mycorrhizal") or "none"),
        "n_fixation": str(axes.get("n_fixation") or "none"),
        "nutrient_package": str(axes.get("nutrient_package") or "none"),
        "drip_tips": axes.get("drip_tips"),
        "leaf_margin": str(axes.get("leaf_margin") or "entire"),
        "snow_adaptation": str(axes.get("snow_adaptation") or "none"),
        "layer": str(axes.get("layer") or "ground"),
        # engine-side dispersal keys (K15 rounds): channel weights drive
        # per-vector radius, the propagule mass the distance decay, the
        # seed bank the establishment carryover in sink cells.
        "dispersal_channels": _copy_nested(axes.get("dispersal_channels")),
        "propagule_mass_mg": axes.get("propagule_mass_mg"),
        "propagule_count": axes.get("propagule_count"),
        "seed_bank": axes.get("seed_bank"),
        # per-capita space demand for the engine's density term
        "crown_spread_m": axes.get("crown_spread_m"),
        # jump-dispersal frequency (long-range hops/yr) for the engine
        "jump_rate": axes.get("jump_rate"),
    }


def _copy_nested(value):
    """Snapshot nested dicts (dispersal_channels) so the view never
    aliases the record's mutable state."""
    if isinstance(value, dict):
        return dict(value)
    return value


# ══════════════════════════════════════════════════════════════════════
# ──  intrinsic stress (B9 §4 — the L1 novelty)  ────────────────────────
# ══════════════════════════════════════════════════════════════════════

# ── the plateau-with-cliffs penalty curve (owner ruling 2026-08-04).
# The penalty is essentially flat across the viable envelope — at most a
# very weak leakage so grossly different body plans are not PERFECTLY
# equal — and rises sharply only when proportions are very bad.  A
# smooth gradient everywhere would hill-climb every lineage toward the
# same optimal body plan (carcinisation) and kill diversity; inside the
# envelope, drift and the ordinary forces must dominate.
WEAK_LEAK_RATE = 0.02    # max in-envelope stress (at a region edge)
CLIFF_STEEP = 2.5        # outside-envelope penalty exponent (>1: cliff)
CLIFF_SCALE = 1.0        # stress at one envelope-width of deviation

# ── acceptance thresholds (spec B9 §8; the tests read these names).
IN_ENVELOPE_EPSILON = 0.03   # in-envelope stress <= this (leakage bound)
DECISIVE_STRESS = 0.9        # the B8-probe cactus must clear this

# ── the mechanical-support channel (canopy vs trunk).
# support_ratio = height / basal width, with a canopy factor for trees
# (see _support_ratio).  Viable envelope per plan, calibrated against
# the authored presets (every preset sits inside with margin — real
# species are not intrinsically stressed at their authored proportions);
# a 200 m cactus with a 0.6 m crown reads ~333, decisively outside.
SUPPORT_RATIO_ENVELOPES = {
    "tree": (8.0, 120.0),
    "shrub": (0.5, 6.0),
    "herb_forb": (1.0, 8.0),
    "grass_sward": (1.0, 15.0),          # bamboo 6.0; reed 12.5
    "rosette_mat": (0.3, 4.0),
    "succulent": (1.0, 25.0),
    "fern_grade": (1.0, 8.0),
    "moss_grade": (0.3, 4.0),
    "runner_meadow": (1.0, 8.0),
    "floating_leaf": (0.05, 2.0),
    "floater": (0.05, 2.0),
    "macroalgae_holdfast": (2.0, 40.0),  # kelp is a slender column by nature
    "fungus": (0.1, 50.0),
    "lichen": (0.1, 4.0),
}
DEFAULT_SUPPORT_RATIO_ENVELOPE = (0.1, 50.0)
CROWN_DBH_REF = 18.0     # the broadleaf crown:DBH norm (K_ASPECT_BROADLEAF)

MECHANICAL_WIRING = (
    "responder traits crown_spread_m / height_m / wood_density (trunk "
    "strength): drift toward the NEAREST envelope edge of support_ratio — "
    "wider base or shorter stem when over-slender, a real crown when "
    "under-built — never toward a point optimum.  The responder TABLE "
    "is L3 content."
)

# ── the energetics channel (size vs storage).
# Reads root_shoot (the belowground investment / storage split — today a
# locked per-plan constant in mass.py, so this knob is constant per plan
# on real content and fires only for the fungus, whose mycelium/fruitbody
# split varies) and, for the sward plans, sward_kg_m2 (the standing-crop
# density — the size side of the ledger).
ROOT_SHOOT_ENVELOPES = {
    "tree": (0.12, 0.45),              # R_TREE 0.26
    "shrub": (0.2, 0.6),               # R_SHRUB 0.40
    "herb_forb": (1.5, 4.5),           # R_HERB 3.0
    "grass_sward": (1.5, 4.5),         # R_GRASS 3.0
    "rosette_mat": (0.0, 0.15),        # 0.0
    "succulent": (0.1, 0.6),           # R_SUCC 0.3
    "fern_grade": (1.5, 4.5),          # R_HERB 3.0
    "moss_grade": (0.0, 0.15),         # 0.0
    "runner_meadow": (0.0, 4.5),       # land 3.0; seagrass folds BGB in (0.0)
    "floating_leaf": (0.5, 2.0),       # R_FLOAT 1.0
    "floater": (0.5, 2.0),             # R_FLOAT 1.0
    "macroalgae_holdfast": (0.0, 0.15),  # holdfast: no root split
    "fungus": (0.5, 40.0),             # mycelium/fruitbody varies 0.6..30
    "lichen": (0.0, 0.15),             # 0.0
}
DEFAULT_ROOT_SHOOT_ENVELOPE = (0.0, 50.0)

SWARD_ENVELOPES = {
    "grass_sward": (0.08, 0.93),       # Gill 2002 ABOVEGROUND crop range
    "runner_meadow": (0.05, 1.5),      # Serrano 2016 totals (incl. seagrass)
}
DEFAULT_SWARD_ENVELOPE = (0.05, 1.5)

ENERGETICS_WIRING = (
    "responder traits root_depth_m / root_spread_m / storage_organ (and "
    "height_m where it drives sward): drift toward the NEAREST envelope "
    "edge of root_shoot / sward_kg_m2 — deeper roots or a smaller canopy "
    "when the reserve is thin — never toward a point optimum.  The "
    "responder TABLE is L3 content."
)


@dataclass(frozen=True)
class StressBubble:
    """Authored exemption bubble in proportion space (B9 §4).

    A pin whose proportions lie outside a stress type's default envelope
    (giraffe, parasitic flower-only plants) carries an authored bubble —
    ``center`` + ``radius`` in the knob's own units — as part of its
    content record.  The viable region for that knob is then the default
    envelope ∪ the bubbles.

    Bubbles are AUTHORING, never generated: the sampler cannot mint
    them, so monsters cannot be laundered through self-granted
    exemptions.  Descendants inherit the bubble; drift inside it is
    free (the clade radiates around the pinned form), drift beyond its
    edge meets the normal cliff.  Bubbles are per stress type and
    independent (a support bubble implies no storage bubble).

    Wiring bubble DATA into the pin/preset loader is out of scope for
    ticket 0042 (the k13 content is frozen and authors none) — the
    assembler and the stress functions accept bubbles in their
    signatures today.
    """

    stress: str             # "mechanical_support" | "energetics"
    knob: str               # "support_ratio" | "root_shoot" | "sward_kg_m2"
    center: float
    radius: float           # must be > 0
    note: str = ""          # authored provenance (the pin it exempts)


def _region_leakage(value: float, lo: float, hi: float) -> float:
    """Weak in-region leakage: zero at the region center, at most
    WEAK_LEAK_RATE at the region edge (linear — so the in-envelope
    gradient is ~WEAK_LEAK_RATE/width: no steering)."""
    center = (lo + hi) / 2.0
    half = (hi - lo) / 2.0
    return WEAK_LEAK_RATE * min(1.0, abs(value - center) / half)


def _region_distance(value: float, lo: float, hi: float) -> float:
    """Absolute distance to the region [lo, hi] (0 inside)."""
    if value < lo:
        return lo - value
    if value > hi:
        return value - hi
    return 0.0


def _plateau_cliff(value: float, lo: float, hi: float,
                   bubbles: Sequence[StressBubble] = ()) -> tuple[float, float]:
    """The plateau-with-cliffs penalty for one scalar knob.

    Viable region = default [lo, hi] ∪ authored bubbles (each an
    interval [center-radius, center+radius]).  Inside the region the
    stress is the weak leakage (≤ WEAK_LEAK_RATE, zero at the region
    center); outside, the cliff: WEAK_LEAK_RATE + CLIFF_SCALE·d^CLIFF_STEEP
    with d the deviation normalized by the DEFAULT envelope width — the
    knob's viable-range unit, so the cliff is one fixed function of
    absolute proportion deviation whatever region edge was crossed
    (beyond any bubble edge the NORMAL cliff applies, B9 §4).  Strictly
    increasing with deviation, toward the nearest envelope edge, never a
    point optimum.  Returns (stress, deviation).
    """
    if not (lo < hi):
        raise ValueError(f"envelope must have lo<hi (got [{lo}, {hi}])")
    width = hi - lo
    regions: list[tuple[float, float]] = [(lo, hi)]
    for b in bubbles:
        if b.radius <= 0.0:
            raise ValueError(
                f"bubble radius must be > 0 (got {b.radius} for "
                f"{b.stress}.{b.knob}@{b.center})")
        regions.append((b.center - b.radius, b.center + b.radius))
    inside = [(lo_, hi_) for lo_, hi_ in regions if lo_ <= value <= hi_]
    if inside:
        # weakest leakage of the covering regions (nearest its center)
        return min(_region_leakage(value, lo_, hi_)
                   for lo_, hi_ in inside), 0.0
    d = min(_region_distance(value, lo_, hi_)
            for lo_, hi_ in regions) / width
    return WEAK_LEAK_RATE + CLIFF_SCALE * d ** CLIFF_STEEP, d


def _support_ratio(view: Mapping, plan: str) -> float | None:
    """The mechanical-support metric.

    trees: (height/dbh)·(crown_dbh_ratio/18) — slenderness times the
    canopy-to-trunk factor (dbh and the crown ratio both come from the
    mass hook's proportions, so the resolved tree form feeds in).
    everything else: height / basal width, basal width = the crown
    spread (for columnar grades — succulent, kelp — the stem IS the
    body).  None when the record carries no measurable body (height ≤ 0
    or no width): the knob reads neutral, no stress.
    """
    h = view.get("height_m")
    if not isinstance(h, (int, float)) or h <= 0.0:
        return None
    props = view.get("mass_proportions") or {}
    if plan == "tree":
        dbh = props.get("dbh_m")
        cr = props.get("crown_dbh_ratio")
        if not isinstance(dbh, (int, float)) or dbh <= 0.0:
            return None
        if not isinstance(cr, (int, float)) or cr <= 0.0:
            cr = CROWN_DBH_REF
        return (h / dbh) * (cr / CROWN_DBH_REF)
    base = view.get("crown_spread_m")
    if not isinstance(base, (int, float)) or base <= 0.0:
        return None
    return h / base


def _energetics_knobs(view: Mapping, plan: str) -> dict[str, float]:
    """The energetics proportion knobs present in this view: root_shoot
    (all plans; missing when mass is zero) and sward_kg_m2 (the sward
    plans only)."""
    props = view.get("mass_proportions") or {}
    knobs: dict[str, float] = {}
    rs = props.get("root_shoot")
    if isinstance(rs, (int, float)):
        knobs["root_shoot"] = rs
    sward = props.get("sward_kg_m2")
    if isinstance(sward, (int, float)) and plan in SWARD_ENVELOPES:
        knobs["sward_kg_m2"] = sward
    return knobs


def _stress_term(stress_key: str, knobs: dict[str, float], plan: str,
                 by_knob: Mapping[str, Mapping[str, tuple[float, float]]],
                 defaults: Mapping[str, tuple[float, float]],
                 bubbles: Sequence[StressBubble], wiring: str) -> dict:
    """Assemble one intrinsic-stress term: the scalar ``value`` (max
    over the knobs of the per-knob plateau-cliff penalty — the dominant
    limiting factor), the per-knob readings/deviations, and the human
    ``cause`` naming the worst knob.  *by_knob* maps knob -> {plan ->
    (lo, hi)} (per-plan-group overrides where morphology demands, B9
    §4); *defaults* holds the fallback envelope per knob.  Knob
    iteration is sorted (determinism hard rule)."""
    terms: list[dict] = []
    for knob in sorted(knobs):
        value = knobs[knob]
        lo, hi = by_knob.get(knob, {}).get(plan, defaults[knob])
        knob_bubbles = [b for b in bubbles
                        if b.stress == stress_key and b.knob == knob]
        s, d = _plateau_cliff(value, lo, hi, knob_bubbles)
        if d == 0.0:
            direction = "none"   # in-envelope or bubble-exempt: drift free
        elif value < lo:
            direction = "raise"
        else:
            direction = "lower"
        terms.append(dict(
            knob=knob, value=value, stress=s, deviation=d,
            envelope=[lo, hi], direction=direction,
        ))
    if not terms:
        # no measurable proportions (e.g. zero-height record): neutral
        return dict(key=stress_key, value=0.0, deviation=0.0,
                    cause="no measurable proportions (neutral)", knobs={},
                    wiring=wiring)
    worst = max(terms, key=lambda t: (t["stress"], t["knob"]))
    if worst["deviation"] == 0.0:
        wv = worst["value"]
        exempt = next(
            (b for b in bubbles
             if b.stress == stress_key and b.knob == worst["knob"]
             and b.center - b.radius <= wv <= b.center + b.radius), None)
        if exempt is not None:
            cause = (f"{worst['knob']} {wv:.3g} inside authored bubble "
                     f"{exempt.center:g}±{exempt.radius:g} "
                     f"(exempt — drift free within)")
        else:
            cause = (f"{worst['knob']} {wv:.3g} in-envelope "
                     f"[{worst['envelope'][0]:.3g}, "
                     f"{worst['envelope'][1]:.3g}]")
    elif worst["value"] < worst["envelope"][0]:
        cause = (f"{worst['knob']} {worst['value']:.3g} is "
                 f"{worst['deviation']:.3g} envelope-widths BELOW the "
                 f"[{worst['envelope'][0]:.3g}, {worst['envelope'][1]:.3g}] floor")
    else:
        cause = (f"{worst['knob']} {worst['value']:.3g} is "
                 f"{worst['deviation']:.3g} envelope-widths ABOVE the "
                 f"[{worst['envelope'][0]:.3g}, {worst['envelope'][1]:.3g}] ceiling")
    knobs_out = {t["knob"]: {k2: v for k2, v in t.items()
                             if k2 != "knob"} for t in terms}
    return dict(
        key=stress_key,
        value=worst["stress"],
        deviation=worst["deviation"],
        cause=cause,
        knobs=knobs_out,
        wiring=wiring,
    )


def mechanical_support(view: Mapping, plan: str,
                       bubbles: Sequence[StressBubble] = ()) -> dict:
    """Intrinsic stress type: mechanical support (canopy vs trunk).

    Reads ONLY the view's derived proportions (support_ratio from the
    mass proportions + height/crown fields) — never the record's raw
    axes.  Returns the scalar stress term dict (``value`` is the vital
    cost; ``cause`` names the worst knob).
    """
    sr = _support_ratio(view, plan)
    knobs = {} if sr is None else {"support_ratio": sr}
    return _stress_term("mechanical_support", knobs, plan,
                        {"support_ratio": SUPPORT_RATIO_ENVELOPES},
                        {"support_ratio": DEFAULT_SUPPORT_RATIO_ENVELOPE},
                        bubbles, MECHANICAL_WIRING)


def energetics(view: Mapping, plan: str,
               bubbles: Sequence[StressBubble] = ()) -> dict:
    """Intrinsic stress type: energetics (size vs storage).

    Reads ONLY the view's derived proportions (root_shoot, and
    sward_kg_m2 on the sward plans) — never the record's raw axes.
    Returns the scalar stress term dict.
    """
    return _stress_term("energetics", _energetics_knobs(view, plan), plan,
                        {"root_shoot": ROOT_SHOOT_ENVELOPES,
                         "sward_kg_m2": SWARD_ENVELOPES},
                        {"root_shoot": DEFAULT_ROOT_SHOOT_ENVELOPE,
                         "sward_kg_m2": DEFAULT_SWARD_ENVELOPE},
                        bubbles, ENERGETICS_WIRING)


def intrinsic_stress(view: Mapping, plan: str,
                     bubbles: Sequence[StressBubble] = ()) -> dict:
    """The B9 §4 intrinsic-stress block: one scalar term per stress type,
    each an ordinary scalar stress like drought or cold, reading only
    the view's derived proportions.  L3 sums these with the
    environmental stresses through the same machinery (one channel)."""
    return {
        "mechanical_support": mechanical_support(view, plan, bubbles),
        "energetics": energetics(view, plan, bubbles),
    }


# ══════════════════════════════════════════════════════════════════════
# ──  the assembler  ─────────────────────────────────────────────────────
# ══════════════════════════════════════════════════════════════════════

def _mass_form(record: SpeciesRecord, pack: ContentPack) -> str | None:
    """Tree mass form from the committed preset grade (see
    TREE_FORM_BY_GRADE); None → the mass hook's per-plan default."""
    if record.plan != "tree" or record.preset is None:
        return None
    preset = pack.presets.get(record.preset)
    if preset is None:
        return None
    return TREE_FORM_BY_GRADE.get(preset["preset"].get("grade"))


def assemble_view(record: SpeciesRecord, pack: ContentPack,
                  bubbles: Sequence[StressBubble] = ()) -> dict:
    """The canonical species-view assembler (B9 §3; THE only derive path
    in exp/k15_biosphere).

    Pure function of *record* + *pack*: reads the committed axes, never
    mutates the record, and two assemblies of the same record are equal
    (deterministic).  *bubbles* (authored exception bubbles, B9 §4) are
    threaded into the intrinsic-stress block.
    """
    plan = record.plan
    if plan is None or plan not in pack.registry.plans:
        raise ValueError(
            f"cannot assemble a view: record {record.sid!r} has no "
            f"registry plan (got {plan!r})")
    axes = record.axes
    view: dict = {"sid": record.sid, "plan": plan, "preset": record.preset}
    view.update(_effective_climate(axes))
    view.update(_mechanical_deriveds(axes, plan))
    view.update(_plan_descriptors(axes, plan, pack))

    est = percap_biomass(axes, plan, _mass_form(record, pack))
    view["mass_total_kg"] = est.total_kg
    view["mass_agb_kg"] = est.agb_kg
    view["mass_proportions"] = dict(est.proportions)

    view["intrinsic_stress"] = intrinsic_stress(view, plan, bubbles)
    return view
