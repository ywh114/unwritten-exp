"""K11 — world persistence.

`save_world` dumps a built world to `seed_N/world.json` +
`seed_N/world.npz`; `load_world` reads it back. The JSON is the
human-inspectable manifest (params, stats, marks, plates metadata, the
full complex, checks, array inventory); the NPZ holds the raster
arrays (compressed — a base64-in-JSON dump would be ~100 MB of
uninspectable blob, against the repo's JSON-inspectable convention).

Uses: re-render PNGs without rebuilding the world when only DRAW logic
changes (`python -m exp.k11_worldgen render --seed N`), and future
kernels that need world state as input.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

VERSION = 1

_PLATES_ARRAYS = ("macro_id", "fine_id", "is_ocean", "is_sea_plate",
                  "is_sea_pocket", "fault_dist", "fault_conv",
                  "fault_kind", "fault_sub", "fine_bias")


def _complex_to_dicts(cx) -> dict:
    return {
        "nodes": [{"id": n.id, "pos": [float(n.pos[0]), float(n.pos[1])]}
                  for n in cx.nodes.values()],
        "edges": [{"id": e.id, "node_a": e.node_a, "node_b": e.node_b,
                   "length": float(e.length), "kind": e.kind,
                   "quality": float(e.quality),
                   "polyline": [[float(a), float(b)] for a, b in e.polyline]}
                  for e in cx.edges.values()],
        "patches": [{"id": q.id, "boundary_edges": list(q.boundary_edges),
                     "measure": float(q.measure), "parent": q.parent,
                     "field": {"mu": [float(v) for v in q.field.mu],
                               "theta": [float(v) for v in q.field.theta],
                               "sigma": [float(v) for v in q.field.sigma]}}
                    for q in cx.patches.values()],
    }


def _complex_from_dicts(d: dict):
    from kernel.complex.cells import Complex, Edge, Node, Patch
    from kernel.gmm_dynamics.dynamics import DriftField
    nodes = [Node(id=n["id"], pos=(n["pos"][0], n["pos"][1]))
             for n in d["nodes"]]
    edges = [Edge(id=e["id"], node_a=e["node_a"], node_b=e["node_b"],
                  length=e["length"], kind=e["kind"], quality=e["quality"],
                  polyline=tuple((a, b) for a, b in e["polyline"]))
             for e in d["edges"]]
    patches = [Patch(id=q["id"],
                     field=DriftField(mu=np.array(q["field"]["mu"]),
                                      theta=np.array(q["field"]["theta"]),
                                      sigma=np.array(q["field"]["sigma"])),
                     boundary_edges=tuple(q["boundary_edges"]),
                     measure=q["measure"], parent=q["parent"])
               for q in d["patches"]]
    return Complex(nodes, edges, patches)


def save_world(out_dir: str, world: dict, delivered: dict, seed: int,
               sea_level: float, factor: int, stats: dict,
               marks: list, checks: dict) -> tuple[str, str]:
    out = Path(out_dir)
    arrays: dict[str, np.ndarray] = {}
    for k in ("elev", "biome_map", "cover", "ocean_mask", "aquatic"):
        arrays[f"w_{k}"] = world[k]
    for k, v in world["hydro"].items():
        arrays[f"h_{k}"] = v
    for k, v in world["climate"].items():
        arrays[f"c_{k}"] = v
    p = world["plates"]
    for k in _PLATES_ARRAYS:
        arrays[f"p_{k}"] = getattr(p, k)
    arrays["p_plate_base"] = np.array(p.plate_base)
    # ocean currents, complete: annual velocity + upwelling rise +
    # depth as arrays, the per-source stream functions and blend
    # weights, gyre parameters and vmax in the manifest — everything
    # velocity_field(month) needs downstream
    c = world["currents"]
    for k in ("u", "v", "rise", "depth_m"):
        arrays[f"r_{k}"] = c[k]
    # the nutrient-circulation store: monthly upwelling, derived from
    # the stored stream functions at save time
    from exp.k11_worldgen.currents import rise_monthly
    arrays["r_rise_m"] = rise_monthly(c)
    for i, psi in enumerate(c["psi"]):
        arrays[f"r_psi_{i}"] = psi
    arrays["r_weights"] = np.array(c["weights"])
    currents_manifest = {
        "vmax": float(c["vmax"]),
        "gyres": [[float(v) for v in g] for g in c["gyres"]],
    }
    if "ramp" in c:            # through-flow source (build_currents)
        currents_manifest["ramp"] = {k: float(v) if k != "i0" else int(v)
                                     for k, v in c["ramp"].items()}
    if "vmax_seeds" in c:        # present once wind refinement ran
        currents_manifest["vmax_seeds"] = float(c["vmax_seeds"])
    for k, v in delivered.items():
        if k != "shape":
            arrays[f"d_{k}"] = v
    npz_path = out / "world.npz"
    np.savez_compressed(npz_path, **arrays)

    manifest = {
        "experiment": "k11_worldgen",
        "k11_version": VERSION,
        "seed": seed,
        "shape": list(world["elev"].shape),
        "sea_level": sea_level,
        "factor": factor,
        "stats": stats,
        "checks": checks,
        "marks": [[k, int(y), int(x), t] for k, y, x, t in marks],
        "plates": {
            "n": p.n, "n_fine": p.n_fine,
            "oceanic": sorted(int(m) for m in p.oceanic),
            "dots": [[float(a), float(b)] for a, b in p.dots],
            "centroids": [[float(a), float(b)] for a, b in p.centroids],
            "velocities": [[float(a), float(b)] for a, b in p.velocities],
            "plate_base": [float(b) for b in p.plate_base],
        },
        "complex": _complex_to_dicts(world["complex"]),
        "currents": currents_manifest,
        "arrays": sorted(arrays),
    }
    json_path = out / "world.json"
    json_path.write_text(json.dumps(manifest))
    return str(json_path), str(npz_path)


def load_world(out_dir: str) -> dict:
    """Load a saved world dump. The plates/complex payloads are rebuilt
    as light namespaces (enough for all render functions); use
    load_complex() for the real K9 Complex."""
    out = Path(out_dir)
    manifest = json.loads((out / "world.json").read_text())
    z = np.load(out / "world.npz")

    world = {k[2:]: z[k] for k in z.files if k.startswith("w_")}
    world["hydro"] = {k[2:]: z[k] for k in z.files if k.startswith("h_")}
    world["climate"] = {k[2:]: z[k] for k in z.files if k.startswith("c_")}
    currents = {k[2:]: z[k] for k in z.files
                if k.startswith("r_") and not k.startswith("r_psi")}
    currents["rise_monthly"] = currents.pop("rise_m")
    currents["psi"] = [z[k] for k in sorted(
        (k for k in z.files if k.startswith("r_psi")),
        key=lambda k: int(k.rsplit("_", 1)[1]))]
    currents["weights"] = list(currents.pop("weights"))
    mc = manifest["currents"]
    currents["vmax"] = mc["vmax"]
    if "vmax_seeds" in mc:
        currents["vmax_seeds"] = mc["vmax_seeds"]
    currents["gyres"] = [tuple(g) for g in mc["gyres"]]
    if "ramp" in mc:
        currents["ramp"] = dict(mc["ramp"])
    currents["n_gyres"] = len(currents["gyres"])
    currents["factor"] = (world["elev"].shape[0]
                          // currents["psi"][0].shape[0])
    currents["ocean_mask"] = world["ocean_mask"]
    world["currents"] = currents
    mp = manifest["plates"]
    world["plates"] = SimpleNamespace(
        n=mp["n"], n_fine=mp["n_fine"], oceanic=set(mp["oceanic"]),
        dots=mp["dots"], centroids=mp["centroids"],
        velocities=mp["velocities"],
        **{k[2:]: z[k] for k in z.files if k.startswith("p_")})
    nodes = {n["id"]: SimpleNamespace(id=n["id"], pos=tuple(n["pos"]))
             for n in manifest["complex"]["nodes"]}
    world["complex"] = SimpleNamespace(
        nodes=nodes, edges=manifest["complex"]["edges"],
        patches=manifest["complex"]["patches"])

    delivered = {k[2:]: z[k] for k in z.files if k.startswith("d_")}
    delivered["shape"] = delivered["elev"].shape
    marks = [(k, y, x, t) for k, y, x, t in manifest["marks"]]
    return {"world": world, "delivered": delivered,
            "manifest": manifest, "marks": marks}


def load_complex(out_dir: str):
    """Rebuild the real K9 Complex from a world dump."""
    out = Path(out_dir)
    manifest = json.loads((out / "world.json").read_text())
    return _complex_from_dicts(manifest["complex"])
