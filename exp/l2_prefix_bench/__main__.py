"""L2 demo CLI: `uv run python -m exp.l2_prefix_bench demo --seed 1 [--json] [--replay]`.

A/B: naive vs. disciplined prefix handling over one scripted hour of
play (40 events). Reports cache-hit rate and $/hour, and checks the
design spec §7.5 envelope (1–5¢/hour) with real numbers.

Default mode: record if DEEPSEEK_API_KEY is set, else replay.
Exit 0 iff every check passes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from llm.llm_client.cassette import CassetteStore
from llm.llm_client.client import LLMClient

from llm.prefix_bench.bench import run_bench
from llm.prefix_bench.builder import PromptBuilder
from exp.l2_prefix_bench.fixtures import DIGEST_STATE, SYSTEM_PROMPT, build_events
from llm.prefix_bench.policies import EveryN

CASSETTE_DIR = Path(__file__).parent / "cassettes"

# Spec §7.5 reference: 1 call/min, 4k cached + 500 uncached + 300 out on
# V4-Flash ≈ $0.0001652/call → ~$0.0099/hr. Envelope claim: 1–5¢/hour.
SPEC_MODEL_PER_HOUR = 60 * 0.0001652
ENVELOPE_HIGH = 0.05


def run_demo(seed: int, replay: bool) -> dict:
    have_key = bool(os.environ.get("DEEPSEEK_API_KEY"))
    mode = "replay" if (replay or not have_key) else "record"
    events = build_events()

    def make_client() -> LLMClient:
        return LLMClient(cassette=CassetteStore(CASSETTE_DIR), mode=mode)

    naive = run_bench(make_client(), events, "naive",
                      system=SYSTEM_PROMPT, digest_state=DIGEST_STATE,
                      purpose="bench-naive")

    builder = PromptBuilder(system=SYSTEM_PROMPT)
    builder.begin_epoch(DIGEST_STATE, intents=["chronicle the hour"])
    disciplined = run_bench(make_client(), events, "disciplined",
                            system=SYSTEM_PROMPT, digest_state=DIGEST_STATE,
                            builder=builder, policy=EveryN(5),
                            purpose="bench-disciplined")

    checks = {
        # provider reality (probed 2026-07-20): prefix cache works on
        # 128-token blocks of any SHARED prefix, so even the naive mode
        # caches its stable system block. The disciplined win is call
        # count + full-prefix stability, not zero-vs-nonzero hits.
        "naive_partial_caching_observed": naive.cache_hit_rate > 0.0,
        "disciplined_hit_rate_at_least_naive": (
            disciplined.cache_hit_rate >= naive.cache_hit_rate - 1e-9
        ),
        "disciplined_hit_rate_above_50pct": disciplined.cache_hit_rate > 0.5,
        "disciplined_fewer_calls": disciplined.calls < naive.calls,
        "disciplined_cheaper": disciplined.cost_usd < naive.cost_usd,
        "within_envelope": disciplined.cost_usd <= ENVELOPE_HIGH,
    }
    ok = all(checks.values())

    def row(r):
        return {
            "events": r.events, "calls": r.calls,
            "prompt_tokens": r.prompt_tokens,
            "cached": r.cached_input_tokens,
            "uncached": r.uncached_input_tokens,
            "completion": r.completion_tokens,
            "cache_hit_rate": round(r.cache_hit_rate, 4),
            "cost_usd": round(r.cost_usd, 6),
            "cost_per_hour": round(r.cost_usd, 6),  # fixture IS one hour
        }

    return {
        "experiment": "l2_prefix_bench", "seed": seed, "mode": mode,
        "naive": row(naive),
        "disciplined": row(disciplined),
        "spec_model_per_hour": SPEC_MODEL_PER_HOUR,
        "envelope": {"low": 0.01, "high": ENVELOPE_HIGH},
        "checks": checks, "ok": ok,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exp.l2_prefix_bench")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the L2 A/B bench")
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument("--json", action="store_true")
    demo.add_argument("--replay", action="store_true", help="force cassette replay")
    args = parser.parse_args(argv)

    report = run_demo(args.seed, args.replay)

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"L2 prefix_bench demo — one hour of play, {report['naive']['events']} events "
              f"(mode: {report['mode']})")
        for name in ("naive", "disciplined"):
            r = report[name]
            print(f"  {name:<12}: {r['calls']:2d} calls, in={r['prompt_tokens']} "
                  f"(cached {r['cached']}, {r['cache_hit_rate']:.0%}), "
                  f"out={r['completion']}, ${r['cost_usd']:.6f}/hr")
        print(f"  spec §7.5 model: ${report['spec_model_per_hour']:.4f}/hr; "
              f"envelope claim: ${report['envelope']['low']:.2f}–${report['envelope']['high']:.2f}/hr")
        for name, passed in report["checks"].items():
            print(f"  {name:<34}: {'PASS' if passed else 'FAIL'}")
        print(f"verdict: {'PASS' if report['ok'] else 'FAIL'}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
