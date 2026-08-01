"""K14 P6 tests — substrate ("ground") classification (B3) over the K11
seed-1 dump, plus synthetic z dicts for the per-genesis unit rules.

Run: uv run pytest -q exp/k14_worldprod/
"""

from __future__ import annotations

import json
import struct

import numpy as np
import pytest

from exp.artifacts import find as artifact_find
from exp.k11_worldgen.units import DEPTH_MAX_M, ELEV_MAX_M
from exp.k14_worldprod import derived, ground
from exp.k14_worldprod.ground import GROUND_ID, N_CLASSES

SEED = 1
SEA = 0.35                      # synthetic sea level (matches the k11 dump)

pytestmark = pytest.mark.skipif(
    artifact_find("k11", SEED) is None, reason="no local k11 seed-1 dump")


@pytest.fixture(scope="module")
def inputs():
    z, manifest, _ = derived.load_inputs(SEED)
    return z, manifest


@pytest.fixture(scope="module")
def gr(inputs):
    z, manifest = inputs
    sea = float(manifest["sea_level"])
    _, vp, sp = derived.vents(z, manifest)
    return ground.build_ground(z, manifest, sea, vp + sp)


@pytest.fixture(scope="module")
def hires(inputs):
    z, manifest = inputs
    sea = float(manifest["sea_level"])
    _, vp, sp = derived.vents(z, manifest)
    return ground.build_ground_hires(z, manifest, sea, vp + sp, 4)


@pytest.fixture(scope="module")
def result():
    return derived.build(SEED)


# ── synthetic worlds ────────────────────────────────────────────────────


def _above(sea: float, m: float) -> float:
    """Normalized w_elev for `m` meters ABOVE sea level."""
    return sea + m / ELEV_MAX_M * (1.0 - sea)


def _below(sea: float, m: float) -> float:
    """Normalized w_elev for `m` meters BELOW sea level."""
    return sea - m / DEPTH_MAX_M * sea


def _ground_z(H: int = 8, W: int = 8) -> dict:
    """A flat, humid, temperate, all-land 8x8 world at 100 m — the neutral
    background the genesis tests perturb one cell of."""
    z: dict = {
        "h_ocean_mask": np.zeros((H, W), bool),
        "h_sea_mask": np.zeros((H, W), bool),
        "h_lake_mask": np.zeros((H, W), bool),
        "h_river_mask": np.zeros((H, W), bool),
        "h_river_speed": np.zeros((H, W)),
        "h_discharge": np.zeros((H, W)),
        "h_accumulation": np.full((H, W), 100.0),
        "h_hand": np.full((H, W), 2.0 * (1.0 - SEA) / ELEV_MAX_M),  # 2 m
        "w_elev": np.full((H, W), _above(SEA, 100.0)),
        "c_P_monthly": np.full((12, H, W), 0.3),      # 1440 mm/yr -> humid
        "c_T": np.full((H, W), (20.0 + 30.0) / 65.0),  # 20 C
        "h_glacier_mask": np.zeros((H, W), bool),
        "h_glacier_flux": np.zeros((H, W)),
        "h_flow_dir": np.full((H, W), 6, np.int8),  # D8 6 = south (1,0):
                                                    # bottom-row cells
                                                    # route off-grid =
                                                    # drainage termini
        "h_salinity": np.zeros((H, W)),
        "r_u": np.zeros((H, W)),
        "r_v": np.zeros((H, W)),
        "w_biome_map": np.full((H, W), 3, np.uint8),   # temperate broadleaf
        "w_aquatic": np.zeros((H, W), np.uint8),
    }
    return z


def _build(z: dict, vent_pts: list[dict] | None = None) -> dict:
    return ground.build_ground(z, {}, SEA, vent_pts or [])


def _w(g: dict) -> np.ndarray:
    """Recover generator weights from d2 (w = exp(-d2); the 1e-6 floor maps
    back to 1e-6)."""
    return np.exp(-g["d2"].astype(np.float64))


# ── determinism / shape ─────────────────────────────────────────────────


def test_deterministic(gr, inputs):
    z, manifest = inputs
    sea = float(manifest["sea_level"])
    _, vp, sp = derived.vents(z, manifest)
    again = ground.build_ground(z, manifest, sea, vp + sp)
    for key in ("d2", "class_id", "mix_ids", "mix_w"):
        assert np.array_equal(gr[key], again[key]), key
    assert gr["meta"] == again["meta"]


