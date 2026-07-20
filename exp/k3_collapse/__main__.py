"""K3 demo CLI: `uv run python -m exp.k3_collapse demo --seed 1 [--json]`.

Six-stage measurement-semantics walkthrough over a 12-person village
square, from distant field observation through approach-and-collapse to
walk-away coarsening, with a hysteresis-distance demo at the end.

Exit 0 iff every check passes.  Twice with --json → byte-identical output.
"""

from __future__ import annotations

import argparse
import json
import math
import sys

import numpy as np

from kernel.hashrng import Stream
from kernel.gmm_dynamics.dynamics import DriftField, Schedule

from kernel.collapse.field import (
    Silhouette,
    absence_renormalize,
    coarsen,
    collapse_field,
    presence_count,
    refine_identity,
)
from exp.k3_collapse.fixtures import (
    EMPTY_RECT,
    FIELD_COMPONENTS,
    PARTIAL_RECT,
    SQUARE,
    build_field,
    build_residents,
)
from kernel.collapse.geometry import Rect, rect_mass
from kernel.collapse.log import CollapseLog
from kernel.collapse.tiers import HysteresisLadder, Tier

# ---- ASCII map helpers -----------------------------------------------------

MAP_W, MAP_H = 60, 25


def _map_char(x: float, y: float, w: int = MAP_W, h: int = MAP_H,
              *, rect: Rect = SQUARE) -> tuple[int, int]:
    """Scale a world coordinate to a character cell."""
    col = int((x - rect.x0) / (rect.x1 - rect.x0) * w)
    row = int((y - rect.y0) / (rect.y1 - rect.y0) * h)
    return max(0, min(col, w - 1)), max(0, min(row, h - 1))


def _render_map(points: list[tuple[str, float, float]],
                comp_means: list[tuple[float, float]] | None = None) -> str:
    """Render a 60×25 ASCII grid.  Points are (char, x, y)."""
    grid = [[" "] * MAP_W for _ in range(MAP_H)]
    if comp_means:
        for mx, my in comp_means:
            col, row = _map_char(mx, my)
            grid[row][col] = "#"
    for ch, x, y in points:
        col, row = _map_char(x, y)
        if 0 <= col < MAP_W and 0 <= row < MAP_H:
            grid[row][col] = ch
    return "\n".join("".join(row) for row in grid)


# ---- demo logic ------------------------------------------------------------


