"""K5 demo fixture — the King's Court scenario.

A ten-promise sequence that exercises every lifecycle operation:
collision (two parties promised the same province), cascade suspension
when the king dies, reconciliation of non-conflicting dependents, and
density ranking showing Westvale as the highest-attention location.

Entities / regions:
    king "eldric"  — ruler of Eldoria
    duke "aldric"  — lord of Northmarch
    lord "beric"   — claimant to Westvale (hard promise)
    lady "cerys"   — claimant to Westvale (soft promise, collider)
    captain "gareth" — captain of the guard (depends on the king)
    "capital" / "northmarch" / "westvale" / "eastport" — regions

Time is measured in days from an arbitrary epoch.  All windows are
perpetual unless a death or deposition sets an end.
"""

from __future__ import annotations

from kernel.promise_ledger import (
    Predicate,
    PredicateKind,
    PromiseLedger,
)

# ---- helpers ---------------------------------------------------------------


def _p(kind: PredicateKind, subject: str, object: str = "", detail: str = "") -> Predicate:
    return Predicate(kind, subject, object, detail)


def build_scenario(seed: int | None = None) -> tuple[PromiseLedger, dict[str, str]]:
    """Return (ledger, ids) where ids maps narrative names to promise ids."""
    L = PromiseLedger(seed=seed)
    ids: dict[str, str] = {}

    # 1.  The canon: King Eldric rules Eldoria.
    ids["king_ruler"] = L.assert_(
        _p(PredicateKind.IS, "eldric", "eldoria", "ruler"),
        scope="eldoria", provenance="canon", note="king coronated",
    )

    # 2.  Duke Aldric controls Northmarch.
    ids["duke_northmarch"] = L.assert_(
        _p(PredicateKind.CONTROLS, "aldric", "northmarch"),
        scope="northmarch", provenance="canon", note="ducal investiture",
    )

    # 3.  Duke Aldric owes fealty to King Eldric (depends on the king
    #     being ruler — cascade test).
    ids["duke_fealty"] = L.assert_(
        _p(PredicateKind.FEALTY, "aldric", "eldric"),
        scope="eldoria", provenance="hard_orchestrator",
        depends_on=(ids["king_ruler"],), note="oath of fealty",
    )

    # 4.  Lord Beric is granted Westvale — the harder promise in the
    #     collider pair.
    ids["beric_westvale"] = L.assert_(
        _p(PredicateKind.CONTROLS, "beric", "westvale"),
        scope="westvale", provenance="hard_orchestrator",
        depends_on=(ids["king_ruler"],),
        note="royal grant to Lord Beric",
    )

    # 5.  Lady Cerys is ALSO promised Westvale — the softer promise.
    #     This CONFLICTS with #4 (same region, different controller).
    #     Since Cerys is soft_orchestrator and Beric is hard_orchestrator,
    #     Cerys's promise is overridden → automatically SUSPENDED.
    ids["cerys_westvale"] = L.assert_(
        _p(PredicateKind.CONTROLS, "cerys", "westvale"),
        scope="westvale", provenance="soft_orchestrator",
        note="king's private assurance to Lady Cerys",
    )

    # 6.  Captain Gareth holds the palace guard — depends on the king.
    ids["gareth_guard"] = L.assert_(
        _p(PredicateKind.HOLDS, "gareth", "capital", "Captain of the Guard"),
        scope="capital", provenance="hard_orchestrator",
        depends_on=(ids["king_ruler"],), note="letters patent",
    )

    # 7.  MEASUREMENT: King Eldric is dead.
    #     Conflicts with #1 (IS ruler vs IS dead) → #1 suspends
    #     (measurement > canon).  Cascade: #3, #4, #6 depend on #1
    #     and also suspend.
    ids["king_dead"] = L.assert_(
        _p(PredicateKind.IS, "eldric", "", "dead"),
        scope="eldoria", provenance="measurement",
        note="the king is dead",
    )

    # 8.  Reconcile: no dependent can restore while #1 (king_ruler)
    #     is still suspended.  The dead-measurement is permanent; the
    #     king-ruler promise stays suspended forever.

    # 9.  The Duke claims the throne — a new hard promise.
    ids["aldric_ruler"] = L.assert_(
        _p(PredicateKind.IS, "aldric", "eldoria", "ruler"),
        scope="eldoria", provenance="hard_orchestrator",
        note="duke claims the throne",
    )

    # 10.  The Duke issues fresh letters to Gareth.
    ids["gareth_confirmed"] = L.assert_(
        _p(PredicateKind.HOLDS, "gareth", "capital", "Captain of the Guard"),
        scope="capital", provenance="hard_orchestrator",
        depends_on=(ids["aldric_ruler"],),
        note="confirmed by Lord Aldric, now ruler",
    )

    return L, ids
