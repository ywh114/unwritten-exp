"""L2 acceptance tests — API-free via FakeCacheTransport: cache hits are
earned by real byte-stability, not asserted."""

from __future__ import annotations

import pytest

from llm.llm_client.client import LLMClient

from llm.prefix_bench.bench import FakeCacheTransport, run_bench
from llm.prefix_bench.builder import PromptBuilder, canonical_digest
from exp.l2_prefix_bench.fixtures import DIGEST_STATE, SYSTEM_PROMPT, build_events
from llm.prefix_bench.policies import EveryN, OnPriority, TokenBudget, estimate_tokens


def make_client(transport) -> LLMClient:
    return LLMClient(api_key="test", transport=transport, mode="live")


def small_events(n=10):
    return [{"text": f"event number {i}"} for i in range(n)]


class TestBuilder:
    def test_prefix_byte_stable_within_epoch(self):
        b = PromptBuilder(system=SYSTEM_PROMPT)
        b.begin_epoch(DIGEST_STATE, intents=["a"])
        b.add_event("one")
        first = b.prefix_bytes()
        b.add_event("two")
        assert b.prefix_bytes() == first

    def test_epoch_change_alters_prefix(self):
        b = PromptBuilder(system=SYSTEM_PROMPT)
        b.begin_epoch(DIGEST_STATE)
        first = b.prefix_bytes()
        b.begin_epoch({**DIGEST_STATE, "season": "winter"})
        assert b.prefix_bytes() != first

    def test_canonical_digest_key_order_independent(self):
        a = canonical_digest({"x": 1, "y": [2, 3], "z": {"b": 1, "a": 2}})
        c = canonical_digest({"z": {"a": 2, "b": 1}, "y": [2, 3], "x": 1})
        assert a == c

    def test_flush_clears_tail_and_empty_build_raises(self):
        b = PromptBuilder(system=SYSTEM_PROMPT)
        b.begin_epoch({})
        with pytest.raises(ValueError):
            b.build_messages()
        b.add_event("one")
        msgs = b.flush()
        assert msgs[-1]["role"] == "user"
        assert "one" in msgs[-1]["content"]
        assert b.pending_count == 0

    def test_pending_tail_survives_epoch_change(self):
        b = PromptBuilder(system=SYSTEM_PROMPT)
        b.begin_epoch({"a": 1})
        b.add_event("one")
        b.begin_epoch({"a": 2})
        assert b.pending_count == 1
        assert "one" in b.flush()[-1]["content"]


class TestPolicies:
    def test_every_n(self):
        p = EveryN(3)
        assert not p.should_flush(1, 10, None)
        assert not p.should_flush(2, 10, None)
        assert p.should_flush(3, 10, None)
        assert p.should_flush(1, 10, "urgent")

    def test_token_budget(self):
        p = TokenBudget(100)
        assert not p.should_flush(1, 99, None)
        assert p.should_flush(1, 100, None)

    def test_on_priority(self):
        p = OnPriority("urgent")
        assert not p.should_flush(50, 10**6, None)
        assert p.should_flush(1, 1, "urgent")

    def test_estimate_tokens(self):
        assert estimate_tokens("abcd") == 1
        assert estimate_tokens("a" * 40) == 10


class TestBench:
    def test_naive_never_caches(self):
        t = FakeCacheTransport()
        r = run_bench(make_client(t), small_events(10), "naive",
                      system=SYSTEM_PROMPT, digest_state=DIGEST_STATE)
        assert r.calls == 10
        assert r.cache_hit_rate == 0.0
        assert r.cost_usd > 0

    def test_disciplined_earns_cache_hits(self):
        t = FakeCacheTransport()
        builder = PromptBuilder(system=SYSTEM_PROMPT)
        builder.begin_epoch(DIGEST_STATE, intents=["x"])
        r = run_bench(make_client(t), small_events(10), "disciplined",
                      system=SYSTEM_PROMPT, digest_state=DIGEST_STATE,
                      builder=builder, policy=EveryN(4))
        # 10 events at EveryN(4): flush at 4, 8, and final 2 → 3 calls
        assert r.calls == 3
        # every call after the first hits the cache
        assert r.cached_input_tokens > 0
        assert r.cache_hit_rate > 0.5

    def test_disciplined_cheaper_than_naive(self):
        events = small_events(12)
        naive = run_bench(make_client(FakeCacheTransport()), events, "naive",
                          system=SYSTEM_PROMPT, digest_state=DIGEST_STATE)
        builder = PromptBuilder(system=SYSTEM_PROMPT)
        builder.begin_epoch(DIGEST_STATE)
        disc = run_bench(make_client(FakeCacheTransport()), events, "disciplined",
                         system=SYSTEM_PROMPT, digest_state=DIGEST_STATE,
                         builder=builder, policy=EveryN(4))
        assert disc.cost_usd < naive.cost_usd

    def test_urgent_flushes_immediately(self):
        t = FakeCacheTransport()
        events = [{"text": f"ev{i}"} for i in range(5)]
        events.insert(2, {"text": "fire!", "priority": "urgent"})
        builder = PromptBuilder(system=SYSTEM_PROMPT)
        builder.begin_epoch(DIGEST_STATE)
        r = run_bench(make_client(t), events, "disciplined",
                      system=SYSTEM_PROMPT, digest_state=DIGEST_STATE,
                      builder=builder, policy=EveryN(100))
        # 6 events: urgent flush at ev2 + final flush → 2 calls despite EveryN(100)
        assert r.calls == 2

    def test_final_partial_batch_flushed(self):
        t = FakeCacheTransport()
        builder = PromptBuilder(system=SYSTEM_PROMPT)
        builder.begin_epoch(DIGEST_STATE)
        r = run_bench(make_client(t), small_events(7), "disciplined",
                      system=SYSTEM_PROMPT, digest_state=DIGEST_STATE,
                      builder=builder, policy=EveryN(5))
        assert r.calls == 2  # 5 + remainder 2


class TestFixture:
    def test_forty_events(self):
        events = build_events()
        assert len(events) == 40
        assert sum(1 for e in events if e.get("priority") == "urgent") == 3
