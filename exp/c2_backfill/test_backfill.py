"""C2 — test suite (API-free: stub transports, tmp cassettes).

Tests:
1. Validation: five focused tests — each rule + clean output
2. Pipeline with stub transport: all 5 stages, ledger + wiki assertions
3. Retry: first invalid, second valid → attempts=2
4. Chekhov enforcement: missing due-promise discharge = rejection
5. Cassette round-trip: record via stub, replay identical
6. Fixture: 20 NPCs, 2 dead; counters evaluate; due promises inside season
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

import llm.llm_client
from capability.eventfulness import sample_count
from kernel.hashrng import Stream
from kernel.counters import Counter, Logistic, Step
from kernel.promise_ledger import PromiseLedger, Predicate, PredicateKind
from kernel.wiki_store import WikiStore
from llm.llm_client import LLMClient, CassetteStore, CostLog
from llm.llm_client.cassette import request_key

from exp.c2_backfill.fixtures import build_village
from capability.backfill.schema import Village
from capability.backfill.schema import (
    BackfillEvent,
    BackfillResult,
    CounterNote,
    SeasonChronicle,
)
from capability.backfill.pipeline import backfill
from capability.backfill.validate import validate_chronicle


# ---- helpers ------------------------------------------------------------------


def _due_promises_of(village: Village) -> list:
    """Return the 2 due promises from the fixture village (window ends inside [0,90])."""
    return [
        p for p in village.ledger.active()
        if p.window[1] is not None and 0 <= p.window[1] <= 90
    ]


def _clean_chronicle(village: Village, k: int = 3) -> SeasonChronicle:
    """A clean, valid chronicle for this village (matches actual due promise IDs
    and counter directions). The first two events discharge due promises;
    remaining events are basic filler."""
    due = _due_promises_of(village)
    assert len(due) >= 2, f"expected at least 2 due promises, got {len(due)}"
    pid0, pid1 = sorted([p.id for p in due])[:2]

    # Read actual counter directions from the village
    counter_dirs: dict[str, str] = {}
    for name, counter in sorted(village.counters.items()):
        v0 = counter.value_at(0.0)
        v1 = counter.value_at(90.0)
        if v1 > v0:
            counter_dirs[name] = "up"
        elif v1 < v0:
            counter_dirs[name] = "down"
        else:
            counter_dirs[name] = "flat"

    events = [
        BackfillEvent(
            title="Miller repaired the wheel",
            kind="discharge",
            involves=["miller_tobias"],
            promise_discharge=pid0,
        ),
        BackfillEvent(
            title="Envoy arrived at the village gate",
            kind="social",
            involves=["carter_garrick", "elder_oswin"],
            promise_discharge=pid1,
        ),
    ]
    # Fill remaining events
    for i in range(k - 2):
        events.append(BackfillEvent(
            title=f"Notable occurrence #{i + 1}",
            kind="other",
            involves=[],
            promise_discharge=None,
        ))

    return SeasonChronicle(
        events=events,
        counter_notes=[
            CounterNote(counter="grain", direction=counter_dirs.get("grain", "up"),
                        reason="harvest was bountiful"),
            CounterNote(counter="population", direction=counter_dirs.get("population", "up"),
                        reason="two births this season"),
            CounterNote(counter="garrison", direction=counter_dirs.get("garrison", "up"),
                        reason="desertions reduced the count"),
        ],
        texture_line="A season of repairs, arrivals, and storms.",
    )




# ============================================================================
# 1. Validation tests (five focused)
# ============================================================================


class TestValidation:
    """Each rule rejects its canned violation and passes a clean output."""

    @staticmethod
    def _village_anchors(village: Village) -> dict[str, tuple[float, float, str]]:
        """Read counter anchors matching what the pipeline would compute."""
        out: dict[str, tuple[float, float, str]] = {}
        for name, c in sorted(village.counters.items()):
            v0 = c.value_at(0.0)
            v1 = c.value_at(90.0)
            if v1 > v0:
                d = "up"
            elif v1 < v0:
                d = "down"
            else:
                d = "flat"
            out[name] = (v0, v1, d)
        return out

    def test_clean_chronicle_passes(self):
        """A clean chronicle should have zero violations."""
        v = build_village(1)
        c = _clean_chronicle(v)
        violations = validate_chronicle(
            c, k=3, dead_slugs=v.dead_slugs,
            counter_anchors=self._village_anchors(v),
            due_promises=_due_promises_of(v),
        )
        assert violations == []

    def test_count_violation(self):
        """Wrong event count → count violation."""
        v = build_village(1)
        c = _clean_chronicle(v, k=3)
        violations = validate_chronicle(
            c, k=5,  # expect 5 but got 3
            dead_slugs=set(),
            counter_anchors=self._village_anchors(v),
            due_promises=_due_promises_of(v),
        )
        assert any("count" in v for v in violations)

    def test_resurrection_violation(self):
        """DEAD NPC in involves → resurrection violation."""
        v = build_village(1)
        c = _clean_chronicle(v, k=3)
        c.events[0].involves.append("old_cade")  # dead NPC
        violations = validate_chronicle(
            c, k=3, dead_slugs=v.dead_slugs,
            counter_anchors=self._village_anchors(v),
            due_promises=_due_promises_of(v),
        )
        assert any("resurrection" in v for v in violations)

    def test_counter_agreement_violation(self):
        """Wrong counter direction → counter_agreement violation."""
        v = build_village(1)
        c = _clean_chronicle(v, k=3)
        # Flip grain direction to be wrong
        actual_dir = self._village_anchors(v)["grain"][2]
        wrong_dir = "down" if actual_dir == "up" else "up"
        c.counter_notes[0].direction = wrong_dir
        violations = validate_chronicle(
            c, k=3, dead_slugs=set(),
            counter_anchors=self._village_anchors(v),
            due_promises=_due_promises_of(v),
        )
        assert any("counter_agreement" in v for v in violations)

    def test_chekhov_violation(self):
        """Missing due-promise discharge → chekhov violation."""
        v = build_village(1)
        c = _clean_chronicle(v, k=3)
        # Remove discharge of second due promise
        c.events[1].promise_discharge = None
        violations = validate_chronicle(
            c, k=3, dead_slugs=set(),
            counter_anchors=self._village_anchors(v),
            due_promises=_due_promises_of(v),
        )
        assert any("chekhov" in v for v in violations)


# ============================================================================
# 2. Pipeline with stub transport
# ============================================================================


class TestPipelineStub:
    """A canned valid chronicle flows through all five stages."""

    def test_pipeline_all_stages(self):
        """All five stages execute; discharges, facts, anchors recorded."""
        village = build_village(42)
        # Use a separate stream just to know k; the pipeline uses its own
        k = sample_count(Stream(42, "c2.test"), 42, "season")
        chronicle = _clean_chronicle(village, k=k)

        # Stub transport: return the canned chronicle
        def stub_transport(payload: dict) -> dict:
            return {
                "choices": [{"message": {
                    "content": chronicle.model_dump_json(),
                }}],
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                },
            }

        client = LLMClient(
            api_key="fake",
            mode="live",
            transport=stub_transport,
        )

        stream = Stream(42, "c2.test")
        result = backfill(village, 0.0, 90.0, client, stream, max_retries=1)

        assert result.accepted
        assert result.attempts == 1

        # Discharges landed in ledger
        assert len(result.discharges) == 2
        for pid in result.discharges:
            p = village.ledger.get(pid)
            assert p is not None
            assert p.state.value == "discharged"

        # Facts landed in wiki (events + discharged/expired promises)
        active_facts = [f for f in village.wiki._facts.values()
                       if f.state.value == "active"]
        assert len(active_facts) >= 3  # at least the 3 events

        # Counter anchors recorded
        assert "grain" in result.counter_anchors
        assert "population" in result.counter_anchors
        assert "garrison" in result.counter_anchors

    def test_counter_anchors_directions(self):
        """Counter anchors have correct directions from K4 evaluation."""
        village = build_village(42)
        k = sample_count(Stream(42, "c2.test"), 42, "season")
        chronicle = _clean_chronicle(village, k=k)

        def stub_transport(payload: dict) -> dict:
            return {
                "choices": [{"message": {
                    "content": chronicle.model_dump_json(),
                }}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }

        client = LLMClient(
            api_key="fake", mode="live", transport=stub_transport,
        )
        stream = Stream(42, "c2.test")
        result = backfill(village, 0.0, 90.0, client, stream, max_retries=1)

        # Grain: Logistic with harvest regime, starting at 500, should grow
        _v0, v1, direction = result.counter_anchors["grain"]
        assert direction == "up"
        assert v1 > 500.0

        # Population: Logistic, slow growth from 120
        _v0, v1, direction = result.counter_anchors["population"]
        assert direction == "up"
        assert v1 >= 120.0

        # Garrison: Step with events at t=20 (+5) and t=50 (-3), net +2
        _v0, v1, direction = result.counter_anchors["garrison"]
        # events: t=20 delta=+5, t=50 delta=-3 → net +2
        assert v1 == 32.0
        assert direction == "up"


# ============================================================================
# 3. Retry
# ============================================================================


class TestRetry:
    """First response invalid, second valid → attempts=2, accepted."""

    def test_retry_after_resurrection(self):
        """First response resurrects a dead NPC; retry with clean passes."""
        village = build_village(42)
        k = sample_count(Stream(42, "c2.test"), 42, "season")

        clean = _clean_chronicle(village, k=k)
        bad = clean.model_copy(deep=True)
        bad.events[0].involves.append("old_cade")

        call_count = [0]

        def stub_transport(payload: dict) -> dict:
            call_count[0] += 1
            if call_count[0] == 1:
                return {
                    "choices": [{"message": {
                        "content": bad.model_dump_json(),
                    }}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                }
            else:
                return {
                    "choices": [{"message": {
                        "content": clean.model_dump_json(),
                    }}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                }

        client = LLMClient(
            api_key="fake", mode="live", transport=stub_transport,
        )
        stream = Stream(42, "c2.test")
        result = backfill(village, 0.0, 90.0, client, stream, max_retries=1)

        assert result.accepted
        assert result.attempts == 2
        assert len(result.violations_history) == 2
        assert len(result.violations_history[0]) > 0  # first had violations
        assert len(result.violations_history[1]) == 0  # second clean


# ============================================================================
# 4. Chekhov enforcement
# ============================================================================


class TestChekhov:
    """Output ignoring due promises is rejected even if otherwise valid."""

    def test_missing_due_discharge_rejected(self):
        """Chronicle with correct count, no dead NPCs, correct counters,
        but missing a due promise → rejected."""
        village = build_village(42)

        due = _due_promises_of(village)
        assert len(due) == 2

        # Build a chronicle that's valid except for missing the Chekhov discharge
        chronicle = SeasonChronicle(
            events=[
                BackfillEvent(
                    title="Miller repaired the wheel",
                    kind="discharge",
                    involves=["miller_tobias"],
                    promise_discharge=due[0].id,  # discharges one
                ),
                BackfillEvent(
                    title="Envoy was delayed",
                    kind="social",
                    involves=["carter_garrick"],
                    promise_discharge=None,  # missing second due promise!
                ),
                BackfillEvent(
                    title="Storm damaged the barn",
                    kind="weather",
                    involves=["farmer_eadric"],
                    promise_discharge=None,
                ),
            ],
            counter_notes=[
                CounterNote(counter="grain", direction="up",
                            reason="harvest was bountiful"),
                CounterNote(counter="population", direction="up",
                            reason="two births"),
                CounterNote(counter="garrison", direction="down",
                            reason="desertions"),
            ],
            texture_line="A mixed season.",
        )

        def stub_transport(payload: dict) -> dict:
            return {
                "choices": [{"message": {
                    "content": chronicle.model_dump_json(),
                }}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
            }

        client = LLMClient(
            api_key="fake", mode="live", transport=stub_transport,
        )
        stream = Stream(42, "c2.test")
        result = backfill(village, 0.0, 90.0, client, stream, max_retries=1)

        # Should be rejected — chekhov violation
        assert not result.accepted

        # But the LLM field for "pid_first_due" won't match actual due ids
        # The actual due promises from the fixture have deterministic ids
        # So we test that violations include chekhov
        last_violations = result.violations_history[-1]
        assert any("chekhov" in v for v in last_violations), \
            f"Expected chekhov violation, got: {last_violations}"


# ============================================================================
# 5. Cassette round-trip
# ============================================================================


class TestCassette:
    """Record via stub, replay identical result."""

    def test_round_trip(self):
        """Record a call via stub, then replay from cassette."""
        village = build_village(1)
        chronicle = _clean_chronicle(village, k=3)

        with tempfile.TemporaryDirectory() as tmp:
            cassette_dir = Path(tmp) / "cassettes"
            cassette = CassetteStore(cassette_dir)

            # --- record ---
            def stub_transport(payload: dict) -> dict:
                return {
                    "choices": [{"message": {
                        "content": chronicle.model_dump_json(),
                    }}],
                    "usage": {
                        "prompt_tokens": 200,
                        "completion_tokens": 100,
                        "prompt_cache_hit_tokens": 50,
                    },
                }

            record_client = LLMClient(
                api_key="fake", mode="record",
                cassette=cassette, transport=stub_transport,
            )
            record_client.call(
                llm.llm_client.Tier.T1_FLASH,
                [{"role": "user", "content": "chronicle please"}],
                schema=SeasonChronicle,
                purpose="c2.test",
            )

            # Verify cassette was written
            assert len(cassette.list()) == 1

            # --- replay (no transport, no API key) ---
            replay_client = LLMClient(
                api_key="", mode="replay", cassette=cassette,
            )
            result = replay_client.call(
                llm.llm_client.Tier.T1_FLASH,
                [{"role": "user", "content": "chronicle please"}],
                schema=SeasonChronicle,
                purpose="c2.test",
            )

            assert result.from_cassette
            assert result.parsed is not None
            assert result.parsed.texture_line == chronicle.texture_line
            assert len(result.parsed.events) == len(chronicle.events)
            assert result.parsed.model_dump_json() == chronicle.model_dump_json()

    def test_replay_miss_raises(self):
        """Replay of unknown request raises CassetteMiss."""
        with tempfile.TemporaryDirectory() as tmp:
            cassette_dir = Path(tmp) / "cassettes"
            cassette = CassetteStore(cassette_dir)

            replay_client = LLMClient(
                api_key="", mode="replay", cassette=cassette,
            )
            with pytest.raises(llm.llm_client.CassetteMiss):
                replay_client.call(
                    llm.llm_client.Tier.T1_FLASH,
                    [{"role": "user", "content": "unknown request"}],
                    purpose="c2.test",
                )


# ============================================================================
# 6. Fixture tests
# ============================================================================


class TestFixture:
    """20 NPCs, 2 dead; counters evaluate; due promises fall inside season."""

    def test_npc_count_and_dead(self):
        """Fixture has exactly 20 NPCs and exactly 2 dead."""
        village = build_village(1)
        assert len(village.npcs) == 20
        assert len(village.dead_slugs) == 2
        dead_count = sum(1 for n in village.npcs if n.dead)
        assert dead_count == 2

    def test_counters_evaluate(self):
        """All counters evaluate at t0 and t1."""
        village = build_village(1)
        for name, counter in village.counters.items():
            v0 = counter.value_at(0.0)
            v1 = counter.value_at(90.0)
            assert isinstance(v0, float)
            assert isinstance(v1, float)
            assert v0 > 0

    def test_garrison_counter_events(self):
        """Garrison counter reflects inserted events."""
        village = build_village(1)
        g = village.counters["garrison"]
        v0 = g.value_at(0.0)
        assert v0 == 30.0
        # After recruitment at t=20
        assert g.value_at(25.0) == 35.0
        # After desertion at t=50
        assert g.value_at(60.0) == 32.0
        # At end
        assert g.value_at(90.0) == 32.0

    def test_grain_grows(self):
        """Grain counter (Logistic + harvest regime) grows."""
        village = build_village(1)
        grain = village.counters["grain"]
        v0 = grain.value_at(0.0)
        v1 = grain.value_at(90.0)
        assert v1 > v0  # Growing under harvest regime

    def test_due_promises_in_season(self):
        """Exactly 2 due promises have window end inside [0, 90]."""
        village = build_village(1)
        due = [
            p for p in village.ledger.active()
            if p.window[1] is not None and 0 <= p.window[1] <= 90
        ]
        assert len(due) == 2, f"Expected 2 due promises, got {len(due)}"

    def test_promise_count(self):
        """At least 6 active promises at t=0."""
        village = build_village(1)
        active = village.ledger.active()
        assert len(active) >= 6

    def test_determinism(self):
        """Same seed → byte-identical villages."""
        v1 = build_village(42)
        v2 = build_village(42)
        # Compare NPCs
        assert [n.slug for n in v1.npcs] == [n.slug for n in v2.npcs]
        # Compare counter values
        for name in v1.counters:
            assert v1.counters[name].value_at(50.0) == v2.counters[name].value_at(50.0)
        # Compare promise ids
        ids1 = [p.id for p in v1.ledger.active()]
        ids2 = [p.id for p in v2.ledger.active()]
        assert ids1 == ids2
