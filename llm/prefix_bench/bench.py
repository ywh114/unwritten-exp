"""L2 — the A/B bench: naive vs. disciplined prefix usage.

`run_bench` drives an event stream through an L1 client in one of two
modes and returns measured token/cost totals:

- **naive** — one call per event, and each call's "digest" includes the
  event itself (the undisciplined baseline: the prefix never repeats,
  so nothing is ever cache-hit).
- **disciplined** — a `PromptBuilder` with an epoch-stable prefix and a
  flush policy batching the tail.

`FakeCacheTransport` simulates the provider's prefix cache for API-free
tests: it reports `prompt_cache_hit_tokens` when the incoming system
prefix is byte-identical to the previous call's — so cache hits in
tests are *earned* by real byte-stability, not asserted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from llm.llm_client.client import LLMClient
from llm.llm_client.tiers import Tier

from llm.prefix_bench.builder import PromptBuilder
from llm.prefix_bench.policies import estimate_tokens

TIER = Tier.T1_FLASH


@dataclass
class BenchResult:
    mode: str
    events: int
    calls: int
    prompt_tokens: int
    cached_input_tokens: int
    uncached_input_tokens: int
    completion_tokens: int
    cost_usd: float

    @property
    def cache_hit_rate(self) -> float:
        """Fraction of input tokens served from cache."""
        return self.cached_input_tokens / self.prompt_tokens if self.prompt_tokens else 0.0


def naive_messages(system: str, digest_state: dict, event: str) -> list[dict]:
    """The undisciplined baseline: the 'digest' embeds the event, so the
    prefix never repeats byte-identically."""
    return [
        {"role": "system", "content": system},
        {"role": "system", "content": "World digest:\n" + json.dumps(
            {**digest_state, "latest_event": event}, sort_keys=True)},
        {"role": "user", "content": f"Event:\n- {event}"},
    ]


def run_bench(
    client: LLMClient,
    events: list[dict],
    mode: str,
    *,
    system: str,
    digest_state: dict,
    builder: PromptBuilder | None = None,
    policy=None,
    purpose: str = "bench",
) -> BenchResult:
    """Drive `events` (dicts with `text` and optional `priority`) through
    the client in `mode` ("naive" | "disciplined") and total the cost."""
    totals = dict(calls=0, prompt=0, cached=0, uncached=0, completion=0, cost=0.0)

    def _account(r) -> None:
        totals["calls"] += 1
        totals["prompt"] += r.cost.prompt_tokens
        totals["cached"] += r.cost.cached_input_tokens
        totals["uncached"] += r.cost.uncached_input_tokens
        totals["completion"] += r.cost.completion_tokens
        totals["cost"] += r.cost.cost_usd

    clock = 0
    for ev in events:
        clock += 1
        if mode == "naive":
            r = client.call(TIER, naive_messages(system, digest_state, ev["text"]),
                            purpose=purpose, clock=clock)
            _account(r)
        elif mode == "disciplined":
            if builder is None or policy is None:
                raise ValueError("disciplined mode requires builder and policy")
            builder.add_event(ev["text"])
            est = estimate_tokens("\n".join(e for e in builder._tail))
            if policy.should_flush(builder.pending_count, est, ev.get("priority")):
                r = client.call(TIER, builder.flush(), purpose=purpose, clock=clock)
                _account(r)
        else:
            raise ValueError(f"unknown mode {mode!r}")

    if mode == "disciplined" and builder is not None and builder.pending_count:
        clock += 1
        r = client.call(TIER, builder.flush(), purpose=purpose, clock=clock)
        _account(r)

    return BenchResult(
        mode=mode, events=len(events), calls=totals["calls"],
        prompt_tokens=totals["prompt"], cached_input_tokens=totals["cached"],
        uncached_input_tokens=totals["uncached"],
        completion_tokens=totals["completion"], cost_usd=totals["cost"],
    )


# ---------------------------------------------------------------------------
# Fake provider cache for API-free tests
# ---------------------------------------------------------------------------


class FakeCacheTransport:
    """Simulates the provider prefix cache.

    Remembers the previous call's system-prefix bytes; if the incoming
    call's prefix (all leading system messages) is byte-identical, the
    estimated prefix tokens are reported as cache hits, else misses.
    Response content is a fixed stub — content is not what a bench
    measures.
    """

    def __init__(self, out_tokens: int = 30):
        self._prev_prefix: str | None = None
        self._out_tokens = out_tokens
        self.payloads: list[dict] = []

    def __call__(self, payload: dict) -> dict:
        self.payloads.append(payload)
        prefix = json.dumps(
            [m for m in payload["messages"] if m["role"] == "system"],
            sort_keys=True, ensure_ascii=False,
        )
        prompt_tokens = sum(estimate_tokens(m["content"]) for m in payload["messages"])
        prefix_tokens = sum(
            estimate_tokens(m["content"]) for m in payload["messages"] if m["role"] == "system"
        )
        hit = prefix_tokens if prefix == self._prev_prefix else 0
        self._prev_prefix = prefix
        return {
            "id": "chatcmpl-fake",
            "choices": [{"message": {"role": "assistant", "content": "noted."}}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": self._out_tokens,
                "prompt_cache_hit_tokens": hit,
                "prompt_cache_miss_tokens": prompt_tokens - hit,
                "completion_tokens_details": {"reasoning_tokens": 0},
            },
        }
