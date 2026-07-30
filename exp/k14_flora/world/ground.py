"""K14 P6 — derived-products layer: substrate ("ground") classification.

Biosphere addendum B3. Internal name is GROUND, never bare "substrate":
K13/K14 `substrate_ok()` already means ANATOMICAL substrate (a mane
needs fur), so reusing the word would pollute every future grep.

One deterministic classification at anchor res (256²). Per class c and
cell a generator weight w_c in [0,1] is a product of bounded evidence
terms (each in [0,1] BY CONSTRUCTION — clips, exponentials, reference
values; never rank or percentile normalization, same religion as the
B2 productivity scale). d2_c = -log(max(w_c, 1e-6)); the dominant class
is argmax w and consumers softmax over -d2 at consume time
(biosphere_conv ruling).

Two engines, neither with a veto (spec §Architecture):
  1. physical process layer (parent material) — the evidence fields;
  2. biome bias (biotic transformation) — multiplicative boosts onto
     biotic/mixed classes. BIASES, NEVER BINDINGS: the weight is capped
     at 1, so a biome can lift a class but never force it, and the
     physical layer holds regardless of what the biome prefers (a
     temperate forest on a steep slope is scree).

Genesis (physical / biotic / mixed) is per-class METADATA, never a
constraint. Underwater is the SAME table, same machinery: retention
reads 1.0 (saturated) and sal_add is None, meaning "the water's own
salinity" (the consumer supplies it; K11 h_salinity covers water only).
"""

from __future__ import annotations

import numpy as np

from exp.k11_worldgen.biomes import BIOME_ID
from exp.k11_worldgen.units import DEPTH_MAX_M, elev_m, hand_m, precip_mm, \
    temp_c
# reuse the B2 reference values where the evidence is the same quantity
from exp.k14_flora.world.derived import ACC_REF, HAND_REF_M, P_REF_MMYR

# ── derivation bounds (knob set #2 — each saturates one evidence term) ──
SLOPE_REF_M = 800.0           # elevation change across ONE 4 km cell that
                              # reads as "steep" (a ~20% grade saturates it)
COLD_REF_C = 2.0              # annual T at/below which "cold" saturates
WARM_BASE_C = 5.0             # tropical-warmth ramp foot (0 below here)
WARM_SPAN_C = 15.0            # ...span to full warmth (1 at 20 C)
GLAC_FLUX_REF = 2000.0        # glacier flux (~p99 of a seeded world) that
                              # saturates the flux half of the glacier term
SALT_LAKE_REF = 50.0          # g/kg: a lake saltier than this is "salt lake"
SALT_LAKE_MAX = 220.0         # g/kg saturating the endorheic salinity halo
CUR_REF = 1.0                 # m/s ocean current saturating bottom energy
DEPTH_ABYSS_M = 4000.0        # bathymetry saturating "abyssal" (abyssal
                              # plains run 4-5 km)
RV_REF = 2.0                  # m/s river speed saturating flow-sorting
DIS_REF = 50.0                # m³/s discharge fallback (~p99) if a dump
                              # lacks h_river_speed — noted, not preferred
DUNE_DEP_GATE = 2.0           # deposition multiplier inside the dune gate
                              # (dunes need BOTH the most-arid band AND a
                              # sand supply; the rest of the arid mosaic is
                              # sand sheet / reg — spec §dune rule)
W_FLOOR = 1e-6                # generator-weight floor feeding -log -> d2

# ── consume-time softmax temperature (knob set #4) ──────────────────────
TAU = 1.0                     # softmax over -d2; at TAU=1 softmax(-d2) is
                              # exactly w normalized to sum 1 (d2 = -log w),
                              # so the top-3 mix shares are the renormalized
                              # generator weights of the three shown classes

