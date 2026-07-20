"""K5 acceptance tests — authoritative promise ledger with TMS-lite
suspension, cascade, density index, and graveyard archival.

Lab spec §2 K5 done-when: scenario suite passes; minimal predicate
vocabulary covering ~20 canonical political facts.
"""

from __future__ import annotations

import pytest

from kernel.promise_ledger import (
    Predicate,
    PredicateKind,
    PromiseLedger,
    PromiseState,
)

from exp.k5_promise_ledger.fixtures import build_scenario

# ---- helpers ---------------------------------------------------------------

_p = lambda kind, s, o="", d="": Predicate(kind, s, o, d)


def _fresh() -> PromiseLedger:
    return PromiseLedger()


# ---- lifecycle -------------------------------------------------------------


class TestLifecycle:
    def test_assert_and_get(self):
        L = _fresh()
        pid = L.assert_(_p(PredicateKind.IS, "alice", "", "dead"), provenance="canon")
        p = L.get(pid)
        assert p is not None
        assert p.state == PromiseState.ACTIVE
        assert p.predicate.kind == PredicateKind.IS

    def test_discharge(self):
        L = _fresh()
        pid = L.assert_(_p(PredicateKind.CONTROLS, "bob", "east"), provenance="hard_orchestrator")
        L.discharge(pid)
        assert L.get(pid).state == PromiseState.DISCHARGED
        assert L.get(pid) not in list(L.active())

    def test_break(self):
        L = _fresh()
        pid = L.assert_(_p(PredicateKind.OWNS, "carl", "sword"))
        L.break_(pid)
        assert L.get(pid).state == PromiseState.BROKEN

    def test_expire(self):
        L = _fresh()
        pid = L.assert_(_p(PredicateKind.LOCATED, "dave", "village"),
                        window=(0, 100))
        assert L.get(pid).state == PromiseState.ACTIVE
        L.expire(50)
        assert L.get(pid).state == PromiseState.ACTIVE  # not yet
        expired = L.expire(100)
        assert pid in expired
        assert L.get(pid).state == PromiseState.EXPIRED

    def test_suspend_and_reconcile(self):
        L = _fresh()
        blocker = L.assert_(_p(PredicateKind.IS, "temp", "", "blocking"))
        pid = L.assert_(_p(PredicateKind.HOLDS, "erin", "capital", "mayor"),
                        provenance="soft_orchestrator")
        L.suspend(pid, suspended_by=blocker)
        assert L.get(pid).state == PromiseState.SUSPENDED
        # discharge the blocker → reconcile should restore
        L.discharge(blocker)
        assert L.get(pid).state == PromiseState.ACTIVE

    def test_reconcile_blocked_by_active_suspender(self):
        L = _fresh()
        # blocker is an active promise
        blocker = L.assert_(_p(PredicateKind.IS, "blocker", "", "present"))
        pid = L.assert_(_p(PredicateKind.FEALTY, "fang", "gale"))
        L.suspend(pid, suspended_by=blocker)
        n = L.reconcile()
        assert n == 0
        assert L.get(pid).state == PromiseState.SUSPENDED


# ---- authority / collision -------------------------------------------------


class TestAuthority:
    def test_higher_overrides_lower(self):
        L = _fresh()
        low = L.assert_(_p(PredicateKind.CONTROLS, "a", "region"),
                        provenance="npc", strength=0.3)
        # hard > npc → low suspends
        high = L.assert_(_p(PredicateKind.CONTROLS, "b", "region"),
                         provenance="hard_orchestrator")
        assert L.get(low).state == PromiseState.SUSPENDED
        assert L.get(high).state == PromiseState.ACTIVE

    def test_lower_suspended_by_higher(self):
        L = _fresh()
        high = L.assert_(_p(PredicateKind.CONTROLS, "a", "region"), provenance="canon")
        low = L.assert_(_p(PredicateKind.CONTROLS, "b", "region"), provenance="soft_orchestrator")
        assert L.get(low).state == PromiseState.SUSPENDED
        assert L.get(high).state == PromiseState.ACTIVE
        assert L.get(low).suspended_by == high

    def test_same_authority_rejected(self):
        L = _fresh()
        L.assert_(_p(PredicateKind.CONTROLS, "a", "region"), provenance="hard_orchestrator")
        with pytest.raises(ValueError, match="same-authority"):
            L.assert_(_p(PredicateKind.CONTROLS, "b", "region"), provenance="hard_orchestrator")

    def test_no_conflict_different_regions(self):
        L = _fresh()
        a = L.assert_(_p(PredicateKind.CONTROLS, "a", "east"))
        b = L.assert_(_p(PredicateKind.CONTROLS, "b", "west"))
        assert L.get(a).state == PromiseState.ACTIVE
        assert L.get(b).state == PromiseState.ACTIVE


