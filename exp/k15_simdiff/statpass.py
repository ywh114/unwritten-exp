"""K15 stat-settling pass — pre-engine calibration report (spec §13).

Runs the LANDED stress stack (stress_adapter.evaluate over the real
world) for every authored flora preset and reports the numbers the
(cal) knobs must be settled against, BEFORE the engine exists:

- per-preset reduced fields (spec §5.1): F_worst (worst month), the
  genesis range (F_worst >= GENESIS_F), the colonizable range
  (F_worst >= EST_F_MIN), the biome composition of the genesis range,
  and the binding constraint histogram (which requirement is the worst
  factor at the cell's worst month).
- per-preset provisional vital rates (FloraSim.vital) against the §6
  constraints: can the plan GROW at s = 0 (birth > death), does it
  persist under the density term in its own genesis cells (equilibrium
  N* vs N_FLOOR, from K = productivity and percap = crown^2 (1+wood) /
  BIOMASS_REF).
- knob checks (spec §13): DIE_K half-life constraint, range-size
  distribution vs the partition knobs, dispersal pmf / jump_rate
  side-by-side (content nits).

The knob defaults below are the spec §13 values UNDER SETTLEMENT —
when the engine lands they move to its module constants and this
report is the regression reference. Pure functions + constants; no
draws anywhere (the stress stack is deterministic), so two runs are
byte-identical.

Usage:  PYTHONPATH=. uv run python -m exp.k15_simdiff.statpass --seed 1 [2 ...]
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np

from exp.k11_worldgen.biomes import BIOMES
from exp.k13_treegen.flora.backbone import GEN_TIME_COEFF, GEN_TIME_EXP
from exp.k13_treegen.flora.content import load_content
from exp.k13_treegen.flora.sim import FloraSim
from exp.k15_simdiff import stress_adapter as sa

FLORA_CONTENT = Path("exp/k13_treegen/content/flora")
K14_OUT = Path("exp/k14_worldprod/out")

# ── spec §13 defaults under settlement (cal) ──────────────────────────
ROUND_YEARS = 100
GENESIS_F = 0.5      # settled 2026-08-01 (stat pass seeds 1-3)
EST_F_MIN = 0.3      # settled 2026-08-01 (stat pass seeds 1-3)
N_FLOOR = 0.01
BIOMASS_REF = 25.0
PROD_CAP_SCALE = 1.0
DENS_C = 0.5
DENS_CAP = 2.0
VIG_K = 0.5
DIE_K = 0.002
PART_AREA_REF = 200
PART_K_MAX = 8
PART_MIN_CELLS = 20

# a "generalist" flag: genesis range larger than this share of the
# plan's medium-valid cells
GENERALIST_SHARE = 0.30
# freshwater habitat mask floor for percentile stats (mean annual
# fresh_availability above this counts as freshwater-valid)
FRESH_MASK_MIN = 0.01


# ── reduced fields (spec §5.1) ────────────────────────────────────────


def reduced(factors: dict[str, np.ndarray]):
    """Worst-month reduction: m*(c), F_worst(c), and per-requirement
    provenance at m*(c) (one aggregation for selection + demography)."""
    F = factors["F"]
    m_star = F.argmin(axis=0)                                   # (H,W)
    F_worst = np.take_along_axis(F, m_star[None], axis=0)[0]
    names = [k for k in factors if k not in ("F", "s_env",
                                             "substrate_share")]
    prov = np.stack([
        np.take_along_axis(factors[r], m_star[None], axis=0)[0]
        for r in names
    ])                                                          # (R,H,W)
    return names, m_star, F_worst, prov


def valid_mask(view: dict, ctx: sa.WorldContext) -> np.ndarray:
    """Cells where the plan's medium is possible (for range SHARES and
    percentiles — the counts themselves already carry the medium /
    habitat factors)."""
    medium = view.get("medium", "land")
    if medium == "dual":
        return np.ones((ctx.H, ctx.W), dtype=bool)
    if medium == "water":
        sal = view.get("salinity_tolerance")
        freshwater = isinstance(sal, (int, float)) \
            and sal < sa.FRESH_SAL_MAX
        if freshwater:
            return ctx.fresh_availability.mean(axis=0) > FRESH_MASK_MIN
        return ctx.water_cell
    return ctx.land_cell


def capacity_anchor(seed: int, ctx: sa.WorldContext) -> np.ndarray:
    """K(c) at anchor: the K14 annual productivity products mean-pooled
    1024 -> 256 (calibration-grade; the engine will re-derive exactly).
    Land reads terrestrial, ocean marine, lakes/rivers freshwater."""
    with np.load(K14_OUT / f"seed_{seed:08d}" / "derived.npz") as d:
        def pool(key):
            a = np.nan_to_num(d[key].astype(np.float64))
            return a.reshape(ctx.H, 4, ctx.W, 4).mean(axis=(1, 3))
        terr, marine, fresh = (pool("terrestrial_productivity"),
                               pool("marine_productivity_ann"),
                               pool("freshwater_productivity_ann"))
    ocean = ctx.water_cell & (ctx.bathy > 0)
    lake = ctx.water_cell & ~ocean
    K = np.where(ctx.land_cell, terr,
                 np.where(ocean, marine, fresh))
    return np.nan_to_num(K).astype(np.float32)


# ── per-preset stats ──────────────────────────────────────────────────


def preset_traits(pack, pid: str) -> dict:
    p = pack.presets[pid]
    return {**p.get("knobs", {}), **p.get("axes", {}),
            "plan": p["preset"]["plan"], "preset": pid}


def partition_k(range_cells: int) -> int:
    """Spec §10 verbatim: K = clip(1 + floor(log2(range / REF)), 1, 8)."""
    if range_cells <= 0:
        return 0
    return int(min(PART_K_MAX,
                   max(1, 1 + math.floor(
                       math.log2(range_cells / PART_AREA_REF)))))


def analyze_preset(pid: str, pack, sim: FloraSim, ctx: sa.WorldContext,
                   K: np.ndarray, biome_of: np.ndarray) -> dict:
    view = sa.preset_view(pid, pack)
    factors = sa.evaluate(view, ctx)
    share = factors["substrate_share"]          # capacity split U(c)
    names, _m, F_worst, prov = reduced(factors)
    del factors
    valid = valid_mask(view, ctx)
    n_valid = int(valid.sum())

    gen = (F_worst >= GENESIS_F) & valid
    col = (F_worst >= EST_F_MIN) & valid
    n_gen, n_col = int(gen.sum()), int(col.sum())

    # biome composition of the genesis range
    biomes: dict[str, int] = {}
    if n_gen:
        ids, cnt = np.unique(biome_of[gen], return_counts=True)
        for i, c in sorted(zip(ids.tolist(), cnt.tolist()),
                           key=lambda t: -t[1]):
            biomes[BIOMES[i]["name"] if i < len(BIOMES) else str(i)] = c

    # binding constraint over colonizable cells (min factor at m*)
    binding: dict[str, int] = {}
    if n_col:
        idx = prov[:, col].argmin(axis=0)
        for r, c in zip(*np.unique(idx, return_counts=True)):
            binding[names[int(r)]] = int(c)

    fw = F_worst[valid]
    q = np.percentile(fw, [50, 90, 99]) if n_valid else [0.0] * 3
    s_env_gen = float((1.0 - 2.0 * F_worst[gen]).mean()) if n_gen else None

    # vital rates + density-term equilibrium in the genesis range
    traits = preset_traits(pack, pid)
    rates = sim.vital(traits, pack)
    height = max(float(traits.get("height_m") or 0.0), 1e-6)
    gen_time = GEN_TIME_COEFF * height ** GEN_TIME_EXP
    crown = float(traits.get("crown_spread_m") or 0.0)
    wood = min(max(float(traits.get("woodiness") or 0.0), 0.0), 1.0)
    percap = crown ** 2 * (1.0 + wood) / BIOMASS_REF
    K_med = float(np.median(K[gen])) if n_gen else (
        float(np.median(K[valid])) if n_valid else 0.0)
    U_med = float(np.median(share[gen])) if n_gen else (
        float(np.median(share[valid])) if n_valid else 1.0)
    K_eff = PROD_CAP_SCALE * K_med * U_med     # capacity split (§6 v0.3)
    n_star = None
    if rates.birth > 0 and percap > 0 and K_eff > 0:
        d_star = K_eff / DENS_C * max(0.0, 1.0 - rates.death / rates.birth)
        n_star = d_star / percap

    ch = traits.get("dispersal_channels") or {}
    flags = []
    if n_gen < PART_MIN_CELLS:
        flags.append("NO_RANGE" if n_gen == 0 else "TINY_RANGE")
    if 0 < n_col < PART_MIN_CELLS:
        flags.append("THIN_COLONIZABLE")
    if n_valid and n_gen > GENERALIST_SHARE * n_valid:
        flags.append("GENERALIST")
    if rates.birth <= rates.death:
        flags.append("VITAL_INVERSION")
    if n_star is not None and n_star < N_FLOOR:
        flags.append("PERSIST_FAIL")

    return {
        "preset": pid,
        "plan": traits["plan"],
        "medium": view.get("medium", "land"),
        "gen_time": round(gen_time, 3),
        "birth": round(rates.birth, 5),
        "death": round(rates.death, 5),
        "establish": round(rates.establish, 4),
        "valid_cells": n_valid,
        "genesis_cells": n_gen,
        "colonizable_cells": n_col,
        "partition_k": partition_k(n_gen),
        "F_worst_q50_q90_q99": [round(float(x), 3) for x in q],
        "s_env_genesis": None if s_env_gen is None else round(s_env_gen, 3),
        "K_median": round(K_med, 4),
        "U_median": round(U_med, 3),
        "percap": round(percap, 4),
        "n_star": None if n_star is None else round(n_star, 5),
        "biomes": dict(list(biomes.items())[:4]),
        "binding": dict(sorted(binding.items(),
                               key=lambda t: -t[1])[:4]),
        "dispersal": {"channels": ch,
                      "jump_rate": traits.get("jump_rate"),
                      "propagule_mass_mg": traits.get("propagule_mass_mg"),
                      "propagule_count": traits.get("propagule_count"),
                      "seed_bank": traits.get("seed_bank")},
        "flags": flags,
    }


# ── knob checks (spec §13 constraints) ────────────────────────────────


def knob_checks(rows: list[dict]) -> list[str]:
    out = []
    half = math.log(2) / (DIE_K * 0.3 * ROUND_YEARS)
    out.append(f"DIE_K={DIE_K}: density half-life at sustained s=0.3 is "
               f"{half:.1f} rounds (spec constraint: >= 5) "
               f"{'OK' if half >= 5 else 'VIOLATED'}")
    no_range = [r["preset"] for r in rows if r["genesis_cells"] == 0]
    out.append(f"GENESIS_F={GENESIS_F}: {len(no_range)}/{len(rows)} "
               f"presets have NO genesis range on this seed"
               + (f": {', '.join(no_range)}" if no_range else ""))
    thin = [r["preset"] for r in rows
            if r["colonizable_cells"] < PART_MIN_CELLS]
    out.append(f"EST_F_MIN={EST_F_MIN}: {len(thin)}/{len(rows)} presets "
               f"colonize < {PART_MIN_CELLS} cells"
               + (f": {', '.join(thin)}" if thin else ""))
    inv = [r["preset"] for r in rows if "VITAL_INVERSION" in r["flags"]]
    out.append(f"vital: {len(inv)} presets cannot grow at s=0 "
               f"(birth <= death): {', '.join(inv) or 'none'}")
    fail = [r["preset"] for r in rows if "PERSIST_FAIL" in r["flags"]]
    out.append(f"density: {len(fail)} presets equilibrate below N_FLOOR "
               f"in their own genesis range (percap vs K): "
               f"{', '.join(fail) or 'none'}")
    return out


# ── report ────────────────────────────────────────────────────────────


def report(seed: int) -> dict:
    pack = load_content(FLORA_CONTENT)
    sim = FloraSim(pack)
    ctx = sa.load_world(seed)
    K = capacity_anchor(seed, ctx)
    with np.load(sa.K11_OUT / f"seed_{seed:08d}" / "world.npz") as z:
        biome_of = z["w_biome_map"].astype(int)
    rows = [analyze_preset(pid, pack, sim, ctx, K, biome_of)
            for pid in sorted(pack.presets)]
    return {"seed": seed, "knobs": {
                "GENESIS_F": GENESIS_F, "EST_F_MIN": EST_F_MIN,
                "N_FLOOR": N_FLOOR, "BIOMASS_REF": BIOMASS_REF,
                "PROD_CAP_SCALE": PROD_CAP_SCALE, "DENS_C": DENS_C,
                "VIG_K": VIG_K, "DIE_K": DIE_K,
                "PART_AREA_REF": PART_AREA_REF,
                "PART_K_MAX": PART_K_MAX,
                "PART_MIN_CELLS": PART_MIN_CELLS},
            "checks": knob_checks(rows), "presets": rows}


def _fmt_row(r: dict) -> str:
    biomes = ", ".join(f"{k} {v}" for k, v in
                       list(r["biomes"].items())[:2])
    bind = ", ".join(f"{k.split(':')[-1]} {v}" for k, v in
                     list(r["binding"].items())[:2])
    nstar = "-" if r["n_star"] is None else f"{r['n_star']:.3f}"
    return (f"{r['preset']:<34} {r['medium']:<5} "
            f"b/d {r['birth']:.4f}/{r['death']:.4f} "
            f"e {r['establish']:.2f} "
            f"gen {r['genesis_cells']:>6} col {r['colonizable_cells']:>6} "
            f"K* {r['partition_k']} N* {nstar:>7} "
            f"| {biomes:<38} | {bind:<28} "
            f"{' '.join(r['flags'])}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, nargs="+", default=[1])
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args()
    all_reports = []
    for seed in args.seed:
        rep = report(seed)
        all_reports.append(rep)
        print(f"\n══ seed {seed} ══")
        for line in rep["checks"]:
            print(f"  · {line}")
        print()
        for r in rep["presets"]:
            print(_fmt_row(r))
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(all_reports, indent=1))
        print(f"\nwrote {args.json}")


if __name__ == "__main__":
    main()