def test_shapes_dtypes_finite(gr):
    H, W = gr["class_id"].shape
    assert gr["d2"].shape == (N_CLASSES, H, W)
    assert gr["d2"].dtype == np.float32
    assert np.isfinite(gr["d2"]).all()
    assert gr["class_id"].dtype == np.uint8
    assert gr["class_id"].min() >= 0 and gr["class_id"].max() < N_CLASSES
    assert gr["mix_ids"].shape == (3, H, W)
    assert gr["mix_ids"].dtype == np.uint8
    assert gr["mix_w"].shape == (3, H, W)
    assert gr["mix_w"].dtype == np.float32
    # top-3 shares renormalize to 1 per cell
    assert np.allclose(gr["mix_w"].sum(axis=0), 1.0, atol=1e-4)
    # the dominant class is the first mix entry
    assert (gr["mix_ids"][0] == gr["class_id"]).all()
    assert len(gr["meta"]) == N_CLASSES


def test_meta_schema(gr):
    for i, c in enumerate(gr["meta"]):
        assert set(c) >= {"name", "color", "hard", "loose", "retention",
                          "rooting_m", "sal_add", "nutrient", "genesis"}
        assert GROUND_ID[c["name"]] == i
        assert len(c["color"]) == 3
        assert isinstance(c["hard"], bool) and isinstance(c["loose"], bool)
    # underwater rows carry sal_add None (= the water's salinity)
    assert gr["meta"][GROUND_ID["abyssal clay"]]["sal_add"] is None
    assert gr["meta"][GROUND_ID["mollisol"]]["sal_add"] == 0.0


# ── genesis rules on synthetic cells ────────────────────────────────────


def test_glacier_cell_till_or_outwash():
    z = _ground_z()
    z["h_glacier_mask"][2, 2] = True
    z["h_glacier_flux"][2, 2] = 5000.0
    z["c_T"][2, 2] = (-5.0 + 30.0) / 65.0            # cold -> soils off
    g = _build(z)
    assert g["class_id"][2, 2] in (GROUND_ID["till"],
                                   GROUND_ID["outwash gravel"])


def test_most_arid_cell_dune_family():
    """Hyperarid TERMINUS cell keeps dune (owner ruling 2026-08-01): the
    supply term opens only at true drainage termini — the fixture's
    flow_dir runs every cell south, so the bottom row routes off-grid.
    With the band fully open (arid ~1) and a saturated terminus supply,
    dune beats the sand sheet; a non-terminus cell with the same
    accumulation would fall back to the deflation self-gate."""
    z = _ground_z()
    z["c_P_monthly"][:, 7, 3] = 0.001                # ~arid = 1
    z["h_accumulation"][7, 3] = 2000.0               # sand supply
    g = _build(z)
    assert g["class_id"][7, 3] in (GROUND_ID["dune sand"],
                                   GROUND_ID["sand sheet"],
                                   GROUND_ID["reg / desert pavement"])
    # the dune gate: with supply, dune sand beats the sand sheet
    w = _w(g)
    assert w[GROUND_ID["dune sand"], 7, 3] > w[GROUND_ID["sand sheet"], 7, 3]


def test_subhumid_terminus_cell_not_dune():
    """Dune is the MOST-ARID fraction of arid cells — a hard band, not
    the smooth arid² (owner ruling 2026-08-01): at 600 mm/yr the old gate
    read arid² = 0.36 and the supply term saturated on acc >= 10, so
    subhumid dune outvoted mollisol. The band zeroes the same cell even
    at a saturated terminus supply."""
    z = _ground_z()
    z["c_P_monthly"][:, 7, 4] = 600.0 / 12.0         # 600 mm/yr subhumid
    z["h_accumulation"][7, 4] = 2000.0               # saturated supply
    g = _build(z)
    w = _w(g)
    assert w[GROUND_ID["dune sand"], 7, 4] < 1e-4    # band zeroes it
    assert g["class_id"][7, 4] != GROUND_ID["dune sand"]