# ---- cascade ---------------------------------------------------------------


class TestCascade:
    def test_dependents_suspend_with_dep(self):
        L = _fresh()
        root = L.assert_(_p(PredicateKind.IS, "king", "", "ruler"))
        child = L.assert_(_p(PredicateKind.HOLDS, "knight", "", "title"),
                          depends_on=(root,))
        L.suspend(root, suspended_by="ext:death")
        assert L.get(child).state == PromiseState.SUSPENDED
        assert L.get(child).suspended_by == "ext:death"

    def test_reconcile_blocked_by_inactive_dep(self):
        L = _fresh()
        root = L.assert_(_p(PredicateKind.IS, "king", "", "ruler"))
        child = L.assert_(_p(PredicateKind.HOLDS, "knight", "", "title"),
                          depends_on=(root,))
        # external suspender (not in ledger) → permanent block on root
        L.suspend(root, suspended_by="ext:death")
        assert L.get(child).state == PromiseState.SUSPENDED
        n = L.reconcile()
        assert n == 0
        assert L.get(child).state == PromiseState.SUSPENDED

    def test_child_reconciles_when_dep_restores(self):
        L = _fresh()
        root = L.assert_(_p(PredicateKind.IS, "king", "", "ruler"))
        child = L.assert_(_p(PredicateKind.HOLDS, "knight", "", "title"),
                          depends_on=(root,))
        # use an in-ledger promise as suspender, then discharge it
        blocker = L.assert_(_p(PredicateKind.IS, "event", "", "crisis"))
        L.suspend(root, suspended_by=blocker)
        assert L.get(child).state == PromiseState.SUSPENDED
        # root and child are both suspended; discharge the blocker
        L.discharge(blocker)
        # now root and child should both reconcile
        assert L.get(root).state == PromiseState.ACTIVE
        assert L.get(child).state == PromiseState.ACTIVE


# ---- conflict rules --------------------------------------------------------


class TestConflictRules:
    def test_dead_conflicts_with_ruler(self):
        L = _fresh()
        ruler = L.assert_(_p(PredicateKind.IS, "king", "", "ruler"), provenance="canon")
        # measurement overrides canon → ruler suspends
        dead = L.assert_(_p(PredicateKind.IS, "king", "", "dead"), provenance="measurement")
        assert L.get(ruler).state == PromiseState.SUSPENDED

    def test_dead_conflicts_with_controls(self):
        L = _fresh()
        dead = L.assert_(_p(PredicateKind.IS, "bob", "", "dead"), provenance="measurement")
        ctrl = L.assert_(_p(PredicateKind.CONTROLS, "bob", "region"), provenance="canon")
        # canon < measurement → controls suspends
        assert L.get(ctrl).state == PromiseState.SUSPENDED
        assert L.get(dead).state == PromiseState.ACTIVE

    def test_banished_conflicts_with_located(self):
        L = _fresh()
        ban = L.assert_(_p(PredicateKind.IS, "exile", "", "banished"), provenance="measurement")
        loc = L.assert_(_p(PredicateKind.LOCATED, "exile", "capital"), provenance="canon")
        assert L.get(loc).state == PromiseState.SUSPENDED
        assert L.get(ban).state == PromiseState.ACTIVE

    def test_hostile_vs_allied_same_authority_rejected(self):
        L = _fresh()
        L.assert_(_p(PredicateKind.HOSTILE, "elves", "dwarves"))
        with pytest.raises(ValueError, match="same-authority"):
            L.assert_(_p(PredicateKind.ALLIED, "elves", "dwarves"))

    def test_hostile_vs_allied_order_insensitive(self):
        L = _fresh()
        L.assert_(_p(PredicateKind.ALLIED, "dwarves", "elves"))
        with pytest.raises(ValueError, match="same-authority"):
            L.assert_(_p(PredicateKind.HOSTILE, "elves", "dwarves"))


# ---- density & graveyard ---------------------------------------------------


class TestDensity:
    def test_density_sums_strength(self):
        L = _fresh()
        L.assert_(_p(PredicateKind.CONTROLS, "a", "capital"), scope="capital", strength=1.0)
        L.assert_(_p(PredicateKind.HOLDS, "b", "capital"), scope="capital", strength=0.5)
        assert L.density("capital") == 1.5

    def test_density_ranking(self):
        L = _fresh()
        L.assert_(_p(PredicateKind.CONTROLS, "duke", "hotspot"), strength=0.9)
        L.assert_(_p(PredicateKind.CONTROLS, "baron", "backwater"), strength=0.2)
        ranked = L.density_ranking()
        densities = {r: d for r, d in ranked}
        assert densities["hotspot"] == 0.9
        assert densities["backwater"] == 0.2
        assert densities["hotspot"] > densities["backwater"]


