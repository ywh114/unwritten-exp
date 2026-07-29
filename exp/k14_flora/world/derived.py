"""K14 P6 — derived-products layer D0: ecology-relevant fields computed
from a K11 world dump (read-only input, via exp.artifacts).

    uv run python -m exp.k14_flora.world.derived --seed 1

Writes to exp/k14_flora/out/world/seed_NNNNNNNN/ (gitignored):
    derived.npz      the engine form (all products, delivery 1024²)
    derived.k11pack  the viewer form (unified overlay datapack)
    manifest.json    input provenance (exp.artifacts stamp+hash)

Everything here is a single-pass raster/graph op over the K11 fields —
no pipeline internals, no re-derived physics (growing season and HAND
come from K11's own products). Constants below are literature regime
values or documented conventions, NOT tuning knobs (units.py ruling:
never tune the world through its readers).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from exp.artifacts import require as artifact_require
from exp.artifacts import write_manifest
from exp.k11_worldgen.units import alt_m, hand_m, precip_mm, temp_c

HERE = Path(__file__).parent
OUT = HERE.parent / "out"          # out/seed_NNNNNNNN/ (shared with the
                                   # k14 tree json+report — one dir per
                                   # seed, derived products flat inside)

# ── waterfalls / rapids (single 4 km step drops at L0 fidelity) ─────────
RAPIDS_DROP_M = 25.0            # concentrated drop -> rapids
FALLS_DROP_M = 75.0             # gorge-grade drop -> waterfall

# ── productivity advection (semi-Lagrangian relaxation) ─────────────────
ADV_STEPS = 4                   # downstream spreading steps
ADV_RETAIN = 0.7                # fraction carried one step downstream
UPWELL_WEIGHT = 1.0             # upwelling vs plume source balance
PLUME_WEIGHT = 0.6
# background production: algae do not need an upwelling — sunlight and
# warmth run the open gyres on recycled nutrients (owner 2026-07-30:
# "it shouldn't all be from upwellings — algae ~ sunlight, temp, wind")
NUTRIENT_FLOOR = 0.15           # recycled-nutrient background
TEMP_OPT_C = 25.0               # Eppley-ish reference, 2^((T-opt)/10)
WIND_MIX_WEIGHT = 0.25          # mixed-layer renewal bonus at ~8 m/s
WIND_REF_MS = 8.0

# ── growing season ──────────────────────────────────────────────────────
GROW_T_C = 5.0                  # months above this count (K11 convention)

# ── vents / hot springs ─────────────────────────────────────────────────
VENT_PERCENTILE = 90.0          # activity threshold for point extraction
FAULT_DECAY_CELLS = 3.0         # fault proximity decay (p_fault_dist is
                                # in CELLS, 0..~130 — not normalized)
VENT_SUPPRESS = 3               # non-max suppression radius (anchor cells)
VENT_MAX_POINTS = 40            # per kind, ranked by activity

_D8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0),
       (1, 1)]


# ── small array helpers ─────────────────────────────────────────────────


def _upsample(a: np.ndarray, factor: int) -> np.ndarray:
    """Bilinear upsample by an integer factor (numpy-only; kron reads
    blocky on continuous fields — the marine-biome lesson)."""
    H, W = a.shape
    ys = (np.arange(H * factor) + 0.5) / factor - 0.5
    xs = (np.arange(W * factor) + 0.5) / factor - 0.5
    y0 = np.clip(np.floor(ys).astype(int), 0, H - 2)
    x0 = np.clip(np.floor(xs).astype(int), 0, W - 2)
    fy = np.clip(ys - y0, 0.0, 1.0)[:, None]
    fx = np.clip(xs - x0, 0.0, 1.0)[None, :]
    a00 = a[np.ix_(y0, x0)]
    a01 = a[np.ix_(y0, x0 + 1)]
    a10 = a[np.ix_(y0 + 1, x0)]
    a11 = a[np.ix_(y0 + 1, x0 + 1)]
    return (a00 * (1 - fy) * (1 - fx) + a01 * (1 - fy) * fx
            + a10 * fy * (1 - fx) + a11 * fy * fx)


def _rank01(a: np.ndarray) -> np.ndarray:
    """Rank normalize to (0,1) — robust across worlds, no hard scale."""
    flat = a.ravel()
    order = flat.argsort().argsort()
    return (order / max(1, flat.size - 1)).reshape(a.shape)


def _norm01(a: np.ndarray, pct: float = 99.0) -> np.ndarray:
    """Percentile normalize, leaky above the percentile (no hard clip
    semantics — values may exceed 1 slightly, consumers treat 1 as
    'reference max')."""
    ref = float(np.percentile(a, pct))
    if ref <= 0:
        return np.zeros_like(a)
    return a / ref


def _local_maxima(a: np.ndarray, radius: int,
                  threshold: float) -> list[tuple[int, int, float]]:
    """Non-max suppression: candidates above threshold, taken in
    descending activity, each suppressing its (2r+1)² neighborhood.
    Plateau-tolerant (fault lines tie) and deterministic."""
    H, W = a.shape
    ys, xs = np.nonzero(a >= threshold)
    order = np.argsort(-a[ys, xs])
    suppressed = np.zeros((H, W), bool)
    out = []
    for i in order.tolist():
        y, x = int(ys[i]), int(xs[i])
        if suppressed[y, x]:
            continue
        out.append((y, x, float(a[y, x])))
        suppressed[max(0, y - radius):y + radius + 1,
                   max(0, x - radius):x + radius + 1] = True
    return out


def _advect(source: np.ndarray, u: np.ndarray, v: np.ndarray,
            retain: float) -> np.ndarray:
    """Semi-Lagrangian relaxation: f <- source + retain x f(back-
    trajectory), ADV_STEPS times. u/v normalized so the max speed moves
    ~1 cell per step. Deterministic, O(steps x cells)."""
    H, W = source.shape
    speed = np.hypot(u, v)
    vmax = float(speed.max())
    if vmax <= 0:
        return source.copy()
    un, vn = u / vmax, v / vmax
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    f = source.copy()
    for _ in range(ADV_STEPS):
        sy = np.clip(yy - vn, 0, H - 1.001)
        sx = np.clip(xx - un, 0, W - 1.001)
        y0, x0 = sy.astype(int), sx.astype(int)
        fy, fx = sy - y0, sx - x0
        adv = (f[y0, x0] * (1 - fy) * (1 - fx) + f[y0, x0 + 1] * (1 - fy) * fx
               + f[y0 + 1, x0] * fy * (1 - fx) + f[y0 + 1, x0 + 1] * fy * fx)
        f = source + retain * adv
    return f


# ── products ────────────────────────────────────────────────────────────


def _river_fields(z) -> tuple[np.ndarray, np.ndarray]:
    """The persisted K11 river-speed / river-ice fields (first-class in
    K11 hydrology+solar — K14 reads them, it does NOT re-derive
    hydraulics). Returns (speed (H,W) m/s, river ice (12,H,W))."""
    for k in ("h_river_speed", "c_riverice_monthly"):
        if k not in z:
            raise KeyError(
                f"{k} missing from the k11 dump — regenerate the world "
                f"(post-speed pipeline): uv run python -m "
                f"exp.k11_worldgen demo --seed N --viewexport")
    return z["h_river_speed"], z["c_riverice_monthly"]


def waterfalls(z, sea: float) -> list[dict]:
    """Concentrated drops along flow_dir on river cells. At 4 km cells a
    single-step drop of 25 m+ is a real gorge/fall at L0 fidelity.
    Basin id = the terminal (outflow) cell's anchor index, found by
    path-halving over the downstream successor map."""
    alt = alt_m(z["w_elev"], sea)
    H, W = alt.shape
    fdir = z["h_flow_dir"]
    river = z["h_river_mask"]
    # terminal-basin map by path halving (terminals point to
    # themselves, so squaring the successor map converges in log2 steps)
    idx = np.arange(H * W, dtype=np.int64).reshape(H, W)
    down = np.full((H, W), -1, dtype=np.int64)
    drop = np.zeros((H, W))
    for i, (dy, dx) in enumerate(_D8):
        m = fdir == i
        ny = np.clip(np.arange(H)[:, None] + dy, 0, H - 1)
        nx = np.clip(np.arange(W)[None, :] + dx, 0, W - 1)
        down = np.where(m, idx[ny, nx], down)
        drop = np.where(m, alt - alt[ny, nx], drop)
    succ = np.where(down < 0, idx, down).ravel()
    for _ in range(17):             # 2^17 > H*W: any path fully jumped
        succ = succ[succ]
    basin = succ.reshape(H, W)
    out = []
    ys, xs = np.nonzero(river & (drop >= RAPIDS_DROP_M))
    for y, x in zip(ys.tolist(), xs.tolist()):
        out.append({"y": y, "x": x, "drop_m": round(float(drop[y, x]), 1),
                    "order": int(z["h_order"][y, x]),
                    "basin": int(basin[y, x]),
                    "kind": "waterfall" if drop[y, x] >= FALLS_DROP_M
                    else "rapids"})
    out.sort(key=lambda p: -p["drop_m"])
    return out


def _solar_fields(z) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The persisted solar/freezing fields (K11 solar.py, first-class
    since 2026-07-30 — no ad-hoc sunlight downstream). Returns
    (insolation (12,H), sea-ice (12,H,W), lake-ice (12,H,W))."""
    for k in ("c_insol_monthly", "c_seaice_monthly", "c_lakeice_monthly"):
        if k not in z:
            raise KeyError(
                f"{k} missing from the k11 dump — regenerate the world "
                f"(post-solar pipeline): uv run python -m "
                f"exp.k11_worldgen demo --seed N --viewexport")
    return z["c_insol_monthly"], z["c_seaice_monthly"], \
        z["c_lakeice_monthly"]


