"""K15 — B5 §8 acceptance/demo driver for the flora stress adapter,
plus the sim-diff engine rounds demo.

    PYTHONPATH=. uv run python -m exp.k15_simdiff --seed 1
    PYTHONPATH=. uv run python -m exp.k15_simdiff --seed 1 --rounds 8
    PYTHONPATH=. uv run python -m exp.k15_simdiff --seed 1 --rounds 8 --per-round

The default mode loads the flora tree
(exp/k13_treegen/out/k14_seedNNNNNNNN.json) and the anchor world
context, evaluates all 150 radiated species (timed), and prints the
B5 §8 acceptance table on seed 1:

  (1) determinism — two full runs, byte-identical arrays;
  (2) mangrove-grade — the wet-adapted tree's lowest worst-month
      stress is in the marsh band (annual fresh_availability >= 0.6;
      graded, not binary);
  (3) xeric-grade — high worst-month stress on wetland
      (fen/bog/gleysol) cells, low in its arid band;
  (4) kelp-grade — low stress only on hard, shallow, photic bottom;
      deep soft bottom ≈ 1;
  (5) calcifuge — excluded from rendzina/caliche country by the
      usable-substrate share (capacity split, post-ruling 2026-08-01);
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

The rounds demo (--rounds N) ends with the delivery pass (ticket 0013):
the full dump under exp/k15_simdiff/out/seed_NNNNNNNN/ (density
fields, amended tree, authority reflog, high-res display pass + viewer
pack — see persist.py). Deterministic: same (seed, rounds) => the
whole dump dir is byte-identical across processes; --no-dump skips it.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from exp.k13_treegen.flora.__main__ import CONTENT as FLORA_CONTENT
from exp.k13_treegen.flora.content import ContentPack, load_content
from exp.k13_treegen.model import Rank, Tree
from exp.k14_worldprod.derived import GROW_T_C, _spread_max
from exp.k14_worldprod.ground import GROUND_ID
from exp.k15_simdiff.stress_adapter import (
    WorldContext,
    annual_stress,
    evaluate,
    load_world,
    preset_view,
    species_view,
    worst_stress,
)

HERE = Path(__file__).resolve().parent
TREE_OUT = HERE.parent / "k13_treegen" / "out"

# ── acceptance band definitions (seed 1; named tunables) ───────────────
# The marsh band (B5 §8.2, post-ruling 2026-08-01): wet-obligate plans
# read fresh_availability — the band is the marsh itself (annual fresh
# availability at/above MARSH_FRESH). Graded, not binary: mean stress
# inside the band must sit below the outside mean, and the global
# minimum must fall in the band.
MARSH_FRESH = 0.6
# wetland cells for the xeric check (B5 §8.3): the dominant ground
# class is fen/bog/gleysol.
WETLAND_CLASSES = (GROUND_ID["fen"], GROUND_ID["bog"], GROUND_ID["gleysol"])
# arid band for the xeric check: annual-mean normalized P below this
# (~80 mm/yr at 400 mm/month max). The preset is a HOT-desert CAM
# succulent — since the biome split added cold deserts, the band is
# further gated to growing-season mean T above ARID_T_GS (cool arid
# belongs to the stonecrop grade, not this one).
ARID_P_ANN = 0.2
ARID_T_GS = 18.0
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
    "- the derived moisture envelope (moisture_opt/moisture_breadth) is\n"
    "    a position on the normalized 0..1 P scale (c_P_monthly raw),\n"
    "    so the water-availability term reads that scale; the climate\n"
    "    moisture (P) half lives there, not in a separate climate\n"
    "    stratum (owner ruling 2026-08-01: envelope = pure derived of\n"
    "    the trait bundle; water-medium plans read their water from the\n"
    "    habitat/medium terms)",
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
    """B5 §8.2: lowest stress in the WETLAND band, graded. Post-ruling
    (2026-08-01): wet-obligate plans read fresh_availability, so the
    band IS the marsh (annual fresh_availability >= MARSH_FRESH); the
    engine's worst-month stress is measured."""
    fac = evaluate(preset_view(MANGROVE_PRESET, pack), ctx)
    w = worst_stress(fac)
    land = ctx.land_cell
    band = land & (ctx.fresh_availability.mean(axis=0) >= MARSH_FRESH)
    y, x = np.unravel_index(np.argmin(w), w.shape)
    in_band = bool(band[y, x])
    band_mean = float(w[band].mean())
    out_mean = float(w[land & ~band].mean())
    ok = in_band and band_mean < out_mean
    detail = (f"min s_worst={w[y, x]:.3f} at ({y},{x}) fresh="
              f"{float(ctx.fresh_availability.mean(axis=0)[y, x]):.2f} "
              f"in-band={in_band}; marsh n={int(band.sum())} mean "
              f"{band_mean:.4f} vs outside {out_mean:.4f} (graded)")
    return ok, detail


