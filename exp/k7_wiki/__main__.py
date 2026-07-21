"""K7 demo CLI: `uv run python -m exp.k7_wiki demo --seed 1 [--json]`.

Five-stage walkthrough over a 30-fact village wiki: query recall,
querier-context filtering, the verbatim lie, K5 promise ingestion
with chronicle, and JSON round-trip fidelity.
"""

from __future__ import annotations

import argparse
import json
import sys

from kernel.promise_ledger import Predicate, PredicateKind, PromiseLedger, PromiseState

from kernel.wiki_store.facts import FactState
from exp.k7_wiki.fixtures import build_store
from kernel.wiki_store.store import QuerierContext, WikiStore

# ---------------------------------------------------------------------------
# demo logic
# ---------------------------------------------------------------------------


def run_demo(seed: int) -> tuple[str, dict, bool]:
    store = build_store()
    checks: dict[str, bool] = {}
    out: list[str] = []

    # --- 1. Recall by query ------------------------------------------------
    out.append("=" * 60)
    out.append("Stage 1 — Recall: 'what happened to the bridge?'")
    results = store.recall("what happened to the bridge?", k=3)
    out.append(store.format_recall(results))
    # the superseding "bridge burned" must appear; the closed "bridge intact" is absent
    bridge_texts = [f.text for f in results]
    checks["bridge_burned_recalled"] = any(
        "burned" in t for t in bridge_texts
    )
    checks["bridge_intact_not_recalled"] = not any(
        "intact" in t for t in bridge_texts
    )

    # --- 2. Recall by querier -----------------------------------------------
    out.append("")
    out.append("=" * 60)
    out.append("Stage 2 — Recall by querier context")

    # a guard sees more: npc provenance + canon
    guard_ctx = QuerierContext(
        allowed_provenances={"npc", "canon"},
    )
    guard_results = store.recall("the miller", querier=guard_ctx, k=8)
    out.append("[guard (npc + canon)]:")
    out.append(store.format_recall(guard_results))

    # a canon-only cleric sees fewer facts
    canon_ctx = QuerierContext(allowed_provenances={"canon"})
    canon_results = store.recall("the miller", querier=canon_ctx, k=5)
    out.append("[cleric (canon only)]:")
    out.append(store.format_recall(canon_results))

    checks["guard_sees_more"] = len(guard_results) >= len(canon_results)
    checks["canon_only_no_rumors"] = all(
        f.provenance == "canon" for f in canon_results
    )

    # --- 3. The lie --------------------------------------------------------
    out.append("")
    out.append("=" * 60)
    out.append("Stage 3 — The lie (verbatim negative-trust fact)")
    lie_results = store.recall("witch poisons grain", k=5)
    # The fabricated rumor must appear verbatim with its negative trust
    # annotation — proving no inversion / rewriting.
    lie_fact = None
    for f in lie_results:
        if f.trust < 0:
            lie_fact = f
            break
    checks["lie_recalled_verbatim"] = (
        lie_fact is not None
        and "witch" in lie_fact.text.lower()
        and "poisons" in lie_fact.text.lower()
        and lie_fact.trust < 0
    )
    out.append(store.format_recall(lie_results))

    # --- 4. K5 integration -------------------------------------------------
    out.append("")
    out.append("=" * 60)
    out.append("Stage 4 — K5 promise ingestion → chronicle")

    L = PromiseLedger(seed=seed)
    king_ruler = L.assert_(
        Predicate(PredicateKind.IS, "eldric", "eldoria", "ruler"),
        provenance="canon",
    )
    duke_northmarch = L.assert_(
        Predicate(PredicateKind.CONTROLS, "aldric", "northmarch"),
        provenance="canon",
    )
    duke_fealty = L.assert_(
        Predicate(PredicateKind.FEALTY, "aldric", "eldric"),
        provenance="hard_orchestrator",
        depends_on=(king_ruler,),
    )

    # king dies → measurement suspends ruler promise
    L.assert_(
        Predicate(PredicateKind.IS, "eldric", "", "dead"),
        provenance="measurement",
    )

    # ingest all non-active promises, then close them for the chronicle
    ingested: list[str] = []
    for p in L.all():
        if p.state != PromiseState.ACTIVE:
            fact_id = store.ingest_promise(p, 50.0)
            ingested.append(fact_id)

    out.append(f"ingested {len(ingested)} discharged/suspended promises as facts")

    # archive them so they appear in the chronicle
    for p in L.all():
        if p.state != PromiseState.ACTIVE:
            fid = next((f.id for f in store._facts.values()
                        if f.promise_id == p.id), None)
            if fid:
                store.forget(fid, 60.0)

    out.append("")
    out.append("chronicle (archived facts):")
    chronicle_text = store.chronicle()
    out.append(chronicle_text if chronicle_text.strip() else "(chronicle empty)")

    checks["promises_ingested"] = len(ingested) == 2
    checks["chronicle_not_empty"] = len(chronicle_text.strip()) > 0
    # chronicle must mention the king and duke
    checks["chronicle_mentions_king"] = "eldric" in chronicle_text.lower()

    # --- 5. Round-trip -----------------------------------------------------
    out.append("")
    out.append("=" * 60)
    out.append("Stage 5 — to_dicts → from_dicts round-trip")

    dicts = store.to_dicts()
    store2 = WikiStore.from_dicts(dicts)
    q = "what happened in Ashwick?"
    r1 = store.recall(q, k=5)
    r2 = store2.recall(q, k=5)
    checks["roundtrip_same_count"] = len(r1) == len(r2)
    checks["roundtrip_same_order"] = all(
        a.id == b.id for a, b in zip(r1, r2)
    )

    ok = all(checks.values())
    text = "\n".join(out)
    return text, checks, ok


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="exp.k7_wiki")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run the K7 demonstration")
    demo.add_argument("--seed", type=int, default=1)
    demo.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    text, checks, ok = run_demo(int(args.seed))

    if args.json:
        json.dump({
            "experiment": "k7_wiki", "seed": args.seed,
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