# ── class table (41; knob set #1 — the floats are draft, the ORDERINGS ──
# ── are the defensible content, consumers of d2 are robust to +-0.1) ────
# Per class: property row (retention, rooting_m, sal_add, nutrient) from
# the spec; hard/loose metadata flags; a muted terrain-legible color; a
# genesis note; and a genesis TAG (physical/biotic/mixed, metadata only).
#   hard  = anchoring rock/hardpan — holdfast rooters need it, roots and
#           burrows do NOT penetrate (impenetrable for free).
#   loose = penetrable/diggable GRANULAR medium — fossorial fauna and
#           sand-swimmers need it (cohesive clays/muds/peats are neither).
# sal_add is None for underwater rows (= the water's salinity).
GROUND_CLASSES: list[dict] = [
    # ── terrestrial — physical ──────────────────────────────────────────
    dict(name="dune sand", retention=0.05, rooting_m=0.3, sal_add=0.0,
         nutrient=0.15, hard=False, loose=True, color=[222, 200, 130],
         genesis="most-arid deposition only", genesis_tag="physical"),
    dict(name="sand sheet", retention=0.10, rooting_m=0.5, sal_add=0.0,
         nutrient=0.20, hard=False, loose=True, color=[210, 188, 128],
         genesis="arid", genesis_tag="physical"),
    dict(name="reg / desert pavement", retention=0.05, rooting_m=0.2,
         sal_add=0.0, nutrient=0.15, hard=True, loose=False,
         color=[176, 150, 118], genesis="winnowing",
         genesis_tag="physical"),   # armored stone lag: anchors, no digging
    dict(name="scree", retention=0.05, rooting_m=0.10, sal_add=0.0,
         nutrient=0.05, hard=True, loose=False, color=[150, 145, 140],
         genesis="slope override", genesis_tag="physical"),
    dict(name="bedrock outcrop", retention=0.02, rooting_m=0.05,
         sal_add=0.0, nutrient=0.02, hard=True, loose=False,
         color=[120, 118, 116], genesis="erosion", genesis_tag="physical"),
    dict(name="alluvium", retention=0.65, rooting_m=2.0, sal_add=0.0,
         nutrient=0.80, hard=False, loose=True, color=[160, 140, 95],
         genesis="deposition", genesis_tag="physical"),
    dict(name="loess", retention=0.55, rooting_m=1.5, sal_add=0.0,
         nutrient=0.70, hard=False, loose=True, color=[190, 170, 120],
         genesis="glacial-margin wind", genesis_tag="physical"),
    dict(name="silt", retention=0.60, rooting_m=1.2, sal_add=0.0,
         nutrient=0.65, hard=False, loose=True, color=[170, 155, 120],
         genesis="low-energy deposition", genesis_tag="physical"),
    dict(name="clay", retention=0.65, rooting_m=0.8, sal_add=0.0,
         nutrient=0.55, hard=False, loose=False, color=[150, 120, 95],
         genesis="still water (plant-available, not total)",
         genesis_tag="physical"),   # cohesive: rootable, not a dig medium
    dict(name="vertisol", retention=0.75, rooting_m=1.2, sal_add=0.0,
         nutrient=0.70, hard=False, loose=False, color=[110, 95, 80],
         genesis="shrink-swell smectite, seasonal cracks",
         genesis_tag="physical"),
    dict(name="till", retention=0.45, rooting_m=0.8, sal_add=0.0,
         nutrient=0.50, hard=False, loose=False, color=[140, 130, 110],
         genesis="glacial", genesis_tag="physical"),
    dict(name="outwash gravel", retention=0.15, rooting_m=0.4, sal_add=0.0,
         nutrient=0.35, hard=False, loose=False, color=[165, 155, 135],
         genesis="glaciofluvial", genesis_tag="physical"),
    dict(name="andisol", retention=0.80, rooting_m=1.0, sal_add=0.0,
         nutrient=0.70, hard=False, loose=False, color=[95, 80, 70],
         genesis="vent proximity (allophane: high water, P fixed)",
         genesis_tag="physical"),
    dict(name="fresh lava", retention=0.05, rooting_m=0.1, sal_add=0.0,
         nutrient=0.30, hard=True, loose=False, color=[70, 65, 68],
         genesis="active fault", genesis_tag="physical"),
    dict(name="rendzina", retention=0.30, rooting_m=0.4, sal_add=0.0,
         nutrient=0.55, hard=False, loose=False, color=[176, 166, 140],
         genesis="limestone (calcicole; absorbs chalk)",
         genesis_tag="physical"),   # no lithology field: base-rich,
                                    # low-leaching climate proxy stands in
    dict(name="laterite cuirasse", retention=0.10, rooting_m=0.2,
         sal_add=0.0, nutrient=0.10, hard=True, loose=False,
         color=[160, 90, 60], genesis="plinthite hardpan, tropical",
         genesis_tag="physical"),
    dict(name="caliche", retention=0.12, rooting_m=0.25, sal_add=0.0,
         nutrient=0.20, hard=True, loose=False, color=[200, 190, 165],
         genesis="petrocalcic hardpan, semi-arid", genesis_tag="physical"),
    dict(name="solonchak", retention=0.10, rooting_m=0.3, sal_add=1.0,
         nutrient=0.05, hard=False, loose=False, color=[235, 230, 210],
         genesis="endorheic/coastal evaporite (absorbs sabkha)",
         genesis_tag="physical"),
    dict(name="solonetz", retention=0.35, rooting_m=0.5, sal_add=0.45,
         nutrient=0.25, hard=False, loose=False, color=[200, 185, 150],
         genesis="sodic, dispersed clay", genesis_tag="physical"),
    dict(name="coastal sand", retention=0.10, rooting_m=0.4, sal_add=0.3,
         nutrient=0.20, hard=False, loose=True, color=[230, 220, 170],
         genesis="littoral", genesis_tag="physical"),
    # ── terrestrial — biotic / mixed ────────────────────────────────────
    dict(name="mollisol", retention=0.70, rooting_m=2.2, sal_add=0.0,
         nutrient=0.95, hard=False, loose=False, color=[120, 90, 55],
         genesis="grassland", genesis_tag="biotic"),
    dict(name="podzol", retention=0.45, rooting_m=0.9, sal_add=0.0,
         nutrient=0.25, hard=False, loose=False, color=[100, 85, 70],
         genesis="conifer/taiga", genesis_tag="biotic"),
    dict(name="ferralsol", retention=0.55, rooting_m=1.5, sal_add=0.0,
         nutrient=0.15, hard=False, loose=False, color=[180, 100, 60],
         genesis="rainforest (nutrients in biomass)", genesis_tag="biotic"),
    dict(name="brown earth", retention=0.60, rooting_m=1.5, sal_add=0.0,
         nutrient=0.65, hard=False, loose=False, color=[130, 100, 65],
         genesis="temperate broadleaf", genesis_tag="biotic"),
    dict(name="fen", retention=0.92, rooting_m=0.5, sal_add=0.0,
         nutrient=0.45, hard=False, loose=False, color=[110, 120, 80],
         genesis="groundwater-fed peat", genesis_tag="mixed"),
    dict(name="bog", retention=0.98, rooting_m=0.3, sal_add=0.0,
         nutrient=0.05, hard=False, loose=False, color=[140, 115, 80],
         genesis="rain-fed Sphagnum dome (carnivory's home)",
         genesis_tag="mixed"),
    dict(name="gleysol", retention=0.85, rooting_m=0.3, sal_add=0.0,
         nutrient=0.30, hard=False, loose=False, color=[120, 130, 130],
         genesis="groundwater waterlogging", genesis_tag="mixed"),
    dict(name="gelisol", retention=0.60, rooting_m=0.4, sal_add=0.0,
         nutrient=0.30, hard=False, loose=False, color=[180, 190, 195],
         genesis="permafrost + cryoturbation", genesis_tag="mixed"),
    dict(name="mangrove mud", retention=0.90, rooting_m=0.5, sal_add=0.6,
         nutrient=0.50, hard=False, loose=False, color=[90, 100, 70],
         genesis="mangrove", genesis_tag="biotic"),
    dict(name="montane ranker", retention=0.35, rooting_m=0.4, sal_add=0.0,
         nutrient=0.40, hard=False, loose=False, color=[140, 135, 110],
         genesis="thin upland soil", genesis_tag="mixed"),
    # ── underwater (retention 1.0 saturated; sal_add None = the water) ──
    dict(name="marine mud", retention=1.0, rooting_m=0.3, sal_add=None,
         nutrient=0.40, hard=False, loose=False, color=[70, 90, 100],
         genesis="marine snow, quiet shelf", genesis_tag="physical"),
    dict(name="abyssal clay", retention=1.0, rooting_m=0.2, sal_add=None,
         nutrient=0.10, hard=False, loose=False, color=[40, 55, 80],
         genesis="pelagic, food-starved", genesis_tag="physical"),
    dict(name="marine sand", retention=1.0, rooting_m=0.3, sal_add=None,
         nutrient=0.25, hard=False, loose=True, color=[150, 160, 130],
         genesis="high-energy shelf", genesis_tag="physical"),
    dict(name="reef carbonate", retention=1.0, rooting_m=0.4, sal_add=None,
         nutrient=0.35, hard=True, loose=False, color=[130, 170, 175],
         genesis="coral", genesis_tag="biotic"),
    dict(name="rocky bottom", retention=1.0, rooting_m=0.05, sal_add=None,
         nutrient=0.20, hard=True, loose=False, color=[90, 95, 100],
         genesis="high energy / kelp holdfast", genesis_tag="physical"),
    dict(name="vent crust", retention=1.0, rooting_m=0.1, sal_add=None,
         nutrient=0.90, hard=True, loose=False, color=[110, 70, 60],
         genesis="hot sulfide chemosynthesis", genesis_tag="mixed"),
    dict(name="cold seep", retention=1.0, rooting_m=0.3, sal_add=None,
         nutrient=0.85, hard=False, loose=False, color=[80, 100, 95],
         genesis="methane chemosynthesis + carbonate", genesis_tag="mixed"),
    dict(name="tidal flat", retention=1.0, rooting_m=0.15, sal_add=0.5,
         nutrient=0.55, hard=False, loose=False, color=[140, 150, 130],
         genesis="tide-sorted, brackish gradient", genesis_tag="physical"),
    dict(name="lake mud", retention=1.0, rooting_m=0.4, sal_add=None,
         nutrient=0.60, hard=False, loose=False, color=[85, 105, 110],
         genesis="deposition + biotic", genesis_tag="mixed"),
    dict(name="river gravel bed", retention=1.0, rooting_m=0.2, sal_add=0.0,
         nutrient=0.30, hard=False, loose=False, color=[130, 130, 120],
         genesis="flow-sorted", genesis_tag="physical"),
    dict(name="river sand bed", retention=1.0, rooting_m=0.3, sal_add=0.0,
         nutrient=0.25, hard=False, loose=True, color=[160, 155, 120],
         genesis="flow-sorted", genesis_tag="physical"),
]

