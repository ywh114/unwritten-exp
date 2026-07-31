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
reads 1.0 (saturated — bare pillow basalt excepted) and sal_add is
None, meaning "the water's own salinity" (the consumer supplies it;
K11 h_salinity covers water only).
"""

from __future__ import annotations

import numpy as np

from exp.k11_worldgen.biomes import BIOME_ID
from exp.k11_worldgen.units import DEPTH_MAX_M, elev_m, hand_m, precip_mm, \
    temp_c
from kernel.hashrng import Stream
# reuse the B2 reference values where the evidence is the same quantity,
# plus the bilinear _upsample helper for the delivery-res re-derivation,
# the _spread_max dilation helper, and the flood-pulse footprint
from exp.k14_worldprod.derived import ACC_REF, HAND_REF_M, P_REF_MMYR, \
    _spread_max, _upsample, flood_pulse

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
DUNE_ACC_REF = 10.0           # upstream (catchment) cells terminating in a
                              # hyperarid cell that read as an aeolian sand
                              # supply — a terminal wadi fan. Endorheic
                              # desert interiors max out near ~20 cells, so
                              # this opens only true drainage termini; the
                              # flat/dry self-gate in _evidence covers the
                              # basin-interior deflation ergs
W_FLOOR = 1e-6                # generator-weight floor feeding -log -> d2

# ── volcanic (vent) evidence — built from the vent/spring POINTS, not ───
# ── the raw fault field: most vents are dormant, and only ACTIVE crater ──
# ── bowls carry fresh lava / pillow basalt / vent crust. Radii are in ────
# ── anchor cells (4 km each) so the same painter runs natively at any ────
# ── resolution. ──────────────────────────────────────────────────────────
VENT_HALO_SIGMA_C = 2.0       # andisol (volcanic-soil) halo sigma
VENT_HALO_CUT_C = 6.0         # halo cut radius (24 km)
VENT_CORE_R_C = 1.2           # crater-bowl disk radius — fresh lava /
                              # pillow basalt / vent crust are disk-only
VENT_SEEP_R_C = 3.5           # cold-seep annulus outer radius
SEEP_SHELF_GATE_M = 200.0     # that annulus's shelf gate (m water depth):
                              # 0 above, ramps to 1 by 2x, uncapped below
                              # (hadal vent seepage is real)
SEEP_HYDRATE_LO_M = 300.0     # passive-margin seeps (vent-independent):
                              # methane-hydrate stability band foot ...
SEEP_HYDRATE_HI_M = 3000.0    # ... and ceiling — a smooth ramp pair over
                              # sedimented continental slopes
VENT_P_ACTIVE_BASE = 0.25     # dormancy roll: p(active) foot ...
VENT_P_ACTIVE_SPAN = 0.25     # ... + span x normalized activity, so even
                              # the world's hottest vent is active ~half
                              # the time (most volcanoes are dormant)

# ── consume-time softmax temperature (knob set #4) ──────────────────────
TAU = 1.0                     # softmax over -d2; at TAU=1 softmax(-d2) is
                              # exactly w normalized to sum 1 (d2 = -log w),
                              # so the top-3 mix shares are the renormalized
                              # generator weights of the three shown classes

# ── class table (42; knob set #1 — the floats are draft, the ORDERINGS ──
# ── are the defensible content, consumers of d2 are robust to +-0.1) ────
# Per class: property row (retention, rooting_m, sal_add, nutrient, ph)
# from the spec; hard/loose metadata flags; a muted terrain-legible
# color; a genesis note; and a genesis TAG (physical/biotic/mixed,
# metadata only).
#   hard  = anchoring rock/hardpan — holdfast rooters need it, roots and
#           burrows do NOT penetrate (impenetrable for free).
#   loose = penetrable/diggable GRANULAR medium — fossorial fauna and
#           sand-swimmers need it (cohesive clays/muds/peats are neither).
# sal_add is None for underwater rows (= the water's salinity).
# ph is soil pH on land, pore/water-column pH underwater (seawater ~8.1,
# hydrothermal crusts acid); the ORDERING (bog < fen, podzol < brown
# earth, laterite < rendzina, solonchak < solonetz) is the content.
GROUND_CLASSES: list[dict] = [
    # ── terrestrial — physical ──────────────────────────────────────────
    dict(name="dune sand", retention=0.05, rooting_m=0.3, sal_add=0.0,
         nutrient=0.15, ph=6.5, hard=False, loose=True, color=[222, 200, 130],
         genesis="most-arid deposition only", genesis_tag="physical"),
    dict(name="sand sheet", retention=0.10, rooting_m=0.5, sal_add=0.0,
         nutrient=0.20, ph=6.5, hard=False, loose=True, color=[210, 188, 128],
         genesis="arid", genesis_tag="physical"),
    dict(name="reg / desert pavement", retention=0.05, rooting_m=0.2,
         sal_add=0.0, nutrient=0.15, ph=7.8, hard=True, loose=False,
         color=[176, 150, 118], genesis="winnowing",
         genesis_tag="physical"),   # armored stone lag: anchors, no digging
    dict(name="scree", retention=0.05, rooting_m=0.10, sal_add=0.0,
         nutrient=0.05, ph=6.8, hard=True, loose=False, color=[150, 145, 140],
         genesis="slope override", genesis_tag="physical"),
    dict(name="bedrock outcrop", retention=0.02, rooting_m=0.05,
         sal_add=0.0, nutrient=0.02, ph=7.0, hard=True, loose=False,
         color=[120, 118, 116], genesis="erosion", genesis_tag="physical"),
    dict(name="alluvium", retention=0.65, rooting_m=2.0, sal_add=0.0,
         nutrient=0.80, ph=6.8, hard=False, loose=True, color=[160, 140, 95],
         genesis="deposition", genesis_tag="physical"),
    dict(name="loess", retention=0.55, rooting_m=1.5, sal_add=0.0,
         nutrient=0.70, ph=7.8, hard=False, loose=True, color=[190, 170, 120],
         genesis="glacial-margin wind", genesis_tag="physical"),
    dict(name="silt", retention=0.60, rooting_m=1.2, sal_add=0.0,
         nutrient=0.65, ph=6.8, hard=False, loose=True, color=[170, 155, 120],
         genesis="low-energy deposition", genesis_tag="physical"),
    dict(name="clay", retention=0.65, rooting_m=0.8, sal_add=0.0,
         nutrient=0.55, ph=6.5, hard=False, loose=False, color=[150, 120, 95],
         genesis="still water (plant-available, not total)",
         genesis_tag="physical"),   # cohesive: rootable, not a dig medium
    dict(name="vertisol", retention=0.75, rooting_m=1.2, sal_add=0.0,
         nutrient=0.70, ph=7.8, hard=False, loose=False, color=[110, 95, 80],
         genesis="shrink-swell smectite, seasonal cracks",
         genesis_tag="physical"),
    dict(name="till", retention=0.45, rooting_m=0.8, sal_add=0.0,
         nutrient=0.50, ph=6.8, hard=False, loose=False, color=[140, 130, 110],
         genesis="glacial", genesis_tag="physical"),
    dict(name="outwash gravel", retention=0.15, rooting_m=0.4, sal_add=0.0,
         nutrient=0.35, ph=6.5, hard=False, loose=False, color=[165, 155, 135],
         genesis="glaciofluvial", genesis_tag="physical"),
    dict(name="andisol", retention=0.80, rooting_m=1.0, sal_add=0.0,
         nutrient=0.70, ph=5.5, hard=False, loose=False, color=[95, 80, 70],
         genesis="vent proximity (allophane: high water, P fixed)",
         genesis_tag="physical"),
    dict(name="fresh lava", retention=0.05, rooting_m=0.1, sal_add=0.0,
         nutrient=0.30, ph=6.5, hard=True, loose=False, color=[70, 65, 68],
         genesis="active fault", genesis_tag="physical"),
    dict(name="rendzina", retention=0.30, rooting_m=0.4, sal_add=0.0,
         nutrient=0.55, ph=7.8, hard=False, loose=False, color=[176, 166, 140],
         genesis="limestone (calcicole; absorbs chalk)",
         genesis_tag="physical"),   # no lithology field: base-rich,
                                    # low-leaching climate proxy stands in
    dict(name="laterite cuirasse", retention=0.10, rooting_m=0.2,
         sal_add=0.0, nutrient=0.10, ph=5.0, hard=True, loose=False,
         color=[160, 90, 60], genesis="plinthite hardpan, tropical",
         genesis_tag="physical"),
    dict(name="caliche", retention=0.12, rooting_m=0.25, sal_add=0.0,
         nutrient=0.20, ph=8.2, hard=True, loose=False, color=[200, 190, 165],
         genesis="petrocalcic hardpan, semi-arid", genesis_tag="physical"),
    dict(name="solonchak", retention=0.10, rooting_m=0.3, sal_add=1.0,
         nutrient=0.05, ph=8.5, hard=False, loose=False, color=[235, 230, 210],
         genesis="endorheic/coastal evaporite (absorbs sabkha)",
         genesis_tag="physical"),
    dict(name="solonetz", retention=0.35, rooting_m=0.5, sal_add=0.45,
         nutrient=0.25, ph=9.0, hard=False, loose=False, color=[200, 185, 150],
         genesis="sodic, dispersed clay", genesis_tag="physical"),
    dict(name="coastal sand", retention=0.10, rooting_m=0.4, sal_add=0.3,
         nutrient=0.20, ph=7.5, hard=False, loose=True, color=[230, 220, 170],
         genesis="littoral", genesis_tag="physical"),
    # ── terrestrial — biotic / mixed ────────────────────────────────────
    dict(name="mollisol", retention=0.70, rooting_m=2.2, sal_add=0.0,
         nutrient=0.95, ph=6.8, hard=False, loose=False, color=[120, 90, 55],
         genesis="grassland", genesis_tag="biotic"),
    dict(name="podzol", retention=0.45, rooting_m=0.9, sal_add=0.0,
         nutrient=0.25, ph=4.5, hard=False, loose=False, color=[100, 85, 70],
         genesis="conifer/taiga", genesis_tag="biotic"),
    dict(name="ferralsol", retention=0.55, rooting_m=1.5, sal_add=0.0,
         nutrient=0.15, ph=5.0, hard=False, loose=False, color=[180, 100, 60],
         genesis="rainforest (nutrients in biomass)", genesis_tag="biotic"),
    dict(name="brown earth", retention=0.60, rooting_m=1.5, sal_add=0.0,
         nutrient=0.65, ph=6.0, hard=False, loose=False, color=[130, 100, 65],
         genesis="temperate broadleaf", genesis_tag="biotic"),
    dict(name="fen", retention=0.92, rooting_m=0.5, sal_add=0.0,
         nutrient=0.45, ph=6.2, hard=False, loose=False, color=[110, 120, 80],
         genesis="groundwater-fed peat", genesis_tag="mixed"),
    dict(name="bog", retention=0.98, rooting_m=0.3, sal_add=0.0,
         nutrient=0.05, ph=4.0, hard=False, loose=False, color=[140, 115, 80],
         genesis="rain-fed Sphagnum dome (carnivory's home)",
         genesis_tag="mixed"),
    dict(name="gleysol", retention=0.85, rooting_m=0.3, sal_add=0.0,
         nutrient=0.30, ph=5.5, hard=False, loose=False, color=[120, 130, 130],
         genesis="groundwater waterlogging", genesis_tag="mixed"),
    dict(name="gelisol", retention=0.60, rooting_m=0.4, sal_add=0.0,
         nutrient=0.30, ph=5.5, hard=False, loose=False, color=[180, 190, 195],
         genesis="permafrost + cryoturbation", genesis_tag="mixed"),
    dict(name="mangrove mud", retention=0.90, rooting_m=0.5, sal_add=0.6,
         nutrient=0.50, ph=6.5, hard=False, loose=False, color=[90, 100, 70],
         genesis="mangrove", genesis_tag="biotic"),
    dict(name="montane ranker", retention=0.35, rooting_m=0.4, sal_add=0.0,
         nutrient=0.40, ph=5.5, hard=False, loose=False, color=[140, 135, 110],
         genesis="thin upland soil", genesis_tag="mixed"),
    # ── underwater (retention 1.0 saturated; sal_add None = the water) ──
    dict(name="marine mud", retention=1.0, rooting_m=0.3, sal_add=None,
         nutrient=0.40, ph=7.8, hard=False, loose=False, color=[70, 90, 100],
         genesis="marine snow, quiet shelf", genesis_tag="physical"),
    dict(name="abyssal clay", retention=1.0, rooting_m=0.2, sal_add=None,
         nutrient=0.10, ph=7.8, hard=False, loose=False, color=[40, 55, 80],
         genesis="pelagic, food-starved", genesis_tag="physical"),
    dict(name="marine sand", retention=1.0, rooting_m=0.3, sal_add=None,
         nutrient=0.25, ph=8.0, hard=False, loose=True, color=[150, 160, 130],
         genesis="high-energy shelf", genesis_tag="physical"),
    dict(name="reef carbonate", retention=1.0, rooting_m=0.4, sal_add=None,
         nutrient=0.35, ph=8.2, hard=True, loose=False, color=[130, 170, 175],
         genesis="coral", genesis_tag="biotic"),
    dict(name="rocky bottom", retention=1.0, rooting_m=0.05, sal_add=None,
         nutrient=0.20, ph=8.1, hard=True, loose=False, color=[90, 95, 100],
         genesis="high energy / kelp holdfast", genesis_tag="physical"),
    dict(name="vent crust", retention=1.0, rooting_m=0.1, sal_add=None,
         nutrient=0.90, ph=5.5, hard=True, loose=False, color=[110, 70, 60],
         genesis="hot sulfide chemosynthesis", genesis_tag="mixed"),
    dict(name="cold seep", retention=1.0, rooting_m=0.3, sal_add=None,
         nutrient=0.85, ph=7.2, hard=False, loose=False, color=[80, 100, 95],
         genesis="methane chemosynthesis + carbonate", genesis_tag="mixed"),
    dict(name="pillow basalt", retention=0.10, rooting_m=0.1, sal_add=None,
         nutrient=0.10, ph=8.0, hard=True, loose=False, color=[62, 68, 76],
         genesis="submarine eruption (quenched pillow lava)",
         genesis_tag="physical"),   # bare rock: the one underwater row not
                                    # reading 1.0 saturated
    dict(name="tidal flat", retention=1.0, rooting_m=0.15, sal_add=0.5,
         nutrient=0.55, ph=7.5, hard=False, loose=False, color=[140, 150, 130],
         genesis="tide-sorted, brackish gradient", genesis_tag="physical"),
    dict(name="lake mud", retention=1.0, rooting_m=0.4, sal_add=None,
         nutrient=0.60, ph=7.0, hard=False, loose=False, color=[85, 105, 110],
         genesis="deposition + biotic", genesis_tag="mixed"),
    dict(name="river gravel bed", retention=1.0, rooting_m=0.2, sal_add=0.0,
         nutrient=0.30, ph=7.2, hard=False, loose=False, color=[130, 130, 120],
         genesis="flow-sorted", genesis_tag="physical"),
    dict(name="river sand bed", retention=1.0, rooting_m=0.3, sal_add=0.0,
         nutrient=0.25, ph=7.2, hard=False, loose=True, color=[160, 155, 120],
         genesis="flow-sorted", genesis_tag="physical"),
]

N_CLASSES = len(GROUND_CLASSES)
GROUND_ID = {c["name"]: i for i, c in enumerate(GROUND_CLASSES)}
assert N_CLASSES == 42, ("B3 specifies 41 ground classes + pillow basalt "
                         "(42nd) added for submarine eruptions")

# domain slices (index ranges) — used by the land/water separation and the
# biome-bias suppression
_TERRESTRIAL = range(0, 30)          # physical + biotic/mixed soils
_MARINE = range(30, 38)              # marine mud .. pillow basalt
_BIOTIC_SOILS = [i for i in _TERRESTRIAL
                 if GROUND_CLASSES[i]["genesis_tag"] in ("biotic", "mixed")]
_BIOTIC_SOILS_SET = set(_BIOTIC_SOILS)

# ── biome bias (knob set #1/#2 — "the biome pretends the climate ────────
# ── considerations were done for you"; multiplicative, capped at 1) ─────
_BIAS: dict[str, dict[str, float]] = {
    "mollisol": {"temperate grassland": 2.5, "tropical grassland": 2.0},
    "podzol": {"boreal taiga": 3.0, "temperate conifer forest": 3.0},
    "ferralsol": {"tropical moist forest": 3.0,
                  # highland pine-oak soils are acrisol/ferralsol types;
                  # without a bias the cells fell through to the physical
                  # layer and read rendzina/sand sheet at ~900 mm/yr.
                  # Podzol would be wrong here: its rule self-docks to
                  # 0.3 at 17 degC ((0.3+0.7*cold))
                  "tropical conifer forest": 2.0},
    "brown earth": {"temperate broadleaf forest": 3.0},
    "gelisol": {"tundra": 2.0},
    "bog": {"tundra": 1.5, "boreal taiga": 1.5},
    "fen": {"flooded grassland": 2.0, "tundra": 1.5},
    "gleysol": {"flooded grassland": 1.5},
    "mangrove mud": {"mangrove": 3.0},
    "montane ranker": {"montane grassland": 2.0},
    "dune sand": {"desert xeric (hot)": 1.5},   # ergs: hot deserts only —
    # cold-desert dunes exist but are rare; the physical arid² gate can
    # still open dune there, it just gets no biome boost
    "sand sheet": {"desert xeric (hot)": 1.5, "desert xeric (cold)": 1.5},
    "reg / desert pavement": {"desert xeric (hot)": 1.5,
                              "desert xeric (cold)": 1.5},
}
_SUPPRESS_BIOMES = ("rock", "ice")   # no soil there: biotic soils x0.2
_SUPPRESS_FACTOR = 0.2


# ── small array helpers ─────────────────────────────────────────────────


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


# ── vent fields (point-based volcanic influence) ────────────────────────


def _vent_active(pts: list[dict], seed: int) -> list[bool]:
    """Deterministic per-vent dormancy roll (K1 stream, one draw per vent,
    in point-list order). Most volcanoes are dormant: p(active) in
    [VENT_P_ACTIVE_BASE, BASE+SPAN] scaled by normalized activity."""
    if not pts:
        return []
    amax = max(p["activity"] for p in pts) or 1.0
    stream = Stream(seed, "k14.ground.vents")
    return [stream.bernoulli(VENT_P_ACTIVE_BASE
                             + VENT_P_ACTIVE_SPAN * (p["activity"] / amax),
                             0, i)
            for i, p in enumerate(pts)]


def _vent_fields(pts: list[dict], shape: tuple[int, int], seed: int,
                 cells_per: int = 1):
    """(ventf, vent_core, seep_ring) painted from the vent/spring points:
    ventf is the gaussian volcanic-soil halo around EVERY vent (weathered
    rock persists on dormant volcanoes); vent_core is the crisp crater-bowl
    disk, ACTIVE vents only; seep_ring is the annulus just outside the
    bowl (methane seeps outlive eruptions). cells_per = delivery factor;
    radii are in anchor cells, so the painter runs natively at any res."""
    H, W = shape
    ventf = np.zeros((H, W))
    core = np.zeros((H, W))
    ring = np.zeros((H, W))
    if not pts:
        return ventf, core, ring
    amax = max(p["activity"] for p in pts) or 1.0
    active = _vent_active(pts, seed)
    box = int(np.ceil(VENT_HALO_CUT_C * cells_per)) + 1
    for p, act in zip(pts, active):
        a = p["activity"] / amax
        cy = p["y"] * cells_per + cells_per // 2
        cx = p["x"] * cells_per + cells_per // 2
        y0, y1 = max(0, cy - box), min(H, cy + box + 1)
        x0, x1 = max(0, cx - box), min(W, cx + box + 1)
        yy, xx = np.mgrid[y0:y1, x0:x1]
        d = np.hypot(yy - cy, xx - cx) / cells_per     # anchor-cell units
        halo = a * np.exp(-(d ** 2) / (2 * VENT_HALO_SIGMA_C ** 2))
        halo[d > VENT_HALO_CUT_C] = 0.0
        np.maximum(ventf[y0:y1, x0:x1], halo, out=ventf[y0:y1, x0:x1])
        ann = ((d > VENT_CORE_R_C) & (d <= VENT_SEEP_R_C)) * (0.8 * a)
        np.maximum(ring[y0:y1, x0:x1], ann, out=ring[y0:y1, x0:x1])
        if act:
            np.maximum(core[y0:y1, x0:x1], (d <= VENT_CORE_R_C) * a,
                       out=core[y0:y1, x0:x1])
    return ventf, core, ring


# ── evidence fields (all bounded [0,1] by construction) ─────────────────


def _evidence(z, sea: float, vent_pts: list[dict], seed: int) -> dict:
    """Compute every bounded evidence field once per build. Returns a dict
    of (H,W) float fields in [0,1] plus the domain masks."""
    ocean = z["h_ocean_mask"] | z["h_sea_mask"]
    lake = z["h_lake_mask"]
    river = z["h_river_mask"]
    land = ~ocean & ~lake & ~river

    hand = hand_m(z["h_hand"], sea)
    wet = np.exp(-hand / HAND_REF_M)                       # waterlogging
    dep_dry = np.clip(z["h_accumulation"] / ACC_REF, 0.0, 1.0)
    dep = dep_dry * wet

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

    # volcanic influence from the vent/spring POINTS (not the raw fault
    # field — a fault line is not a volcano): gaussian andisol halo around
    # every vent, crisp crater bowls on ACTIVE vents only (K1 dormancy
    # roll), seep annulus around every vent.
    ventf, vent_core, seep_ring = _vent_fields(vent_pts, ocean.shape, seed,
                                               cells_per=1)

    # ── derived soil salinity (no upstream field — spec calls this out) ──
    # max of three bounded terms:
    #  (a) endorheic: the salt-lake halo — a lake saltier than SALT_LAKE_REF
    #      spreads its clip(salinity/SALT_LAKE_MAX) value 3 cells out;
    #  (b) arid evaporation: arid, non-depositional ground concentrates
    #      salts (half weight). arid², same leak as sand sheet: the
    #      1500 mm linear reference leaves arid=0.4 at 900 mm/yr, and
    #      un-squared it put solonetz/solonchak on a third of the humid
    #      tropical-conifer highlands;
    #  (c) coast: within 2 cells of the ocean (spray/brackish, 0.3).
    salt_lake = lake & (z["h_salinity"] > SALT_LAKE_REF)
    salt_src = np.where(salt_lake,
                        np.clip(z["h_salinity"] / SALT_LAKE_MAX, 0.0, 1.0),
                        0.0)
    endorheic = _spread_max(salt_src, 3)
    arid_evap = arid ** 2 * (1.0 - dep) * 0.5
    coast = _dilate8(ocean, 2).astype(np.float64) * 0.3
    salsoil = np.maximum(np.maximum(endorheic, arid_evap), coast)

    # marine: bottom energy from current speed; depth from bathymetry
    energy = np.clip(np.hypot(z["r_u"], z["r_v"]) / CUR_REF, 0.0, 1.0)
    bathy = np.maximum(sea - z["w_elev"], 0.0) / sea * DEPTH_MAX_M
    depthn = np.clip(bathy / DEPTH_ABYSS_M, 0.0, 1.0)

    # cold-seep provenance (two components — see the cold seep rule):
    # shelf_gate docks the vent-ring component off shallow shelves (no
    # hydrate stability there); seep_passive is the vent-independent
    # passive-margin component, a smooth hydrate-stability band over
    # sedimented slopes. Both bounded [0,1] — the 1.6 gain lets a
    # sediment-rich slope cell outvote marine mud, the clip keeps the
    # evidence invariant (the band pair itself peaks at 0.8).
    shelf_gate = np.clip((bathy - SEEP_SHELF_GATE_M) / SEEP_SHELF_GATE_M,
                         0.0, 1.0)
    hydrate = (np.clip((bathy - SEEP_HYDRATE_LO_M) / SEEP_HYDRATE_LO_M,
                       0.0, 1.0)
               * np.clip((SEEP_HYDRATE_HI_M - bathy) / SEEP_HYDRATE_HI_M,
                         0.0, 1.0))
    seep_passive = np.clip(hydrate * dep * (0.4 + 0.6 * slope) * 1.6,
                           0.0, 1.0)

    # rivers: flow speed at anchor res (persisted by K11); fall back to a
    # bounded discharge rank ONLY if a stale dump lacks it (noted, and no
    # actual rank — a clip over DIS_REF).
    if "h_river_speed" in z:
        rs = np.clip(z["h_river_speed"] / RV_REF, 0.0, 1.0)
    else:
        rs = np.clip(z["h_discharge"] / DIS_REF, 0.0, 1.0)

    # seasonal channels (dry washes): LAND cells carrying water in SOME
    # months only. A seasonal river below the L0 cutoff is not "no
    # water", and its bed is not the surrounding soil — the channel
    # keeps its flow-sorted deposit year-round (wadi/arroyo). Weighted
    # by the dry fraction: an 11-month channel is nearly a river, a
    # 1-month wash nearly bare bed.
    if "h_river_width_monthly" in z:
        nwet = (z["h_river_width_monthly"] > 0).sum(axis=0)
        seasw = ((nwet > 0) & (nwet < 12) & land).astype(np.float64) \
            * (12 - nwet) / 12.0
    else:
        seasw = np.zeros(rs.shape, dtype=np.float64)
    # flood pulse: the seasonal discharge SWING of nearby channels, HAND-
    # gated (derived.flood_pulse) — snowmelt floodplains and ephemeral
    # wash corridors; feeds alluvium (the floodplain soil) and the
    # terrestrial productivity bonus
    pulse = flood_pulse(z, sea)

    # tidal band: land/ocean cells within 1 cell of the shoreline, flat
    # (slope < 0.05), and — for water cells — shallow.
    near_ocean1 = _dilate8(ocean, 1)
    coast_band = (near_ocean1 & ~ocean) | (_dilate8(~ocean, 1) & ocean)
    flat = slope < 0.05
    shallow = depthn < 0.05
    tidal = (coast_band & flat & (~ocean | shallow)).astype(np.float64)

    # dune gate: ergs need hyperaridity plus EITHER a sediment supply
    # (terminal wadi fan — but endorheic desert interiors have tiny
    # catchments, max ~20 cells) OR simply the flattest, driest ground
    # (basin-interior deflation fields; the 0.8 keeps self-gated dunes
    # just below fan-fed ones, playas/rough ground stay out via
    # (1-wet)/(1-slope)). The arid² weighting is what confines the gate —
    # and every (1-dune_dep) suppression keyed on it — to true desert;
    # without it reg got suppressed on ALL flat dry land.
    dune_gate = (np.maximum(
        np.clip(z["h_accumulation"] / DUNE_ACC_REF, 0.0, 1.0),
        0.8 * (1 - slope) * (1 - wet)) * arid ** 2)

    # lake littoral (UNDERWATER only — the ring of LAKE cells adjacent to
    # shore; shore land keeps its own soils, treeline-to-lake is common):
    # sandy where the bed is gentle and winnowed, rocky where steep, while
    # lake mud holds the deep center and the high-deposition inflow deltas
    lake_shore = (_dilate8(land, 1) & lake).astype(np.float64)

    # shared per-class sub-expressions. The remaining halo/dilation terms
    # are computed here at anchor res; the hi-res pass upsamples the
    # finished fields (never re-dilates at delivery res) so the halo width
    # in km is preserved and only the edges go smooth. The vent fields
    # above are the exception: painted from points natively at either res.
    reef = (z["w_aquatic"] == 4).astype(np.float64)     # K11 "coral reef"

    return dict(
        ocean=ocean.astype(np.float64), lake=lake.astype(np.float64),
        river=river.astype(np.float64), land=land.astype(np.float64),
        dep=dep, wet=wet, slope=slope, arid=arid, cold=cold, warm=warm,
        glac=glac, ventf=ventf, vent_core=vent_core, seep_ring=seep_ring,
        shelf_gate=shelf_gate, seep_passive=seep_passive,
        salsoil=salsoil, energy=energy, depthn=depthn, rs=rs, tidal=tidal,
        near_ocean1=near_ocean1.astype(np.float64),
        lake_shore=lake_shore,
        dune_dep=dune_gate,
        seasw=seasw, pulse=pulse,
        loamy=0.5 + 0.5 * dep, reef=reef,
        biome=z["w_biome_map"], vent_pts=vent_pts)


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
# exactly zero off its domain. Computed ONE PLANE AT A TIME from the
# evidence dict so the hi-res pass can stream classes without ever holding
# all 42 delivery-res planes (the rule is pointwise, so it reruns at any
# resolution unchanged). The table order in GROUND_CLASSES fixes the ids.
def _class_weight(name: str, e: dict) -> np.ndarray:
    land, ocean = e["land"], e["ocean"]
    lake, river = e["lake"], e["river"]
    dep, wet, slope = e["dep"], e["wet"], e["slope"]
    arid, cold, warm = e["arid"], e["cold"], e["warm"]
    glac, ventf, vent_core = e["glac"], e["ventf"], e["vent_core"]
    salsoil, energy, depthn = e["salsoil"], e["energy"], e["depthn"]
    rs, tidal = e["rs"], e["tidal"]
    dune_dep, loamy = e["dune_dep"], e["loamy"]
    seep_ring, reef = e["seep_ring"], e["reef"]
    shelf_gate, seep_passive = e["shelf_gate"], e["seep_passive"]
    seasw, pulse = e["seasw"], e["pulse"]
    no = e["near_ocean1"]
    lake_shore = e["lake_shore"]

    # terrestrial — physical
    if name == "dune sand":            # aridity already lives in dune_dep's gate
        return dune_dep * (1 - 0.5 * slope) * land
    if name == "sand sheet":
        # arid^1.5: the 1500 mm linear reference leaves arid=0.4 at 900
        # mm/yr, and un-squared arid gave sheet ~0.4 weight on ANY flat
        # semi-humid cell (it dominated tropical conifer highlands);
        # full arid² (0.4 -> 0.16) overcorrected — sheet collapsed to
        # 0.01-0.5% of land and reg inherited the whole semi-arid band,
        # backwards (sand sheets outsize ergs on Earth). The 1.5 power
        # keeps the humid loss (0.4 -> 0.25, below brown earth's
        # loamy-docked 0.3) while holding the semi-arid band
        # (0.6 -> 0.46, 0.8 -> 0.72).
        return arid ** 1.5 * (1 - slope) * (1 - 0.6 * dune_dep) * land
    if name == "reg / desert pavement":
        # arid²: true-desert default only — the semi-arid band belongs to
        # sand sheet and the (1-arid)-scaled soils (reg was cosmopolitan).
        # Where the dune gate is open the sand is mobile and the pavement
        # is disturbed — but only at half weight: suppressing by the full
        # gate cost reg 40-65% in its own heartland where dunes never
        # actually win (semi-arid flats), gifting the area to solonetz.
        return arid ** 2 * (1 - dep) * (1 - 0.5 * slope) * (1 - 0.5 * dune_dep) * land
    if name == "scree":                # the slope override
        return slope ** 1.5 * (1 - 0.3 * slope) * land
    if name == "bedrock outcrop":      # steepest cliffs
        return slope ** 3 * land
    if name == "alluvium":
        # dep-keyed alluvial plain OR the flood-pulse footprint: a river
        # with a strong seasonal swing (snowmelt, monsoon, ephemeral
        # flash) builds a floodplain of fresh fluvisol even where the
        # mean deposition signal is modest — the flood pulse IS the
        # floodplain builder
        return (np.maximum(dep * (1 - 0.6 * wet), pulse * 0.9)
                * (1 - slope) * land)
    if name == "loess":
        return glac * (1 - dep) * (1 - slope) * (1 - wet) * 0.8 * land
    if name == "silt":
        return dep * (1 - slope) * (0.4 + 0.6 * wet) * 0.9 * land
    if name == "clay":
        return dep * wet ** 2 * 0.95 * land
    if name == "vertisol":
        return dep * np.sqrt(wet * arid) * (1 - slope) * land
    if name == "till":
        return glac * (1 - 0.5 * slope) * land
    if name == "outwash gravel":
        return glac * dep * 0.8 * land
    if name == "andisol":
        return ventf * (1 - slope) * land
    if name == "fresh lava":
        # the crater bowl of an ACTIVE vent only (vent_core is already
        # dormancy-gated); dormant flanks weather to andisol
        return vent_core * (0.3 + 0.7 * slope) * land
    if name == "rendzina":
        return ((1 - arid) * (1 - cold) * (1 - wet) * (1 - dep)
                * (1 - slope) * 0.75 * land)
    if name == "laterite cuirasse":
        return warm * (1 - arid) * (1 - slope) * 0.6 * land
    if name == "caliche":
        return arid * (1 - wet) * (1 - dep) * (1 - slope) * 0.7 * land
    if name == "solonchak":
        return salsoil ** 2 * (1 - slope) * land
    if name == "solonetz":
        return salsoil * (1 - salsoil) * 4.0 * (1 - slope) * 0.6 * land
    if name == "coastal sand":
        # ocean littoral + the lake-shore ring where the bed is gentle and
        # winnowed (high-deposition inflow shores stay lake mud)
        return (no * land * 0.8 + lake_shore * (1 - dep)) * (1 - slope)
    # terrestrial — biotic / mixed (biome bias applied by the caller)
    if name == "mollisol":
        # steppe-tolerant (chernozem): arid only docks 0.6, so semi-arid
        # grassland reads mollisol instead of falling through to sand sheet
        return (1 - 0.6 * arid) * (1 - cold) * (1 - slope) * loamy * land
    if name == "podzol":
        return (1 - arid) * (0.3 + 0.7 * cold) * (1 - slope) * loamy * land
    if name == "ferralsol":
        return warm * (1 - arid) * (1 - slope) * loamy * land
    if name == "brown earth":
        return (1 - arid) * (1 - cold) * (1 - slope) * loamy * land
    if name == "fen":
        # warm-temperate wetland counterpart of bog (which is cold-gated)
        return wet * loamy * (1 - slope) * 0.9 * (0.4 + 0.6 * warm) * land
    if name == "bog":
        # rain-fed peat prefers COLD wetlands: without the gate every wet
        # flat on the planet read bog (9% of land — Earth has ~3%, mostly
        # cold). Soft gate, not a veto: warm bogs exist, just rarer.
        return wet * (1 - dep) * (1 - slope) * 0.85 * (0.5 + 0.5 * cold) * land
    if name == "gleysol":
        return wet * loamy * (1 - slope) * 0.8 * land
    if name == "gelisol":
        return cold * (1 - slope) * 0.9 * land
    if name == "mangrove mud":
        return wet * no * warm * (1 - slope) * land
    if name == "montane ranker":
        return (1 - dep) * (1 - slope) * (0.4 + 0.6 * cold) * 0.7 * land
    # underwater — vent/seep influence suppresses the deep-ocean
    # background (pillow basalt / vent crust at the active core split by
    # depth, cold seep in the annulus beyond and on passive margins)
    if name == "marine mud":
        return (1 - depthn) * (1 - energy) * (1 - reef) * ocean
    if name == "abyssal clay":
        return (depthn ** 2 * (1 - energy) * (1 - 0.5 * ventf)
                * (1 - 0.5 * seep_ring) * (1 - 0.5 * seep_passive) * ocean)
    if name == "marine sand":
        return (1 - depthn) * energy * (1 - energy) * 1.2 * (1 - reef) * ocean
    if name == "reef carbonate":
        # a reef IS carbonate — no cap: it must outvote the mud/sand
        # background on its own mask (it lost 99.5% of reef cells before)
        return reef * (1 - 0.5 * depthn) * ocean
    if name == "rocky bottom":
        # high-energy ocean floor + steep lake beds (rocky littoral)
        return energy ** 2 * ocean + lake_shore * slope ** 2
    if name == "vent crust":
        # active crater bowls only — dormant vents keep their seep ring;
        # vent crust is the sulfide cap of DEEP, long-lived systems (the
        # shallow submarine bowls quench to pillow basalt instead)
        return vent_core * ocean * depthn
    if name == "cold seep":
        # two provenances: vent-adjacent hydrothermal seepage — the ring
        # around every vent, shelf-gated (no hydrate stability on shallow
        # shelves) but uncapped below, hadal vent seepage is real; plus
        # passive-margin seeps decoupled from vents (seep_passive above)
        return (seep_ring * (0.5 + 0.5 * depthn) * shelf_gate
                + seep_passive) * ocean
    if name == "pillow basalt":
        # the shallow submarine crater bowl: erupted lava quenches to
        # pillows (deep bowls grow the sulfide cap and read vent crust)
        return vent_core * ocean * (1 - 0.5 * depthn)
    if name == "tidal flat":           # interface class
        return tidal * 0.9
    if name == "lake mud":
        # (1 - 0.5*slope), not (1 - slope): lake mud is the ONLY lake-domain
        # class, so it must stay > 0 across the whole lake bed — including
        # steep delivered shore cells where the upsampled slope clips to 1
        return lake * (1 - 0.5 * slope) * (0.5 + 0.5 * dep)
    if name == "river gravel bed":
        # seasw: a dry wash keeps its flow-sorted bed — seasonal
        # channels on land read as river bed, split by the same speed
        # evidence (speed is unknown off the annual network: rs=0
        # there, so dry washes default to sand, the common arroyo bed)
        return (river + seasw) * rs
    if name == "river sand bed":
        return (river + seasw) * (1 - rs)
    raise KeyError(f"unknown ground class: {name}")


def build_ground(z, manifest: dict, sea: float,
                 vent_pts: list[dict]) -> dict:
    """The B3 ground pass at anchor res. Returns d2 (42,H,W float32),
    class_id (H,W uint8), mix_ids/mix_w (top-3), and meta (the JSON-able
    class table). Deterministic — the only RNG is the K1 vent-dormancy
    stream keyed by manifest['seed']."""
    seed = int(manifest.get("seed", 0))
    e = _evidence(z, sea, vent_pts, seed)
    bias = _biome_bias(e["biome"])

    stacked = np.stack(
        [np.clip(_class_weight(c["name"], e) * bias[i], 0.0, 1.0)
         for i, c in enumerate(GROUND_CLASSES)], axis=0)   # (42,H,W)
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
                 nutrient=c["nutrient"], ph=c["ph"], genesis=c["genesis"],
                 genesis_tag=c["genesis_tag"]) for c in GROUND_CLASSES]
    return dict(d2=d2, class_id=class_id,
                mix_ids=order.astype(np.uint8),
                mix_w=mix_w.astype(np.float32), meta=meta)


CLASS_PH = np.array([c["ph"] for c in GROUND_CLASSES], dtype=np.float32)


def mix_ph(mix_ids: np.ndarray, mix_w: np.ndarray) -> np.ndarray:
    """Per-cell pH = the top-3 mix-weighted mean of the class pH rows.
    Pointwise (a consume-time transform over the persisted mix), so the
    same helper serves the anchor and delivery-res mixes. Soil pH on
    land, pore/water pH underwater — vent cells come out acid from the
    class row alone, no special-casing."""
    return (mix_w * CLASS_PH[mix_ids]).sum(axis=0).astype(np.float32)


# ── delivery-resolution re-derivation (de-blocking) ─────────────────────
# The classification rule is POINTWISE per cell, so it reruns at delivery
# res (1024²) instead of kron-stamping the anchor map into 4x4 px blocks —
# the deliver.py delivery rule: derived/pointwise quantities are re-derived
# at the target resolution from interpolated parents; only relational
# quantities stay at anchor res. Continuous evidence is bilinear-upsampled
# from anchor (halo/dilation terms included — they were computed at anchor
# above, so the halo width in km is preserved and only edges go smooth).
# Everything CATEGORICAL comes from the delivered K11 fields, never from a
# kron'd anchor map: domain masks (d_*_mask), the biome map (d_biome_map —
# biome-driven edges then coincide with the displayed Biomes divides), and
# the reef class (d_aquatic). The vent fields are re-painted from the point
# list natively at delivery res (crisp crater bowls, no 4x4 halo blocks).

# evidence planes that get bilinear-upsampled anchor -> delivery
_HI_FIELDS = ("dep", "wet", "slope", "arid", "cold", "warm", "glac",
              "salsoil", "energy", "depthn", "rs", "tidal",
              "near_ocean1", "lake_shore", "dune_dep", "loamy",
              "seasw", "pulse", "shelf_gate", "seep_passive")


def _upsample_evidence(e: dict, z, factor: int, seed: int) -> dict:
    """The anchor evidence dict re-gridded to delivery res."""
    hi = {k: _upsample(e[k], factor) for k in _HI_FIELDS}
    if "d_ocean_mask" in z:                 # delivered fields (real world)
        ocean = z["d_ocean_mask"] | z["d_sea_mask"]
        lake = z["d_lake_mask"]
        river = z["d_river_mask"]
        biome = z["d_biome_map"]
        reef = (z["d_aquatic"] == 4).astype(np.float64)
        if "d_river_speed" in z:
            # painted along the delivered river path (k11 deliver) —
            # the upsampled anchor speed evidence bled off-path and
            # missed the meandering delivered line
            hi["rs"] = np.clip(z["d_river_speed"] / RV_REF, 0.0, 1.0)
    else:                                   # synthetic: stamp the anchor maps
        def _stamp(m: np.ndarray) -> np.ndarray:
            return np.repeat(np.repeat(m > 0.5, factor, 0), factor, 1)
        ocean, lake, river = _stamp(e["ocean"]), _stamp(e["lake"]), \
            _stamp(e["river"])
        biome = np.repeat(np.repeat(e["biome"], factor, 0), factor, 1)
        reef = _upsample(e["reef"], factor)
    land = ~ocean & ~lake & ~river
    if "d_river_width_monthly" in z:
        # seasonal channels at delivered res: the stamped monthly
        # networks give the wet-month count natively (no 4x4 bleed) —
        # the anchor-upsampled seasw above is the fallback for dumps
        # without the monthly planes
        nwet_hi = (z["d_river_width_monthly"] > 0).sum(axis=0)
        hi["seasw"] = ((nwet_hi > 0) & (nwet_hi < 12) & land) \
            .astype(np.float64) * (12 - nwet_hi) / 12.0
    hi["ocean"] = ocean.astype(np.float64)
    hi["lake"] = lake.astype(np.float64)
    hi["river"] = river.astype(np.float64)
    hi["land"] = land.astype(np.float64)
    hi["biome"] = biome
    hi["reef"] = reef
    ventf, vent_core, seep_ring = _vent_fields(
        e["vent_pts"], ocean.shape, seed, cells_per=factor)
    hi["ventf"], hi["vent_core"], hi["seep_ring"] = ventf, vent_core, \
        seep_ring
    return hi


def _class_bias(i: int, biome: np.ndarray,
                sup_mask: np.ndarray) -> np.ndarray | None:
    """The (H,W) multiplicative bias for one class, or None when the class
    has no opinion (bias == 1 everywhere) so the caller can skip the
    multiply. Same logic as the anchor _biome_bias, one slice at a time."""
    name = GROUND_CLASSES[i]["name"]
    has_bias = name in _BIAS
    is_biotic = i in _BIOTIC_SOILS_SET
    if not has_bias and not is_biotic:
        return None
    bias = np.ones(biome.shape, np.float64)
    if has_bias:
        for bname, mult in _BIAS[name].items():
            bias[biome == BIOME_ID[bname]] = mult
    if is_biotic:
        bias[sup_mask] = _SUPPRESS_FACTOR
    return bias


def _classify(e: dict) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pointwise classification at whatever resolution `e` is gridded to.
    STREAMS the 42 classes one plane at a time, keeping a running top-3
    (ids + weights) and dominant — never materializes all 42 planes (that
    would be ~170 MB at delivery res). Returns (class_id, mix_ids, mix_w)."""
    H, W = e["land"].shape
    biome = e["biome"]
    sup_mask = np.isin(biome, [BIOME_ID[b] for b in _SUPPRESS_BIOMES])
    top_w = np.zeros((3, H, W), np.float64)      # sorted descending
    top_id = np.zeros((3, H, W), np.uint8)
    for i, c in enumerate(GROUND_CLASSES):
        w = _class_weight(c["name"], e)
        bias = _class_bias(i, biome, sup_mask)
        if bias is not None:
            w = w * bias
        w = np.clip(w, 0.0, 1.0)
        # insert this class into the per-cell top-3 by direct comparison.
        # STRICT > so a tie keeps the earlier (lower-id) class ahead — the
        # same low-tie-break as argmax, so top_id[0] == class_id always.
        a, b, d = top_w[0], top_w[1], top_w[2]
        ia, ib, ic = top_id[0], top_id[1], top_id[2]
        m0 = w > a
        m1 = (~m0) & (w > b)
        m2 = (~m0) & (~m1) & (w > d)
        n0 = np.where(m0, w, a)
        n1 = np.where(m0, a, np.where(m1, w, b))
        n2 = np.where(m0, b, np.where(m1, b, np.where(m2, w, d)))
        j0 = np.where(m0, i, ia)
        j1 = np.where(m0, ia, np.where(m1, i, ib))
        j2 = np.where(m0, ib, np.where(m1, ib, np.where(m2, i, ic)))
        top_w[0], top_w[1], top_w[2] = n0, n1, n2
        top_id[0], top_id[1], top_id[2] = j0, j1, j2
    # at TAU=1 the renormalized top-3 softmax shares ARE the renormalized
    # generator weights (matches the anchor mix_w exactly)
    mix_w = top_w / top_w.sum(axis=0, keepdims=True)
    return (top_id[0].astype(np.uint8), top_id.astype(np.uint8),
            mix_w.astype(np.float32))


def build_ground_hires(z, manifest: dict, sea: float,
                       vent_pts: list[dict], factor: int = 4) -> dict:
    """The delivery-res ground map: class_id (H*f, W*f uint8) and top-3
    mix_ids/mix_w, re-derived pointwise from upsampled evidence + delivered
    categorical fields (no 4x4 blocks). No full d2 here — consumers read
    the anchor-res d2."""
    seed = int(manifest.get("seed", 0))
    e = _evidence(z, sea, vent_pts, seed)
    e_hi = _upsample_evidence(e, z, factor, seed)
    class_id, mix_ids, mix_w = _classify(e_hi)
    return dict(class_id=class_id, mix_ids=mix_ids, mix_w=mix_w)
