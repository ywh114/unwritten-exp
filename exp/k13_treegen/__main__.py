"""M9 — persistence & CLI: TOML content in, JSON tree out.

    uv run python -m exp.k13_treegen SEED [--out DIR] [--species N]

Builds the tree for SEED (8-digit zero-padded in output names), names it,
runs the metrics gate, and writes:
    <out>/k13_seedNNNNNNNN.json    the committed tree (byte-stable)
    <out>/k13_seedNNNNNNNN.report  the metrics report (diff-able)
With --species, also prints N random species descriptions (the M11
qualitative gate). Defaults: out = exp/k13_treegen/out.
"""

from __future__ import annotations

import argparse
import pathlib

from exp.k13_treegen.backbone import build
from exp.k13_treegen.content import load_content
from exp.k13_treegen.describe import describe
from exp.k13_treegen.metrics import run_checks
from exp.k13_treegen.model import Rank
from exp.k13_treegen.nomenclature import assign_names

CONTENT = pathlib.Path(__file__).parent / "content" / "fauna"
OUT = pathlib.Path(__file__).parent / "out"


def generate(seed: int, pack) -> tuple:
    tree = build(seed, pack)
    from exp.artifacts import current_commit
    tree.meta["commit"] = current_commit()   # provenance stamp
    assign_names(tree, pack, seed)
    for n in tree.nodes.values():
        if n.rank is Rank.SPECIES:
            n.description = describe(n, pack)[0]
    report = run_checks(tree, pack)
    return tree, report


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("seed", type=int)
    ap.add_argument("--out", type=pathlib.Path, default=OUT)
    ap.add_argument("--species", type=int, default=0,
                    help="print N random species descriptions")
    args = ap.parse_args()

    pack = load_content(CONTENT)
    tree, report = generate(args.seed, pack)
    args.out.mkdir(parents=True, exist_ok=True)
    stem = f"k13_seed{args.seed:08d}"
    tree_path = args.out / f"{stem}.json"
    report_path = args.out / f"{stem}.report"
    tree_path.write_text(tree.dumps())
    report_path.write_text(report.text())
    counts = tree.to_json()["meta"]["counts"]
    print(f"{tree_path}  {counts}")
    print(f"{report_path}  {'OK' if report.ok else 'VIOLATIONS'}")
    if not report.ok:
        print(report.text())
    if args.species:
        sp = [n for n in tree.nodes.values() if n.rank is Rank.SPECIES]
        step = max(1, len(sp) // args.species)
        for n in sp[::step][:args.species]:
            text, _ = describe(n, pack)
            print(f"  {n.name.binomial:<28} {text}")


if __name__ == "__main__":
    main()
