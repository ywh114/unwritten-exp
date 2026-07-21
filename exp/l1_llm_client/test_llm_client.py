"""L1 acceptance tests — all API-free (stub transport + tmp cassettes).

Lab spec §3 L1 done-when: cassettes make CI API-free; the cost log
schema is fixed (downstream reads it).
"""

from __future__ import annotations

import json

import pytest

from llm.llm_client.cassette import CassetteMiss, CassetteStore
from llm.llm_client.client import LLMClient, SchemaError
from llm.llm_client.costlog import compute_cost
from exp.l1_llm_client.fixtures import PROMPT, VillageRumor
from llm.llm_client import grammar
from llm.llm_client.tiers import Tier
from kernel.hashrng import Stream

GOOD_JSON = json.dumps({
    "headline": "Miller seen at the burned bridge",
    "subject": "the miller",
    "severity": 3,
    "involves_mill": True,
})


def make_response(content: str, *, reasoning: str | None = None, usage: dict | None = None,
                  response_id: str = "chatcmpl-test") -> dict:
    msg: dict = {"role": "assistant", "content": content}
    if reasoning is not None:
        msg["reasoning_content"] = reasoning
    return {
        "id": response_id,
        "choices": [{"message": msg, "finish_reason": "stop"}],
        "usage": usage or {
            "prompt_tokens": 100,
            "completion_tokens": 20,
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 20,
            "completion_tokens_details": {"reasoning_tokens": 0},
        },
    }


class StubTransport:
    """Serves queued responses; records payloads."""

    def __init__(self, responses: list[dict]):
        self.responses = list(responses)
        self.payloads: list[dict] = []

    def __call__(self, payload: dict) -> dict:
        self.payloads.append(payload)
        if not self.responses:
            raise AssertionError("transport called with no queued responses")
        return self.responses.pop(0)


def client_with(transport, cassette=None, mode="live") -> LLMClient:
    return LLMClient(api_key="test-key", transport=transport, cassette=cassette, mode=mode)


class TestTierRouting:
    def test_t1_disables_thinking(self):
        t = StubTransport([make_response(GOOD_JSON)])
        client_with(t).call(Tier.T1_FLASH, PROMPT, VillageRumor)
        assert t.payloads[0]["thinking"] == {"type": "disabled"}
        assert t.payloads[0]["model"] == "deepseek-v4-flash"

    def test_t2_thinks_by_default(self):
        t = StubTransport([make_response(GOOD_JSON, reasoning="let me think")])
        client_with(t).call(Tier.T2_FLASH_THINKING, PROMPT, VillageRumor)
        assert "thinking" not in t.payloads[0]  # default = thinking on

    def test_t3_uses_pro(self):
        t = StubTransport([make_response(GOOD_JSON)])
        client_with(t).call(Tier.T3_PRO, PROMPT, VillageRumor)
        assert t.payloads[0]["model"] == "deepseek-v4-pro"

    def test_t0_rejected_by_call(self):
        with pytest.raises(ValueError):
            client_with(StubTransport([])).call(Tier.T0_GRAMMAR, PROMPT)


class TestStrictJson:
    def test_schema_message_prepended(self):
        t = StubTransport([make_response(GOOD_JSON)])
        client_with(t).call(Tier.T1_FLASH, PROMPT, VillageRumor)
        msgs = t.payloads[0]["messages"]
        assert msgs[0]["role"] == "system"
        assert "json" in msgs[0]["content"].lower()
        assert t.payloads[0]["response_format"] == {"type": "json_object"}

    def test_valid_parse(self):
        r = client_with(StubTransport([make_response(GOOD_JSON)])).call(
            Tier.T1_FLASH, PROMPT, VillageRumor)
        assert r.parsed is not None
        assert r.parsed.severity == 3
        assert r.parsed.involves_mill is True

    def test_fenced_json_stripped(self):
        fenced = f"```json\n{GOOD_JSON}\n```"
        r = client_with(StubTransport([make_response(fenced)])).call(
            Tier.T1_FLASH, PROMPT, VillageRumor)
        assert r.parsed is not None

    def test_retry_with_warning(self):
        t = StubTransport([
            make_response("not json at all"),
            make_response(GOOD_JSON),
        ])
        r = client_with(t).call(Tier.T1_FLASH, PROMPT, VillageRumor)
        assert r.parsed is not None
        assert r.cost.attempts == 2
        # attempt 2 must carry the failed output + warning
        second = t.payloads[1]["messages"]
        assert second[-2]["role"] == "assistant"
        assert second[-2]["content"] == "not json at all"
        assert "failed validation" in second[-1]["content"]

    def test_schema_error_after_exhaustion(self):
        t = StubTransport([make_response("garbage")] * 3)
        with pytest.raises(SchemaError):
            client_with(t).call(Tier.T1_FLASH, PROMPT, VillageRumor, max_attempts=3)


