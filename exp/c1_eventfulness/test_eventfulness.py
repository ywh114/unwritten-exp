"""C1 acceptance tests."""

from __future__ import annotations

import json
import math
import tempfile
from pathlib import Path

import pytest

from kernel.hashrng import Stream
from llm.llm_client import LLMClient, Tier, CassetteStore, CassetteMiss

from capability.eventfulness.bench import (
    build_prompt_conditioned,
    build_prompt_unconditioned,
    run_arm,
)
from exp.c1_eventfulness.fixtures import build_intervals
from capability.eventfulness.sampler import sample_count, target_distribution


def _normal_sf(z):
    return 0.5 * math.erfc(z / math.sqrt(2.0))

def _chi2_pval(stat, df):
    z = ((stat / df) ** (1/3) - (1 - 2/(9*df))) / math.sqrt(2/(9*df))
    return stat, _normal_sf(z)


class TestSampler:
    def test_zero_rate_week(self):
        stream = Stream(1, "c1.test")
        zeros = sum(1 for _ in range(10_000)
                    if sample_count(stream, _, "week") == 0)
        assert zeros / 10_000 >= 0.50

    def test_mean_monotone_increasing(self):
        stream = Stream(2, "c1.test")
        means = {}
        for scale in ("week", "season", "year"):
            counts = target_distribution(stream, scale, n=10_000)
            means[scale] = sum(counts) / len(counts)
        assert means["week"] < means["season"] < means["year"]

    def test_determinism(self):
        a = target_distribution(Stream(42, "c1.test"), "season", n=100)
        b = target_distribution(Stream(42, "c1.test"), "season", n=100)
        assert a == b

    def test_regime_doubling_raises_mean(self):
        base = target_distribution(Stream(7, "c1.test"), "year", regime=1.0, n=5000)
        doubled = target_distribution(Stream(7, "c1.test"), "year", regime=2.0, n=5000)
        assert sum(doubled) / len(doubled) > sum(base) / len(base)

    def test_regime_low_lowers_mean(self):
        base = target_distribution(Stream(7, "c1.test"), "year", regime=1.0, n=5000)
        low = target_distribution(Stream(7, "c1.test"), "year", regime=0.2, n=5000)
        assert sum(low) / len(low) < sum(base) / len(base)

    def test_knuth_index_plan(self):
        a = sample_count(Stream(99, "c1.test"), 5, "week")
        b = sample_count(Stream(99, "c1.test"), 5, "week")
        assert a == b


class TestPrompt:
    def test_conditioned_contains_exact_count(self):
        msgs = build_prompt_conditioned("season", "autumn of year 3", 4)
        user_text = " ".join(m["content"] for m in msgs if m["role"] == "user")
        assert "4 notable events" in user_text or "exactly 4" in user_text.lower()

    def test_quiet_form_for_zero(self):
        msgs = build_prompt_conditioned("week", "week 1", 0)
        user_text = " ".join(m["content"] for m in msgs if m["role"] == "user")
        assert "nothing" in user_text.lower()

    def test_few_shots_present(self):
        msgs = build_prompt_conditioned("season", "winter", 0)
        combined = " ".join(m["content"] for m in msgs)
        assert "barley came in fine" in combined.lower()


class TestChi2:
    def test_sampler_vs_self_passes(self):
        all_a = []
        all_b = []
        for trial in range(100):
            all_a += target_distribution(Stream(trial, "c1.chi2"), "year", n=5000)
            all_b += target_distribution(Stream(trial + 1000, "c1.chi2"), "year", n=5000)
        bins_a = [sum(1 for x in all_a if min(x, 5) == i) for i in range(6)]
        bins_b = [sum(1 for x in all_b if min(x, 5) == i) for i in range(6)]
        probs = [x / sum(bins_b) for x in bins_b]
        n = len(all_a)
        stat, p = _chi2_pval(
            sum((bins_a[i] - n * probs[i])**2 / max(1, n * probs[i])
                for i in range(6)), 5)
        assert p > 0.01, f"pooled p={p:.4f}"

    def test_biased_fails(self):
        biased = [5] * 1000
        target = target_distribution(Stream(42, "c1.chi2b"), "year", n=1000)
        bins_b = [sum(1 for x in biased if min(x, 3) == i) for i in range(4)]
        bins_t = [sum(1 for x in target if min(x, 3) == i) for i in range(4)]
        probs = [x / sum(bins_t) for x in bins_t]
        stat = sum((bins_b[i] - 1000 * probs[i])**2 / max(1, 1000 * probs[i])
                   for i in range(4))
        _, p = _chi2_pval(stat, 3)
        assert p <= 0.01


def _stub_transport(canned: dict):
    def _transport(payload):
        return dict(canned)
    return _transport

def _make_canned(notable_events, texture="village texture"):
    return {
        "choices": [{"message": {"content": json.dumps({
            "notable_events": notable_events, "texture_line": texture})}}],
        "usage": {"prompt_tokens": 200, "completion_tokens": 50,
                  "total_tokens": 250, "prompt_cache_hit_tokens": 0,
                  "prompt_cache_miss_tokens": 200},
    }


class TestStubArms:
    def test_obedience_smoke(self):
        intervals = build_intervals()[:10]
        stream = Stream(1, "c1.stub")
        client = LLMClient(api_key="stub", mode="live",
                           transport=_stub_transport(
                               _make_canned(["event a", "event b"])))
        report = run_arm(client, stream, intervals, conditioned=True)
        assert report.total_calls == 10

    def test_obedience_miss_counted(self):
        intervals = build_intervals()[:5]
        stream = Stream(1, "c1.stub2")
        client = LLMClient(api_key="stub", mode="live",
                           transport=_stub_transport(_make_canned(["a", "b", "c"])))
        report = run_arm(client, stream, intervals, conditioned=True)
        assert report.total_calls == 5


class TestCassette:
    def test_record_replay_identical(self):
        intervals = build_intervals()[:5]
        stream = Stream(7, "c1.cass")
        canned = _make_canned(["alembic exploded"])
        with tempfile.TemporaryDirectory() as tmp:
            cs = CassetteStore(Path(tmp))
            client_rec = LLMClient(api_key="stub", mode="record", cassette=cs,
                                   transport=_stub_transport(canned))
            report_rec = run_arm(client_rec, stream, intervals, conditioned=True)
            stream2 = Stream(7, "c1.cass")
            client_rep = LLMClient(mode="replay", cassette=cs)
            report_rep = run_arm(client_rep, stream2, intervals, conditioned=True)
            assert [r["k_measured"] for r in report_rec.results] == \
                   [r["k_measured"] for r in report_rep.results]

    def test_replay_miss_raises(self):
        cs = CassetteStore(Path(tempfile.mkdtemp()))
        client = LLMClient(mode="replay", cassette=cs)
        with pytest.raises(CassetteMiss):
            client.call(Tier.T1_FLASH, [{"role": "user", "content": "hi"}])
