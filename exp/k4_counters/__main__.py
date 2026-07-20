"""K4 demo CLI: `uv run python -m exp.k4_counters demo --seed 1 [--json]`.

Evaluates the granary fixture across a year, renders an ASCII chart with
the burn marked, and checks: the burn steps grain down 10×, grain recovers
within the year, and population still lags at year's end. Exit 0 iff all
checks pass. (--seed is accepted per lab convention; the fixture is fully
analytic, so results are seed-independent.)
"""

from __future__ import annotations

import argparse
import json
import sys

from exp.k4_counters.fixtures import BURN_DAY, DAYS, GRAIN_PER_PERSON, build_village

CHART_ROWS = 60
CHART_COLS = 50
GRAIN_MAX = 1000.0
POP_MAX = 500.0


def _chart(grain, population) -> list[str]:
    lines = []
    for row in range(CHART_ROWS):
        t = row * DAYS / CHART_ROWS
        g = grain.value_at(t)
        p = population.value_at(t)
        cells = [" "] * (CHART_COLS + 1)
        cells[min(int(g / GRAIN_MAX * CHART_COLS), CHART_COLS)] = "G"
        cells[min(int(p / POP_MAX * CHART_COLS), CHART_COLS)] = "P"
        mark = "*" if abs(t - BURN_DAY) < DAYS / CHART_ROWS / 2 else " "
        lines.append(f"{mark} day {int(t):3d} |{''.join(cells)}| G={g:7.1f} P={p:6.1f}")
    return lines


def run_demo() -> dict:
    grain, population = build_village()

    pre_burn_grain = grain.value_at(BURN_DAY - 1e-9)
    post_burn_grain = grain.value_at(BURN_DAY)
    pre_burn_pop = population.value_at(BURN_DAY - 1e-9)

    checks = {
        # The burn is an exact 10x step down, committed at the anchor.
        "burn_step": abs(post_burn_grain / pre_burn_grain - 0.1) < 1e-12,
        # Grain recovers most of the way within the remaining season.
        "grain_recovers": grain.value_at(DAYS) / pre_burn_grain >= 0.75,
        # Population at year's end is still far below its pre-burn level —
        # the lag the demo exists to show.
        "population_lags": population.value_at(DAYS) / pre_burn_pop <= 0.5,
        # Re-anchoring daily must not move any evaluation (exact flow).
        "anchor_exactness": _anchor_exactness(),
    }
    ok = all(checks.values())

    times = [row * DAYS / CHART_ROWS for row in range(CHART_ROWS)]
    return {
        "experiment": "k4_counters",
        "anchors": {
            "grain": [(a.t, round(a.value, 4), a.note) for a in grain.anchors],
            "population": [(a.t, round(a.value, 4), a.note) for a in population.anchors],
        },
        "series": {
            "t": times,
            "grain": [grain.value_at(t) for t in times],
            "population": [population.value_at(t) for t in times],
        },
        "burn_day": BURN_DAY,
        "year_end": {
            "grain": grain.value_at(DAYS),
            "grain_supported_population": grain.value_at(DAYS) / GRAIN_PER_PERSON,
            "population": population.value_at(DAYS),
        },
        "checks": checks,
        "ok": ok,
    }


def _anchor_exactness() -> bool:
    """Dense re-anchoring (every day) vs. the sparse chain: max diff."""
    from kernel.counters.counters import Counter

    sparse, _ = build_village()
    redone = Counter(sparse.regimes)
    redone.set_anchor(0, sparse.value_at(0), sparse.anchor_at(0).law, note="spring sowing")
    for day in range(1, DAYS + 1):
        a = sparse.anchor_at(day)
        redone.set_anchor(day, sparse.value_at(day), a.law, a.regime, note="dense")
    return all(
        abs(redone.value_at(t) - sparse.value_at(t)) <= 1e-9 * max(1.0, abs(sparse.value_at(t)))
        for t in (i * 0.5 for i in range(2 * DAYS + 1))
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exp.k4_counters")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the K4 demonstration")
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    report = run_demo()

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        grain, population = build_village()
        print("K4 counters demo — granary across a year (G=grain, P=population, *=burn)")
        for line in _chart(grain, population):
            print(line)
        end = report["year_end"]
        print(f"\nyear end: grain {end['grain']:.1f} (feeds {end['grain_supported_population']:.0f}), "
              f"population {end['population']:.1f} — still lagging")
        for name, passed in report["checks"].items():
            print(f"  {name:<18}: {'PASS' if passed else 'FAIL'}")
        print(f"verdict: {'PASS' if report['ok'] else 'FAIL'}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