class TestCassettes:
    def test_record_then_replay_identical(self, tmp_path):
        cassette = CassetteStore(tmp_path)
        live = client_with(StubTransport([make_response(GOOD_JSON)]),
                           cassette=cassette, mode="record")
        r1 = live.call(Tier.T1_FLASH, PROMPT, VillageRumor)

        # replay mode: no API key, transport that explodes if called
        replayer = LLMClient(cassette=cassette, mode="replay",
                             transport=StubTransport([]))
        r2 = replayer.call(Tier.T1_FLASH, PROMPT, VillageRumor)
        assert r2.from_cassette
        assert r2.parsed.model_dump() == r1.parsed.model_dump()
        assert r2.raw_text == r1.raw_text

    def test_replay_miss_raises(self, tmp_path):
        replayer = LLMClient(cassette=CassetteStore(tmp_path), mode="replay")
        with pytest.raises(CassetteMiss):
            replayer.call(Tier.T1_FLASH, PROMPT, VillageRumor)

    def test_record_only_on_success(self, tmp_path):
        cassette = CassetteStore(tmp_path)
        with pytest.raises(SchemaError):
            client_with(StubTransport([make_response("bad")] * 3),
                        cassette=cassette, mode="record").call(
                Tier.T1_FLASH, PROMPT, VillageRumor, max_attempts=3)
        assert cassette.list() == []


class TestCostLog:
    def test_usage_parsing(self):
        usage = {
            "prompt_tokens": 100,
            "completion_tokens": 25,
            "prompt_cache_hit_tokens": 80,
            "prompt_cache_miss_tokens": 20,
            "completion_tokens_details": {"reasoning_tokens": 12},
        }
        r = client_with(StubTransport([
            make_response(GOOD_JSON, reasoning="hmm", usage=usage)
        ])).call(Tier.T2_FLASH_THINKING, PROMPT, VillageRumor)
        c = r.cost
        assert c.prompt_tokens == 100
        assert c.cached_input_tokens == 80
        assert c.uncached_input_tokens == 20
        assert c.completion_tokens == 25
        assert c.reasoning_tokens == 12
        assert c.source == "live"
        assert c.cost_usd == pytest.approx(compute_cost("deepseek-v4-flash", 80, 20, 25))

    def test_missing_usage_yields_zeros(self):
        resp = make_response(GOOD_JSON)
        resp["usage"] = None
        r = client_with(StubTransport([resp])).call(Tier.T1_FLASH, PROMPT, VillageRumor)
        assert r.cost.prompt_tokens == 0
        assert r.cost.cost_usd == 0.0

    def test_cost_matches_spec_75(self):
        # Engine spec §7.5 worked example: 4k cached + 500 uncached + 300 out
        # on V4-Flash ≈ $0.00017/min.
        cost = compute_cost("deepseek-v4-flash", 4000, 500, 300)
        assert cost == pytest.approx(0.0001652, rel=1e-9)


class TestGrammarTier:
    def test_deterministic(self):
        a = grammar.render("rumor_headline", Stream(1, "g"), 0)
        b = grammar.render("rumor_headline", Stream(1, "g"), 0)
        assert a == b

    def test_unknown_template(self):
        with pytest.raises(KeyError):
            grammar.render("nope", Stream(1, "g"), 0)

    def test_templates_expand(self):
        line = grammar.render("weather_line", Stream(1, "g"), 0)
        assert len(line.split()) >= 4
