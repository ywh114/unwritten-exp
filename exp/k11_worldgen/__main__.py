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


def build_world(seed: int, shape: tuple[int, int] = SHAPE, sink=None) -> dict:
    stream = Stream(seed, "k11.worldgen")
    elev, plates = build_elevation(stream, shape, sea_level=SEA_LEVEL)
    bag = {"plates": plates, "elev": elev}
    if sink is not None:
        sink.write(1, load_stage_draw(1, bag))
        sink.write(2, load_stage_draw(2, bag))
    # ocean = below-sea cells CONNECTED to the border; enclosed
    # below-sea basins are land (lake beds or dry depressions)
    from exp.k11_worldgen.hydrology import connected_ocean
    ocean_mask = connected_ocean(elev, SEA_LEVEL)
    hydro = build_hydrology(elev, ocean_mask, sea_level=SEA_LEVEL, seed=seed)
    bag["hydro"] = hydro
    if sink is not None:
        sink.write(3, load_stage_draw(3, bag))

    def _hook(n, arr):
        # coarse climate intermediates, nearest-upsampled for the screen
        f = 1024 // arr.shape[0]

        def draw(p, a=arr, f=f):
            write_png_gray(p, np.kron(normalize_u8(a, 0.0, 1.0),
                                      np.ones((f, f))))
        sink.write(n, draw)

    climate = build_climate(elev, hydro, SEA_LEVEL, seed=seed,
                            stage_hook=_hook if sink is not None else None)
    bag["climate"] = climate
    if sink is not None:
        sink.write(6, load_stage_draw(6, bag))
        sink.write(7, load_stage_draw(7, bag))
    # discharge: precipitation-weighted accumulation (river mouths are
    # ranked by water volume, not just basin cell count)
    from exp.k11_worldgen.hydrology import flow_accumulation
    hydro["discharge"] = flow_accumulation(
        hydro["w_route"], hydro["flow_dir"], hydro["flat_depth"],
        weight=climate["P"])
    biome_map = classify_biomes(elev, hydro, climate, SEA_LEVEL)
    bag["biome_map"] = biome_map
    if sink is not None:
        sink.write(8, load_stage_draw(8, bag))
    cover = forest_cover(biome_map, growing_season_p(climate))
    biome_names = [b["name"] for b in BIOMES]
    complex_ = derive_complex(hydro, biome_map, biome_names)
    return {
        "elev": elev, "plates": plates, "hydro": hydro, "climate": climate,
        "biome_map": biome_map, "cover": cover, "complex": complex_,
        "biome_names": biome_names, "ocean_mask": ocean_mask,
    }


def run_demo(seed: int) -> dict:
    import os
    out_dir = f"{OUT_DIR}/seed_{seed:08d}"
    os.makedirs(out_dir, exist_ok=True)
    sink = LoadingSink(out_dir)
    world = build_world(seed, sink=sink)
    delivered = upscale_world(world["elev"], world["hydro"], world["climate"],
                              world["complex"], SEA_LEVEL)
    sink.write(9, load_stage_draw(9, {"delivered": delivered}))
    sink.write(10, load_stage_draw(10, {"delivered": delivered}))
    paths = render_all(out_dir, delivered, world["complex"])
    monthly_paths = render_monthly(out_dir, world["climate"])

    elev, hydro, climate = world["elev"], world["hydro"], world["climate"]
    biome_map, complex_ = world["biome_map"], world["complex"]
    names = world["biome_names"]

    # determinism: rebuild and compare
    world2 = build_world(seed)
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
    biome_hist = {names[i]: int((biome_map == i).sum()) for i in range(len(names))}

    checks = {
        "determinism": det_ok,
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
    ok = all(checks.values())

    # world sheet (2048x1024) + plates diagram + loading stages
    from exp.k11_worldgen.biomes import PALETTE
    stats_for_legend = {
        "sea_level": SEA_LEVEL,
        "plates": world["plates"].n,
        "oceanic": len(world["plates"].oceanic),
        "ocean_fraction": ocean_frac,
        "river_cells": river_cells,
        "lake_cells": lake_cells,
        "max_stream_order": int(hydro["order"].max()),
        "high_relief_fraction": high_relief,
    }
    delivered_hist = []
    dm = delivered["biome_map"]
    for i, n in enumerate(names):
        # full vocabulary in the legend — a biome absent from this seed
        # shows 0 cells rather than vanishing from the key
        delivered_hist.append((n, int((dm == i).sum()), PALETTE[i]))
    delivered_hist.sort(key=lambda t: -t[1])
    from exp.k11_worldgen.marks import compute_marks
    marks = compute_marks(delivered, hydro, SEA_LEVEL, 4)
    render_world(f"{out_dir}/world.png", delivered, world["plates"], 4,
                 seed, stats_for_legend, delivered_hist, PALETTE, marks)
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

    paths = render_all(out_dir, delivered, world["complex"])
    monthly_paths = render_monthly(out_dir, world["climate"])
    names = [b["name"] for b in BIOMES]
    from exp.k11_worldgen.biomes import PALETTE
    dm = delivered["biome_map"]
    hist = [(n, int((dm == i).sum()), PALETTE[i]) for i, n in enumerate(names)]
    hist.sort(key=lambda t: -t[1])
    stats = {**manifest["stats"], "sea_level": sea_level}
    render_world(f"{out_dir}/world.png", delivered, world["plates"],
                 factor, seed, stats, hist, PALETTE, marks)
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
    rend = sub.add_parser("render", help="re-render PNGs from seed_N/world.json")
    rend.add_argument("--seed", type=int, default=1)
    args = parser.parse_args(argv)

    if args.command == "render":
        report = run_render(args.seed)
        print(f"re-rendered from {OUT_DIR}/seed_{args.seed:08d}/world.json")
        for p in report["pngs"]:
            print(f"    {Path(p).name}")
        return 0

    report = run_demo(args.seed)

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
