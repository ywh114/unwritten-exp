"""K11 — export a self-contained viewer bundle (.k11view) from a world dump.

    uv run python -m exp.k11_worldgen.viewexport [--seed N] [--out DIR]

The bundle is ONE binary file the standalone map.html reads via drag-drop
(no server): a JSON header (little-endian length-prefixed) followed by raw
quantized field arrays. Layout:

    magic "K11V" (4B) | header_len (uint32 LE) | header (JSON UTF-8)
    | field arrays in header["order"], each shape[0]*shape[1] items of
      the dtype named in header["fields"][name]["dtype"]

Quantization: uint8/uint16 with per-field scale/offset (in the header);
masks packed one bit per mask into a single uint8 "masks" field. ~13 MB
per 1024x1024 world.
"""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path

import numpy as np

from exp.k11_worldgen.biomes import BIOME_ID, BIOMES
from exp.k11_worldgen.units import alt_m, hand_m, precip_mm, temp_c

HERE = Path(__file__).parent
OUT = HERE / "out"


def _q8(v: np.ndarray, lo: float, hi: float) -> tuple[np.ndarray, dict]:
    return (np.clip((v - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8),
            {"dtype": "u1", "scale": (hi - lo) / 255, "offset": float(lo)})


def _q16(v: np.ndarray, lo: float, hi: float) -> tuple[np.ndarray, dict]:
    return (np.clip((v - lo) / (hi - lo) * 65535, 0, 65535)
            .astype(np.uint16),
            {"dtype": "<u2", "scale": (hi - lo) / 65535, "offset": float(lo)})


def export(seed_dir: Path, out_path: Path) -> None:
    manifest = json.loads((seed_dir / "world.json").read_text())
    z = np.load(seed_dir / "world.npz")
    d = {k[2:]: z[k] for k in z.files if k.startswith("d_")}
    sea = float(manifest["sea_level"])
    shape = d["elev"].shape

    fields: dict[str, np.ndarray] = {}
    meta: dict[str, dict] = {}

    def put(name: str, arr: np.ndarray, m: dict) -> None:
        fields[name] = arr
        meta[name] = m

    a, m = _q16(alt_m(d["elev"], sea), 0, 8000)  # seed max ~6.5km
    put("elev_m", a, m)
    a, m = _q16(temp_c(d["T"]), -40, 40)
    put("T_c", a, m)
    a, m = _q16(precip_mm(d["P"]), 0, 600)
    put("P_mm", a, m)
    a, m = _q8(d["cover"], 0, 1)
    put("cover", a, m)
    a, m = _q8(d["salinity"], 0, 40)
    put("salinity", a, m)
    a, m = _q16(d["depth"], 0, 6000)
    put("depth_m", a, m)
    a, m = _q16(hand_m(d["hand"], sea), 0, 200)
    put("hand_m", a, m)
    a, m = _q16(d["width"], 0, 500)
    put("width_m", a, m)
    put("biome", d["biome_map"].astype(np.uint8), {"dtype": "u1"})
    put("aquatic", d["aquatic"].astype(np.uint8), {"dtype": "u1"})
    masks = (d["river_mask"].astype(np.uint8)
             | (d["lake_mask"].astype(np.uint8) << 1)
             | (d["ocean_mask"].astype(np.uint8) << 2)
             | (d["sea_mask"].astype(np.uint8) << 3))
    put("masks", masks, {"dtype": "u1",
                         "bits": ["river", "lake", "ocean", "sea"]})
    if "w_biome_d2_1" in z.files:
        d1, d2 = z["w_biome_d2_1"], z["w_biome_d2_2"]
        sim = (d2 - d1) / np.maximum(d2, 1e-9)
        factor = shape[0] // sim.shape[0]
        sim = np.repeat(np.repeat(sim, factor, 0), factor, 1)
        a, m = _q8(sim, 0, 1)
        put("biome_sim", a, m)

    header = {
        "format": "k11view/1",
        "seed": manifest["seed"],
        "shape": list(shape),
        "sea_level": sea,
        "stats": manifest["stats"],
        "biome_names": {str(i): n for n, i in BIOME_ID.items()},
        "biome_colors": {str(BIOME_ID[b["name"]]): list(b["color"])
                         for b in BIOMES},
        "backdrop_png_b64": __import__("base64").b64encode(
            (seed_dir / "world.png").read_bytes()).decode()
        if (seed_dir / "world.png").exists() else None,
        "pngs": sorted(p.stem for p in seed_dir.glob("*.png")
                       if p.stem != "load"),
        "order": list(fields),
        "fields": meta,
    }
    blob = json.dumps(header).encode()
    with open(out_path, "wb") as f:
        f.write(b"K11V")
        f.write(struct.pack("<I", len(blob)))
        f.write(blob)
        for name in header["order"]:
            fields[name].astype(meta[name]["dtype"].lstrip("<"),
                                copy=False).tofile(f)
    mb = out_path.stat().st_size / 1e6
    print(f"{out_path}  {mb:.1f} MB  fields: {', '.join(header['order'])}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--dir", type=Path, default=OUT)
    args = ap.parse_args()
    seed_dir = args.dir / f"seed_{args.seed:08d}"
    export(seed_dir, seed_dir / f"seed_{args.seed:08d}.k11view")


if __name__ == "__main__":
    main()