def marine_productivity(z, currents: dict | None) -> np.ndarray:
    """Monthly marine productivity (12, 256²), normalized:
    nutrient x light x temperature x wind mixing. Nutrient = upwelling
    (r_rise_m) + river-plume injection at mouths, advected downstream,
    over the recycled-production floor. Light = the PERSISTED monthly
    insolation, cut by sea-ice cover. Temperature = Eppley-ish
    2^((T-25)/10) capped at 1. Wind = mixed-layer renewal bonus."""
    insol, seaice, _ = _solar_fields(z)
    ocean = z["h_ocean_mask"] | z["h_sea_mask"]
    # plume source: discharge at river cells whose downstream is ocean
    dis = z["h_discharge"]
    fdir = z["h_flow_dir"]
    H, W = dis.shape
    plume = np.zeros_like(dis)
    for i, (dy, dx) in enumerate(_D8):
        m = fdir == i
        ny = np.clip(np.arange(H)[:, None] + dy, 0, H - 1)
        nx = np.clip(np.arange(W)[None, :] + dx, 0, W - 1)
        to_ocean = np.zeros((H, W), bool)
        to_ocean[ny, nx] = ocean[ny, nx]
        plume = np.where(m & z["h_river_mask"] & to_ocean, dis, plume)
    plume = _norm01(plume) * PLUME_WEIGHT

    sst = temp_c(z["c_T_monthly"])                  # (12, H, W)
    temp_term = np.minimum(2.0 ** ((sst - TEMP_OPT_C) / 10.0), 1.0)
    wscale = float(z["c_wind_scale"]) if "c_wind_scale" in z else 1.0
    wind = (np.hypot(z["c_wind_u"].mean(axis=1),
                     z["c_wind_v"].mean(axis=1)) * wscale)  # (12,128,128)
    mixing = 1.0 + WIND_MIX_WEIGHT * np.clip(wind / WIND_REF_MS, 0.0, 1.0)

    out = np.zeros((12, H, W))
    for m in range(12):
        up = np.clip(z["r_rise_m"][m], 0.0, None)
        source = _norm01(up) * UPWELL_WEIGHT + plume
        if currents is not None:
            from exp.k11_worldgen.currents import velocity_field
            u, v = velocity_field(currents, m)
        else:
            u = z["r_u"]
            v = z["r_v"]
        nutrient = NUTRIENT_FLOOR + _advect(source, u, v, ADV_RETAIN)
        light = insol[m][:, None] * (1.0 - seaice[m])
        prod = (nutrient * light * temp_term[m]
                * _upsample(mixing[m], 2))
        # normalize AFTER the full product (the upwelling tail stacks
        # otherwise); leaky above the reference
        out[m] = np.where(ocean, _norm01(prod), 0.0)
    return out