def test_glacier_cell_no_dune():
    """Cold/glacier tails (owner ruling 2026-08-01): (1-cold) and (1-glac)
    zero the dune gate on frozen ground — 48 seed-1 dune cells sat ON the
    glacier mask at t -6..-9 C before the ruling. A frozen terminus cell
    with a saturated supply reads ~0 dune; till wins the cell (the
    test_glacier_cell_till_or_outwash family)."""
    z = _ground_z()
    z["c_P_monthly"][:, 7, 5] = 200.0 / 12.0         # cold desert ~arid 0.87
    z["c_T"][7, 5] = (-8.0 + 30.0) / 65.0            # frozen
    z["h_glacier_mask"][7, 5] = True
    z["h_glacier_flux"][7, 5] = 5000.0
    z["h_accumulation"][7, 5] = 2000.0               # saturated supply
    g = _build(z)
    w = _w(g)
    assert w[GROUND_ID["dune sand"], 7, 5] < 1e-4
    assert g["class_id"][7, 5] == GROUND_ID["till"]


def test_sand_sheet_cold_gate_cold_cell_reads_reg():
    """Cold gate (owner ruling 2026-08-01): real cold deserts are
    reg/pavement, not sand seas — the sheet's pure-precipitation arid
    rule read a ~200 mm/yr / 5 C cold cell as sand sea. Below ~5 C
    annual (warm = 0, the cold-desert band) the sheet docks to its 0.15
    floor, so the cold-arid cell falls through to reg (which keeps its
    symmetric cold-desert bias); the identical cell at 20 C keeps its
    sand sheet. Mirrors the bog (cold-gated) / fen (warm-gated) pair."""
    from exp.k11_worldgen.biomes import BIOME_ID

    def arid_cell(biome, temp_c):
        z = _ground_z()
        z["c_P_monthly"][:, 4, 4] = 200.0 / 400.0 / 12.0   # 200 mm/yr
        z["c_T"][4, 4] = (temp_c + 30.0) / 65.0
        # no dune supply (acc=0) and no deflation field (wet=1): dune_dep
        # reads 0, so the sheet-vs-reg cold gate is isolated — interior
        # fixture cells are not drainage termini either (flow_dir runs
        # every cell south; only the bottom row routes off-grid)
        z["h_accumulation"][4, 4] = 0.0
        z["h_hand"][4, 4] = 0.0
        z["w_biome_map"][:] = biome
        return _build(z)

    sheet = GROUND_ID["sand sheet"]
    reg = GROUND_ID["reg / desert pavement"]
    cold = arid_cell(BIOME_ID["desert xeric (cold)"], 5.0)
    w = _w(cold)
    assert cold["class_id"][4, 4] == reg          # reg inherits cold-arid
    assert w[sheet, 4, 4] < w[reg, 4, 4]
    assert 0.05 < w[sheet, 4, 4] < 0.2            # strongly docked, not zero
    hot = arid_cell(BIOME_ID["desert xeric (hot)"], 20.0)
    assert hot["class_id"][4, 4] == sheet          # hot-arid unchanged


def test_sand_sheet_cold_gate_cold_grassland_to_reg():
    """The owner's exact case: a ~200 mm/yr / 5 C TEMPERATE GRASSLAND
    (no desert biome anywhere) previously read sand sheet — arid^1.5 =
    0.81 beat reg ~0.73 and mollisol ~0.63 on the flat cell. With the
    gate the cold grassland reads reg, mollisol staying the soil
    competitor."""
    from exp.k11_worldgen.biomes import BIOME_ID
    z = _ground_z()
    z["c_P_monthly"][:, 4, 4] = 200.0 / 400.0 / 12.0
    z["c_T"][4, 4] = (5.0 + 30.0) / 65.0
    z["h_accumulation"][4, 4] = 0.0                 # no dune supply
    z["h_hand"][4, 4] = 0.0                         # no deflation field
    z["w_biome_map"][:] = BIOME_ID["temperate grassland"]
    g = _build(z)
    w = _w(g)
    sheet = GROUND_ID["sand sheet"]
    reg = GROUND_ID["reg / desert pavement"]
    moll = GROUND_ID["mollisol"]
    assert g["class_id"][4, 4] == reg
    assert w[sheet, 4, 4] < w[reg, 4, 4]
    assert w[sheet, 4, 4] < w[moll, 4, 4]


