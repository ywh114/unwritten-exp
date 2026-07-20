"""K1 demo CLI: `uv run python -m exp.k1_hashrng demo --seed 1 [--json]`.

Dumps a year of daily draws for two entities, proves bit-identical rerun,
and runs a χ² uniformity check over a fresh population of streams.
Exit code 0 iff every check passes.
"""

from __future__ import annotations

import argparse
import json
import sys

from kernel.hashrng import Stream, sample
from exp.k1_hashrng.statcheck import chi2_uniformity

YEAR_DAYS = 365
CHI2_ENTITIES = 200
CHI2_CLOCKS = 500  # 200 x 500 = 100k draws
CHI2_BINS = 100
CHI2_P_LO = 0.001
CHI2_P_HI = 0.999


def run_demo(seed: int) -> dict:
    entities = [f"villager:{i:03d}" for i in (1, 2)]
    streams = [Stream(seed, e) for e in entities]

    # 1. A year of daily draws per entity.
    year = {e: [s.uniform(day) for day in range(YEAR_DAYS)] for e, s in zip(entities, streams)}
    digests = {e: s.digest(0, YEAR_DAYS) for e, s in zip(entities, streams)}

    # 2. Bit-identical rerun: rebuild streams from scratch, re-digest.
    rerun_digests = {e: Stream(seed, e).digest(0, YEAR_DAYS) for e in entities}
    rerun_ok = rerun_digests == digests

    # 3. Canonical one-shot signature agrees with the Stream API.
    canonical_ok = sample(seed, entities[0], 0) == streams[0].uniform(0)

    # 4. χ² uniformity over a fresh population of streams.
    draws = [
        Stream(seed, f"chi2:{i:04d}").uniform(c)
        for i in range(CHI2_ENTITIES)
        for c in range(CHI2_CLOCKS)
    ]
    stat, df, p = chi2_uniformity(draws, CHI2_BINS)
    chi2_ok = CHI2_P_LO < p < CHI2_P_HI

    ok = rerun_ok and canonical_ok and chi2_ok
    return {
        "experiment": "k1_hashrng",
        "seed": seed,
        "streams": {
            e: {
                "digest_sha256": digests[e],
                "days": year[e],
                "head": year[e][:5],
            }
            for e in entities
        },
        "checks": {
            "bit_identical_rerun": rerun_ok,
            "canonical_signature": canonical_ok,
            "chi2_uniformity": {
                "samples": len(draws),
                "bins": CHI2_BINS,
                "statistic": round(stat, 3),
                "df": df,
                "p_value": round(p, 6),
                "ok": chi2_ok,
            },
        },
        "ok": ok,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exp.k1_hashrng")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the K1 demonstration")
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    report = run_demo(args.seed)

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"K1 hashrng demo — world seed {args.seed}")
        for e, s in report["streams"].items():
            print(f"  {e}: {s['digest_sha256'][:16]}…  first draws: "
                  + ", ".join(f"{u:.6f}" for u in s["head"]))
        c = report["checks"]
        chi = c["chi2_uniformity"]
        print(f"  bit-identical rerun : {'PASS' if c['bit_identical_rerun'] else 'FAIL'}")
        print(f"  canonical signature : {'PASS' if c['canonical_signature'] else 'FAIL'}")
        print(f"  χ² uniformity       : stat={chi['statistic']} df={chi['df']} "
              f"p={chi['p_value']} ({chi['samples']} draws) "
              f"{'PASS' if chi['ok'] else 'FAIL'}")
        print(f"verdict: {'PASS' if report['ok'] else 'FAIL'}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