N_CLASSES = len(GROUND_CLASSES)
GROUND_ID = {c["name"]: i for i, c in enumerate(GROUND_CLASSES)}
assert N_CLASSES == 41, "B3 specifies exactly 41 ground classes"

# domain slices (index ranges) — used by the land/water separation and the
# biome-bias suppression
_TERRESTRIAL = range(0, 30)          # physical + biotic/mixed soils
_MARINE = range(30, 37)              # marine mud .. cold seep
_BIOTIC_SOILS = [i for i in _TERRESTRIAL
                 if GROUND_CLASSES[i]["genesis_tag"] in ("biotic", "mixed")]

# ── biome bias (knob set #1/#2 — "the biome pretends the climate ────────
# ── considerations were done for you"; multiplicative, capped at 1) ─────
_BIAS: dict[str, dict[str, float]] = {
    "mollisol": {"temperate grassland": 3.0, "tropical grassland": 2.5},
    "podzol": {"boreal taiga": 3.0, "temperate conifer forest": 3.0},
    "ferralsol": {"tropical moist forest": 3.0},
    "brown earth": {"temperate broadleaf forest": 3.0},
    "gelisol": {"tundra": 2.0},
    "bog": {"tundra": 1.5, "boreal taiga": 1.5},
    "fen": {"flooded grassland": 2.0, "tundra": 1.5},
    "gleysol": {"flooded grassland": 1.5},
    "mangrove mud": {"mangrove": 3.0},
    "montane ranker": {"montane grassland": 2.0},
    "dune sand": {"desert xeric shrubland": 1.5},
    "sand sheet": {"desert xeric shrubland": 1.5},
    "reg / desert pavement": {"desert xeric shrubland": 1.5},
}
_SUPPRESS_BIOMES = ("rock", "ice")   # no soil there: biotic soils x0.2
_SUPPRESS_FACTOR = 0.2