def soil_fertility(z) -> np.ndarray:
    """F = rank(accumulation) x (1 - rank(HAND)) on land — sediment
    deposition without waterlogging (riverine/alluvial peaks)."""
    land = ~z["h_ocean_mask"] & ~z["h_sea_mask"] & ~z["h_lake_mask"]
    f = _rank01(z["h_accumulation"]) * (1.0 - _rank01(z["h_hand"]))
    return np.where(land, f, 0.0)


def freshwater_productivity(z) -> np.ndarray:
    """Lake/river productivity: warmth x inflow x shallowness, all
    rank-based (no hard scale), shallow warm lakes peak — cut by the
    annual ice-free fraction (persisted lake/river ice)."""
    _, _, lakeice = _solar_fields(z)
    _, riverice = _river_fields(z)
    water = z["h_lake_mask"] | z["h_river_mask"]
    ice = np.where(z["h_river_mask"], riverice, lakeice)
    warm = np.clip(temp_c(z["c_T"]), 0.0, None)
    shallow = 1.0 - _rank01(z["h_depth"])
    ice_free = 1.0 - ice.mean(axis=0)
    f = (_rank01(warm) * _rank01(z["h_accumulation"]) * shallow
         * ice_free)
    return np.where(water, f, 0.0)


def growing_season(z) -> np.ndarray:
    """Months with mean T above GROW_T_C (K11's own threshold
    convention), at anchor res."""
    t = temp_c(z["c_T_monthly"])          # (12, 256, 256)
    return (t > GROW_T_C).sum(axis=0).astype(np.float64)


