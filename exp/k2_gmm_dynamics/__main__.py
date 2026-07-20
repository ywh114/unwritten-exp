"""K2 demo CLI: `uv run python -m exp.k2_gmm_dynamics demo --seed 1 [--json]`.

50 villagers on the toy map; the season (90 days) is crossed in ONE
`evolve` call per villager — no ticking, ever. Prints ASCII density plots
at dawn / noon / night, a mass-conservation line from 1 minute to 10,000
years, a timing line proving Δt = 1 century costs the same as Δt = 1
minute, and an overall PASS/FAIL verdict. Exit code 0 iff all checks pass.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time

import numpy as np

from exp.k2_gmm_dynamics import fixtures
from kernel.gmm_dynamics.dynamics import DriftField, evolve, sample_at
from kernel.gmm_dynamics.gmm import GMM
from kernel.hashrng import Stream

SEASON_DAYS = 90
DENSITY_CHARS = " .:-=+*#%@"
GRID_COLS = 60
GRID_ROWS = 30
GRID_X = (-45.0, 55.0)
GRID_Y = (-25.0, 25.0)

PHASES = {"dawn": 390.0, "noon": 720.0, "night": 1380.0}  # 06:30 / 12:00 / 23:00
SITE_RADIUS = 10.0
MIN_ON_SITE = 0.60
TIMING_REPEATS = 300
MAX_TIMING_RATIO = 50.0

MINUTE = 1.0
DAY = fixtures.MINUTES_PER_DAY
YEAR = 365.25 * DAY
MASS_DTS = {
    "1 minute": MINUTE,
    "1 day": DAY,
    "1 year": YEAR,
    "1 century": 100 * YEAR,
    "10000 years": 10_000 * YEAR,
}


def season_dist(world_seed: int, index: int, phase: float) -> GMM:
    """Villager `index` evolved from season-start (midnight, day 0) to the
    given phase on day SEASON_DAYS-1 — a single `evolve` call over ~90 days."""
    t1 = (SEASON_DAYS - 1) * DAY + phase
    return evolve(fixtures.initial_dist(world_seed, index), 0.0, t1, fixtures.villager_schedule(world_seed, index))


def population_gmm(world_seed: int, phase: float) -> GMM:
    """Whole-village density at a phase: 50 components, equal weight."""
    parts = [season_dist(world_seed, i, phase) for i in range(fixtures.N_VILLAGERS)]
    n = fixtures.N_VILLAGERS
    return GMM(
        np.concatenate([g.weights / n for g in parts]),
        np.concatenate([g.means for g in parts]),
        np.concatenate([g.covs for g in parts]),
    )


def density_grid(gmm: GMM) -> np.ndarray:
    """Mixture pdf on the ASCII grid, rows = y (top row highest y)."""
    xs = np.linspace(GRID_X[0], GRID_X[1], GRID_COLS)
    ys = np.linspace(GRID_Y[1], GRID_Y[0], GRID_ROWS)
    grid = np.zeros((GRID_ROWS, GRID_COLS))
    xx, yy = np.meshgrid(xs, ys)
    for w, m, p in zip(gmm.weights, gmm.means, gmm.covs):
        det = max(float(np.linalg.det(p)), 1e-300)
        inv = np.linalg.inv(p)
        dx = xx - m[0]
        dy = yy - m[1]
        expo = inv[0, 0] * dx * dx + 2.0 * inv[0, 1] * dx * dy + inv[1, 1] * dy * dy
        grid += w * np.exp(-0.5 * expo) / (2.0 * math.pi * math.sqrt(det))
    return grid


def render_grid(grid: np.ndarray) -> list[str]:
    peak = grid.max()
    if peak <= 0.0:
        return ["".join(DENSITY_CHARS[0] for _ in range(GRID_COLS)) for _ in range(GRID_ROWS)]
    levels = grid / peak
    idx = np.minimum((levels * (len(DENSITY_CHARS) - 1)).astype(int), len(DENSITY_CHARS) - 1)
    return ["".join(DENSITY_CHARS[i] for i in row) for row in idx]


def run_demo(seed: int) -> dict:
    # 1. Season skip + density plots at three phases.
    grids = {}
    means = {}
    for name, phase in PHASES.items():
        g = population_gmm(seed, phase)
        grids[name] = render_grid(density_grid(g))
        means[name] = g.mixture_mean().tolist()

    # 2. Mass conservation, single field and through the schedule.
    field = DriftField(mu=fixtures.FIELDS, theta=(0.2, 0.2), sigma=(0.3, 0.3))
    d0 = fixtures.initial_dist(seed, 0)
    sched = fixtures.villager_schedule(seed, 0)
    mass = {}
    for label, dt in MASS_DTS.items():
        err_field = abs(evolve(d0, 0.0, dt, field).total_mass() - 1.0)
        err_sched = abs(evolve(d0, 0.0, dt, sched).total_mass() - 1.0)
        mass[label] = {"single_field": err_field, "schedule": err_sched}
    mass_ok = all(v["single_field"] <= 1e-9 and v["schedule"] <= 1e-9 for v in mass.values())

    # 3. Timing: Δt = 1 minute vs Δt = 1 century under the same schedule.
    t_min = _time_evolve(d0, MINUTE, sched)
    t_cen = _time_evolve(d0, 100 * YEAR, sched)
    ratio = t_cen / t_min if t_min > 0.0 else float("inf")
    timing_ok = ratio < MAX_TIMING_RATIO

    # 4. Day cycle: farmers at the fields at noon, everyone home/tavern at night.
    noon_farmers = 0
    n_farmers = 0
    night_on_site = 0
    for i in range(fixtures.N_VILLAGERS):
        role = fixtures.villager_role(seed, i)
        if role == "farmer":
            n_farmers += 1
            d = season_dist(seed, i, PHASES["noon"])
            x, y = sample_at(d, Stream(seed, f"villager:{i:03d}", context_digest="demo-noon"), clock=0)
            if math.hypot(x - fixtures.FIELDS[0], y - fixtures.FIELDS[1]) <= SITE_RADIUS:
                noon_farmers += 1
        d = season_dist(seed, i, PHASES["night"])
        x, y = sample_at(d, Stream(seed, f"villager:{i:03d}", context_digest="demo-night"), clock=0)
        hx, hy = fixtures.villager_home(seed, i)
        if min(
            math.hypot(x - hx, y - hy),
            math.hypot(x - fixtures.TAVERN[0], y - fixtures.TAVERN[1]),
        ) <= SITE_RADIUS:
            night_on_site += 1
    farmers_frac = noon_farmers / n_farmers if n_farmers else 1.0
    night_frac = night_on_site / fixtures.N_VILLAGERS
    cycle_ok = farmers_frac >= MIN_ON_SITE and night_frac >= MIN_ON_SITE

    # 5. The plots visibly differ by phase.
    flat = {k: np.array([list(r) for r in g]) for k, g in grids.items()}
    corr = _grid_corr(flat["dawn"], flat["noon"])
    plots_ok = corr < 0.95

    checks = {
        "mass_conserved": {"ok": mass_ok, "errors": mass},
        "evolve_o1": {
            "ok": timing_ok,
            "seconds_per_evolve_1min": t_min,
            "seconds_per_evolve_1century": t_cen,
            "ratio_century_over_minute": ratio,
            "max_ratio": MAX_TIMING_RATIO,
        },
        "day_cycle": {
            "ok": cycle_ok,
            "farmers_at_fields_noon": f"{noon_farmers}/{n_farmers}",
            "villagers_home_or_tavern_night": f"{night_on_site}/{fixtures.N_VILLAGERS}",
        },
        "plots_differ": {"ok": plots_ok, "dawn_noon_grid_correlation": corr},
    }
    ok = all(c["ok"] for c in checks.values())
    return {
        "experiment": "k2_gmm_dynamics",
        "seed": seed,
        "season_days": SEASON_DAYS,
        "phases": PHASES,
        "mixture_means": means,
        "grids": grids,
        "checks": checks,
        "ok": ok,
    }


def _time_evolve(d0: GMM, dt: float, sched) -> float:
    """Best per-call wall time over TIMING_REPEATS calls."""
    best = float("inf")
    for _ in range(3):
        start = time.perf_counter()
        for _ in range(TIMING_REPEATS):
            evolve(d0, 0.0, dt, sched)
        best = min(best, (time.perf_counter() - start) / TIMING_REPEATS)
    return best


def _grid_corr(a: np.ndarray, b: np.ndarray) -> float:
    """Pearson correlation between two rendered grids (0/1 char masks)."""
    af = (a != " ").astype(float).ravel()
    bf = (b != " ").astype(float).ravel()
    if af.std() == 0.0 or bf.std() == 0.0:
        return 1.0 if np.array_equal(af, bf) else 0.0
    return float(np.corrcoef(af, bf)[0, 1])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exp.k2_gmm_dynamics")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the K2 demonstration")
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    report = run_demo(args.seed)

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"K2 gmm_dynamics demo — world seed {args.seed}")
        print(f"50 villagers, {report['season_days']} days crossed in ONE evolve call per villager")
        for name in ("dawn", "noon", "night"):
            mm = report["mixture_means"][name]
            print(f"\n{dname(name)} (mixture mean = ({mm[0]:+.1f}, {mm[1]:+.1f})):")
            for row in report["grids"][name]:
                print(f"  |{row}|")
        c = report["checks"]
        print("\nmass conservation |Σw − 1|:")
        for label, errs in c["mass_conserved"]["errors"].items():
            print(f"  Δt = {label:<13} field: {errs['single_field']:.1e}  schedule: {errs['schedule']:.1e}")
        t = c["evolve_o1"]
        print(f"\ntiming: evolve Δt=1 minute {t['seconds_per_evolve_1min'] * 1e6:.1f} µs "
              f"vs Δt=1 century {t['seconds_per_evolve_1century'] * 1e6:.1f} µs "
              f"(ratio {t['ratio_century_over_minute']:.2f}×, must be < {t['max_ratio']:.0f}×)")
        d = c["day_cycle"]
        print(f"\nday cycle: noon farmers at fields {d['farmers_at_fields_noon']}, "
              f"night home/tavern {d['villagers_home_or_tavern_night']}")
        for name, chk in c.items():
            print(f"  {name:<16}: {'PASS' if chk['ok'] else 'FAIL'}")
        print(f"verdict: {'PASS' if report['ok'] else 'FAIL'}")

    return 0 if report["ok"] else 1


def dname(name: str) -> str:
    return {"dawn": "dawn 06:30", "noon": "noon 12:00", "night": "night 23:00"}[name]


if __name__ == "__main__":
    raise SystemExit(main())