def test_steep_forest_cell_scree_override():
    z = _ground_z()                                  # temperate broadleaf
    z["w_elev"][4, 4] = _above(SEA, 740.0)           # 640 m over one cell
    g = _build(z)                                    # slope = 640/800 = 0.8
    w = _w(g)
    # the slope override beats the forest's own (x3-biased) brown earth
    assert g["class_id"][4, 4] == GROUND_ID["scree"]
    assert w[GROUND_ID["scree"], 4, 4] > w[GROUND_ID["brown earth"], 4, 4]


def test_deep_quiet_ocean_abyssal():
    z = _ground_z()
    z["h_ocean_mask"][:, 6:] = True
    z["w_elev"][:, 6:] = _below(SEA, 5000.0)         # depthn = 1
    z["w_biome_map"][:, 6:] = 17
    g = _build(z)
    assert g["class_id"][2, 6] in (GROUND_ID["abyssal clay"],
                                   GROUND_ID["marine mud"])
    assert g["class_id"][2, 6] == GROUND_ID["abyssal clay"]


def test_land_vent_cell_andisol():
    z = _ground_z()
    z["c_T"][2, 2] = (-5.0 + 30.0) / 65.0            # cold -> brown earth off
    pts = [{"y": 2, "x": 2, "activity": 1.0}]
    g = _build(z, pts)
    # the andisol halo sits on every vent, dormant or active; on flat land
    # it outvotes the crater-bowl lava even when the vent IS active
    assert g["class_id"][2, 2] == GROUND_ID["andisol"]


def test_ocean_vent_core_and_cold_seep_ring():
    H, W = 12, 12
    z = _ground_z(H, W)
    z["h_ocean_mask"][:] = True
    z["w_elev"][:] = _below(SEA, 5000.0)             # deep everywhere
    z["w_biome_map"][:] = 17
    pts = [{"y": 5, "x": 5, "activity": 1.0}]
    g = _build(z, pts)
    # dormancy is a K1 roll on manifest seed ({} -> 0): active vents carry
    # vent crust in the crater-bowl disk, dormant ones weather to clay
    active = ground._vent_active(pts, 0)[0]
    assert g["class_id"][5, 5] == (GROUND_ID["vent crust"] if active
                                   else GROUND_ID["abyssal clay"])
    assert g["class_id"][5, 7] == GROUND_ID["cold seep"]   # seep annulus


def test_submarine_vent_depth_split_pillow_vs_crust():
    """Shallow submarine active bowls quench to pillow basalt; deep
    (abyssal) bowls grow the sulfide cap and read vent crust. (Manifest
    seed 0 leaves the single vent active.)"""
    pts = [{"y": 5, "x": 5, "activity": 1.0}]
    assert ground._vent_active(pts, 0)[0]            # fixture precondition
    z = _ground_z(12, 12)
    z["h_ocean_mask"][:] = True
    z["w_biome_map"][:] = 17
    z["w_elev"][:] = _below(SEA, 500.0)              # shelf depth
    g = _build(z, pts)
    assert g["class_id"][5, 5] == GROUND_ID["pillow basalt"]
    z["w_elev"][:] = _below(SEA, 5000.0)             # abyssal
    g = _build(z, pts)
    assert g["class_id"][5, 5] == GROUND_ID["vent crust"]


def test_cold_seep_gated_off_shallow_shelf():
    """The vent-ring seep component is gated off on shallow shelves
    (<~200 m, no hydrate stability there): even right inside a vent's
    annulus, a 100 m shelf cell carries ~0 cold-seep evidence and keeps
    its marine mud."""
    z = _ground_z(12, 12)
    z["h_ocean_mask"][:] = True
    z["w_biome_map"][:] = 17
    z["w_elev"][:] = _below(SEA, 100.0)              # shallow shelf
    pts = [{"y": 5, "x": 5, "activity": 1.0}]
    g = _build(z, pts)
    w = _w(g)
    assert w[GROUND_ID["cold seep"], 5, 7] < 1e-4    # ring cell, gated
    assert g["class_id"][5, 7] == GROUND_ID["marine mud"]


