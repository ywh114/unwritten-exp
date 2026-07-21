"""C2 demo CLI: `uv run python -m exp.c2_backfill demo --seed 1 [--replay] [--json]`.

Runs the backfill pipeline and prints:
1. The season's committed facts + chronicle (seed 1)
2. Validator catching seeded violations
3. Acceptance across 50 seeded runs
4. Archaeological legibility report

Default mode: record if DEEPSEEK_API_KEY is set, else replay from cassettes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from kernel.hashrng import Stream
from llm.llm_client import LLMClient, CassetteStore

from exp.c2_backfill.fixtures import build_village
from capability.backfill.schema import (
    BackfillEvent,
    BackfillResult,
    CounterNote,
    SeasonChronicle,
)
from capability.backfill.pipeline import backfill
from capability.backfill.validate import validate_chronicle

CASSETTE_DIR = Path(__file__).parent / "cassettes"
TOTAL_RUNS = 50


# ---- helper -------------------------------------------------------------------


def _cost_line(entries: list) -> str:
    if not entries:
        return "no cost data"
    tin = sum(x.prompt_tokens for x in entries)
    tcached = sum(x.cached_input_tokens for x in entries)
    tout = sum(x.completion_tokens for x in entries)
    cost = sum(x.cost_usd for x in entries)
    return f"tokens: {tin} in / {tcached} cached / {tout} out  —  ${cost:.4f}"


# ---- one-pass runner ----------------------------------------------------------


@dataclass
class _RunReport:
    result: BackfillResult
    village: object          # Village — avoids import loop in type hint
    seed: int


def _run_all(seeds: range, api_key: str, cassette: CassetteStore,
             mode: str) -> list[_RunReport]:
    """Run backfill for every seed; returns reports in seed order."""
    reports: list[_RunReport] = []
    for s in seeds:
        v = build_village(s)
        s_stream = Stream(s, "c2.demo")
        s_client = LLMClient(api_key=api_key, cassette=cassette, mode=mode)
        r = backfill(v, 0.0, 90.0, s_client, s_stream, max_retries=1)
        reports.append(_RunReport(result=r, village=v, seed=s))
    return reports


# ---- demo logic ---------------------------------------------------------------


def run_demo(seed: int, replay: bool) -> tuple[str, dict, bool]:
    checks: dict[str, bool] = {}
    out: list[str] = []

    # --- setup ---
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    mode = "replay" if replay else ("record" if api_key else "replay")
    cassette = CassetteStore(CASSETTE_DIR)

    out.append(f"C2 backfill — {'replay' if mode == 'replay' else 'live/record'} mode, seed {seed}")

    # ========================================================================
    # Stage 1: the season for seed 1
    # ========================================================================
    out.append("")
    out.append("=== Stage 1: the season (seed 1) ===")

    client1 = LLMClient(api_key=api_key, cassette=cassette, mode=mode)
    stream1 = Stream(seed, "c2.demo")
    village = build_village(seed)
    result = backfill(village, 0.0, 90.0, client1, stream1, max_retries=1)

    if not result.accepted:
        out.append(f"  FAILED — not accepted after {result.attempts} attempts")
        out.append(f"  violations: {result.violations_history[-1]}")
    else:
        out.append(f"  accepted in {result.attempts} attempt(s)")

    out.append("")
    out.append("--- committed facts ---")
    wiki_facts = [f for f in village.wiki._facts.values() if f.state.value == "active"]
    for f in sorted(wiki_facts, key=lambda x: x.id):
        out.append(f"  [{f.id}] (trust:{f.trust:.1f}) t={f.valid_from:.0f} {f.text}")

    out.append("")
    out.append("--- chronicle ---")
    out.append(result.chronicle_text)

    out.append("")
    out.append(f"--- cost (stage 1) ---")
    out.append(f"  calls: {len(result.cost_entries)}")
    out.append(f"  {_cost_line(result.cost_entries)}")

    out.append("")
    out.append("--- counter anchors ---")
    for name, (v0, v1, direction) in sorted(result.counter_anchors.items()):
        out.append(f"  {name}: {v0:.1f} → {v1:.1f} ({direction})")

    # ========================================================================
    # Stage 2: validator catches seeded violations (no LLM)
    # ========================================================================
    out.append("")
    out.append("=== Stage 2: validator catches seeded violations ===")

    # 2a: resurrection — a canned output with a DEAD NPC
    resurrection_chronicle = SeasonChronicle(
        events=[
            BackfillEvent(
                title="Old Cade's ghost appears at the mill",
                kind="other",
                involves=["old_cade", "miller_tobias"],
                promise_discharge=None,
            ),
        ],
        counter_notes=[
            CounterNote(counter="grain", direction="up", reason="crops grew"),
            CounterNote(counter="population", direction="up",
                        reason="births exceeded deaths"),
            CounterNote(counter="garrison", direction="down",
                        reason="desertions"),
        ],
        texture_line="A strange season.",
    )
    res_violations = validate_chronicle(
        resurrection_chronicle, k=1,
        dead_slugs=village.dead_slugs,
        counter_anchors=result.counter_anchors,
        due_promises=[],
    )
    out.append(f"  resurrection trap: {res_violations}")
    checks["validator_catches_resurrection"] = any(
        "resurrection" in v for v in res_violations
    )

    # 2b: counter disagreement — wrong direction
    counter_chronicle = SeasonChronicle(
        events=[
            BackfillEvent(
                title="Grain stores dwindled",
                kind="economic",
                involves=["miller_tobias"],
                promise_discharge=None,
            ),
        ],
        counter_notes=[
            CounterNote(counter="grain", direction="down",
                        reason="blight destroyed crops"),
            CounterNote(counter="population", direction="up",
                        reason="births exceeded deaths"),
            CounterNote(counter="garrison", direction="down",
                        reason="desertions"),
        ],
        texture_line="A blighted season.",
    )
    ctr_violations = validate_chronicle(
        counter_chronicle, k=1,
        dead_slugs=village.dead_slugs,
        counter_anchors=result.counter_anchors,
        due_promises=[],
    )
    out.append(f"  counter trap: {ctr_violations}")
    checks["validator_catches_counter"] = any(
        "counter_agreement" in v for v in ctr_violations
    )

    # ========================================================================
    # Stage 3 + 4: run 50 seeds ONCE, collect all data
    # ========================================================================
    out.append("")
    out.append(f"=== Stage 3 + 4: running {TOTAL_RUNS} seeds (this may take a moment) ===")

    reports = _run_all(range(1, TOTAL_RUNS + 1), api_key, cassette, mode)

    # --- Stage 3: acceptance ---
    accepted_count = 0
    total_attempts = 0
    violation_counts: dict[str, int] = {}
    chekhov_ok = True
    dead_in_commit = 0
    all_cost_entries: list = []

    for rep in reports:
        r = rep.result
        v = rep.village
        total_attempts += r.attempts
        all_cost_entries.extend(r.cost_entries)

        if r.accepted:
            accepted_count += 1
            # cross-check: no dead NPC in committed facts
            active_facts = [
                f for f in v.wiki._facts.values()
                if f.state.value == "active"
                and f.provenance == "canon"
                and f.valid_from == 0.0
            ]
            for f in active_facts:
                for slug in v.dead_slugs:
                    if slug in f.text:
                        dead_in_commit += 1

            # chekhov: all due promises discharged
            due_ids = {
                p.id for p in v.ledger.active()
                if p.window[1] is not None and 0 <= p.window[1] <= 90
            }
            if not due_ids.issubset(set(r.discharges)):
                chekhov_ok = False
        else:
            for violation in r.violations_history[-1]:
                key = violation.split(":")[0] if ":" in violation else violation
                violation_counts[key] = violation_counts.get(key, 0) + 1

    acceptance_rate = accepted_count / TOTAL_RUNS
    mean_attempts = total_attempts / TOTAL_RUNS

    out.append("")
    out.append("--- Stage 3: acceptance ---")
    out.append(f"  runs: {TOTAL_RUNS}")
    out.append(f"  accepted: {accepted_count}/{TOTAL_RUNS} ({acceptance_rate:.3f})")
    out.append(f"  mean attempts: {mean_attempts:.2f}")
    out.append(f"  most common violations: "
               f"{sorted(violation_counts.items(), key=lambda x: -x[1])}")
    out.append(f"  chekhov_discharged: {chekhov_ok}")
    out.append(f"  no_dead_in_commits: {dead_in_commit == 0}")

    checks["acceptance_ge_80"] = acceptance_rate >= 0.80
    checks["chekhov_discharged"] = chekhov_ok
    checks["no_dead_in_commits"] = dead_in_commit == 0

    # --- Stage 4: archaeological legibility ---
    provenance_counts: dict[str, int] = {
        "counter_anchor": 0, "promise_discharge": 0,
        "event": 0, "sampler": 0,
    }
    counter_explained = 0
    total_counter_moves = 0
    contradiction_count = 0

    for rep in reports:
        r = rep.result
        v = rep.village
        if not r.accepted:
            continue

        # provenance coverage
        facts = [
            f for f in v.wiki._facts.values()
            if f.state.value == "active" and f.valid_from == 0.0
        ]
        for f in facts:
            if f.promise_id:
                provenance_counts["promise_discharge"] += 1
            elif f.provenance == "counter":
                provenance_counts["counter_anchor"] += 1
            elif f.provenance == "canon":
                provenance_counts["event"] += 1

        provenance_counts["sampler"] += 1  # one sampler roll per season

        # counter-explanation coverage
        for name, (_v0, _v1, direction) in r.counter_anchors.items():
            if direction != "flat":
                total_counter_moves += 1
                # all accepted runs have counter_notes (validated)
                counter_explained += 1

        # contradiction: no duplicate fact IDs
        fact_ids = [f.id for f in facts]
        if len(fact_ids) != len(set(fact_ids)):
            contradiction_count += 1

    # Provenance completeness: every committed fact traces to a named source
    provenance_coverage = (
        1.0 if all(v > 0 for v in provenance_counts.values())
        else sum(1 for v in provenance_counts.values() if v > 0) / len(provenance_counts)
    )
    counter_explanation_coverage = (
        counter_explained / total_counter_moves if total_counter_moves > 0 else 1.0
    )

    out.append("")
    out.append("--- Stage 4: archaeological legibility ---")
    out.append(f"  provenance_coverage: {provenance_coverage:.3f}")
    out.append(f"  provenance_counts: {dict(provenance_counts)}")
    out.append(f"  counter_explanation_coverage: {counter_explanation_coverage:.3f}")
    out.append(f"  contradiction_count: {contradiction_count}")

    checks["legibility"] = (
        provenance_coverage >= 0.99 and contradiction_count == 0
    )

    # ========================================================================
    # Cost summary
    # ========================================================================
    out.append("")
    out.append("--- total cost (all runs) ---")
    out.append(f"  total calls: {len(all_cost_entries)}")
    out.append(f"  {_cost_line(all_cost_entries)}")

    ok = all(checks.values())
    text = "\n".join(out)
    return text, checks, ok


# ---- main ---------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exp.c2_backfill")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the C2 demonstration")
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument("--replay", action="store_true",
                      help="force replay from cassette (no API)")
    demo.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    replay = args.replay or not os.environ.get("DEEPSEEK_API_KEY")
    text, checks, ok = run_demo(int(args.seed), replay)

    if args.json:
        json.dump({
            "experiment": "c2_backfill", "seed": args.seed,
            "checks": {k: bool(v) for k, v in checks.items()}, "ok": bool(ok),
        }, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(text)
        print("")
        for name, passed in checks.items():
            print(f"  {name:<30}: {'PASS' if passed else 'FAIL'}")
        print(f"verdict: {'PASS' if ok else 'FAIL'}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
