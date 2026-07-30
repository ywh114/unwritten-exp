"""K11 demo CLI: `uv run python -m exp.k11_worldgen demo --seed 1 [--json]`.

Generates one 256x256 L0 world (plates -> elevation -> hydrology ->
climate -> biomes -> complex -> scatter), renders the PNG set into
exp/k11_worldgen/out/, and runs structural checks. Exit 0 iff all pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

from kernel.hashrng import Stream
from kernel.complex.audit import audit

from exp.k11_worldgen.biomes import BIOMES, classify_biomes, forest_cover, growing_season_p
from exp.k11_worldgen.climate import build_climate
from exp.k11_worldgen.complexify import derive_complex
from exp.k11_worldgen.deliver import upscale_world
from exp.k11_worldgen.hydrology import build_hydrology
from exp.k11_worldgen.plates import build_elevation
from exp.k11_worldgen.raster import normalize_u8, write_png_gray
from exp.k11_worldgen.render import (
    LoadingSink,
    load_stage_draw,
    render_all,
    render_loading,
    render_monthly,
    render_plates,
    render_world,
)

OUT_DIR = str(Path(__file__).parent / "out")
SHAPE = (256, 256)  # L0 anchor grid: one cell = 4 km (map = 1024×1024 km);
                    # delivery interpolates to 1024² at 1 km cells (deliver.py)
SEA_LEVEL = 0.35
# weather samples per month: the FINAL climate (pass 2) is the world's
# weather pattern — full N. The pass-1 scaffold (its only consumers
# are the conditioning inputs: forest cover, pond/stream balance) runs
# lean.
N_SAMPLES_FINAL = 8
N_SAMPLES_SCAFFOLD = 4


def _compass_from(mu: float, mv: float) -> str:
    """8-point compass name for the direction a (mu, mv) wind vector
    blows FROM (meteorological convention; v is south-positive)."""
    import math
    deg = math.degrees(math.atan2(-mv, -mu)) % 360.0
    return ("E", "SE", "S", "SW", "W", "NW", "N", "NE")[
        int((deg + 22.5) // 45) % 8]


def _step(msg: str) -> None:
    """Progress line for the demo build (each logic pass, as it starts).
    Stderr, so `--json` stdout stays machine-readable."""
    print(f"[k11] {msg}", file=sys.stderr, flush=True)


def build_world(seed: int, shape: tuple[int, int] = SHAPE, sink=None,
                realistic: bool = False, center_lat: float | None = None,
                shrink: float = 6.0) -> dict:
    """Two-pass pipeline (second order, never circular):

    PASS 1 — the full pipeline in honest dependency order: plates ->
    elevation -> carve -> hydrology -> currents -> climate (bare
    ground; forests don't exist yet) -> biomes -> forest cover.

    PASS 2 — a coarse rerun where each stage conditions on the others'
    pass-1 outputs: hydrology sees the pass-1 climate (lush ponds and
    streams), climate reruns with the REAL forest cover from the
    pass-1 biomes and the new water (same K1 stream — same weather
    systems, new surface conditions), then biomes/cover/aquatic/
    complex are re-derived from the conditioned fields. The pass-2
    states are the world; pass 1 is a scaffold.
    """
    stream = Stream(seed, "k11.worldgen")
    _step("plates + elevation")
    elev, plates = build_elevation(stream, shape, sea_level=SEA_LEVEL)
    _step("volcanoes")
    from exp.k11_worldgen.plates import build_volcanoes
    elev, volcanoes = build_volcanoes(stream.child("volcanoes"), plates,
                                      elev, SEA_LEVEL)
    bag = {"plates": plates, "elev": elev, "sea_level": SEA_LEVEL}
    if sink is not None:
        sink.write(1, load_stage_draw(1, bag))
        sink.write(2, load_stage_draw(2, bag))
    # ocean = below-sea cells CONNECTED to the border; enclosed
    # below-sea basins are land (lake beds or dry depressions)
    from exp.k11_worldgen.hydrology import carve_gorges, connected_ocean
    ocean_mask = connected_ocean(elev, SEA_LEVEL)
    # antecedent gorges: big rivers notch their spill sills BEFORE
    # hydrology (reflood-notch-reflood); the carved terrain feeds
    # everything downstream (lapse, biomes, render). Ocean
    # connectivity is re-derived after carving.
    _step("gorge carve")
    bag["elev_raw"] = elev
    elev = carve_gorges(elev, ocean_mask)
    ocean_mask = connected_ocean(elev, SEA_LEVEL)
    bag["elev"] = elev
    if sink is not None:
        sink.write(3, load_stage_draw(3, bag))
    _step("hydrology")
    hydro = build_hydrology(elev, ocean_mask, sea_level=SEA_LEVEL, seed=seed)
    bag["hydro"] = hydro
    if sink is not None:
        sink.write(4, load_stage_draw(4, bag))
    # ocean currents after hydrology, as an ABSOLUTE vorticity-seeded
    # feature (pre-wind): the stream-function solve bends the flow
    # around continents; the wind correlation arrives in the
    # conditioning pass (refine_currents, after pass-1 climate)
    from exp.k11_worldgen.currents import build_currents, refine_currents
    _step("currents (vorticity seeds)")
    currents = build_currents(elev, ocean_mask, SEA_LEVEL, seed=seed)
    bag["currents"] = currents
    if sink is not None:
        sink.write(5, load_stage_draw(5, bag))

    _step("pass 1: climate (bare ground)")
    climate1 = build_climate(elev, hydro, SEA_LEVEL, seed=seed,
                             n_samples=N_SAMPLES_SCAFFOLD,
                             realistic=realistic, center_lat=center_lat,
                             shrink=shrink, currents=currents)
    bag["climate"] = climate1
    if sink is not None:
        sink.write(6, load_stage_draw(6, bag))
        sink.write(7, load_stage_draw(7, bag))
    _step("glaciers + glacial terrain (one-shot)")
    # Detect the ice on the pass-1 routing + climate, then let the land
    # respond ONCE (erosion/deposition/ice raise) and re-route the water
    # over the responded terrain. Detection is not repeated afterwards —
    # refine_hydrology receives the state and reuses it (no iteration
    # loop: the climate that made the ice saw the pre-glacial terrain,
    # that second-order feedback is deliberately skipped).
    from exp.k11_worldgen.hydrology import detect_glaciers, glacial_terrain
    gstate = detect_glaciers(hydro, climate1)
    if gstate is not None:
        elev2, g_changed = glacial_terrain(elev, {**hydro, **gstate},
                                           SEA_LEVEL)
        if g_changed:
            elev = elev2
            bag["elev"] = elev
            ocean_prev = ocean_mask
            ocean_mask = connected_ocean(elev, SEA_LEVEL)
            hydro = build_hydrology(elev, ocean_mask, sea_level=SEA_LEVEL,
                                    seed=seed)
            bag["hydro"] = hydro
            if not np.array_equal(ocean_mask, ocean_prev):
                # moraine/outwash changed the coastline — the current
                # solve's boundary moved (same K1 streams, deterministic)
                currents = build_currents(elev, ocean_mask, SEA_LEVEL,
                                          seed=seed)
                bag["currents"] = currents
        # the glacier state travels WITH hydrology from here on —
        # biomes (ice override), refine (melt), persistence all read it
        hydro.update(gstate)
    _step("pass 1: biomes + forest cover")
    biome1, _sim1 = classify_biomes(elev, hydro, climate1, SEA_LEVEL)
    bag["biome_map"] = biome1
    bag["climate1"] = climate1
    bag["biome1"] = biome1
    if sink is not None:
        sink.write(8, load_stage_draw(8, bag))
    cover1 = forest_cover(biome1, growing_season_p(climate1))

    _step("pass 2: currents + wind correlation")
    # the curl of the world's OWN mean annual wind (the delivered
    # weather pattern's mean) joins the vorticity sources — surface
    # currents correlate with the real circulation, and pass-2 climate
    # reads the refined field for SST
    currents = refine_currents(currents, elev, ocean_mask, SEA_LEVEL,
                               climate1)
    bag["currents"] = currents
    if sink is not None:
        sink.write(9, load_stage_draw(9, bag))

    from exp.k11_worldgen.hydrology import flow_accumulation, refine_hydrology
    _step("pass 2: hydrology conditioned on climate")
    bag["hydro1_lake"] = hydro["lake_mask"].copy()
    bag["hydro1_river"] = hydro["river_mask"].copy()
    hydro = refine_hydrology(hydro, elev, climate1, SEA_LEVEL, seed=seed,
                             glacier_state=gstate)
    bag["hydro"] = hydro
    if sink is not None:
        sink.write(10, load_stage_draw(10, bag))
    _step("pass 2: climate (real forests, new water)")
    climate = build_climate(elev, hydro, SEA_LEVEL, seed=seed,
                            realistic=realistic, center_lat=center_lat,
                            shrink=shrink, currents=currents, green=cover1,
                            gain=climate1["gain"])
    bag["climate"] = climate
    if sink is not None:
        sink.write(11, load_stage_draw(11, bag))
        sink.write(12, load_stage_draw(12, bag))
    # discharge: P-weighted accumulation of the FINAL climate (river
    # mouths are ranked by water volume, not just basin cell count)
    hydro["discharge"] = flow_accumulation(
        hydro["w_route"], hydro["flow_dir"], hydro["flat_depth"],
        weight=climate["P"])
    # the final discharge supersedes refine's — refresh the annual speed
    # to match (same K1 stream: the per-cell jitter draw is identical)
    from exp.k11_worldgen.hydrology import river_speed, speed_jitter
    hydro["river_speed"] = river_speed(
        hydro["discharge"], hydro["river_mask"], hydro["w_route"],
        hydro["flow_dir"], SEA_LEVEL,
        speed_jitter(seed, hydro["river_mask"].shape))
    _step("pass 2: biomes + aquatic + complex")
    biome_map, biome_sim = classify_biomes(elev, hydro, climate, SEA_LEVEL)
    bag["biome_map"] = biome_map
    bag["biome_sim"] = biome_sim
    if sink is not None:
        sink.write(13, load_stage_draw(13, bag))
    cover = forest_cover(biome_map, growing_season_p(climate))
    biome_names = [b["name"] for b in BIOMES]
    # THE river network: one month-aware complex — base edges carry
    # per-month width classes, seasonal edges join or float beside
    # them (complexify derives the monthly per-cell products too)
    complex_, edge_monthly = derive_complex(hydro, biome_map, biome_names)
    from exp.k11_worldgen.aquatic import classify_aquatic
    aquatic = classify_aquatic(elev, hydro, climate, SEA_LEVEL,
                               currents=currents)
    bag["aquatic"] = aquatic
    if sink is not None:
        sink.write(14, load_stage_draw(14, bag))
    return {
        "elev": elev, "plates": plates, "hydro": hydro, "climate": climate,
        "biome_map": biome_map, "biome_sim": biome_sim, "cover": cover,
        "complex": complex_, "edge_monthly": edge_monthly,
        "biome_names": biome_names, "ocean_mask": ocean_mask,
        "aquatic": aquatic, "currents": currents, "volcanoes": volcanoes,
    }


def run_demo(seed: int, check_determinism: bool = False,
             realistic: bool = False, center_lat: float | None = None,
             shrink: float = 6.0) -> dict:
    import os
    from exp.k11_worldgen.climate import resolve_center_lat
    center_lat = resolve_center_lat(seed, center_lat)
    out_dir = f"{OUT_DIR}/seed_{seed:08d}"
    os.makedirs(out_dir, exist_ok=True)
    sink = LoadingSink(out_dir)
    world = build_world(seed, sink=sink, realistic=realistic,
                        center_lat=center_lat, shrink=shrink)
    _step("delivery (upscale to 1024)")
    delivered = upscale_world(world["elev"], world["hydro"], world["climate"],
                              world["complex"], SEA_LEVEL,
                              aquatic=world["aquatic"],
                              currents=world["currents"],
                              edge_monthly=world["edge_monthly"])
    sink.write(15, load_stage_draw(15, {"delivered": delivered}))
    sink.write(16, load_stage_draw(16, {"delivered": delivered}))
    _step("render PNGs")
    paths = render_all(out_dir, delivered, world["complex"],
                       currents=world["currents"],
                       climate=world["climate"])
    monthly_paths = render_monthly(out_dir, world["climate"], currents=world["currents"])

    elev, hydro, climate = world["elev"], world["hydro"], world["climate"]
    biome_map, complex_ = world["biome_map"], world["complex"]
    names = world["biome_names"]

    # determinism: rebuild and compare (opt-in — it doubles the runtime)
    det_ok = True
    if check_determinism:
        world2 = build_world(seed, realistic=realistic,
                             center_lat=center_lat, shrink=shrink)
        det_ok = (np.array_equal(world["elev"], world2["elev"])
                  and np.array_equal(world["biome_map"], world2["biome_map"]))

    # structural checks
    H, W = SHAPE
    high_relief = float((elev > 0.72).mean())
    ocean_frac = float(world["ocean_mask"].mean())
    river_cells = int(hydro["river_mask"].sum())
    lake_cells = int(hydro["lake_mask"].sum())

    # every river cell drains to the ocean
    drains = True
    direction = hydro["flow_dir"]
    from exp.k11_worldgen.hydrology import _D8
    for sy, sx in zip(*np.where(hydro["river_mask"])):
        y, x, seen = sy, sx, set()
        while True:
            # sane sinks: ocean or lake inlet
            if hydro["ocean_mask"][y, x] or hydro["lake_mask"][y, x]:
                break
            if (y, x) in seen:
                drains = False
                break
            seen.add((y, x))
            d = direction[y, x]
            if d < 0:
                drains = False
                break
            y, x = y + _D8[d][0], x + _D8[d][1]
        if not drains:
            break

    # lakes first: no river cell inside a lake (by construction, verified)
    rivers_clear = not bool((hydro["river_mask"] & hydro["lake_mask"]).any())

    # lake equipotential: w constant within each 4-connected lake component
    equipotential = True
    lake = hydro["lake_mask"]
    seen = np.zeros_like(lake, dtype=bool)
    for sy in range(H):
        for sx in range(W):
            if lake[sy, sx] and not seen[sy, sx]:
                comp, stack = [], [(sy, sx)]
                while stack:
                    y, x = stack.pop()
                    if seen[y, x] or not lake[y, x]:
                        continue
                    seen[y, x] = True
                    comp.append((y, x))
                    for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                        ny, nx_ = y + dy, x + dx
                        if 0 <= ny < H and 0 <= nx_ < W and not seen[ny, nx_]:
                            stack.append((ny, nx_))
                ws = [hydro["w"][y, x] for y, x in comp]
                if max(ws) - min(ws) > 1e-9:
                    equipotential = False

    # biome coherence after smoothing
    same, total = 0, 0
    for y in range(1, H - 1):
        for x in range(1, W - 1):
            total += 1
            same += int((biome_map[y - 1:y + 2, x - 1:x + 2] == biome_map[y, x]).sum() >= 5)
    coherence = same / total

    defects = audit(complex_)
    # At L0, disconnected_component is expected: each watershed is a disjoint
    # drainage tree (roads will connect basins at L1/C5). The fatal classes
    # are mechanical defects.
    _FATAL = ("dangling_edge", "nodeless_intersection", "isolated_patch")
    fatal = [d for d in defects if d.split(":")[0] in _FATAL]
    # histogram over the DELIVERED 1024² map (1 km² cells, what the viewer
    # displays) — the anchor map would report 65536 4x4-km cells instead
    biome_hi = delivered["biome_map"]
    biome_hist = {names[i]: int((biome_hi == i).sum())
                  for i in range(len(names))}

    checks = {
        # ranges: broad high terrain, or at least one real >3.6 km peak
        # (slim island arcs fail the area test but are still ranges)
        "ranges_exist": high_relief > 0.003 or float(elev.max()) > 0.72,
        "large_ocean": 0.25 < ocean_frac < 0.75,
        "rivers_exist": river_cells > 50,
        "drains_to_ocean_or_lake": drains,
        "rivers_avoid_lakes": rivers_clear,
        "lakes_equipotential": equipotential,
        "biome_coherent": coherence > 0.6,
        "complex_audit_clean": len(fatal) == 0,
        "complex_nontrivial": len(complex_.nodes) > 2 and len(complex_.patches) > 3,
    }
    if check_determinism:
        checks["determinism"] = det_ok
    ok = all(checks.values())

    # world sheet (2048x1024) + plates diagram + loading stages
    from exp.k11_worldgen.biomes import PALETTE
    from exp.k11_worldgen.units import precip_mm, temp_c
    land_d = ~delivered["ocean_mask"] & ~delivered["lake_mask"]
    ann_t = temp_c(delivered["T"])[land_d]
    climate_trivia = {
        "t_min": float(ann_t.min()), "t_max": float(ann_t.max()),
        "t_mean": float(ann_t.mean()),
        "p_mm_yr": float(precip_mm(delivered["P"])[land_d].mean() * 12),
    }
    # sea-ice extent over the year (share of ocean cells iced)
    clim = world["climate"]
    ocean_m = hydro["ocean_mask"]
    if ocean_m.any() and "seaice_monthly" in clim:
        ice_ext = [float(clim["seaice_monthly"][m][ocean_m].mean())
                   for m in range(12)]
        climate_trivia["seaice_frac_min"] = min(ice_ext)
        climate_trivia["seaice_frac_max"] = max(ice_ext)
        lat_arr = clim["lat"]
        climate_trivia["lat_span"] = [round(float(lat_arr[-1]), 1),
                                      round(float(lat_arr[0]), 1)]
        dl = clim["daylen_monthly"]
        climate_trivia["pole_daylen_range"] = [
            round(float(dl[:, 0].min()), 1),
            round(float(dl[:, 0].max()), 1)]
    if "snow_monthly" in clim:
        land_a = ~hydro["ocean_mask"] & ~hydro["lake_mask"]
        if land_a.any():
            snow_ann = clim["snow_monthly"].mean(axis=0)
            climate_trivia["snowpack_max_mean_mm"] = round(
                float(snow_ann[land_a].max()), 0)
            melt_m = [float(clim["snowmelt_monthly"][m].sum())
                      for m in range(12)]
            climate_trivia["snowmelt_peak_month"] = \
                int(np.argmax(melt_m)) + 1
    if "river_monthly" in hydro:
        seasonal = (hydro["river_monthly"].any(axis=0)
                    & ~hydro["river_perm"])
        climate_trivia["seasonal_river_cells"] = int(seasonal.sum())
    if "glacier_mask" in hydro:
        climate_trivia["glacier_cells"] = int(hydro["glacier_mask"].sum())
        # termini: glacier cells whose downstream is not glacier —
        # the melt/calving fronts
        from exp.k11_worldgen.hydrology import _D8
        g = hydro["glacier_mask"]
        term = 0
        gm = float(hydro["glacier_melt_monthly"].sum()) \
            if "glacier_melt_monthly" in hydro else 0.0
        for y, x in zip(*np.nonzero(g)):
            d = hydro["flow_dir"][y, x]
            if d < 0 or not g[y + _D8[d][0], x + _D8[d][1]]:
                term += 1
        climate_trivia["glacier_termini"] = term
        climate_trivia["glacier_melt_mm_yr"] = round(gm, 0)
    salt_cells = int((hydro["salinity"][hydro["lake_mask"]] > 10.0).sum())
    salt_max = (float(hydro["salinity"][hydro["lake_mask"]].max())
                if hydro["lake_mask"].any() else 0.0)
    climate_mode = ({"realistic": True, "center_lat": center_lat,
                     "shrink": shrink} if realistic
                    else {"realistic": False})
    stats_for_legend = {
        "sea_level": SEA_LEVEL,
        "plates": world["plates"].n,
        "oceanic": len(world["plates"].oceanic),
        "ocean_fraction": ocean_frac,
        "river_cells": river_cells,
        "lake_cells": lake_cells,
        "max_stream_order": int(hydro["order"].max()),
        "high_relief_fraction": high_relief,
        "salt_lake_cells": salt_cells,
        "salt_max_gkg": salt_max,
        "climate_mode": climate_mode,
        "climate_trivia": climate_trivia,
        # the emergent prevailing surface wind (annual mean of the
        # delivered snapshots), as a meteorological FROM direction
        "prev_wind": _compass_from(float(world["climate"]["wind_u"].mean()),
                                   float(world["climate"]["wind_v"].mean())),
    }
    delivered_hist = []
    dm = delivered["biome_map"]
    for i, n in enumerate(names):
        # full vocabulary in the legend — a biome absent from this seed
        # shows 0 cells rather than vanishing from the key
        delivered_hist.append((n, int((dm == i).sum()), PALETTE[i]))
    delivered_hist.sort(key=lambda t: -t[1])
    from exp.k11_worldgen.marks import compute_marks
    marks = compute_marks(delivered, hydro, SEA_LEVEL, 4,
                          volcanoes=world["volcanoes"])
    from exp.k11_worldgen.aquatic import aquatic_legend_hist
    aq_hists = aquatic_legend_hist(
        delivered["aquatic"],
        delivered["ocean_mask"] | delivered["lake_mask"]
        | delivered["river_mask"])
    render_world(f"{out_dir}/world.png", delivered, world["plates"], 4,
                 seed, stats_for_legend, delivered_hist, PALETTE, marks,
                 aquatic_hists=aq_hists)
    render_plates(f"{out_dir}/plates.png", world["plates"], world["elev"])
    loading_paths = sink.paths

    # convenience link: out/world_<seed>.png -> this seed's world sheet
    top_link = f"{OUT_DIR}/world_{seed:08d}.png"
    if os.path.lexists(top_link):
        os.remove(top_link)
    os.symlink(os.path.relpath(f"{out_dir}/world.png", OUT_DIR), top_link)

    from exp.k11_worldgen.persist import save_world
    json_path, npz_path = save_world(out_dir, world, delivered, seed,
                                     SEA_LEVEL, 4, report_stats := {
        "plates": world["plates"].n,
        "fine_cells": world["plates"].n_fine,
        "climate_mode": climate_mode,
        "climate_trivia": climate_trivia,
        "salt_lake_cells": salt_cells,
        "salt_max_gkg": round(salt_max, 1),
        "ocean_fraction": round(ocean_frac, 3),
        "high_relief_fraction": round(high_relief, 4),
        "river_cells": river_cells,
        "lake_cells": lake_cells,
        "max_stream_order": int(hydro["order"].max()),
        "biome_histogram": biome_hist,
        "complex": {
            "nodes": len(complex_.nodes),
            "edges": len(complex_.edges),
            "patches": len(complex_.patches),
            "audit_defects": defects,
            "audit_fatal": fatal,
        },
        "biome_coherence": round(coherence, 3),
    }, marks, checks)

    return {
        "experiment": "k11_worldgen", "seed": seed, "shape": SHAPE,
        "stats": report_stats,
        "pngs": paths + [f"{out_dir}/world.png", f"{out_dir}/plates.png"],
        "monthly_pngs": monthly_paths,
        "loading_pngs": loading_paths,
        "dump": [json_path, npz_path],
        "checks": checks, "ok": ok,
    }


def run_render(seed: int) -> dict:
    """Re-render all PNGs from a saved world dump (no worldgen)."""
    from exp.k11_worldgen.persist import load_world
    from exp.k11_worldgen.render import (
        render_all,
        render_loading,
        render_monthly,
        render_plates,
        render_world,
    )

    out_dir = f"{OUT_DIR}/seed_{seed:08d}"
    data = load_world(out_dir)
    world, delivered, manifest, marks = (
        data["world"], data["delivered"], data["manifest"], data["marks"])
    sea_level = manifest["sea_level"]
    factor = manifest["factor"]

    paths = render_all(out_dir, delivered, world["complex"],
                       currents=world["currents"],
                       climate=world["climate"])
    monthly_paths = render_monthly(out_dir, world["climate"], currents=world["currents"])
    names = [b["name"] for b in BIOMES]
    from exp.k11_worldgen.biomes import PALETTE
    dm = delivered["biome_map"]
    hist = [(n, int((dm == i).sum()), PALETTE[i]) for i, n in enumerate(names)]
    hist.sort(key=lambda t: -t[1])
    stats = {**manifest["stats"], "sea_level": sea_level}
    aq_hists = None
    if "aquatic" in delivered:
        from exp.k11_worldgen.aquatic import aquatic_legend_hist
        aq_hists = aquatic_legend_hist(
            delivered["aquatic"],
            delivered["ocean_mask"] | delivered["lake_mask"]
            | delivered["river_mask"])
    render_world(f"{out_dir}/world.png", delivered, world["plates"],
                 factor, seed, stats, hist, PALETTE, marks,
                 aquatic_hists=aq_hists)
    render_plates(f"{out_dir}/plates.png", world["plates"], world["elev"])
    loading_paths = render_loading(out_dir, world, delivered,
                                   world["plates"], sea_level)
    return {"pngs": paths + [f"{out_dir}/world.png", f"{out_dir}/plates.png"],
            "monthly_pngs": monthly_paths, "loading_pngs": loading_paths}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exp.k11_worldgen")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="generate the demo world")
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument("--json", action="store_true")
    demo.add_argument("--check-determinism", action="store_true",
                      help="rebuild the world and byte-compare (doubles runtime)")
    demo.add_argument("--realistic", action="store_true",
                      help="earth-patch temperature (northern hemisphere); "
                           "winds stay random")
    demo.add_argument("--center-lat", type=float, default=None,
                      help="realistic mode: patch center latitude, degN "
                           "(default: 45N + seeded wiggle, mostly +-5 "
                           "with a leaky cap)")
    demo.add_argument("--shrink", type=float, default=6.0,
                      help="realistic mode: planet shrink factor "
                           "(map spans 1024 km * shrink / 111 degrees)")
    demo.add_argument("--viewexport", action="store_true",
                      help="also bake the .k11view viewer bundle after "
                           "generating")
    rend = sub.add_parser("render", help="re-render PNGs from seed_N/world.json")
    rend.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)

    if args.command == "render":
        report = run_render(args.seed)
        print(f"re-rendered from {OUT_DIR}/seed_{args.seed:08d}/world.json")
        for p in report["pngs"]:
            print(f"    {Path(p).name}")
        return 0

    report = run_demo(args.seed, check_determinism=args.check_determinism,
                      realistic=args.realistic, center_lat=args.center_lat,
                      shrink=args.shrink)

    if args.viewexport:
        from exp.k11_worldgen.viewexport import export
        seed_dir = Path(f"{OUT_DIR}/seed_{args.seed:08d}")
        export(seed_dir, seed_dir / f"seed_{args.seed:08d}.k11view")

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        s = report["stats"]
        print(f"K11 worldgen demo — {SHAPE[0]}x{SHAPE[1]} L0 world, seed {report['seed']}")
        print(f"  plates={s['plates']}  ocean={s['ocean_fraction']:.1%}  "
              f"high_relief={s['high_relief_fraction']:.2%}  "
              f"river_cells={s['river_cells']}  lake_cells={s['lake_cells']}")
        print(f"  biomes: {s['biome_histogram']}")
        c = s["complex"]
        print(f"  complex: {c['nodes']} nodes, {c['edges']} edges, "
              f"{c['patches']} patches, audit={c['audit_defects'] or 'clean'}")
        print(f"  pngs -> {OUT_DIR}/seed_{report['seed']:08d}/")
        for p in report["pngs"]:
            print(f"    {Path(p).name}")
        for name, passed in report["checks"].items():
            print(f"  {name:<26}: {'PASS' if passed else 'FAIL'}")
        print(f"verdict: {'PASS' if report['ok'] else 'FAIL'}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
