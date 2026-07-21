"""K7 acceptance tests — trust-scored wiki store with deterministic retrieval.

Lab spec §2 K7 done-when: ported behaviours match Ara's; new metadata
round-trips; trust semantics for lies are correct; content-addressed ids.
"""

from __future__ import annotations

import pytest

from kernel.wiki_store.facts import Fact, FactState, close, make_fact
from kernel.wiki_store.index import HashedIndex
from kernel.wiki_store.store import QuerierContext, WikiStore


# ---- helpers ---------------------------------------------------------------

def _fresh() -> WikiStore:
    return WikiStore()


# ---------------------------------------------------------------------------
# 1. record
# ---------------------------------------------------------------------------

class TestRecord:
    def test_trust_range_validated(self):
        with pytest.raises(ValueError):
            make_fact("x", trust=1.5)
        with pytest.raises(ValueError):
            make_fact("x", trust=-1.5)

    def test_content_addressed_id_stable(self):
        a = make_fact("the mill burned", provenance="canon", valid_from=0.0)
        b = make_fact("the mill burned", provenance="canon", valid_from=0.0)
        assert a.id == b.id

    def test_different_content_different_id(self):
        a = make_fact("the mill burned")
        b = make_fact("the mill collapsed")
        assert a.id != b.id


# ---------------------------------------------------------------------------
# 2. recall
# ---------------------------------------------------------------------------

class TestRecall:
    def test_relevant_fact_returned(self):
        store = _fresh()
        f = make_fact("the mill burned", provenance="canon")
        store.write(f)
        results = store.recall("burned mill")
        assert len(results) >= 1
        assert results[0].text == "the mill burned"

    def test_distance_cap(self):
        store = _fresh()
        f = make_fact("the mill burned")
        store.write(f)
        results = store.recall("completely unrelated topic", max_distance=0.65)
        assert len(results) == 0

    def test_ordering_deterministic(self):
        store = _fresh()
        a = make_fact("alpha fact", valid_from=0.0)
        b = make_fact("beta fact", valid_from=0.0)
        store.write(a)
        store.write(b)
        r1 = store.recall("fact", k=2)
        r2 = store.recall("fact", k=2)
        assert [f.id for f in r1] == [f.id for f in r2]


# ---------------------------------------------------------------------------
# 3. temporal
# ---------------------------------------------------------------------------

class TestTemporal:
    def test_as_of_filters(self):
        store = _fresh()
        f = make_fact("old news", valid_from=10.0, valid_until=20.0)
        store.write(f)
        assert len(store.recall("old", as_of=5.0)) == 0  # before start
        assert len(store.recall("old", as_of=15.0)) == 1  # during
        assert len(store.recall("old", as_of=25.0)) == 0  # after end

    def test_archived_excluded_from_recall(self):
        store = _fresh()
        f = make_fact("expired")
        store.write(f)
        store.forget(f.id, 50.0)
        assert len(store.recall("expired")) == 0


# ---------------------------------------------------------------------------
# 4. forget
# ---------------------------------------------------------------------------

class TestForget:
    def test_forget_closes_never_deletes(self):
        store = _fresh()
        f = make_fact("ghost")
        store.write(f)
        store.forget(f.id, 100.0)
        assert store._facts[f.id].state == FactState.ARCHIVED
        assert store._facts[f.id].valid_until == 100.0
        # still in the graveyard
        assert f.id in {g.id for g in store._facts.values()
                        if g.state == FactState.ARCHIVED}

    def test_chronicle_shows_closing_time(self):
        store = _fresh()
        f = make_fact("ancient")
        store.write(f)
        store.forget(f.id, 42.0)
        chronicle = store.chronicle()
        assert "t=42" in chronicle
        assert "ancient" in chronicle


# ---------------------------------------------------------------------------
# 5. supersede
# ---------------------------------------------------------------------------

class TestSupersede:
    def test_old_closed_new_active(self):
        store = _fresh()
        old = make_fact("bridge intact", valid_from=0.0)
        store.write(old)
        new = make_fact("bridge burned", valid_from=30.0)
        store.supersede(new, old.id)
        assert store._facts[old.id].state == FactState.ARCHIVED
        assert store._facts[old.id].superseded_by == new.id
        assert store._facts[new.id].state == FactState.ACTIVE

    def test_recall_returns_only_new(self):
        store = _fresh()
        old = make_fact("bridge intact", valid_from=0.0)
        store.write(old)
        new = make_fact("bridge burned", valid_from=30.0)
        store.supersede(new, old.id)
        results = store.recall("bridge", k=5, as_of=30.0)
        assert any("burned" in f.text for f in results)
        assert not any("intact" in f.text for f in results)


# ---------------------------------------------------------------------------
# 6. querier hard bounds
# ---------------------------------------------------------------------------

