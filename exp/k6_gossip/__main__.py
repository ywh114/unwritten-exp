"""K6 demo CLI: `uv run python -m exp.k6_gossip demo --seed 1 [--json]`.

Propagates "the mill burned" through a 50-NPC Watts–Strogatz contact
graph for 7 days, then prints distortion-vs-distance curves, sample
beliefs, traceback results, and an A/B comparison with halved tau.

Exit 0 iff all checks pass.  Twice with --json → byte-identical output.
"""

from __future__ import annotations

import argparse
import json
import sys

import networkx as nx

from kernel.hashrng import Stream

from exp.k6_gossip.fixtures import build_graph, build_rumor, injected_node
from exp.k6_gossip.network import GossipNetwork, GossipParams

DAYS = 7


# ---- helpers ---------------------------------------------------------------


def _distance_bucket(dist: int) -> str:
    if dist <= 0:
        return "0"
    if dist == 1:
        return "1"
    if dist == 2:
        return "2"
    return "3+"


def _bucket_report(net: GossipNetwork, source: int) -> list[dict]:
    """Per-distance-bucket stats: believers count, mean trust, mean dropped
    fields per rumor, mean |magnitude − 1.0|."""
    buckets: dict[str, list] = {"0": [], "1": [], "2": [], "3+": []}
    dist_map = dict(nx.shortest_path_length(net.graph, source=source))

    for node in net.believers():
        b = net.belief(node)
        if b is None:
            continue
        d = dist_map.get(node, 999)
        key = _distance_bucket(d)
        dropped = (1 if b.rumor.location is None else 0) + \
                  (1 if b.rumor.day is None else 0)
        buckets[key].append({
            "trust": b.trust,
            "dropped": dropped,
            "mag_err": abs(b.rumor.magnitude - 1.0),
        })

    report = []
    for key in ["0", "1", "2", "3+"]:
        items = buckets[key]
        if not items:
            report.append({"bucket": key, "believers": 0})
        else:
            report.append({
                "bucket": key,
                "believers": len(items),
                "mean_trust": sum(it["trust"] for it in items) / len(items),
                "mean_dropped": sum(it["dropped"] for it in items) / len(items),
                "mean_mag_err": sum(it["mag_err"] for it in items) / len(items),
            })
    return report


def _sample_beliefs(net: GossipNetwork, source: int, n: int = 5) -> list[dict]:
    """n sample beliefs at increasing distances from source."""
    dist_map = dict(nx.shortest_path_length(net.graph, source=source))
    by_dist = sorted(
        [(dist_map.get(node, 999), node) for node in net.believers()],
        key=lambda x: x[0],
    )
    samples = []
    seen = set()
    for dist, node in by_dist:
        if node in seen:
            continue
        seen.add(node)
        b = net.belief(node)
        if b:
            samples.append({
                "node": node,
                "distance": dist,
                "trust": b.trust,
                "rumor": {
                    "subject": b.rumor.subject,
                    "event": b.rumor.event,
                    "location": b.rumor.location,
                    "day": b.rumor.day,
                    "magnitude": b.rumor.magnitude,
                },
            })
        if len(samples) >= n:
            break
    return samples


# ---- demo logic ------------------------------------------------------------