def test_passive_margin_cold_seep_wins():
    """Vent-independent passive-margin seep: a sedimented slope cell in
    the hydrate band (300-3000 m) with NO vent nearby reads cold seep —
    and the same cell without sediment keeps its marine mud (passive
    seeps do not blanket every slope)."""
    z = _ground_z(12, 12)
    z["h_ocean_mask"][:] = True
    z["w_biome_map"][:] = 17
    z["w_elev"][:] = _below(SEA, 800.0)              # mid hydrate band
    z["w_elev"][4, 5] = SEA                          # 800 m scarp -> slope 1
    z["h_accumulation"][:] = 2000.0                  # sediment-rich bed
    z["h_hand"][:] = 0.0                             # saturated -> dep = 1
    g = _build(z)                                    # no vent points
    w = _w(g)
    assert g["class_id"][5, 5] == GROUND_ID["cold seep"]
    assert (w[GROUND_ID["cold seep"], 5, 5]
            > w[GROUND_ID["marine mud"], 5, 5])
    z["h_accumulation"][:] = 100.0                   # starve the sediment
    g2 = _build(z)
    assert g2["class_id"][5, 5] == GROUND_ID["marine mud"]


def test_river_speed_sorts_gravel_vs_sand():
    z = _ground_z()
    z["h_river_mask"][2, 2] = True
    z["h_river_speed"][2, 2] = 3.0                   # fast -> gravel
    z["h_river_mask"][3, 3] = True
    z["h_river_speed"][3, 3] = 0.2                   # slow -> sand
    g = _build(z)
    assert g["class_id"][2, 2] == GROUND_ID["river gravel bed"]
    assert g["class_id"][3, 3] == GROUND_ID["river sand bed"]


def test_seasonal_wash_keeps_its_river_bed():
    """A land cell carrying water in SOME months only (a seasonal
    channel below the L0 cutoff in its dry months) still reads as a
    flow-sorted river bed — a wadi is not the surrounding soil. Speed
    is unknown off the annual network (rs=0), so the bed defaults to
    sand; a permanently dry control cell keeps its soil. (Biome set to
    tundra so no ×3 biome bias caps a soil class and hides the rule.)"""
    from exp.k11_worldgen.biomes import BIOME_ID
    z = _ground_z()
    z["w_biome_map"][:] = BIOME_ID["tundra"]
    rwm = np.zeros((12, 8, 8), np.int8)
    rwm[:3, 2, 2] = 1                                # wet 3 months at (2,2)
    z["h_river_width_monthly"] = rwm
    g = _build(z)
    assert g["class_id"][2, 2] == GROUND_ID["river sand bed"]
    assert g["class_id"][4, 4] not in (GROUND_ID["river sand bed"],
                                       GROUND_ID["river gravel bed"])
    # dry-fraction weighting: an 11-month channel is nearly a river —
    # the bed weight scales with the dry share of the year
    w = _w(g)
    rwm2 = np.zeros((12, 8, 8), np.int8)
    rwm2[:11, 2, 2] = 1
    z["h_river_width_monthly"] = rwm2
    g2 = _build(z)
    w2 = np.exp(-g2["d2"].astype(np.float64))
    assert (w[GROUND_ID["river sand bed"], 2, 2]
            > w2[GROUND_ID["river sand bed"], 2, 2])


def test_flood_pulse_builds_alluvium():
    """A river with a strong seasonal discharge swing (snowmelt /
    monsoon / flash) builds a fluvisol floodplain on its low-HAND
    banks even where the mean deposition signal is modest. (Tundra
    biome again: no bias cap.)"""
    from exp.k11_worldgen.biomes import BIOME_ID
    z = _ground_z()
    z["w_biome_map"][:] = BIOME_ID["tundra"]
    z["h_river_mask"][4, 4] = True
    rwm = np.zeros((12, 8, 8), np.int8)
    rwm[:, 4, 4] = 1                                 # permanent channel
    dis = np.zeros((12, 8, 8))
    dis[:3, 4, 4] = 200.0                            # 3-month flood pulse
    z["h_river_width_monthly"] = rwm
    z["h_discharge_monthly"] = dis
    g = _build(z)
    # the low-HAND neighbor (2 m everywhere -> wet ground) is alluvium
    assert g["class_id"][4, 5] == GROUND_ID["alluvium"]
    # two rings out the pulse still reaches, then dies
    w = _w(g)
    assert w[GROUND_ID["alluvium"], 4, 6] > 0.3
    assert w[GROUND_ID["alluvium"], 0, 0] < 0.05