def run_demo(seed: int) -> tuple[str, dict, bool]:
    stream = Stream(seed, "k3.demo")
    log = CollapseLog()
    field = build_field()
    residents = build_residents()

    checks: dict[str, bool] = {}
    out: list[str] = []

    # --- 1. Far -------------------------------------------------------------
    out.append("=" * 60)
    out.append("Stage 1 — Far (field only)")
    pc = presence_count(field, SQUARE)
    out.append(f"  presence_count in square = {pc:.6f}  (expected 12)")
    checks["presence_count_12"] = abs(pc - 12.0) < 0.1

    # --- 2. Approach (mid) — coarse collapse --------------------------------
    out.append("")
    out.append("=" * 60)
    out.append("Stage 2 — Approach mid  (field → silhouettes)")
    silhouettes = collapse_field(field, SQUARE, stream, clock=2, log=log)
    out.append(f"  silhouettes: {len(silhouettes)}  (expected 12)")
    checks["silhouette_count_12"] = len(silhouettes) == 12

    comp_means = [(c[1][0], c[1][1]) for c in FIELD_COMPONENTS]
    dots = [(f"{i % 10}", s.position[0], s.position[1])
            for i, s in enumerate(silhouettes)]
    out.append(_render_map(dots, comp_means))
    out.append("  legend: # = component mean, digit = silhouette index mod 10")

    # --- 3. Approach (near) — fine collapse ---------------------------------
    out.append("")
    out.append("=" * 60)
    out.append("Stage 3 — Approach near  (silhouettes → identities)")
    assigned: set[str] = set()
    identities: list = []
    outside_assigned = False
    for i, sil in enumerate(silhouettes):
        ident = refine_identity(sil, residents, stream, clock=3 + i,
                                assigned_ids=assigned, log=log)
        identities.append(ident)
        assigned.add(ident.id)
        if ident.id in ("nina", "oscar"):
            outside_assigned = True

    out.append(f"  identities: {len(identities)}")
    out.append(f"  outside residents assigned: {outside_assigned}")
    checks["outside_never_assigned"] = not outside_assigned

    # all 12 identities have unique resident ids
    unique_ids = {i.id for i in identities}
    checks["all_ids_unique"] = len(unique_ids) == 12

    # positions unchanged from silhouettes — filtration invariant
    pos_match = all(
        math.isclose(ident.position[0], sil.position[0], rel_tol=1e-12) and
        math.isclose(ident.position[1], sil.position[1], rel_tol=1e-12)
        for ident, sil in zip(identities, silhouettes)
    )
    checks["position_unchanged"] = pos_match

    initials = [(ident.name[0], ident.position[0], ident.position[1])
                for ident in identities]
    out.append(_render_map(initials, comp_means))
    out.append("  legend: # = component mean, A-Z = resident initials")

    # --- 4. Walk away — coarsen (both policies) -----------------------------
    out.append("")
    out.append("=" * 60)
    out.append("Stage 4 — Walk away  (identities → field)")

    # 4a: last-position
    field_a = coarsen(identities, dt=0.5, sigma=1.0, policy="last-position")
    out.append(f"  [last-position]  total_mass={field_a.total_mass():.6f}  "
               f"mixture_mean=({field_a.mixture_mean()[0]:.3f}, {field_a.mixture_mean()[1]:.3f})")
    checks["coarsen_mass_preserved"] = abs(field_a.total_mass() - 12.0) < 1e-9

    # mean of positions before coarsen
    pos_arr = np.array([list(i.position) for i in identities])
    pos_mean = pos_arr.mean(axis=0)
    field_mean_a = field_a.mixture_mean()
    checks["coarsen_mean_preserved"] = (
        abs(field_mean_a[0] - pos_mean[0]) < 1e-9 and
        abs(field_mean_a[1] - pos_mean[1]) < 1e-9
    )

    # 4b: schedule-snap (simple home schedule for comparison)
    home_field = DriftField(mu=(0.0, 0.0), theta=(0.1, 0.1), sigma=(0.5, 0.5))
    home_schedule = Schedule(period=1440.0, segments=[(0.0, home_field)])
    sched_map = {r.id: home_schedule for r in residents}
    field_b = coarsen(identities, dt=720.0, sigma=1.0,
                      policy="schedule-snap", schedules=sched_map)
    out.append(f"  [schedule-snap] total_mass={field_b.total_mass():.6f}  "
               f"mixture_mean=({field_b.mixture_mean()[0]:.3f}, {field_b.mixture_mean()[1]:.3f})")

    # --- 5. Search empty / partial rect -------------------------------------
    out.append("")
    out.append("=" * 60)
    out.append("Stage 5 — Search empty / partial rects")

    # empty rect — identity operation
    pre_sum = float(field.weights.sum())
    field_empty = absence_renormalize(field, EMPTY_RECT, hard_count=True)
    post_sum = float(field_empty.weights.sum())
    out.append(f"  empty rect: mass {pre_sum:.1f} → {post_sum:.1f}  (expected unchanged)")
    checks["empty_rect_identity"] = abs(pre_sum - post_sum) < 1e-12

    # partial rect — presence drops, total renormalised
    field_part = absence_renormalize(field, PARTIAL_RECT, hard_count=True)
    part_sum = float(field_part.weights.sum())
    out.append(f"  partial rect: mass {pre_sum:.1f} → {part_sum:.1f}  "
               f"(expected 12.0 after hard-count renormalisation)")
    checks["partial_rect_renormalised"] = abs(part_sum - 12.0) < 1e-12

    for k in range(field.n_components):
        out.append(f"    component {k}: weight {field.weights[k]:.2f} → {field_part.weights[k]:.2f}")

    # --- 6. Hysteresis demo -------------------------------------------------
    out.append("")
    out.append("=" * 60)
    out.append("Stage 6 — Hysteresis distance series")
    ladder = HysteresisLadder(promote_radius=10.0, demote_epsilon=3.0)
    # wobble distances that oscillate around 10 without crossing 13
    wobble = [12, 9, 12, 9, 12, 9, 12, 9, 12, 9, 15, 12, 9]
    tier_seq: list[str] = []
    current = Tier.FIELD
    for d in wobble:
        current = ladder.tier_for_distance(d, current)
        tier_seq.append(current.name)
    out.append(f"  distances: {wobble}")
    out.append(f"  tiers:     {tier_seq}")
    # must not flicker FIELD↔SILHOUETTE within the band
    no_flicker = True
    for i in range(len(tier_seq) - 2):
        if tier_seq[i] == tier_seq[i+2] and tier_seq[i] != tier_seq[i+1]:
            no_flicker = False
    checks["hysteresis_no_flicker"] = no_flicker

    ok = all(bool(v) for v in checks.values())
    text = "\n".join(out)
    return text, checks, ok


# ---- main ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exp.k3_collapse")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the K3 demonstration")
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    text, checks, ok = run_demo(args.seed)

    if args.json:
        json.dump({"experiment": "k3_collapse", "seed": args.seed,
                   "checks": {k: bool(v) for k, v in checks.items()}, "ok": bool(ok)}, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(text)
        for name, passed in checks.items():
            print(f"  {name:<30}: {'PASS' if passed else 'FAIL'}")
        print(f"verdict: {'PASS' if ok else 'FAIL'}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