# ── small array helpers ─────────────────────────────────────────────────


def _spread_max(a: np.ndarray, n: int) -> np.ndarray:
    """n-ring 8-connected neighborhood MAX (edge-clamped). One helper, two
    uses: dilating a mask (values 0/1) and spreading a salt-lake halo.
    Deterministic, numpy-only."""
    out = np.asarray(a, dtype=np.float64)
    H, W = out.shape
    for _ in range(n):
        p = np.pad(out, 1, mode="edge")
        acc = np.full((H, W), -np.inf)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                np.maximum(acc, p[1 + dy:H + 1 + dy, 1 + dx:W + 1 + dx],
                           out=acc)
        out = acc
    return out


def _dilate8(mask: np.ndarray, n: int = 1) -> np.ndarray:
    """Grow a boolean mask by n 8-connected rings."""
    return _spread_max(np.asarray(mask, dtype=np.float64), n) > 0.5


def _slope_field(elev: np.ndarray) -> np.ndarray:
    """Max absolute elevation difference (meters) to the 4 cardinal
    neighbors, edge-clamped — the steepest single-step grade through a
    cell, np.gradient-style but taking the max of the four instead of the
    axis-separated components."""
    up = np.vstack([elev[:1], elev[:-1]])
    down = np.vstack([elev[1:], elev[-1:]])
    left = np.hstack([elev[:, :1], elev[:, :-1]])
    right = np.hstack([elev[:, 1:], elev[:, -1:]])
    return np.maximum.reduce([np.abs(elev - up), np.abs(elev - down),
                              np.abs(elev - left), np.abs(elev - right)])