class TestQuerierBounds:
    def test_provenance_filter(self):
        store = _fresh()
        store.write(make_fact("canon fact", provenance="canon"))
        store.write(make_fact("npc rumor", provenance="npc:farmer"))
        ctx = QuerierContext(allowed_provenances={"canon"})
        results = store.recall("fact", querier=ctx, k=5)
        assert all(f.provenance == "canon" for f in results)

    def test_trust_floor(self):
        store = _fresh()
        store.write(make_fact("high trust", trust=0.9))
        store.write(make_fact("low trust", trust=0.1))
        ctx = QuerierContext(trust_floor=0.8)
        results = store.recall("trust", querier=ctx, k=5)
        assert all(f.trust >= 0.8 for f in results)


# ---------------------------------------------------------------------------
# 7. no inversion
# ---------------------------------------------------------------------------

class TestNoInversion:
    def test_negative_trust_returned_verbatim(self):
        store = _fresh()
        f = make_fact("the miller is a witch", trust=-0.8, provenance="npc:neighbour")
        store.write(f)
        results = store.recall("miller witch", k=5)
        assert len(results) >= 1
        formatted = store.format_recall(results)
        assert "witch" in formatted.lower()
        assert "-0.80" in formatted

    def test_no_inversion_in_format(self):
        store = _fresh()
        store.write(make_fact("Alice is a thief", trust=-0.6))
        results = store.recall("Alice thief", k=5)
        formatted = store.format_recall(results)
        # text must appear verbatim — no negation or rewriting
        assert "thief" in formatted
        assert "Alice is a thief" in formatted


# ---------------------------------------------------------------------------
# 8. promise ingestion
# ---------------------------------------------------------------------------

class TestPromiseIngestion:
    def test_provenance_and_window_aligned(self):
        from kernel.promise_ledger import (
            Predicate, PredicateKind, PromiseLedger,
        )
        L = PromiseLedger(seed=42)
        pid = L.assert_(
            Predicate(PredicateKind.IS, "king", "", "ruler"),
            provenance="canon", window=(0.0, 100.0),
        )
        L.discharge(pid)

        store = _fresh()
        p = L.get(pid)
        fid = store.ingest_promise(p, 50.0)
        f = store._facts[fid]
        assert f.provenance == "canon"
        assert f.valid_from == 0.0
        assert f.valid_until == 100.0
        assert f.promise_id == pid


# ---------------------------------------------------------------------------
# 9. chronicle
# ---------------------------------------------------------------------------

class TestChronicle:
    def test_ordered_by_closing_time(self):
        store = _fresh()
        f1 = make_fact("first", valid_from=0.0)
        f2 = make_fact("second", valid_from=0.0)
        store.write(f1)
        store.write(f2)
        store.forget(f1.id, 10.0)
        store.forget(f2.id, 5.0)
        chronicle = store.chronicle()
        lines = [l for l in chronicle.split("\n") if l.strip()]
        assert "second" in lines[0]  # closed earlier
        assert "first" in lines[1]

    def test_byte_identical(self):
        store_a = _fresh()
        f = make_fact("test chronicle")
        store_a.write(f)
        store_a.forget(f.id, 10.0)
        c1 = store_a.chronicle()

        store_b = _fresh()
        store_b.write(make_fact("test chronicle"))
        store_b.forget(list(store_b._facts.keys())[0], 10.0)
        c2 = store_b.chronicle()
        assert c1 == c2


# ---------------------------------------------------------------------------
# 10. round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_identical_recall_after_restore(self):
        store = _fresh()
        store.write(make_fact("the mill burned", provenance="canon"))
        store.write(make_fact("the inn is haunted", provenance="npc:farmer", trust=0.3))
        store.write(make_fact("the well is dry", trust=-0.5))

        dicts = store.to_dicts()
        store2 = WikiStore.from_dicts(dicts)

        for query in ["burned", "haunted", "dry well"]:
            r1 = store.recall(query, k=3)
            r2 = store2.recall(query, k=3)
            assert [f.id for f in r1] == [f.id for f in r2], query


# ---------------------------------------------------------------------------
# 11. HashedIndex
# ---------------------------------------------------------------------------

class TestHashedIndex:
    def test_self_query_distance_near_zero(self):
        idx = HashedIndex()
        idx.add("a", "the mill burned down last night")
        results = idx.query("the mill burned down last night", 1)
        assert len(results) == 1
        assert results[0][1] == pytest.approx(0.0, abs=0.01)

    def test_token_overlap_beats_disjoint(self):
        idx = HashedIndex()
        idx.add("a", "the mill burned down last night")
        idx.add("b", "the queen held a banquet")
        results = idx.query("burned mill", 2)
        assert results[0][0] == "a"

    def test_ordering_independent_of_insertion(self):
        idx_a = HashedIndex()
        idx_a.add("x", "first fact")
        idx_a.add("y", "second fact")
        r1 = idx_a.query("fact", 2)

        idx_b = HashedIndex()
        idx_b.add("y", "second fact")
        idx_b.add("x", "first fact")
        r2 = idx_b.query("fact", 2)

        assert r1 == r2
