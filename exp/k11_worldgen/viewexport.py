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


def _q8s(v: np.ndarray, lim: float) -> tuple[np.ndarray, dict]:
    """Signed symmetric int8 quantization: zero is EXACT (uint8 maps 0 to
    127.5, which truncates to a constant nonzero vector — over land that
    drew perfectly straight 'currents' across whole continents)."""
    lim = max(float(lim), 1e-12)
    return (np.clip(np.round(v / lim * 127), -127, 127).astype(np.int8),
            {"dtype": "i1", "scale": lim / 127, "offset": 0.0})


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
    # d["P"] is the mean-MONTHLY normalized field (classify_streaming
    # averages over 12 months); the viewer labels this field mm/yr, so
    # convert to the annual TOTAL here — the old export shipped the
    # monthly mean under a "mm/yr" label (~12x underreported)
    a, m = _q16(precip_mm(d["P"]) * 12.0, 0, 4800)
    put("P_mm", a, m)
    a, m = _q8(d["cover"], 0, 1)
    put("cover", a, m)
    # 0..260 g/kg: salt lakes run to ~220 — the old 0..40 clip flattened
    # every hypersaline cell to "40" in tooltip/search and killed the
    # Hydro layer's salinity-deviation signal
    a, m = _q8(d["salinity"], 0, 260)
    put("salinity", a, m)
    a, m = _q16(d["salinity"], 0, 260)
    put("salinity", a, m)
    # physical depth in meters, computed from elev/w (NOT d["depth"] —
    # older dumps carry a normalized 0/1 water mask there). Ocean
    # bathymetry from terrain below sea level; lake/river fill depth
    # from the water surface over the bed.
    from exp.k11_worldgen.units import DEPTH_MAX_M, ELEV_MAX_M, elev_m
    bathy = np.maximum(sea - d["elev"], 0.0) / sea * DEPTH_MAX_M
    fill = np.maximum(d["w"] - d["elev"], 0.0) / (1.0 - sea) * ELEV_MAX_M
    depth = np.where(d["ocean_mask"], bathy, fill)
    a, m = _q16(depth, 0, 6000)
    put("depth_m", a, m)
    a, m = _q16(hand_m(d["hand"], sea), 0, 200)
    put("hand_m", a, m)
    # Strahler stream order (anchor res, kron-upsampled, masked to the
    # delivered river corridor; 0 off-river). d["width"] stays unexported:
    # it is a 1-3 render corridor class, not a physical width
    if "h_order" in z.files:
        ho = z["h_order"]
        factor = shape[0] // ho.shape[0]
        oh = np.repeat(np.repeat(ho, factor, 0), factor, 1)
        oh = np.where(d["river_mask"], oh, 0).astype(np.uint8)
        put("order", oh, {"dtype": "u1"})
    put("biome", d["biome_map"].astype(np.uint8), {"dtype": "u1"})
    put("aquatic", d["aquatic"].astype(np.uint8), {"dtype": "u1"})
    from exp.k11_worldgen.aquatic import AQUATIC
    aquatic_names = {str(i): a_["name"] for i, a_ in enumerate(AQUATIC)}
    aquatic_colors = {str(i): list(a_["color"])
                      for i, a_ in enumerate(AQUATIC)}
    mask_parts = [("river", d["river_mask"]), ("lake", d["lake_mask"]),
                  ("ocean", d["ocean_mask"]), ("sea", d["sea_mask"])]
    if "glacier_mask" in d:      # newer dumps: flowing-ice extent
        mask_parts.append(("glacier", d["glacier_mask"]))
    masks = np.zeros(shape, dtype=np.uint8)
    for bit, (_bn, bm_) in enumerate(mask_parts):
        masks |= bm_.astype(np.uint8) << bit
    put("masks", masks, {"dtype": "u1",
                         "bits": [bn for bn, _ in mask_parts]})
    if "glacier_m" in d:
        # per-cell ice thickness (m), 0 off the glacier — u16 keeps the
        # sub-meter taper at thin snouts readable
        a, m = _q16(d["glacier_m"], 0, 2000)
        put("glacier_m", a, m)
    if "w_biome_d2_1" in z.files:
        d1, d2 = z["w_biome_d2_1"], z["w_biome_d2_2"]
        sim = (d2 - d1) / np.maximum(d2, 1e-9)
        factor = shape[0] // sim.shape[0]
        sim = np.repeat(np.repeat(sim, factor, 0), factor, 1)
        a, m = _q8(sim, 0, 1)
        put("biome_sim", a, m)

    # monthly climate at ANCHOR res (12 planes each; the viewer averages
    # selected months and upscales x4 for the overlay)
    monthly: dict[str, np.ndarray] = {}
    monthly_meta: dict[str, dict] = {}
    if "c_T_monthly" in z.files:
        tq, tm = _q8(temp_c(z["c_T_monthly"]), -40, 40)
        monthly["t_monthly"] = tq
        monthly_meta["t_monthly"] = tm
        pq, pm = _q8(precip_mm(z["c_P_monthly"]), 0, 300)
        monthly["p_monthly"] = pq
        monthly_meta["p_monthly"] = pm
    # monthly VECTOR fields for viewer fieldlines: wind = per-month mean
    # over the n_samples axis (coarse climate grid); currents = seasonal
    # velocity_field rebuilt from the persisted psi/weights/gyres payload
    if "c_wind_u" in z.files:
        wu = z["c_wind_u"].mean(axis=1)
        wv = z["c_wind_v"].mean(axis=1)
        lim = float(np.abs(np.stack([wu, wv])).max())
        a, m_ = _q8s(wu, lim)
        monthly["wu_monthly"] = a
        monthly_meta["wu_monthly"] = m_
        a, m_ = _q8s(wv, lim)
        monthly["wv_monthly"] = a
        monthly_meta["wv_monthly"] = m_
    # solar geometry + freezing (persisted first-class fields)
    if "c_seaice_monthly" in z.files:
        a, m_ = _q8(z["c_seaice_monthly"], 0, 1)
        monthly["seaice_monthly"] = a
        monthly_meta["seaice_monthly"] = m_
    if "c_lakeice_monthly" in z.files:
        a, m_ = _q8(z["c_lakeice_monthly"], 0, 1)
        monthly["lakeice_monthly"] = a
        monthly_meta["lakeice_monthly"] = m_
    if "c_riverice_monthly" in z.files:
        a, m_ = _q8(z["c_riverice_monthly"], 0, 1)
        monthly["riverice_monthly"] = a
        monthly_meta["riverice_monthly"] = m_
    if "c_snow_monthly" in z.files:
        a, m_ = _q8(z["c_snow_monthly"], 0, 500)
        monthly["snow_monthly"] = a
        monthly_meta["snow_monthly"] = m_
    if "d_river_width_monthly" in z.files:
        # monthly river networks STAMPED at delivered res (the same
        # river_raster as the annual network — taper/meander baked in);
        # width classes 0-3, 0 off-network
        monthly["river_width_monthly"] = \
            z["d_river_width_monthly"].astype(np.uint8)
        monthly_meta["river_width_monthly"] = {"dtype": "u1"}
    if "c_insol_monthly" in z.files:
        # row fields (12, H) -> planes at ANCHOR res (like t_monthly)
        w_anchor = z["c_T"].shape[1]
        ins = z["c_insol_monthly"]
        ins = np.broadcast_to(ins[:, :, None],
                              (12, ins.shape[1], w_anchor))
        a, m_ = _q8(ins, 0, 1.2)
        monthly["insol_monthly"] = a
        monthly_meta["insol_monthly"] = m_
        dl = z["c_daylen_monthly"]
        dl = np.broadcast_to(dl[:, :, None], (12, dl.shape[1], w_anchor))
        a, m_ = _q8(dl, 0, 24)
        monthly["daylen_monthly"] = a
        monthly_meta["daylen_monthly"] = m_
    if "c_lat" in z.files:
        # row field at anchor res -> delivery rows (kron, then columns)
        factor = shape[0] // z["c_lat"].shape[0]
        lat_rows = np.repeat(z["c_lat"], factor)
        lat2d = np.broadcast_to(lat_rows[:, None], shape)
        a, m_ = _q8(lat2d, -90, 90)
        put("lat", a, m_)
    try:
        from exp.k11_worldgen.currents import velocity_field
        from exp.k11_worldgen.persist import load_world
        cur = load_world(str(seed_dir))["world"]["currents"]
        cu = np.stack([velocity_field(cur, mm)[0] for mm in range(12)])
        cv = np.stack([velocity_field(cur, mm)[1] for mm in range(12)])
        lim = float(np.abs(np.stack([cu, cv])).max())
        a, m_ = _q8s(cu, lim)
        monthly["cu_monthly"] = a
        monthly_meta["cu_monthly"] = m_
        a, m_ = _q8s(cv, lim)
        monthly["cv_monthly"] = a
        monthly_meta["cv_monthly"] = m_
    except (KeyError, ValueError):
        pass  # older dumps without the full currents payload
    for name, arr in monthly.items():
        monthly_meta[name]["shape"] = list(arr.shape)

    backdrop = None
    for name in ("worldmap.png", "world.png"):
        p_ = seed_dir / name
        if p_.exists():
            backdrop = __import__("base64").b64encode(
                p_.read_bytes()).decode()
            break

    header = {
        "format": "k11view/1",
        "seed": manifest["seed"],
        "shape": list(shape),
        "sea_level": sea,
        "stats": manifest["stats"],
        "biome_names": {str(i): n for n, i in BIOME_ID.items()},
        "biome_colors": {str(BIOME_ID[b["name"]]): list(b["color"])
                         for b in BIOMES},
        "aquatic_names": aquatic_names,
        "aquatic_colors": aquatic_colors,
        "backdrop_png_b64": backdrop,
        "backdrop_is_square": (seed_dir / "worldmap.png").exists(),
        "monthly_shape": ([12] + list(monthly["t_monthly"].shape[1:])
                          if monthly else None),
        "monthly_fields": monthly_meta,
        "monthly_order": list(monthly),
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
        for name, arr in monthly.items():
            arr.tofile(f)
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