def check_xeric(ctx: WorldContext, pack: ContentPack,
                dist_ocean) -> tuple[bool, str]:
    """B5 §8.3: high stress on wetland cells, low in the HOT arid band
    (the preset is a hot-desert CAM succulent; cool arid is the
    stonecrop grade's habitat) — measured on the engine's worst-month
    stress (the dormancy gate makes annual means read mild; the
    growing-season worst month is what the rounds cache)."""
    c = worst_stress(evaluate(preset_view(XERIC_PRESET, pack), ctx))
    land = ctx.land_cell
    wetland = land & np.isin(ctx.ground_class, list(WETLAND_CLASSES))
    p_ann = ctx.p_norm.mean(axis=0)
    grow = ctx.t_c >= np.float32(GROW_T_C)
    t_gs = ((ctx.t_c * grow).sum(axis=0)
            / np.maximum(grow.sum(axis=0), 1))
    arid = land & (p_ann < ARID_P_ANN) & (t_gs > ARID_T_GS)
    y, x = np.unravel_index(np.argmin(c), c.shape)
    w_mean = float(c[wetland].mean())
    a_mean = float(c[arid].mean())
    gap = w_mean - a_mean
    ok = w_mean > 0.8 and a_mean < 0.7 and gap > 0.3 and bool(arid[y, x])
    detail = (f"wetland(fen/bog/gleysol) n={int(wetland.sum())} mean "
              f"s_worst={w_mean:.3f}; arid(p<{ARID_P_ANN}) "
              f"n={int(arid.sum())} mean s_worst={a_mean:.3f} (gap "
              f"{gap:+.3f}); global min s={c[y, x]:.3f} at ({y},{x}) "
              f"arid={bool(arid[y, x])}")
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
    """B5 §8.5, post-ruling (2026-08-01): the calcifuge is excluded from
    alkaline country by CAPACITY — best-of-class suitability finds the
    acid patch even in lime country, so the usable-substrate share
    carries the exclusion (podzol/bog share >> rendzina/caliche share);
    a freshwater taxon in bog-blackwater cells scores per its
    ph_tolerance position (stress-side, unchanged)."""
    from exp.k15_simdiff.req_flora import REQ_PH_HIGH, REQ_PH_LOW
    fac = evaluate(preset_view(CALCIFUGE_PRESET, pack), ctx)
    share = fac["substrate_share"]
    land = ctx.land_cell
    acid = land & np.isin(ctx.ground_class, list(ACID_CLASSES))
    alk = land & np.isin(ctx.ground_class, list(ALKALINE_CLASSES))
    a_share = float(share[acid].mean())
    k_share = float(share[alk].mean())
    ok1 = a_share > k_share + 0.2
    # bog-blackwater: dominant bog class, low water pH (the implicit
    # hydrology chemistry of B5 §7.2).
    black = land & (ctx.ground_class == GROUND_ID["bog"]) \
        & (ctx.water_ph < BLACKWATER_PH)
    bog = evaluate(preset_view(BOG_TAXON_PRESET, pack), ctx)
    fresh = evaluate(preset_view(FRESH_TAXON_PRESET, pack), ctx)
    # the split factors' product IS the per-position pH suitability
    bog_ph = float((bog[REQ_PH_LOW] * bog[REQ_PH_HIGH])[0, black].mean())
    fresh_ph = float((fresh[REQ_PH_LOW]
                      * fresh[REQ_PH_HIGH])[0, black].mean())
    # sphagnum (ph position 0.05 -> opt pH 4.25) fits blackwater;
    # duckweed (0.5 -> opt 6.5) does not.
    ok2 = bog_ph > fresh_ph + 0.05
    detail = (f"heath share on podzol/bog n={int(acid.sum())} mean "
              f"{a_share:.3f} vs rendzina/caliche n={int(alk.sum())} "
              f"mean {k_share:.3f} (capacity split); bog-blackwater "
              f"n={int(black.sum())} water_ph mean="
              f"{float(ctx.water_ph[black].mean()):.2f}: sphagnum "
              f"ph_suit={bog_ph:.3f} vs duckweed ph_suit={fresh_ph:.3f} "
              f"(per-position)")
    return ok1 and ok2, detail


