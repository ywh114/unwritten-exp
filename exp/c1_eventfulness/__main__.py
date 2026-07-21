"""C1 demo CLI: `uv run python -m exp.c1_eventfulness demo --seed 1 [--replay] [--json]`.

Runs both arms (unconditioned + conditioned) over 100 intervals (200 LLM
calls when recording).  Prints per-scale histograms, obedience rate, bias
demonstration, and the cost report.  Exit 0 iff all checks pass.

Default mode: record if DEEPSEEK_API_KEY is set, else replay from
committed cassettes.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

from kernel.hashrng import Stream
from llm.llm_client import LLMClient, Tier, CassetteStore

from capability.eventfulness.bench import run_arm
from exp.c1_eventfulness.fixtures import VILLAGE_CONTEXT, build_intervals
from capability.eventfulness.sampler import SCALES, target_distribution

CASSETTE_DIR = Path(__file__).parent / "cassettes"
_NA = -1  # "not applicable" marker for unconditioned k


# ---- χ² helper ------------------------------------------------------------


def _normal_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def _chi2_pvalue(stat: float, df: int) -> float:
    z = ((stat / df) ** (1.0 / 3.0) - (1.0 - 2.0 / (9.0 * df))) / math.sqrt(
        2.0 / (9.0 * df)
    )
    return _normal_sf(z)


def _chi2_test(bin_counts: list[int], expected_probs: list[float]) -> tuple[float, float]:
    """χ² goodness-of-fit of binned counts against expected probabilities;
    returns (stat, p_value)."""
    n = sum(bin_counts)
    stat = 0.0
    df = 0
    for o, e in zip(bin_counts, expected_probs):
        if e > 0:
            stat += (o - n * e) ** 2 / (n * e)
            df += 1
    df = max(1, df - 1)
    return stat, _chi2_pvalue(stat, df)


# ---- histogram ------------------------------------------------------------


def _histo(counts: list[int], max_bin: int = 8) -> str:
    bins = [0] * (max_bin + 2)
    for c in counts:
        bins[min(c, max_bin + 1)] += 1
    lines = []
    total = len(counts)
    for i in range(len(bins) - 1):
        bar = "#" * max(1, int(bins[i] / max(1, total) * 40))
        label = f"{i}" if i < max_bin else f"{max_bin}+"
        lines.append(f"  {label:>3s}  {bar}  ({bins[i]})")
    return "\n".join(lines)


# ---- demo logic ------------------------------------------------------------


def run_demo(seed: int, replay: bool) -> tuple[str, dict, bool]:
    intervals = build_intervals()
    checks: dict[str, bool] = {}
    out: list[str] = []

    # --- setup client ---
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    mode = "replay" if replay else ("record" if api_key else "replay")
    cassette = CassetteStore(CASSETTE_DIR)
    client = LLMClient(api_key=api_key, cassette=cassette, mode=mode)

    # --- run arms ---
    stream = Stream(seed, "c1.demo")
    out.append(f"C1 eventfulness — {'replay' if mode == 'replay' else 'live/record'} mode, seed {seed}")

    out.append("")
    out.append("--- unconditioned arm ---")
    unc = run_arm(client, stream, intervals, conditioned=False, context=VILLAGE_CONTEXT)
    out.append(f"  {unc.total_calls} calls, "
               f"{_cost_line(unc.cost_log.entries)}")

    out.append("")
    out.append("--- conditioned arm ---")
    stream2 = Stream(seed, "c1.demo")
    con = run_arm(client, stream2, intervals, conditioned=True, context=VILLAGE_CONTEXT)
    out.append(f"  {con.total_calls} calls, "
               f"{_cost_line(con.cost_log.entries)}")

    # --- per-scale comparisons ---
    scales_order = ["week", "season", "year"]
    for scale in scales_order:
        out.append("")
        out.append(f"=== {scale} ===")
        unc_vals = [r["k_measured"] for r in unc.results if r["scale"] == scale]
        con_vals = [r["k_measured"] for r in con.results if r["scale"] == scale]
        con_req   = [r["k_requested"] for r in con.results if r["scale"] == scale]

        out.append(f"unconditioned (n={len(unc_vals)}):")
        out.append(_histo(unc_vals))
        out.append(f"conditioned (n={len(con_vals)}):")
        out.append(_histo(con_vals))

    # --- checks ---

    # obedience: measured == requested for ≥ 95%
    matches = sum(
        1 for r in con.results if r["k_measured"] == r["k_requested"]
    )
    obedience = matches / len(con.results)
    checks["obedience_ge_95"] = obedience >= 0.95

    # conditioned matches target per scale
    target_stream = Stream(seed, "c1.target")
    target_ok = True
    for scale in scales_order:
        target_counts = target_distribution(target_stream, scale, n=10_000)
        con_vals = [r["k_measured"] for r in con.results if r["scale"] == scale]
        # bin into {0, 1, 2, 3+}
        def _bin3(counts):
            b = [0, 0, 0, 0]
            for c in counts:
                b[min(c, 3)] += 1
            return b
        t_bins = _bin3(target_counts)
        c_bins = _bin3(con_vals)
        t_probs = [x / sum(t_bins) for x in t_bins]
        if sum(c_bins) > 0 and sum(t_bins) > 0:
            _, p = _chi2_test(c_bins, t_probs)
            if p <= 0.01:
                target_ok = False
                out.append(f"  χ² fail for {scale}: p={p:.4f}")
    checks["conditioned_matches_target"] = target_ok

    # quiet is normal: conditioned zero-rate ≥ sampler pooled P(0) − 0.05
    target_stream2 = Stream(seed, "c1.target2")
    target_counts_all = [
        c for s in scales_order for c in target_distribution(target_stream2, s, n=3_333)
    ]
    target_zerorate = sum(1 for c in target_counts_all if c == 0) / len(target_counts_all)
    con_zeros = sum(1 for r in con.results if r["k_measured"] == 0)
    con_zerorate = con_zeros / len(con.results)
    checks["quiet_is_normal"] = con_zerorate >= target_zerorate - 0.05

    # bias demonstrated: unconditioned zero-rate < conditioned
    unc_zeros = sum(1 for r in unc.results if r["k_measured"] == 0)
    unc_zerorate = unc_zeros / len(unc.results)
    checks["bias_demonstrated"] = unc_zerorate < con_zerorate

    # barley is fine: ≥ 1 conditioned k=0 chronicle with empty events +
    # non-empty texture — print one verbatim
    barley_ok = False
    for r in con.results:
        if r["k_requested"] == 0 and r["k_measured"] == 0 and r["chronicle"]:
            barley_ok = True
            out.append("")
            out.append(f"  quiet outcome example: [{r['chronicle']}]")
            break
    checks["barley_is_fine"] = barley_ok

    # cost summary
    all_entries = unc.cost_log.entries + con.cost_log.entries
    out.append("")
    out.append("--- cost ---")
    out.append(f"  calls: {unc.total_calls + con.total_calls}")
    out.append(f"  {_cost_line(all_entries)}")
    out.append(f"  conditioned obedience: {obedience:.3f}")
    out.append(f"  unconditioned zero-rate: {unc_zerorate:.3f}")
    out.append(f"  conditioned zero-rate:   {con_zerorate:.3f}")

    ok = all(checks.values())
    text = "\n".join(out)
    return text, checks, ok


def _cost_line(entries: list) -> str:
    if not entries:
        return "no cost data"
    tin = sum(x.prompt_tokens for x in entries)
    tcached = sum(x.cached_input_tokens for x in entries)
    tout = sum(x.completion_tokens for x in entries)
    cost = sum(x.cost_usd for x in entries)
    return f"tokens: {tin} in / {tcached} cached / {tout} out  —  ${cost:.4f}"


# ---- main ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exp.c1_eventfulness")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the C1 demonstration")
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument("--replay", action="store_true",
                      help="force replay from cassette (no API)")
    demo.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    replay = args.replay or not os.environ.get("DEEPSEEK_API_KEY")
    text, checks, ok = run_demo(int(args.seed), replay)

    if args.json:
        json.dump({
            "experiment": "c1_eventfulness", "seed": args.seed,
            "checks": {k: bool(v) for k, v in checks.items()}, "ok": bool(ok),
        }, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(text)
        for name, passed in checks.items():
            print(f"  {name:<30}: {'PASS' if passed else 'FAIL'}")
        print(f"verdict: {'PASS' if ok else 'FAIL'}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