# ── evidence fields (all bounded [0,1] by construction) ─────────────────


def _evidence(z, sea: float, vent_activity: np.ndarray) -> dict:
    """Compute every bounded evidence field once per build. Returns a dict
    of (H,W) float fields in [0,1] plus the domain masks."""
    ocean = z["h_ocean_mask"] | z["h_sea_mask"]
    lake = z["h_lake_mask"]
    river = z["h_river_mask"]
    land = ~ocean & ~lake & ~river

    hand = hand_m(z["h_hand"], sea)
    wet = np.exp(-hand / HAND_REF_M)                       # waterlogging
    dep = (np.clip(z["h_accumulation"] / ACC_REF, 0.0, 1.0) * wet)

    elev = elev_m(z["w_elev"], sea)                        # signed meters
    slope = np.clip(_slope_field(elev) / SLOPE_REF_M, 0.0, 1.0)

    p_ann = precip_mm(z["c_P_monthly"]).sum(axis=0)        # mm/yr
    arid = 1.0 - np.clip(p_ann / P_REF_MMYR, 0.0, 1.0)

    t_ann = temp_c(z["c_T"])                               # degC, annual
    cold = np.clip((COLD_REF_C - t_ann) / COLD_REF_C, 0.0, 1.0)
    warm = np.clip((t_ann - WARM_BASE_C) / WARM_SPAN_C, 0.0, 1.0)

    glac = np.clip(
        _dilate8(z["h_glacier_mask"], 2).astype(np.float64)
        + np.clip(z["h_glacier_flux"] / GLAC_FLUX_REF, 0.0, 1.0) * 0.5,
        0.0, 1.0)

    # vent activity normalized by its 99th percentile — a documented BOUND
    # (same convention as the marine rework): a single extreme fault clips
    # instead of re-anchoring the rest of the field.
    vp99 = max(float(np.percentile(vent_activity, 99.0)), 1e-12)
    ventf = np.clip(vent_activity / vp99, 0.0, 1.0)

    # ── derived soil salinity (no upstream field — spec calls this out) ──
    # max of three bounded terms:
    #  (a) endorheic: the salt-lake halo — a lake saltier than SALT_LAKE_REF
    #      spreads its clip(salinity/SALT_LAKE_MAX) value 3 cells out;
    #  (b) arid evaporation: arid, non-depositional ground concentrates
    #      salts (half weight);
    #  (c) coast: within 2 cells of the ocean (spray/brackish, 0.3).
    salt_lake = lake & (z["h_salinity"] > SALT_LAKE_REF)
    salt_src = np.where(salt_lake,
                        np.clip(z["h_salinity"] / SALT_LAKE_MAX, 0.0, 1.0),
                        0.0)
    endorheic = _spread_max(salt_src, 3)
    arid_evap = arid * (1.0 - dep) * 0.5
    coast = _dilate8(ocean, 2).astype(np.float64) * 0.3
    salsoil = np.maximum(np.maximum(endorheic, arid_evap), coast)

    # marine: bottom energy from current speed; depth from bathymetry
    energy = np.clip(np.hypot(z["r_u"], z["r_v"]) / CUR_REF, 0.0, 1.0)
    bathy = np.maximum(sea - z["w_elev"], 0.0) / sea * DEPTH_MAX_M
    depthn = np.clip(bathy / DEPTH_ABYSS_M, 0.0, 1.0)

    # rivers: flow speed at anchor res (persisted by K11); fall back to a
    # bounded discharge rank ONLY if a stale dump lacks it (noted, and no
    # actual rank — a clip over DIS_REF).
    if "h_river_speed" in z:
        rs = np.clip(z["h_river_speed"] / RV_REF, 0.0, 1.0)
    else:
        rs = np.clip(z["h_discharge"] / DIS_REF, 0.0, 1.0)

    # tidal band: land/ocean cells within 1 cell of the shoreline, flat
    # (slope < 0.05), and — for water cells — shallow.
    near_ocean1 = _dilate8(ocean, 1)
    coast_band = (near_ocean1 & ~ocean) | (_dilate8(~ocean, 1) & ocean)
    flat = slope < 0.05
    shallow = depthn < 0.05
    tidal = (coast_band & flat & (~ocean | shallow)).astype(np.float64)

    return dict(
        ocean=ocean.astype(np.float64), lake=lake.astype(np.float64),
        river=river.astype(np.float64), land=land.astype(np.float64),
        dep=dep, wet=wet, slope=slope, arid=arid, cold=cold, warm=warm,
        glac=glac, ventf=ventf, salsoil=salsoil, energy=energy,
        depthn=depthn, rs=rs, tidal=tidal,
        near_ocean1=near_ocean1.astype(np.float64),
        biome=z["w_biome_map"], aquatic=z["w_aquatic"])