def test_lake_littoral_bleed():
    """Underwater littoral gradient: sandy on gentle winnowed shores,
    rocky on steep beds, lake mud only in the deep center — and the
    shore LAND keeps its own soil (treeline-to-lake)."""
    z = _ground_z()
    z["h_lake_mask"][3:6, 3:6] = True                # 3x3 lake, 8x8 world
    g = _build(z)
    # gentle, low-deposition shore ring reads coastal sand, not uniform mud
    assert g["class_id"][3, 3] == GROUND_ID["coastal sand"]
    # the deep center (no land neighbor) stays lake mud
    assert g["class_id"][4, 4] == GROUND_ID["lake mud"]
    # the land next to the lake keeps its terrestrial soil
    assert g["class_id"][2, 3] not in (GROUND_ID["lake mud"],
                                       GROUND_ID["coastal sand"],
                                       GROUND_ID["rocky bottom"])
    # steep lake bed -> rocky littoral
    z2 = _ground_z()
    z2["h_lake_mask"][3:6, 3:6] = True
    z2["w_elev"][2, 3] = _above(SEA, 800.0)          # 700 m shore cliff
    g2 = _build(z2)
    assert g2["class_id"][3, 3] == GROUND_ID["rocky bottom"]


def test_cliff_coast_coastal_sand_docked():
    """Littoral slope dock (owner ruling 2026-08-01): the OCEAN term now
    docks (1-slope)^2, so cliff coasts (slope > 0.3, a 24% grade) fall
    toward scree while gentle beaches keep their coastal sand. The
    LAKE-shore ring keeps the old (1-slope) — untouched owner decision."""
    from exp.k11_worldgen.biomes import BIOME_ID
    z = _ground_z()
    z["h_ocean_mask"][:, 7] = True                   # ocean on the east
    z["w_biome_map"][:, :7] = BIOME_ID["tundra"]     # no x3 soil bias cap
    z["w_elev"][5, 6] = _above(SEA, 180.0)           # 80 m over a cell ->
                                                    # slope 0.1: a gentle
                                                    # beach (above the
                                                    # tidal-flat <0.05 band)
    z["w_elev"][3, 6] = _above(SEA, 740.0)           # 640 m cliff -> slope .8
    g = _build(z)
    w = _w(g)
    coast = GROUND_ID["coastal sand"]
    # the beach cell keeps coastal sand; the cliff cell reads scree and
    # its coastal-sand weight is docked hard below the beach's
    assert g["class_id"][5, 6] == coast
    assert g["class_id"][3, 6] == GROUND_ID["scree"]
    assert w[coast, 3, 6] < 0.5 * w[coast, 5, 6]


# ── biome bias: a bias, never a binding ─────────────────────────────────


def test_biome_bias_lifts_without_binding():
    z = _ground_z()
    # identical physicals, two biomes
    z["w_biome_map"][2, 2] = 7                       # temperate grassland
    z["w_biome_map"][2, 3] = 12                      # desert xeric (hot)
    z["c_P_monthly"][:, 2, 2] = 0.15625              # arid = 0.5 (both)
    z["c_P_monthly"][:, 2, 3] = 0.15625
    g = _build(z)
    w = _w(g)
    mol = w[GROUND_ID["mollisol"]]
    assert mol[2, 2] > mol[2, 3]                     # grassland lifts it
    assert mol[2, 2] < 0.99                          # ...but does not bind to 1


# ── land / water separation ─────────────────────────────────────────────


def test_marine_zero_on_land_and_soils_zero_on_ocean(gr, inputs):
    z, _ = inputs
    w = _w(gr)
    ocean = z["h_ocean_mask"] | z["h_sea_mask"]
    land = ~ocean & ~z["h_lake_mask"] & ~z["h_river_mask"]
    marine = list(ground._MARINE)                # marine mud..pillow basalt
    # marine classes carry `ocean`: exactly ~floor on land
    assert w[marine][:, land].max() < 1e-4
    # terrestrial soils carry `land`: exactly ~floor on the ocean
    assert w[list(ground._TERRESTRIAL)][:, ocean].max() < 1e-4


# ── delivery-res re-derivation (de-blocking) ────────────────────────────