def run_demo(seed: int) -> tuple[str, dict, bool]:
    graph = build_graph(seed)
    rumor = build_rumor()
    source = injected_node()

    # --- baseline run ---
    params = GossipParams()
    net = GossipNetwork(graph, params, world_seed=seed)
    net.inject(source, rumor, trust=1.0)
    net.propagate(DAYS)

    bucket_rpt = _bucket_report(net, source)
    samples = _sample_beliefs(net, source)
    believers = net.believers()
    loc_rate = net.localization_rate(source)

    # --- A/B: tau halved ---
    params_halved = GossipParams(tau=0.425)
    net_b = GossipNetwork(graph.copy(), params_halved, world_seed=seed)
    net_b.inject(source, rumor, trust=1.0)
    net_b.propagate(DAYS)
    bucket_b = _bucket_report(net_b, source)

    # --- trace examples ---
    trace_examples = []
    for node in believers[:5]:
        pred = net.trace_source(node)
        dist_map = dict(nx.shortest_path_length(net.graph, source=source))
        dist = nx.shortest_path_length(net.graph, pred, source) if pred is not None else -1
        trace_examples.append({
            "start_node": node,
            "predicted_source": pred,
            "true_source": source,
            "error_hops": dist,
        })

    # --- checks ---
    checks: dict[str, bool] = {}

    # believers > 30
    checks["believers_gt_30"] = len(believers) > 30

    # mean trust non-increasing across distance buckets 0,1,2,3+
    trusts = [d.get("mean_trust", 0) for d in bucket_rpt]
    checks["trust_non_increasing"] = all(
        trusts[i] >= trusts[i + 1] - 1e-9
        for i in range(len(trusts) - 1) if bucket_rpt[i].get("believers", 0) and bucket_rpt[i+1].get("believers", 0)
    )

    # localization_rate ≥ 0.70
    checks["localization_rate"] = loc_rate >= 0.70

    # tau-halved: lower mean trust in bucket ≥ 2
    tau_check_ok = True
    for a, b in zip(bucket_rpt, bucket_b):
        if a["bucket"] in ("2", "3+") and a.get("believers", 0) and b.get("believers", 0):
            if b.get("mean_trust", 0) >= a.get("mean_trust", 0):
                tau_check_ok = False
    checks["tau_halved_lower_trust"] = tau_check_ok

    ok = all(checks.values())

    text_lines = [
        "K6 gossip demo — 'the mill burned' through 50-NPC graph, 7 days",
        "",
        "=== Distance-bucket report (baseline) ===",
    ]
    for d in bucket_rpt:
        text_lines.append(
            f"  bucket {d['bucket']}: {d.get('believers', 0):3d} believers  "
            f"mean_trust={d.get('mean_trust', 0):.4f}  "
            f"mean_dropped={d.get('mean_dropped', 0):.2f}  "
            f"mean_mag_err={d.get('mean_mag_err', 0):.3f}"
        )

    text_lines.append("")
    text_lines.append("=== Sample beliefs ===")
    for s in samples:
        r = s["rumor"]
        text_lines.append(
            f"  node {s['node']:2d} (dist {s['distance']:2d}): "
            f"trust={s['trust']:.4f}  "
            f"\"{r['subject']} {r['event']} @ {r['location']} day {r['day']}  "
            f"mag={r['magnitude']:.3f}\""
        )

    text_lines.append("")
    text_lines.append("=== Traceback ===")
    text_lines.append(f"  localization_rate = {loc_rate:.3f}")
    for ex in trace_examples:
        text_lines.append(
            f"  node {ex['start_node']:2d} → predicted {ex['predicted_source']}  "
            f"(true {ex['true_source']}, error {ex['error_hops']} hops)"
        )

    text_lines.append("")
    text_lines.append("=== A/B: tau halved (baseline vs τ={:.3f}) ===".format(params_halved.tau))
    for a, b in zip(bucket_rpt, bucket_b):
        text_lines.append(
            f"  bucket {a['bucket']}: "
            f"trust {a.get('mean_trust', 0):.4f} → {b.get('mean_trust', 0):.4f}"
        )

    text = "\n".join(text_lines)
    return text, checks, ok


# ---- main ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exp.k6_gossip")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the K6 demonstration")
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    seed = int(args.seed)
    text, checks, ok = run_demo(seed)

    if args.json:
        json.dump({
            "experiment": "k6_gossip", "seed": seed,
            "checks": {k: bool(v) for k, v in checks.items()}, "ok": bool(ok),
        }, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(text)
        for name, passed in checks.items():
            print(f"  {name:<28}: {'PASS' if passed else 'FAIL'}")
        print(f"verdict: {'PASS' if ok else 'FAIL'}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
