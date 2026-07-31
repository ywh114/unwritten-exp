"""K15 — B5 §8 acceptance/demo driver for the flora stress adapter.

    PYTHONPATH=. uv run python -m exp.k15_simdiff --seed 1

Loads the flora tree (exp/k13_treegen/out/k14_seedNNNNNNNN.json) and the
anchor world context, evaluates all 150 radiated species (timed), and
prints the B5 §8 acceptance table on seed 1:

  (1) determinism — two full runs, byte-identical arrays;
  (2) mangrove-grade — the wet-adapted coastal tree's lowest stress is
      in the high-HAND coastal band (graded, not binary);
  (3) xeric-grade — high stress on wetland (fen/bog/gleysol) cells,
      low in its arid band;
  (4) kelp-grade — low stress only on hard, shallow, photic bottom;
      deep soft bottom ≈ 1;
  (5) calcifuge — lower stress on podzol/bog than rendzina/caliche;
      a freshwater taxon in bog-blackwater cells scores per its
      ph_tolerance position;
  (7) budget — full 150-species annual evaluation ≤ 5 s;
  (8) signed scale — an every-axis-near-optimal cell reads s < 0.

The acceptance presets are evaluated as AUTHORED traits (B5 §1 stat
settling and §8 wording are about the authored presets; radiated
species drift far from them — e.g. a willow species with root_depth
16.8 m is not a willow). The timing/determinism checks run the 150
radiated species, which is the spec's budget unit.

Determinism: everything here is a pure function of (world dump, record)
— no draws — so the two timing runs must be byte-identical.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from exp.k13_treegen.flora.__main__ import CONTENT as FLORA_CONTENT
from exp.k13_treegen.flora.content import ContentPack, load_content
from exp.k13_treegen.model import Rank, Tree
from exp.k14_worldprod.derived import _spread_max
from exp.k14_worldprod.ground import GROUND_ID
from exp.k15_simdiff.stress_adapter import (
    WorldContext,
    annual_stress,
    evaluate,
    load_world,
    preset_view,
    species_view,
)

HERE = Path(__file__).resolve().parent
TREE_OUT = HERE.parent / "k13_treegen" / "out"

# ── acceptance band definitions (seed 1; named tunables) ───────────────
# The high-HAND coastal band (B5 §8.2): HAND waterlogging is exp(-hand/
# HAND_REF) — the "high-HAND" band is the drainage-adjacent lowland
# (hand below HAND_WET_M) within COASTAL_REACH_C cells (~48 km at the
# 4 km anchor) of the ocean. Graded, not binary: mean stress inside the
# band must sit below the outside mean, and the global minimum must
# fall in the band.
COASTAL_REACH_C = 12
HAND_WET_M = 1.0
# wetland cells for the xeric check (B5 §8.3): the dominant ground
# class is fen/bog/gleysol.
WETLAND_CLASSES = (GROUND_ID["fen"], GROUND_ID["bog"], GROUND_ID["gleysol"])
# arid band for the xeric check: annual-mean normalized P below this
# (~80 mm/yr at 400 mm/month max).
ARID_P_ANN = 0.2
# kelp-grade substrate/depth bands (B5 §8.4): eff_hard mix share and
# column-depth thresholds.
KELP_HARD = 0.7
KELP_DEEP_M = 500.0
# calcifuge soils (B5 §8.5): acid (podzol/bog) vs alkaline
# (rendzina/caliche); bog-blackwater = dominant bog class with low
# water pH.
ACID_CLASSES = (GROUND_ID["podzol"], GROUND_ID["bog"])
ALKALINE_CLASSES = (GROUND_ID["rendzina"], GROUND_ID["caliche"])
BLACKWATER_PH = 5.5
# budget (B5 §8.7).
BUDGET_S = 5.0
# near-optimal threshold for the signed-scale check (B5 §8.8).
NEAR_OPTIMAL_F = 0.8

# the acceptance presets (authored traits — see module docstring).
MANGROVE_PRESET = "tree.willow"     # closest authored wetland tree
XERIC_PRESET = "succulent.cactus"
KELP_PRESET = "macroalgae_holdfast.kelp"
CALCIFUGE_PRESET = "shrub.heath"    # acid-heath calcifuge (Calluna)
BOG_TAXON_PRESET = "moss_grade.sphagnum"
FRESH_TAXON_PRESET = "floater.duckweed"
VIGOR_TAXON_PRESET = "floater.duckweed"

_RESOLUTIONS = (
    "- no mangrove flora plan/preset exists in the content pack; "
    "tree.willow (the\n    closest authored wetland tree, waterlogging "
    "tolerance 0.8) is the\n    mangrove-grade proxy for B5 §8.2",
    "- the [niche] moisture_opt/moisture_breadth are positions on the\n"
    "    normalized 0..1 P scale (c_P_monthly raw), so the climate P\n"
    "    term reads that scale; water-medium plans do not pay a\n"
    "    precipitation cost (their moisture niche is the water itself,\n"
    "    carried by the habitat/medium terms)",
    "- acceptance presets evaluate AUTHORED traits: radiated species\n"
    "    drift far from their preset (a willow species with root_depth\n"
    "    16.8 m is not a willow); the budget/determinism checks run the\n"
    "    150 radiated species",
    "- the anchor ground mix is not persisted (only ground_d2); it is\n"
    "    re-derived by re-running the deterministic B3 pass and verified\n"
    "    bit-for-bit against the persisted ground_eff_* rasters",
    "- water_ph at anchor extends fresh_ph to land cells carrying\n"
    "    implicit freshwater habitat (fresh_availability > 0): the\n"
    "    bog-blackwater chemistry of B5 §7.2 (\"the chemistry once in\")",
)


def dist_to_ocean(ctx: WorldContext) -> np.ndarray:
    """(H,W) int32: 8-connected ring distance to the nearest ocean cell
    (0 on ocean). Deterministic numpy-only dilation."""
    ring = (ctx.bathy > 0).astype(np.float64)
    dist = np.zeros((ctx.H, ctx.W), dtype=np.int32)
    for d in range(1, max(ctx.H, ctx.W)):
        prev = ring > 0.5
        ring = _spread_max(ring, 1) > 0.5
        dist[ring & ~prev & (dist == 0)] = d
    return dist


def _fmt(ok: bool, name: str, detail: str) -> str:
    return f"  [{'PASS' if ok else 'FAIL'}] {name:<48} {detail}"


def check_mangrove(ctx: WorldContext, pack: ContentPack,
                   dist_ocean) -> tuple[bool, str]:
    """B5 §8.2: lowest stress in the high-HAND coastal band, graded."""
    w = annual_stress(evaluate(preset_view(MANGROVE_PRESET, pack), ctx))
    land = ctx.land_cell
    band = land & (dist_ocean <= COASTAL_REACH_C) & (ctx.hand_m < HAND_WET_M)
    y, x = np.unravel_index(np.argmin(w), w.shape)
    in_band = bool(band[y, x])
    band_mean = float(w[band].mean())
    out_mean = float(w[land & ~band].mean())
    ok = in_band and band_mean < out_mean
    detail = (f"min s={w[y, x]:.3f} at ({y},{x}) dist_ocean="
              f"{dist_ocean[y, x]} hand={ctx.hand_m[y, x]:.2f}m "
              f"in-band={in_band}; band n={int(band.sum())} mean "
              f"{band_mean:.4f} vs outside {out_mean:.4f} (graded)")
    return ok, detail


def check_xeric(ctx: WorldContext, pack: ContentPack,
                dist_ocean) -> tuple[bool, str]:
    """B5 §8.3: high stress on wetland cells, low in the arid band."""
    c = annual_stress(evaluate(preset_view(XERIC_PRESET, pack), ctx))
    land = ctx.land_cell
    wetland = land & np.isin(ctx.ground_class, list(WETLAND_CLASSES))
    p_ann = ctx.p_norm.mean(axis=0)
    arid = land & (p_ann < ARID_P_ANN)
    y, x = np.unravel_index(np.argmin(c), c.shape)
    w_mean = float(c[wetland].mean())
    a_mean = float(c[arid].mean())
    gap = w_mean - a_mean
    ok = w_mean > 0.8 and a_mean < 0.7 and gap > 0.3 and bool(arid[y, x])
    detail = (f"wetland(fen/bog/gleysol) n={int(wetland.sum())} mean "
              f"s={w_mean:.3f}; arid(p<{ARID_P_ANN}) n={int(arid.sum())} "
              f"mean s={a_mean:.3f} (gap {gap:+.3f}); global min "
              f"s={c[y, x]:.3f} at ({y},{x}) arid={bool(arid[y, x])}")
    return ok, detail


def check_kelp(ctx: WorldContext, pack: ContentPack,
               dist_ocean) -> tuple[bool, str]:
    """B5 §8.4: low stress only on hard, shallow, photic bottom; deep
    soft bottom ≈ 1."""
    k = annual_stress(evaluate(preset_view(KELP_PRESET, pack), ctx))
    hard_photic = ((ctx.eff_hard > KELP_HARD) & (ctx.bathy > 0)
                   & (ctx.bathy <= ctx.photic))
    deep_soft = (ctx.eff_hard < 0.3) & (ctx.bathy > KELP_DEEP_M)
    y, x = np.unravel_index(np.argmin(k), k.shape)
    h_mean = float(k[hard_photic].mean())
    d_mean = float(k[deep_soft].mean())
    ok = h_mean < 0.25 and d_mean > 0.9 and bool(hard_photic[y, x])
    detail = (f"hard&shallow&photic n={int(hard_photic.sum())} mean "
              f"s={h_mean:.3f} (min {float(k[hard_photic].min()):.3f}); "
              f"deep soft n={int(deep_soft.sum())} mean s={d_mean:.3f}; "
              f"global min s={k[y, x]:.3f} at ({y},{x}) "
              f"hard={ctx.eff_hard[y, x]:.2f} depth={ctx.bathy[y, x]:.0f}m "
              f"photic={ctx.photic[y, x]:.0f}m")
    return ok, detail


def check_calcifuge(ctx: WorldContext, pack: ContentPack,
                    dist_ocean) -> tuple[bool, str]:
    """B5 §8.5: calcifuge lower on podzol/bog than rendzina/caliche; a
    freshwater taxon in bog-blackwater cells scores per its
    ph_tolerance position."""
    from exp.k15_simdiff.req_flora import REQ_PH
    h = annual_stress(evaluate(preset_view(CALCIFUGE_PRESET, pack), ctx))
    land = ctx.land_cell
    acid = land & np.isin(ctx.ground_class, list(ACID_CLASSES))
    alk = land & np.isin(ctx.ground_class, list(ALKALINE_CLASSES))
    a_mean = float(h[acid].mean())
    k_mean = float(h[alk].mean())
    ok1 = a_mean < k_mean
    # bog-blackwater: dominant bog class, low water pH (the implicit
    # hydrology chemistry of B5 §7.2).
    black = land & (ctx.ground_class == GROUND_ID["bog"]) \
        & (ctx.water_ph < BLACKWATER_PH)
    bog = evaluate(preset_view(BOG_TAXON_PRESET, pack), ctx)
    fresh = evaluate(preset_view(FRESH_TAXON_PRESET, pack), ctx)
    bog_ph = float(bog[REQ_PH][0, black].mean())
    fresh_ph = float(fresh[REQ_PH][0, black].mean())
    # sphagnum (ph position 0.05 -> opt pH 4.25) fits blackwater;
    # duckweed (0.5 -> opt 6.5) does not.
    ok2 = bog_ph > fresh_ph + 0.05
    detail = (f"heath on podzol/bog n={int(acid.sum())} mean "
              f"s={a_mean:.3f} vs rendzina/caliche n={int(alk.sum())} mean "
              f"s={k_mean:.3f}; bog-blackwater n={int(black.sum())} "
              f"water_ph mean={float(ctx.water_ph[black].mean()):.2f}: "
              f"sphagnum REQ_PH={bog_ph:.3f} vs duckweed "
              f"REQ_PH={fresh_ph:.3f} (per-position)")
    return ok1 and ok2, detail


def check_signed_scale(ctx: WorldContext, pack: ContentPack,
                       dist_ocean) -> tuple[bool, str]:
    """B5 §8.8: an every-axis-near-optimal cell reads s < 0 (the good
    end keeps its gradient)."""
    r = evaluate(preset_view(VIGOR_TAXON_PRESET, pack), ctx)
    s = r["s_env"]
    m, y, x = np.unravel_index(np.argmin(s), s.shape)
    factors = {k: float(a[m, y, x]) for k, a in r.items()
               if k not in ("F", "s_env")}
    fmin = min(factors.values())
    ok = float(s[m, y, x]) < 0.0 and fmin >= NEAR_OPTIMAL_F
    detail = (f"{VIGOR_TAXON_PRESET} at (m={m},y={y},x={x}) "
              f"s={float(s[m, y, x]):.3f}, min factor {fmin:.3f} "
              f"(>={NEAR_OPTIMAL_F}); F={float(r['F'][m, y, x]):.3f}")
    return ok, detail


def check_determinism(tree, pack, ctx) -> tuple[bool, str]:
    """B5 §8.1: two full runs byte-identical (float32 arrays must match
    exactly — the pure-function/no-draw contract)."""
    sp = [n for n in tree.nodes.values() if n.rank is Rank.SPECIES]
    first = [evaluate(species_view(n, pack), ctx)["s_env"] for n in sp]
    second = [evaluate(species_view(n, pack), ctx)["s_env"] for n in sp]
    bad = sum(1 for a, b in zip(first, second)
              if not np.array_equal(a, b))
    ok = bad == 0
    detail = f"150 species x 12 months: {bad} mismatches (byte-compare)"
    return ok, detail


def run(seed: int) -> int:
    pack = load_content(FLORA_CONTENT)
    ctx = load_world(seed)
    tree = Tree.from_json(json.loads(
        (TREE_OUT / f"k14_seed{seed:08d}.json").read_text()))
    sp = [n for n in tree.nodes.values() if n.rank is Rank.SPECIES]
    assert len(sp) == 150, len(sp)

    print(f"K15 flora stress adapter — B5 §8 acceptance (seed {seed})")
    print(f"  world: anchor {ctx.H}x{ctx.W}, sea_level {ctx.sea_level}, "
          f"species {len(sp)}, presets {len(pack.presets)}")
    print()

    checks: list[tuple[str, bool, str]] = []

    # (7) budget: the full 150-species annual evaluation, timed once.
    t0 = time.perf_counter()
    [evaluate(species_view(n, pack), ctx) for n in sp]
    wall = time.perf_counter() - t0
    checks.append(("(7) budget: full 150-species evaluation",
                   wall <= BUDGET_S,
                   f"wall {wall:.2f}s (limit {BUDGET_S}s)"))

    # (1) determinism: a second full run, byte-identical arrays.
    t1 = time.perf_counter()
    ok1, d1 = check_determinism(tree, pack, ctx)
    det_wall = time.perf_counter() - t1
    checks.append(("(1) determinism: two runs byte-identical", ok1,
                   f"{d1} ({det_wall:.2f}s)"))

    dist_ocean = dist_to_ocean(ctx)
    for name, fn in (
            ("(2) mangrove-grade: min in high-HAND coastal band",
             check_mangrove),
            ("(3) xeric-grade: wetland high, arid band low", check_xeric),
            ("(4) kelp-grade: hard shallow photic only; deep soft ~1",
             check_kelp),
            ("(5) calcifuge + bog-blackwater pH position",
             check_calcifuge),
            ("(8) signed scale: near-optimal cell reads s < 0",
             check_signed_scale)):
        ok, detail = fn(ctx, pack, dist_ocean)
        checks.append((name, ok, detail))

    for name, ok, detail in checks:
        print(_fmt(ok, name, detail))

    print()
    print("resolved ambiguities:")
    for r in _RESOLUTIONS:
        print(f"  {r}")
    print()
    all_ok = all(ok for _, ok, _ in checks)
    print(f"RESULT: {'ALL CHECKS PASS' if all_ok else 'SEE FAILURES ABOVE'}")
    return 0 if all_ok else 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    raise SystemExit(run(args.seed))


if __name__ == "__main__":
    main()