def vents(z, manifest: dict) -> tuple[np.ndarray, list[dict], list[dict]]:
    """Vent field (fault activity) + point extraction: marine vents on
    active convergent/subduction faults, hot springs on land activity
    maxima. Ranked by activity, capped per kind. fault_conv is SIGNED —
    only the positive (active) half feeds the field; fault_dist is in
    cells, decayed over FAULT_DECAY_CELLS."""
    activity = (np.clip(z["p_fault_conv"], 0.0, None)
                * np.exp(-z["p_fault_dist"] / FAULT_DECAY_CELLS))
    thr = float(np.percentile(activity, VENT_PERCENTILE))
    ocean = z["h_ocean_mask"] | z["h_sea_mask"]
    pts = _local_maxima(activity, VENT_SUPPRESS, max(thr, 1e-9))
    vents_m = sorted((p for p in pts if ocean[p[0], p[1]]),
                     key=lambda p: -p[2])
    springs = sorted((p for p in pts if not ocean[p[0], p[1]]),
                     key=lambda p: -p[2])
    vp = [{"y": y, "x": x, "activity": round(a, 4)}
          for y, x, a in vents_m[:VENT_MAX_POINTS]]
    sp = [{"y": y, "x": x, "activity": round(a, 4)}
          for y, x, a in springs[:VENT_MAX_POINTS]]
    return activity, vp, sp