def _biome_bias(biome: np.ndarray) -> np.ndarray:
    """(N_CLASSES, H, W) multiplicative bias, 1.0 where a class has no
    opinion. Biases, never bindings — build_ground caps the product at 1."""
    bias = np.ones((N_CLASSES,) + biome.shape, dtype=np.float64)
    for name, per_biome in _BIAS.items():
        i = GROUND_ID[name]
        for bname, mult in per_biome.items():
            bias[i, biome == BIOME_ID[bname]] = mult
    sup = np.isin(biome, [BIOME_ID[b] for b in _SUPPRESS_BIOMES])
    for i in _BIOTIC_SOILS:
        bias[i, sup] = _SUPPRESS_FACTOR
    return bias


# ── per-class generator weights ─────────────────────────────────────────
# One documented rule per class from its genesis note. Every term is a
# bounded evidence field (or product thereof); land classes carry `land`,
# marine classes `ocean`, lake/river classes their own mask — so a class is
# exactly zero off its domain. Rules are keyed by class NAME; the table
# order in GROUND_CLASSES fixes the ids.
def _weights(e: dict) -> dict[str, np.ndarray]:
    land, ocean = e["land"], e["ocean"]
    lake, river = e["lake"], e["river"]
    dep, wet, slope = e["dep"], e["wet"], e["slope"]
    arid, cold, warm = e["arid"], e["cold"], e["warm"]
    glac, ventf = e["glac"], e["ventf"]
    salsoil, energy, depthn = e["salsoil"], e["energy"], e["depthn"]
    rs, tidal = e["rs"], e["tidal"]
    dune_dep = np.clip(dep * DUNE_DEP_GATE, 0.0, 1.0)
    loamy = 0.5 + 0.5 * dep
    # vent influence suppresses the deep-ocean background (vent crust at
    # the core, cold seep in a 2-ring around it, abyssal clay elsewhere)
    vent_core = ventf > 0.5
    seep_ring = (_dilate8(vent_core, 2) & ~vent_core).astype(np.float64)
    reef = (e["aquatic"] == 4).astype(np.float64)     # K11 "coral reef"

    w: dict[str, np.ndarray] = {}
    # terrestrial — physical
    w["dune sand"] = arid ** 2 * dune_dep * land          # most-arid gate
    w["sand sheet"] = arid * (1 - slope) * (1 - 0.6 * dune_dep) * land
    w["reg / desert pavement"] = arid * (1 - dep) * (1 - 0.5 * slope) * land
    w["scree"] = slope ** 1.5 * (1 - 0.3 * slope) * land  # the slope override
    w["bedrock outcrop"] = slope ** 3 * land              # steepest cliffs
    w["alluvium"] = dep * (1 - slope) * (1 - 0.6 * wet) * land
    w["loess"] = glac * (1 - dep) * (1 - slope) * (1 - wet) * 0.8 * land
    w["silt"] = dep * (1 - slope) * (0.4 + 0.6 * wet) * 0.9 * land
    w["clay"] = dep * wet ** 2 * 0.95 * land
    w["vertisol"] = dep * np.sqrt(wet * arid) * (1 - slope) * land
    w["till"] = glac * (1 - 0.5 * slope) * land
    w["outwash gravel"] = glac * dep * 0.8 * land
    w["andisol"] = ventf * (1 - slope) * land
    w["fresh lava"] = ventf * slope * land
    w["rendzina"] = ((1 - arid) * (1 - cold) * (1 - wet) * (1 - dep)
                     * (1 - slope) * 0.75 * land)
    w["laterite cuirasse"] = warm * (1 - arid) * (1 - slope) * 0.6 * land
    w["caliche"] = arid * (1 - wet) * (1 - dep) * (1 - slope) * 0.7 * land
    w["solonchak"] = salsoil ** 2 * (1 - slope) * land
    w["solonetz"] = salsoil * (1 - salsoil) * 4.0 * (1 - slope) * 0.6 * land
    w["coastal sand"] = e["near_ocean1"] * (1 - slope) * 0.8 * land
    # terrestrial — biotic / mixed (biome-biased in build_ground)
    w["mollisol"] = (1 - arid) * (1 - cold) * (1 - slope) * loamy * land
    w["podzol"] = (1 - arid) * (0.3 + 0.7 * cold) * (1 - slope) * loamy * land
    w["ferralsol"] = warm * (1 - arid) * (1 - slope) * loamy * land
    w["brown earth"] = (1 - arid) * (1 - cold) * (1 - slope) * loamy * land
    w["fen"] = wet * loamy * (1 - slope) * 0.9 * land
    w["bog"] = wet * (1 - dep) * (1 - slope) * 0.85 * land
    w["gleysol"] = wet * loamy * (1 - slope) * 0.8 * land
    w["gelisol"] = cold * (1 - slope) * 0.9 * land
    w["mangrove mud"] = wet * e["near_ocean1"] * warm * (1 - slope) * land
    w["montane ranker"] = (1 - dep) * (1 - slope) * (0.4 + 0.6 * cold) \
        * 0.7 * land
    # underwater
    w["marine mud"] = (1 - depthn) * (1 - energy) * ocean
    w["abyssal clay"] = depthn ** 2 * (1 - energy) * (1 - 0.5 * ventf) \
        * (1 - 0.5 * seep_ring) * ocean
    w["marine sand"] = (1 - depthn) * energy * (1 - energy) * 1.2 * ocean
    w["reef carbonate"] = reef * (1 - 0.5 * depthn) * ocean * 0.9
    w["rocky bottom"] = energy ** 2 * ocean
    w["vent crust"] = ventf * ocean
    w["cold seep"] = seep_ring * (0.5 + 0.5 * depthn) * ocean
    w["tidal flat"] = tidal * 0.9                          # interface class
    w["lake mud"] = lake * (1 - slope) * (0.5 + 0.5 * dep)
    w["river gravel bed"] = river * rs
    w["river sand bed"] = river * (1 - rs)
    return w


