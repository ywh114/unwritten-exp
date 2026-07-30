"""K14 P6 — datapack writer: the unified viewer-overlay bundle (.k11pack).

One binary file the K11 map viewer (map.html) reads via drag-drop AFTER
a .k11view bundle; overlay buttons build themselves from the header's
declarative layer metadata — no per-layer viewer code (owner decision
2026-07-29 #1). Same container convention as .k11view:

    magic "K11P" (4B) | header_len (uint32 LE) | header (JSON UTF-8)
    | arrays in header["order"], each shape-product items of the
      layer's dtype

Layer metadata (header["layers"]):
    id, label, kind (continuous|categorical|points|vectors),
    field (binary array name; absent for points), dtype, scale, offset,
    shape, colormap ([[t, [r,g,b]], ...] for continuous; {state: [r,g,b]}
    for categorical), alpha, mask (land|ocean|freshwater|river|lake|
    null — evaluated against the base bundle's masks), unit,
    month_dim (12 for monthly fields — the viewer's month mask applies),
    points (inline list for kind=points: {y, x, ...attrs}, delivery
    coords), color ([r,g,b] for points/vectors)

A kind=categorical layer (the B3 "ground" layer) carries `classes` — the
full class table (name/color/flags/props/genesis; the palette's source of
truth) — plus a flat {id: [r,g,b]} `colormap` so the existing categorical
renderer keeps working. It may also carry auxiliary planes `mix_ids` and
`mix_w`, each a sub-dict {field, dtype, shape} whose arrays trail the main
fields in the binary section (header["order"] lists main fields first, then
aux). An older viewer reads only each layer's main `field` and stops before
the trailing aux bytes, so it ignores them gracefully.

Quantization mirrors viewexport: uint8/uint16 with per-layer
scale/offset in the header.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

import numpy as np

MAGIC = b"K11P"
FORMAT = "k11pack/1"


def _q8(v: np.ndarray, lo: float, hi: float) -> tuple[np.ndarray, dict]:
    return (np.clip((v - lo) / (hi - lo) * 255, 0, 255).astype(np.uint8),
            {"dtype": "u1", "scale": (hi - lo) / 255, "offset": float(lo)})


def _q16(v: np.ndarray, lo: float, hi: float) -> tuple[np.ndarray, dict]:
    return (np.clip((v - lo) / (hi - lo) * 65535, 0, 65535)
            .astype(np.uint16),
            {"dtype": "<u2", "scale": (hi - lo) / 65535,
             "offset": float(lo)})


# auxiliary array keys a layer may carry alongside its main "field"
# (e.g. the ground layer's top-3 mix planes). Each value is a sub-dict
# {field, dtype, shape}; the arrays themselves live in the `arrays` map.
AUX_KEYS = ("mix_ids", "mix_w")


def write_pack(out_path: Path, layers: list[dict],
               arrays: dict[str, np.ndarray], meta: dict) -> Path:
    """Write a .k11pack. *layers* is the declarative layer list (points
    layers carry their data inline); *arrays* maps field name -> quantized
    array; *meta* becomes the header preamble (generator, seed, ...).

    Binary order is every layer's main field (in layer order) followed by
    any auxiliary arrays (mix_ids/mix_w). Aux arrays trail the whole pack,
    so an older viewer — which reads only the main `field` of each layer —
    stops before them and ignores them gracefully."""
    order: list[str] = []
    dtypes: dict[str, str] = {}
    for l in layers:
        if l.get("field"):
            order.append(l["field"])
            dtypes[l["field"]] = l["dtype"]
    for l in layers:
        for key in AUX_KEYS:
            if key in l:
                order.append(l[key]["field"])
                dtypes[l[key]["field"]] = l[key]["dtype"]
    header = {"format": FORMAT, **meta, "layers": layers, "order": order}
    blob = json.dumps(header).encode()
    with open(out_path, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack("<I", len(blob)))
        f.write(blob)
        for name in order:
            arrays[name].astype(dtypes[name].lstrip("<"), copy=False).tofile(f)
    return out_path


# ── P6 pack: the D0 products as viewer layers ───────────────────────────

# named ramps as stop lists (t, [r,g,b]); the viewer interpolates
RAMP_TERRESTRIAL = [[0.0, [40, 32, 16]], [0.5, [96, 128, 48]],
                    [1.0, [190, 230, 120]]]
RAMP_MARINE = [[0.0, [8, 32, 64]], [0.5, [16, 128, 128]],
               [1.0, [120, 230, 200]]]
RAMP_FRESH = [[0.0, [16, 32, 80]], [1.0, [100, 180, 240]]]
RAMP_SPEED = [[0.0, [30, 30, 30]], [1.0, [240, 200, 60]]]
RAMP_VENT = [[0.0, [20, 10, 10]], [1.0, [230, 80, 40]]]
RAMP_SEASON = [[0.0, [40, 20, 60]], [0.5, [120, 70, 160]],
               [1.0, [220, 180, 240]]]
RAMP_PULSE = [[0.0, [20, 25, 35]], [0.5, [60, 110, 160]],
              [1.0, [140, 220, 250]]]


def build_pack(result: dict, out_path: Path) -> Path:
    """Serialize a derived.build() result as derived.k11pack."""
    p = result["products"]
    layers: list[dict] = []
    arrays: dict[str, np.ndarray] = {}

    def continuous(id_, label, field, lo, hi, ramp, alpha, mask, unit,
                   month_dim=None):
        arr = p[field]
        q, m = _q8(arr, lo, hi)
        layer = {"id": id_, "label": label, "kind": "continuous",
                 "field": field, **m, "shape": list(arr.shape),
                 "colormap": ramp, "alpha": alpha, "mask": mask,
                 "unit": unit}
        if month_dim:
            layer["month_dim"] = month_dim
        layers.append(layer)
        arrays[field] = q

    continuous("terr_prod", "Terrestrial productivity",
               "terrestrial_productivity", 0, 3.0, RAMP_TERRESTRIAL,
               0.55, "land", "")
    continuous("marine_prod", "Marine productivity", "marine_productivity",
               0, 2.0, RAMP_MARINE, 0.55, "ocean", "", month_dim=12)
    continuous("fresh_prod", "Freshwater productivity",
               "freshwater_productivity", 0, 1.5, RAMP_FRESH, 0.6,
               "freshwater", "", month_dim=12)
    continuous("river_speed", "River speed", "river_speed",
               0, 3, RAMP_SPEED, 0.8, "river", " m/s")
    continuous("vents", "Vent field", "vent_field",
               0, float(np.percentile(p["vent_field"], 99)) or 1.0,
               RAMP_VENT, 0.5, None, "")
    continuous("grow_season", "Growing season", "growing_season",
               0, 12, RAMP_SEASON, 0.5, "land", " mo")
    continuous("flood_pulse", "Flood pulse", "flood_pulse",
               0, 1, RAMP_PULSE, 0.6, "land", "")

    # substrate ("ground") — the first CATEGORICAL layer. The palette lives
    # in `classes` (the B3 class table: name/color/flags/props/genesis); a
    # flat {id: color} `colormap` is emitted alongside so the existing
    # categorical renderer (which keys colormap[String(v)]) works unchanged.
    # The top-3 mix planes ride along as auxiliary u1 arrays on the layer.
    classes = result["ground_meta"]
    colormap = {str(i): c["color"] for i, c in enumerate(classes)}
    layers.append({
        "id": "ground", "label": "Substrate (ground)", "kind": "categorical",
        "field": "ground_class", "dtype": "u1",
        "shape": list(p["ground_class"].shape),
        "classes": classes, "colormap": colormap, "scope": "all",
        "mask": None, "alpha": 0.7,
        "mix_ids": {"field": "ground_mix_ids", "dtype": "u1",
                    "shape": list(p["ground_mix_ids"].shape)},
        "mix_w": {"field": "ground_mix_w", "dtype": "u1",
                  "shape": list(p["ground_mix_w"].shape)}})
    arrays["ground_class"] = p["ground_class"].astype(np.uint8)
    arrays["ground_mix_ids"] = p["ground_mix_ids"].astype(np.uint8)
    arrays["ground_mix_w"] = np.clip(
        np.round(p["ground_mix_w"] * 255.0), 0, 255).astype(np.uint8)

    for pid, label, color in (
            ("waterfalls", "Waterfalls", [80, 200, 240]),
            ("vents_pts", "Marine vents", [240, 80, 50]),
            ("springs", "Hot springs", [240, 160, 60])):
        key = {"waterfalls": "waterfalls", "vents_pts": "vents",
               "springs": "hot_springs"}[pid]
        layers.append({"id": pid, "label": label, "kind": "points",
                       "points": result["points"][key], "color": color})

    return write_pack(out_path, layers, arrays,
                      {"generator": "k14_flora", "pack": "d0_derived",
                       "seed": result["seed"]})