def check_signed_scale(ctx: WorldContext, pack: ContentPack,
                       dist_ocean) -> tuple[bool, str]:
    """B5 §8.8: an every-axis-near-optimal cell reads s < 0 (the good
    end keeps its gradient)."""
    r = evaluate(preset_view(VIGOR_TAXON_PRESET, pack), ctx)
    s = r["s_env"]
    m, y, x = np.unravel_index(np.argmin(s), s.shape)
    factors = {k: float(a[m, y, x]) for k, a in r.items()
               if k not in ("F", "s_env", "substrate_share")}
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
            ("(2) mangrove-grade: min in the marsh band",
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


def run_rounds(seed: int, rounds: int, *, do_dump: bool = True,
               per_round: bool = False) -> int:
    """The engine rounds demo (spec §4/§12 driver side): genesis plus
    *rounds* full rounds on the world seed, with a per-round table
    (instances, lineages, mass, occupied cells, commit outcomes, wall)
    and a final digest. Determinism note: the same (seed, rounds) run
    is byte-identical across processes — ``test_full_run_acceptance``
    (slow) is the gate for that. The delivery pass (ticket 0013): by
    default the run ends by writing the full dump under
    ``exp/k15_simdiff/out/seed_NNNNNNNN/`` (density fields, amended
    tree, reflog, high-res display pass + viewer pack) — deterministic,
    same seed => byte-identical files."""
    from exp.k15_simdiff import persist
    from exp.k15_simdiff.engine import Engine

    eng = Engine(seed)
    t0 = time.perf_counter()
    eng.genesis()
    n0 = len(eng.instances)
    print(f"K15 sim-diff engine — rounds demo (seed {seed})")
    print(f"  genesis: {n0} instances "
          f"({len({d.x.species_id for d in eng.instances.values()})} "
          f"lineages) in {time.perf_counter() - t0:.1f}s")
    print(f"  {'r':>3} {'inst':>6} {'lin':>5} {'mass':>10} {'cells':>7} "
          f"{'keep':>5} {'merg':>5} {'sub':>4} {'splt':>4} {'ext':>4} "
          f"{'wall':>6}")
    t_start = time.perf_counter()
    for t in range(rounds):
        tr = time.perf_counter()
        log = eng.round(t)
        if per_round:
            persist.round_snapshot(eng, t)
        oc = Counter(int(d.outcome) for d in log.instances)
        mass = sum(d.mass for d in eng.instances.values())
        cells = sum(int(d.cells.sum()) for d in eng.instances.values())
        lin = len({d.x.species_id for d in eng.instances.values()})
        print(f"  {t:>3} {len(eng.instances):>6} {lin:>5} {mass:>10.0f} "
              f"{cells:>7} {oc[0]:>5} {oc[1]:>5} {oc[2]:>4} {oc[3]:>4} "
              f"{len(log.extinct_species):>4} "
              f"{time.perf_counter() - tr:>5.1f}s", flush=True)
    total = time.perf_counter() - t_start
    print(f"  {rounds} rounds in {total:.1f}s "
          f"(mean {total / max(rounds, 1):.1f}s/round); retired "
          f"{len(eng.retired)}, reflog {len(eng.authority.reflog)} "
          f"entries")
    if do_dump:
        out = persist.dump(eng, rounds)
        for f in sorted(p.name for p in out.iterdir()):
            print(f"  delivered {out.name}/{f}")
        print(f"delivery dump: {out}")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--rounds", type=int, default=0,
                    help="run the engine rounds demo instead of the "
                         "adapter acceptance (N full rounds)")
    ap.add_argument("--no-dump", action="store_true",
                    help="skip the delivery dump after the rounds demo")
    ap.add_argument("--per-round", action="store_true",
                    help="also write per-round density snapshots "
                         "(rounds/rNNNN.json)")
    args = ap.parse_args()
    if args.rounds > 0:
        raise SystemExit(run_rounds(args.seed, args.rounds,
                                    do_dump=not args.no_dump,
                                    per_round=args.per_round))
    raise SystemExit(run(args.seed))


if __name__ == "__main__":
    main()
