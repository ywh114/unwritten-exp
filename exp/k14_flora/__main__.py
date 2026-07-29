"""K14 persistence & CLI: TOML content in, JSON tree out.

    uv run python -m exp.k14_flora SEED [--out DIR] [--species N]

Builds the flora tree for SEED (8-digit zero-padded in output names),
names it, runs the metrics gate, and writes:
    <out>/k14_seedNNNNNNNN.json    the committed tree (byte-stable)
    <out>/k14_seedNNNNNNNN.report  the metrics report (diff-able)
With --species, also prints N sample species one-liners. Defaults:
out = exp/k14_flora/out.
"""

from __future__ import annotations

import argparse
import pathlib

from exp.k14_flora.backbone import build
from exp.k14_flora.content import load_content
from exp.k14_flora.metrics import run_checks
from exp.k14_flora.model import Rank
from exp.k14_flora.naming import assign_names

CONTENT = pathlib.Path(__file__).parent / "content"
OUT = pathlib.Path(__file__).parent / "out"


def generate(seed: int, pack) -> tuple:
    tree = build(seed, pack)
    assign_names(tree, pack, seed)
    report = run_checks(tree, pack)
    return tree, report


def _one_liner(n) -> str:
    a = n.axes
    return (f"{a.get('raunkiaer', '?'):<15} {a.get('height_m', 0):>8.2f} m  "
            f"{a.get('leaf_shape', '?')}/{a.get('flower_color', '?')}  "
            f"{a.get('pollination_syndrome', '?')}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("seed", type=int)
    ap.add_argument("--out", type=pathlib.Path, default=None)
    ap.add_argument("--species", type=int, default=0,
                    help="print N sample species one-liners")
    args = ap.parse_args()

    pack = load_content(CONTENT)
    tree, report = generate(args.seed, pack)
    out_dir = args.out or (OUT / f"seed_{args.seed:08d}")
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"k14_seed{args.seed:08d}"
    tree_path = out_dir / f"{stem}.json"
    report_path = out_dir / f"{stem}.report"
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
            print(f"  {n.name.binomial:<28} {_one_liner(n)}")


if __name__ == "__main__":
    main()