# ── assembly ────────────────────────────────────────────────────────────


class _Npz(dict):
    """dict over the npz (single open) so products read fields without
    re-opening; carries the seed dir for the currents payload."""
    _seed_dir: Path

    def __init__(self, seed_dir: Path):
        with np.load(seed_dir / "world.npz") as z:
            super().__init__((k, z[k]) for k in z.files)
        self._seed_dir = seed_dir


def load_inputs(seed: int) -> tuple[dict, dict, Path]:
    """(npz fields, world.json manifest, seed_dir) for a K11 dump."""
    seed_dir = artifact_require("k11", seed)
    z = _Npz(seed_dir)
    manifest = json.loads((seed_dir / "world.json").read_text())
    return z, manifest, seed_dir


def build(seed: int) -> dict:
    """All D0 products at delivery resolution (1024²) + point lists."""
    z, manifest, _ = load_inputs(seed)
    sea = float(manifest["sea_level"])
    factor = 4  # 256² anchor -> 1024² delivery
    # delivery-resolution masks (mask AFTER upsampling — bilinear bleed
    # across the shoreline otherwise leaks ocean products onto land)
    d_ocean = z["d_ocean_mask"] | z["d_sea_mask"]
    d_land = ~d_ocean & ~z["d_lake_mask"]
    d_fresh = z["d_lake_mask"] | z["d_river_mask"]

    products: dict[str, np.ndarray] = {}
    points: dict[str, list] = {}

    spd, _ = _river_fields(z)
    products["river_speed"] = np.where(
        z["d_river_mask"], _upsample(spd, factor), 0.0)
    points["waterfalls"] = waterfalls(z, sea)
    mprod = marine_productivity(z, _currents_payload(z))
    products["marine_productivity"] = np.stack(
        [np.where(d_ocean, _upsample(mprod[m], factor), 0.0)
         for m in range(12)])
    products["marine_productivity_ann"] = np.where(
        d_ocean, _upsample(mprod.mean(axis=0), factor), 0.0)
    products["soil_fertility"] = np.where(
        d_land, _upsample(soil_fertility(z), factor), 0.0)
    products["freshwater_productivity"] = np.where(
        d_fresh, _upsample(freshwater_productivity(z), factor), 0.0)
    products["growing_season"] = np.where(
        d_land, _upsample(growing_season(z), factor), 0.0)
    vent_field, vent_pts, spring_pts = vents(z, manifest)
    products["vent_field"] = _upsample(vent_field, factor)
    points["vents"] = vent_pts
    points["hot_springs"] = spring_pts
    # points carry anchor coords; scale to delivery for the viewer
    for lst in points.values():
        for p in lst:
            p["y"], p["x"] = p["y"] * factor, p["x"] * factor
    return {"seed": seed, "products": products, "points": points}


def _currents_payload(z) -> dict | None:
    """The persisted currents payload for monthly velocity_field (falls
    back to the annual mean field when absent)."""
    try:
        from exp.k11_worldgen.persist import load_world
        return load_world(str(z._seed_dir))["world"]["currents"]
    except Exception:
        return None


def save(result: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_dir / "derived.npz",
                        **result["products"],
                        **{f"pts_{k}": json.dumps(v)
                           for k, v in result["points"].items()})
    write_manifest(out_dir, inputs=[("k11", result["seed"])],
                   note="k14 D0 derived products")
    from exp.k14_flora.world.datapack import build_pack
    build_pack(result, out_dir / "derived.k11pack")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    out = args.out or (OUT / f"seed_{args.seed:08d}")
    result = build(args.seed)
    save(result, out)
    for name, a in result["products"].items():
        print(f"  {name}: {a.shape} mean={a.mean():.4f} "
              f"max={a.max():.4f}")
    for name, lst in result["points"].items():
        print(f"  {name}: {len(lst)} points")
    print(out)


if __name__ == "__main__":
    main()