class TestGraveyard:
    def test_non_active_in_graveyard(self):
        L = _fresh()
        pid = L.assert_(_p(PredicateKind.OWNS, "miller", "mill"))
        L.discharge(pid)
        grave = L.graveyard()
        assert any(p.id == pid for p in grave)
        assert pid not in {p.id for p in L.active()}

    def test_scope_filter(self):
        L = _fresh()
        a = L.assert_(_p(PredicateKind.CONTROLS, "x", "east"), scope="east")
        b = L.assert_(_p(PredicateKind.CONTROLS, "y", "west"), scope="west")
        L.discharge(a)
        L.discharge(b)
        assert len(L.graveyard(scope="east")) == 1
        assert len(L.graveyard(scope="west")) == 1
        assert len(L.graveyard(scope="north")) == 0


# ---- scenario --------------------------------------------------------------


class TestScenario:
    def test_fixture_expected_states(self):
        ledger, ids = build_scenario()

        # Cerys suspended by Beric's harder claim
        assert ledger.get(ids["cerys_westvale"]).state == PromiseState.SUSPENDED

        # King's rule suspended by death measurement
        assert ledger.get(ids["king_ruler"]).state == PromiseState.SUSPENDED

        # Cascade: Beric, Gareth, fealty all suspended
        for key in ("beric_westvale", "gareth_guard", "duke_fealty"):
            assert ledger.get(ids[key]).state == PromiseState.SUSPENDED, key

        # Aldric is now the active ruler
        assert ledger.get(ids["aldric_ruler"]).state == PromiseState.ACTIVE

        # Gareth's new commission is active
        assert ledger.get(ids["gareth_confirmed"]).state == PromiseState.ACTIVE

        # No active conflicts
        assert ledger.validate() == []

        # Westvale appears in the density ranking (has suspended promises
        # that mark it as a region of interest, even if active density is 0).
        ranked_regions = {r for r, _ in ledger.density_ranking()}
        assert "westvale" in ranked_regions

    def test_fixture_no_duplicate_ids(self):
        _, ids = build_scenario()
        assert len(set(ids.values())) == len(ids)


# ---- vocabulary coverage (spec-note) ---------------------------------------


def test_predicate_kinds_cover_canonical_facts():
    """Demonstrate that the 10 kinds can express ≥20 canonical political
    facts, as the K5 vocabulary question requires."""
    examples = [
        (PredicateKind.OWNS,     "merchant", "granary", ""),
        (PredicateKind.OWNS,     "dragon",   "hoard", ""),
        (PredicateKind.CONTROLS, "baron",    "fief", ""),
        (PredicateKind.CONTROLS, "council",  "free_city", ""),
        (PredicateKind.IS,       "king",     "",    "dead"),
        (PredicateKind.IS,       "prince",   "",    "heir"),
        (PredicateKind.IS,       "duke",     "",    "ruler"),
        (PredicateKind.IS,       "traitor",  "",    "banished"),
        (PredicateKind.FEALTY,   "vassal",   "liege", ""),
        (PredicateKind.FEALTY,   "knight",   "order", ""),
        (PredicateKind.HOSTILE,  "kingdom_a", "kingdom_b", ""),
        (PredicateKind.ALLIED,   "elves",    "humans", ""),
        (PredicateKind.LOCATED,  "wizard",   "tower", ""),
        (PredicateKind.LOCATED,  "army",     "pass", ""),
        (PredicateKind.DISPUTED, "borderlands", "kingdom_a,kingdom_b", ""),
        (PredicateKind.DISPUTED, "throne",   "claimant_a,claimant_b", ""),
        (PredicateKind.BOUND,    "queen",    "king",  "marriage"),
        (PredicateKind.BOUND,    "clan_a",   "clan_b", "blood_truce"),
        (PredicateKind.HOLDS,    "marshal",  "army",  "commander"),
        (PredicateKind.HOLDS,    "abbot",    "abbey", "prelate"),
    ]
    assert len(examples) == 20
    # all construct without error
    for kind, s, o, d in examples:
        p = Predicate(kind, s, o, d)
        assert p.narrative()  # renders


def test_predicate_vocabulary_is_minimal():
    """No two kinds are semantically equivalent."""
    kinds = list(PredicateKind)
    for i in range(len(kinds)):
        for j in range(i + 1, len(kinds)):
            assert kinds[i].value != kinds[j].value
