"""K5 demo CLI: `uv run python -m exp.k5_promise_ledger demo [--seed N] [--json]`.

Walks through the King's Court scenario step by step, printing state
transitions and a density ranking.  Exit 0 iff every check passes.
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap

from kernel.promise_ledger import PromiseState
from kernel.promise_ledger.predicates import PredicateKind

from exp.k5_promise_ledger.fixtures import build_scenario


def _demo_text(ledger, ids, seed: int | None = None) -> str:
    out: list[str] = []

    def _active(label: str) -> None:
        out.append(f"  {label}:")
        for p in ledger.active():
            out.append(f"    [{p.provenance}] {p.predicate.narrative()}  ({p.id})")
        out.append("")

    # Step through the narrative that build_scenario performs, inspecting
    # state at each interesting point.
    from kernel.promise_ledger import (
        Predicate,
        PredicateKind,
        PromiseLedger,
    )

    _p = lambda kind, s, o="", d="": Predicate(kind, s, o, d)

    L = PromiseLedger(seed=seed)
    ids_check: dict[str, str] = {}

    # 1. King Eldric rules Eldoria.
    out.append("1.  [canon]  King Eldric IS ruler of Eldoria")
    ids_check["king_ruler"] = L.assert_(
        _p(PredicateKind.IS, "eldric", "eldoria", "ruler"),
        scope="eldoria", provenance="canon",
    )

    # 2. Duke Aldric controls Northmarch.
    out.append("2.  [canon]  Duke Aldric CONTROLS Northmarch")
    ids_check["duke_northmarch"] = L.assert_(
        _p(PredicateKind.CONTROLS, "aldric", "northmarch"),
        scope="northmarch", provenance="canon",
    )

    # 3. Duke owes fealty.
    out.append("3.  [hard]   Duke owes FEALTY to King")
    ids_check["duke_fealty"] = L.assert_(
        _p(PredicateKind.FEALTY, "aldric", "eldric"),
        scope="eldoria", provenance="hard_orchestrator",
        depends_on=(ids_check["king_ruler"],),
    )

    # 4. Beric gets Westvale (hard).
    out.append("4.  [hard]   King promises Westvale to Lord Beric")
    ids_check["beric"] = L.assert_(
        _p(PredicateKind.CONTROLS, "beric", "westvale"),
        scope="westvale", provenance="hard_orchestrator",
        depends_on=(ids_check["king_ruler"],),
    )

    # 5. Cerys gets Westvale (soft) → collider, suspends.
    out.append("5.  [soft]   King also promises Westvale to Lady Cerys")
    out.append("    → CONFLICT with #4 (both CONTROLS westvale)")
    out.append("    → soft < hard → Cerys's promise SUSPENDED")
    ids_check["cerys"] = L.assert_(
        _p(PredicateKind.CONTROLS, "cerys", "westvale"),
        scope="westvale", provenance="soft_orchestrator",
    )
    cerys = L.get(ids_check["cerys"])
    assert cerys and cerys.state == PromiseState.SUSPENDED

    # 6. Gareth holds Captain of the Guard.
    out.append("6.  [hard]   Gareth HOLDS Captain of the Guard")
    ids_check["gareth"] = L.assert_(
        _p(PredicateKind.HOLDS, "gareth", "capital", "Captain of the Guard"),
        scope="capital", provenance="hard_orchestrator",
        depends_on=(ids_check["king_ruler"],),
    )

    out.append("--- state after initial assertions ---")
    _active("active promises")

    # 7. King dies.
    out.append("7.  [measurement]  King Eldric IS dead")
    out.append("    → CONFLICT with #1 (dead vs ruler)")
    out.append("    → measurement > canon → King's rule SUSPENDED")
    out.append("    → cascade: #3 fealty, #4 Beric, #6 Gareth all depend on #1 → SUSPENDED")
    ids_check["king_dead"] = L.assert_(
        _p(PredicateKind.IS, "eldric", "", "dead"),
        scope="eldoria", provenance="measurement",
    )

    out.append("--- state after king's death ---")
    _active("active promises")

    # 8. Reconcile.
    n = L.reconcile()
    out.append(f"8.  reconcile() → {n} promises restored")
    out.append("    (all suspended depend on #1, which is still suspended → none recover)")
    _active("active promises")

    # 9. Duke claims throne.
    out.append("9.  [hard]   Duke Aldric claims the throne")
    ids_check["aldric_ruler"] = L.assert_(
        _p(PredicateKind.IS, "aldric", "eldoria", "ruler"),
        scope="eldoria", provenance="hard_orchestrator",
    )

    # 10. Duke confirms Gareth.
    out.append("10. [hard]   Duke confirms Gareth as Captain")
    ids_check["gareth2"] = L.assert_(
        _p(PredicateKind.HOLDS, "gareth", "capital", "Captain of the Guard"),
        scope="capital", provenance="hard_orchestrator",
        depends_on=(ids_check["aldric_ruler"],),
    )

    out.append("--- final state ---")
    _active("active promises")

    # density ranking
    out.append("density ranking:")
    for region, d in L.density_ranking():
        out.append(f"  {region:<14} {d:.1f}")

    # graveyard
    out.append("\ngraveyard:")
    for p in L.graveyard():
        out.append(f"  [{p.state.value}] {p.predicate.narrative()}  ({p.id}) {p.note}")

    return "\n".join(out)


def _build_checks(ledger, ids) -> dict[str, bool]:
    c: dict[str, bool] = {}

    # Collider: Cerys is suspended
    cerys = ledger.get(ids["cerys_westvale"])
    c["cerys_suspended"] = cerys is not None and cerys.state == PromiseState.SUSPENDED

    # King's death suspended his rule
    king = ledger.get(ids["king_ruler"])
    c["king_suspended"] = king is not None and king.state == PromiseState.SUSPENDED

    # Cascade: Beric also suspended (depends on king_ruler)
    beric = ledger.get(ids["beric_westvale"])
    c["beric_cascade_suspended"] = beric is not None and beric.state == PromiseState.SUSPENDED

    # Gareth (old) also suspended
    gareth_old = ledger.get(ids["gareth_guard"])
    c["gareth_cascade_suspended"] = gareth_old is not None and gareth_old.state == PromiseState.SUSPENDED

    # Duke's fealty also suspended (depends on king)
    fealty = ledger.get(ids["duke_fealty"])
    c["fealty_cascade_suspended"] = fealty is not None and fealty.state == PromiseState.SUSPENDED

    # Aldric ruler is active
    aldric = ledger.get(ids["aldric_ruler"])
    c["aldric_active"] = aldric is not None and aldric.state == PromiseState.ACTIVE

    # New Gareth commission active
    gareth2 = ledger.get(ids["gareth_confirmed"])
    c["gareth_new_active"] = gareth2 is not None and gareth2.state == PromiseState.ACTIVE

    # Density: westvale appears in the ranking (even at 0 — it has suspended
    # promises, which the ranking collects as a region of interest).
    ranked_regions = {r for r, _ in ledger.density_ranking()}
    c["westvale_in_ranking"] = "westvale" in ranked_regions

    # Validate: no conflicting active pairs
    conflicts = ledger.validate()
    c["no_active_conflicts"] = len(conflicts) == 0

    # Graveyard: Cerys is in it (suspended = non-active = graveyard)
    grave_ids = {p.id for p in ledger.graveyard()}
    c["cerys_in_graveyard"] = ids["cerys_westvale"] in grave_ids

    # Westvale appears in density ranking (has suspended promises that mark it)
    ranked_regions = {r for r, _ in ledger.density_ranking()}
    c["westvale_in_ranking"] = "westvale" in ranked_regions

    return c


def run_demo(seed: int | None = None) -> dict:
    ledger, ids = build_scenario(seed=seed)
    checks = _build_checks(ledger, ids)
    ok = all(checks.values())

    active_serialised = [
        {
            "id": p.id,
            "scope": p.scope,
            "predicate": {
                "kind": str(p.predicate.kind),
                "subject": p.predicate.subject,
                "object": p.predicate.object,
                "detail": p.predicate.detail,
            },
            "provenance": p.provenance,
            "state": str(p.state),
            "note": p.note,
        }
        for p in ledger.all()
    ]

    return {
        "experiment": "k5_promise_ledger",
        "active_count": len(ledger.active()),
        "graveyard_count": len(ledger.graveyard()),
        "density_ranking": [
            {"region": r, "density": d} for r, d in ledger.density_ranking()
        ],
        "promises": active_serialised,
        "checks": checks,
        "ok": ok,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exp.k5_promise_ledger")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the K5 demonstration")
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv)

    ledger, ids = build_scenario(seed=args.seed)
    report = run_demo(seed=args.seed)

    if args.json:
        json.dump(report, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(_demo_text(ledger, ids, seed=args.seed))
        for name, passed in report["checks"].items():
            print(f"  {name:<28}: {'PASS' if passed else 'FAIL'}")
        print(f"verdict: {'PASS' if report['ok'] else 'FAIL'}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
