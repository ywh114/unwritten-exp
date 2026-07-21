"""L1 — llm_client: the one dependency every LLM experiment shares.

DeepSeek V4 wrapper with:
- tier routing (T1 flash / T2 flash-thinking / T3 pro — T0 is local, see
  `grammar.py`),
- strict-JSON output validated against pydantic schemas with the Ara
  retry-with-warning pattern (failed output plus a warning is fed back,
  up to `max_attempts`),
- cassette record/replay (CI is API-free in replay mode),
- per-call token + cost logging (frozen `CostEntry` schema).

The API key comes from `api_key` or DEEPSEEK_API_KEY and is never
logged, never written to cassettes, never printed.
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from llm.llm_client.cassette import CassetteStore, request_key
from llm.llm_client.costlog import CostEntry, CostLog, call_id_for, compute_cost
from llm.llm_client.tiers import MODEL_IDS, TIER_THINKING, Tier

Transport = Callable[[dict], dict]

DEFAULT_BASE_URL = "https://api.deepseek.com"


class SchemaError(Exception):
    """Structured output failed validation after all attempts."""


@dataclass
class CallResult:
    parsed: BaseModel | None     # validated pydantic object, if schema given
    raw_text: str                # assistant content as returned
    reasoning: str | None        # reasoning_content, when the tier thinks
    usage: dict                  # API usage block
    cost: CostEntry
    from_cassette: bool


def urllib_transport(base_url: str, api_key: str, timeout: float = 120.0) -> Transport:
    """Default transport: one POST per call to /chat/completions."""
    url = base_url.rstrip("/") + "/chat/completions"

    def transport(payload: dict) -> dict:
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    return transport


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.removesuffix("```").strip()
    return t


class LLMClient:
    """Tier-routed DeepSeek client with cassettes and cost logging.

    mode: "live" (API only), "record" (API + write cassette),
    "replay" (cassette only — no API key needed, unknown requests raise
    CassetteMiss). In replay mode the transport is never invoked.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        cassette: CassetteStore | None = None,
        mode: str = "live",
        transport: Transport | None = None,
        cost_log: CostLog | None = None,
    ) -> None:
        if mode not in ("live", "record", "replay"):
            raise ValueError(f"unknown mode {mode!r}")
        if mode in ("record", "replay") and cassette is None:
            raise ValueError(f"mode {mode!r} requires a cassette store")
        self.mode = mode
        self.cassette = cassette
        self.cost_log = cost_log if cost_log is not None else CostLog()
        self._api_key = api_key if api_key is not None else os.environ.get("DEEPSEEK_API_KEY", "")
        if transport is not None:
            self._transport = transport
        elif mode == "replay":
            self._transport = None  # never called
        else:
            if not self._api_key:
                raise ValueError("no API key (api_key or DEEPSEEK_API_KEY) for live/record mode")
            self._transport = urllib_transport(base_url, self._api_key)

    # ---- public API ---------------------------------------------------------

    def call(
        self,
        tier: Tier,
        messages: list[dict],
        schema: type[BaseModel] | None = None,
        *,
        purpose: str = "",
        clock: int = 0,
        max_tokens: int = 512,
        temperature: float = 0.0,
        max_attempts: int = 3,
    ) -> CallResult:
        """One structured (or plain) call at a tier.

        With `schema`, the model is instructed to answer strict JSON; the
        output is validated with pydantic, and failures retry with the
        bad output plus a warning fed back (Ara pattern).
        """
        if tier == Tier.T0_GRAMMAR:
            raise ValueError("T0 is the local grammar tier — use grammar.render()")
        model = MODEL_IDS[tier]
        thinking = TIER_THINKING[tier]

        full_messages = list(messages)
        if schema is not None:
            full_messages = [self._schema_message(schema)] + full_messages

        canonical = {
            "model": model,
            "thinking": thinking,
            "messages": full_messages,
            "schema": schema.__name__ if schema is not None else None,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        key = request_key(canonical)

        if self.mode == "replay":
            response = self.cassette.replay(key)
            parsed = None
            if schema is not None:
                # recorded content was validated at record time; a parse
                # failure here means the cassette is stale or corrupt
                content = response["choices"][0]["message"].get("content") or ""
                try:
                    parsed = schema.model_validate(json.loads(_strip_fences(content)))
                except (json.JSONDecodeError, ValidationError) as exc:
                    raise SchemaError(f"cassette for tier {tier.value} no longer validates: {exc}")
            return self._finish(response, tier, model, thinking, schema,
                                purpose, clock, attempts=1, from_cassette=True,
                                parsed=parsed)

        # live / record: attempt loop with retry-with-warning
        attempts_log: list[dict] = []
        working = list(full_messages)
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            payload = {
                "model": model,
                "messages": working,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if not thinking:
                payload["thinking"] = {"type": "disabled"}
            if schema is not None:
                payload["response_format"] = {"type": "json_object"}

            response = self._transport(payload)
            attempts_log.append({"payload": payload, "response": response})
            content = response["choices"][0]["message"].get("content") or ""

            if schema is None:
                if self.mode == "record":
                    self.cassette.record(key, canonical, attempts_log)
                return self._finish(response, tier, model, thinking, None,
                                    purpose, clock, attempts=attempt, from_cassette=False)
            try:
                parsed = schema.model_validate(json.loads(_strip_fences(content)))
                if self.mode == "record":
                    self.cassette.record(key, canonical, attempts_log)
                return self._finish(response, tier, model, thinking, schema,
                                    purpose, clock, attempts=attempt, from_cassette=False,
                                    parsed=parsed)
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
                working = working + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": (
                        "Your previous output failed validation: "
                        f"{exc}. Respond again with valid JSON only, "
                        "matching the schema exactly."
                    )},
                ]
        raise SchemaError(
            f"tier {tier.value} failed validation after {max_attempts} attempts: {last_error}"
        )

    # ---- internals ------------------------------------------------------------

    def _schema_message(self, schema: type[BaseModel]) -> dict:
        return {
            "role": "system",
            "content": (
                "Respond with a single JSON object matching this JSON Schema. "
                "No prose, no markdown fences.\n"
                + json.dumps(schema.model_json_schema(), sort_keys=True)
            ),
        }

    def _finish(self, response, tier, model, thinking, schema,
                purpose, clock, *, attempts, from_cassette, parsed=None) -> CallResult:
        message = response["choices"][0]["message"]
        usage = response.get("usage") or {}
        cached = int(usage.get("prompt_cache_hit_tokens", 0))
        uncached = int(usage.get("prompt_cache_miss_tokens",
                                 usage.get("prompt_tokens", 0) - cached))
        completion = int(usage.get("completion_tokens", 0))
        reasoning_tokens = int(
            (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)
        )
        cost = CostEntry(
            call_id=call_id_for(json.dumps({"response": response.get("id"), "purpose": purpose})),
            clock=clock,
            purpose=purpose,
            tier=tier.value,
            model=model,
            thinking=thinking,
            attempts=attempts,
            prompt_tokens=cached + uncached,
            cached_input_tokens=cached,
            uncached_input_tokens=uncached,
            completion_tokens=completion,
            reasoning_tokens=reasoning_tokens,
            cost_usd=compute_cost(model, cached, uncached, completion),
            source="replay" if from_cassette else self.mode,
        )
        self.cost_log.append(cost)
        return CallResult(
            parsed=parsed,
            raw_text=message.get("content") or "",
            reasoning=message.get("reasoning_content"),
            usage=usage,
            cost=cost,
            from_cassette=from_cassette,
        )