def test_hires_shapes_and_finite(hires):
    assert hires["class_id"].shape == (1024, 1024)
    assert hires["class_id"].dtype == np.uint8
    assert hires["class_id"].max() < N_CLASSES
    assert hires["mix_ids"].shape == (3, 1024, 1024)
    assert hires["mix_w"].shape == (3, 1024, 1024)
    assert not np.isnan(hires["mix_w"]).any()
    assert np.allclose(hires["mix_w"].sum(axis=0), 1.0, atol=1e-4)
    assert (hires["mix_ids"][0] == hires["class_id"]).all()


def test_hires_deterministic(inputs):
    z, manifest = inputs
    sea = float(manifest["sea_level"])
    _, vp, sp = derived.vents(z, manifest)
    again = ground.build_ground_hires(z, manifest, sea, vp + sp, 4)
    first = ground.build_ground_hires(z, manifest, sea, vp + sp, 4)
    for key in ("class_id", "mix_ids", "mix_w"):
        assert np.array_equal(first[key], again[key]), key


def test_hires_not_block_aligned(hires):
    """The re-derived map is NOT a kron stamp: a stamp can only change
    class at columns divisible by the factor, so any mid-block transition
    proves the edges were re-derived at delivery res (ragged-edge style
    from test_worldgen.py::test_glacier_extent_hires_tapers_edges)."""
    factor = 4
    cid = hires["class_id"]
    ragged_rows = 0
    for row in cid:
        cols = np.flatnonzero(np.diff(row.astype(np.int16)) != 0) + 1
        if len(cols) and np.any(cols % factor):
            ragged_rows += 1
    assert ragged_rows > cid.shape[0] // 2


def test_hires_histogram_consistent_with_anchor(gr, hires):
    """Sharpening, not re-classifying: the delivery-res dominant histogram
    keeps the same top classes, each within ~20% of its anchor area. Top-3
    sets must match exactly (the marine duo + top soil are far apart);
    ranks 4/5 are allowed to swap — the #4/#5/#6 classes sit within
    ~0.1-0.3pp of each other, so the delivered-res biome map legitimately
    reorders them (reg and till swapped across resolutions after the
    sand-sheet arid² change). The area tolerance is 20% rather than 15%
    because mollisol — the most biome-biased of the top classes — picks
    up ~0.6pp where the delivered-res biome map draws slightly more
    temperate grassland than the anchor map; every other top class sits
    under 10%."""
    def fracs(cid):
        u, c = np.unique(cid.ravel(), return_counts=True)
        return {int(k): v / cid.size for k, v in zip(u, c)}
    fa, fh = fracs(gr["class_id"]), fracs(hires["class_id"])
    top_a = sorted(fa, key=fa.get, reverse=True)[:5]
    top_h = sorted(fh, key=fh.get, reverse=True)[:5]
    assert set(top_a[:3]) == set(top_h[:3]), (top_a, top_h)
    for k in set(top_a) | set(top_h):
        rel = abs(fh.get(k, 0) - fa.get(k, 0)) / fa.get(k, 1e-12)
        assert rel < 0.20, (ground.GROUND_CLASSES[k]["name"], fa.get(k),
                            fh.get(k))


# ── reachability audit ──────────────────────────────────────────────────


def test_every_class_reachable_on_seed1(gr):
    """Every one of the 42 classes has w>0 somewhere on the seed-1 world.
    As of writing NONE need a synthetic fallback; if a future knob change
    strands a class, add a synthetic cell here rather than weakening the
    assertion."""
    w = _w(gr)
    unreachable = [ground.GROUND_CLASSES[i]["name"] for i in range(N_CLASSES)
                   if not (w[i] > 1e-5).any()]
    assert unreachable == [], f"unreachable classes: {unreachable}"


# ── datapack: categorical layer round-trips ─────────────────────────────


