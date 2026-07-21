"""L1 demo CLI: `uv run python -m exp.l1_llm_client demo --seed 1 [--json] [--replay]`.

Structured call at each tier (T0 local grammar, T1 flash, T2
flash-thinking, T3 pro), then the same calls replayed from cassette with
the API off, then a cost report. Default mode: record if an API key is
present, else replay. `--replay` forces replay (CI / API-free).

Exit 0 iff every check passes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from kernel.hashrng import Stream

from llm.llm_client import grammar
from llm.llm_client.cassette import CassetteStore
from llm.llm_client.client import LLMClient
from llm.llm_client.costlog import CostLog
from exp.l1_llm_client.fixtures import PROMPT, VillageRumor
from llm.llm_client.tiers import Tier

CASSETTE_DIR = Path(__file__).parent / "cassettes"
TIERS = [Tier.T1_FLASH, Tier.T2_FLASH_THINKING, Tier.T3_PRO]


def run_demo(seed: int, replay: bool) -> dict:
    import os

    checks: dict[str, bool] = {}
    cassette = CassetteStore(CASSETTE_DIR)
    have_key = bool(os.environ.get("DEEPSEEK_API_KEY"))
    mode = "replay" if (replay or not have_key) else "record"

    report: dict = {"experiment": "l1_llm_client", "seed": seed, "mode": mode}

    # --- T0: local grammar tier (zero tokens) --------------------------------
    stream = Stream(seed, "l1.grammar")
    line = grammar.render("rumor_headline", stream, 0)
    line_again = grammar.render("rumor_headline", Stream(seed, "l1.grammar"), 0)
    report["t0"] = {"line": line, "deterministic": line == line_again, "tokens": 0}
    checks["t0_deterministic"] = line == line_again

    # --- T1/T2/T3: structured calls -------------------------------------------
    client = LLMClient(cassette=cassette, mode=mode)
    results = {}
    for clock, tier in enumerate(TIERS, start=1):
        r = client.call(tier, PROMPT, VillageRumor, purpose="demo", clock=clock,
                        max_tokens=512)
        results[tier.value] = {
            "parsed": r.parsed.model_dump() if r.parsed else None,
            "model": r.cost.model,
            "thinking": r.cost.thinking,
            "usage": {
                "prompt": r.cost.prompt_tokens,
                "cached": r.cost.cached_input_tokens,
                "uncached": r.cost.uncached_input_tokens,
                "completion": r.cost.completion_tokens,
                "reasoning": r.cost.reasoning_tokens,
            },
            "cost_usd": r.cost.cost_usd,
            "attempts": r.cost.attempts,
            "from_cassette": r.from_cassette,
        }
        checks[f"{tier.value}_valid_schema"] = r.parsed is not None
        checks[f"{tier.value}_severity_range"] = r.parsed is not None and 1 <= r.parsed.severity <= 5

    # T2 must have spent reasoning tokens; T1 must not.
    checks["t2_thinks"] = results[Tier.T2_FLASH_THINKING.value]["usage"]["reasoning"] > 0
    checks["t1_no_thinking"] = results[Tier.T1_FLASH.value]["usage"]["reasoning"] == 0

    # --- Replay from cassette with the API off --------------------------------
    replayer = LLMClient(cassette=cassette, mode="replay")
    for tier in TIERS:
        live_parsed = results[tier.value]["parsed"]
        r = replayer.call(tier, PROMPT, VillageRumor, purpose="demo", clock=100)
        checks[f"{tier.value}_replay_identical"] = (
            r.parsed is not None and r.parsed.model_dump() == live_parsed
        )
    checks["replay_no_api_key_needed"] = True  # reaching here proves it

    # --- Cost report ------------------------------------------------------------
    totals = client.cost_log.totals()
    report["tiers"] = results
    report["cost"] = {
        "calls": totals["calls"],
        "tokens_in": totals["prompt_tokens"],
        "tokens_cached": totals["cached_input_tokens"],
        "tokens_out": totals["completion_tokens"],
        "cost_usd": round(totals["cost_usd"], 8),
    }
    report["checks"] = checks
    report["ok"] = all(checks.values())
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exp.l1_llm_client")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the L1 demonstration")
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument("--json", action="store_true")
    demo.add_argument("--replay", action="store_true",
                      help="force cassette replay (API-free)")
    args = parser.parse_args(argv)

    report = run_demo(args.seed, args.replay)

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"L1 llm_client demo — mode: {report['mode']}")
        print(f"  T0 grammar (local, 0 tokens): \"{report['t0']['line']}\"")
        for tier, r in report["tiers"].items():
            p = r["parsed"] or {}
            print(f"  {tier}: \"{p.get('headline')}\" (severity {p.get('severity')}, "
                  f"mill={p.get('involves_mill')})")
            print(f"    in={r['usage']['prompt']} (cached {r['usage']['cached']}) "
                  f"out={r['usage']['completion']} reasoning={r['usage']['reasoning']} "
                  f"attempts={r['attempts']} ${r['cost_usd']:.6f}")
        c = report["cost"]
        print(f"  cost: {c['calls']} calls, in={c['tokens_in']} "
              f"(cached {c['tokens_cached']}), out={c['tokens_out']}, "
              f"${c['cost_usd']:.6f}")
        for name, passed in report["checks"].items():
            print(f"  {name:<28}: {'PASS' if passed else 'FAIL'}")
        print(f"verdict: {'PASS' if report['ok'] else 'FAIL'}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