def build_ground(z, manifest: dict, sea: float,
                 vent_activity: np.ndarray) -> dict:
    """The B3 ground pass at anchor res. Returns d2 (41,H,W float32),
    class_id (H,W uint8), mix_ids/mix_w (top-3), and meta (the JSON-able
    class table). Deterministic — no RNG anywhere."""
    e = _evidence(z, sea, vent_activity)
    bias = _biome_bias(e["biome"])
    rules = _weights(e)

    stacked = np.stack(
        [np.clip(rules[c["name"]] * bias[i], 0.0, 1.0)
         for i, c in enumerate(GROUND_CLASSES)], axis=0)   # (41,H,W)
    d2 = (-np.log(np.maximum(stacked, W_FLOOR))).astype(np.float32)
    class_id = np.argmax(stacked, axis=0).astype(np.uint8)

    # top-3 mix. softmax over the FULL -d2 vector at temperature TAU; at
    # TAU=1 that equals w normalized to sum 1, and the three shown shares
    # are then RENORMALIZED over themselves so each cell's top-3 sums to 1
    # (an honest mosaic spans 4-5 classes — the tail is signal, not noise).
    logits = -d2.astype(np.float64) / TAU
    logits -= logits.max(axis=0, keepdims=True)
    full = np.exp(logits)
    full /= full.sum(axis=0, keepdims=True)
    # stable so a tie at the top keeps ascending class order — the first mix
    # entry then always equals argmax (class_id), which also breaks ties low
    order = np.argsort(-stacked, axis=0, kind="stable")[:3]   # (3,H,W)
    mix_w = np.take_along_axis(full, order, axis=0)
    mix_w /= mix_w.sum(axis=0, keepdims=True)

    meta = [dict(name=c["name"], color=c["color"], hard=c["hard"],
                 loose=c["loose"], retention=c["retention"],
                 rooting_m=c["rooting_m"], sal_add=c["sal_add"],
                 nutrient=c["nutrient"], genesis=c["genesis"],
                 genesis_tag=c["genesis_tag"]) for c in GROUND_CLASSES]
    return dict(d2=d2, class_id=class_id,
                mix_ids=order.astype(np.uint8),
                mix_w=mix_w.astype(np.float32), meta=meta)