def _read_pack(path):
    raw = path.read_bytes()
    assert raw[:4] == b"K11P"
    hlen = struct.unpack("<I", raw[4:8])[0]
    header = json.loads(raw[8:8 + hlen])
    dt_size = {"u1": 1, "<u2": 2}
    shapes: dict[str, tuple] = {}
    for layer in header["layers"]:
        if layer.get("field"):
            shapes[layer["field"]] = (layer["shape"], layer["dtype"])
        for key in ("mix_ids", "mix_w"):
            if key in layer:
                shapes[layer[key]["field"]] = (layer[key]["shape"],
                                               layer[key]["dtype"])
    arrays: dict[str, np.ndarray] = {}
    off = 8 + hlen
    for name in header["order"]:
        shape, dt = shapes[name]
        n = int(np.prod(shape))
        sz = dt_size[dt]
        np_dt = np.uint8 if dt == "u1" else "<u2"
        arrays[name] = np.frombuffer(raw[off:off + n * sz],
                                     dtype=np_dt).reshape(shape)
        off += n * sz
    assert off == len(raw)                    # no trailing/underrun bytes
    return header, arrays


def test_pack_categorical_layer(result, tmp_path):
    from exp.k14_worldprod.datapack import build_pack
    path = build_pack(result, tmp_path / "derived.k11pack")
    header, arrays = _read_pack(path)

    kinds = {l["id"]: l["kind"] for l in header["layers"]}
    assert kinds["ground"] == "categorical"
    # older continuous layers are untouched
    assert kinds["terr_prod"] == "continuous"
    assert kinds["marine_prod"] == "continuous"

    gl = next(l for l in header["layers"] if l["id"] == "ground")
    assert gl["scope"] == "all"
    assert len(gl["classes"]) == N_CLASSES
    assert gl["classes"][0]["name"] == "dune sand"
    # palette travels in classes AND as a flat colormap for the current
    # categorical renderer (colormap[String(v)])
    assert set(gl["colormap"]) == {str(i) for i in range(N_CLASSES)}
    assert gl["colormap"]["0"] == gl["classes"][0]["color"]
    # mix planes ride along on the layer
    assert gl["mix_ids"]["shape"] == [3, 1024, 1024]
    assert gl["mix_w"]["shape"] == [3, 1024, 1024]

    # the dominant-class array round-trips exactly (nearest, categorical)
    assert arrays["ground_class"].shape == (1024, 1024)
    assert np.array_equal(arrays["ground_class"],
                          result["products"]["ground_class"])
    # mix_w quantized to weights*255
    assert arrays["ground_mix_w"].max() <= 255
    assert np.allclose(arrays["ground_mix_w"].reshape(3, -1).sum(axis=0),
                       255, atol=2)


# ── pH rows + mix-derived field ─────────────────────────────────────────

def test_class_ph_rows_defensible_orderings():
    ph = {c["name"]: c["ph"] for c in ground.GROUND_CLASSES}
    assert len(ph) == N_CLASSES
    for name, v in ph.items():
        assert 3.5 <= v <= 9.5, name
    # the ORDERINGS are the defensible content (floats are draft knobs)
    assert ph["bog"] < ph["fen"]                     # rain-fed < gw-fed peat
    assert ph["podzol"] < ph["brown earth"]          # taiga < temperate
    assert ph["laterite cuirasse"] < ph["rendzina"]  # leached < limestone
    assert ph["solonchak"] < ph["solonetz"]          # saline < sodic
    assert ph["vent crust"] < 6.0                    # hydrothermal acidity
    assert 7.5 <= ph["marine mud"] <= 8.5            # seawater-buffered


def test_meta_carries_ph(gr):
    for row in gr["meta"]:
        assert 3.5 <= row["ph"] <= 9.5, row["name"]


def test_mix_ph_weighted_mean():
    ids = np.array([[[GROUND_ID["podzol"]]],
                    [[GROUND_ID["caliche"]]],
                    [[GROUND_ID["dune sand"]]]], dtype=np.uint8)
    w = np.array([[[0.5]], [[0.25]], [[0.25]]], dtype=np.float32)
    got = ground.mix_ph(ids, w)
    assert got.shape == (1, 1)
    assert got[0, 0] == pytest.approx(
        0.5 * 4.5 + 0.25 * 8.2 + 0.25 * 6.5, abs=1e-6)


def test_mix_ph_matches_anchor_mix(gr):
    ph = ground.mix_ph(gr["mix_ids"], gr["mix_w"])
    assert ph.shape == gr["class_id"].shape
    # bounded by the class-table extremes everywhere
    lo = min(c["ph"] for c in ground.GROUND_CLASSES)
    hi = max(c["ph"] for c in ground.GROUND_CLASSES)
    assert ph.min() >= lo - 1e-6 and ph.max() <= hi + 1e-6
