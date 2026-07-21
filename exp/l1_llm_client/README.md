# L1 — llm_client

## Goal

The one dependency every LLM experiment shares: a DeepSeek V4 wrapper
with tier routing, strict-JSON structured output, cassette
record/replay, and per-call token + cost logging. Done-when: cassettes
make CI API-free; the cost log schema is frozen (everything downstream
reads it).

## API

Library home: `llm.llm_client` (promoted 2026-07-20 per lab spec §6).

- **`Tier`**: `T0_GRAMMAR` (local, zero tokens), `T1_FLASH`,
  `T2_FLASH_THINKING`, `T3_PRO`. Verified against the live API
  (2026-07-20): model ids are `deepseek-v4-flash` / `deepseek-v4-pro`;
  flash thinks *by default*, so T1/T2 share the model and differ only in
  `thinking: {"type": "disabled"}`.
- **`LLMClient(api_key=None, cassette=None, mode=..., transport=None,
  cost_log=None)`** — modes `live` / `record` / `replay`. Replay needs
  no API key and never touches the network; an unknown request raises
  `CassetteMiss` (that is what makes CI API-free). The key comes from
  `api_key` or `DEEPSEEK_API_KEY` and is never logged or written to
  cassettes. `transport` is injectable for tests.
- **`client.call(tier, messages, schema=None, *, purpose, clock,
  max_tokens, temperature, max_attempts=3) -> CallResult`** — with a
  pydantic `schema`, a strict-JSON system message is prepended and the
  output is validated; failures retry with the bad output + warning fed
  back (Ara pattern), up to `max_attempts`, then `SchemaError`.
  Replays re-validate against the schema (stale cassettes fail loudly).
- **`grammar.render(template_id, stream, clock)`** — T0: deterministic
  template expansion, zero tokens.
- **`CassetteStore(dir)`** — one JSON file per call keyed by request
  content hash; records all attempts.
- **`CostLog` / `CostEntry`** — the FROZEN schema: `call_id, clock,
  purpose, tier, model, thinking, attempts, prompt_tokens,
  cached_input_tokens, uncached_input_tokens, completion_tokens,
  reasoning_tokens, cost_usd, source`. No wall-clock time (determinism);
  cost is computed from the tier price table, not API-reported dollars.
  Price table: flash rates per engine spec §7.5; pro at 3× (inferred
  from the spec's T3 example — L2 verifies with real numbers).

## Demo

`uv run python -m exp.l1_llm_client demo --seed 1 [--json] [--replay]`

T0 grammar line, then a structured `VillageRumor` call at T1/T2/T3,
then the same three calls replayed from cassette with the API off
(identical parsed output), then a cost report. Default: record if
`DEEPSEEK_API_KEY` is set, else replay. Cassettes are committed under
`cassettes/`.

Measured on the committed cassette (seed 1): 3 calls, in=765 tokens
(128 cached), out=345 (226 reasoning at T2), **$0.000283** total;
T1/T3 one attempt each, zero retries.

## Verdict

**works** (2026-07-20). 18 API-free tests: tier routing (T1 disables
thinking, T2 default-on, T3 pro), schema message + `response_format`,
valid/fenced/invalid JSON handling, retry-with-warning (failed output
fed back, attempts counted), SchemaError on exhaustion, cassette
record/replay identity, replay-miss raises, record-only-on-success,
usage parsing (cache hit/miss, reasoning tokens), cost math matching
spec §7.5's worked example, grammar determinism. Live-recorded
cassettes replay byte-identically with the key unset.

## Spec-notes

- **The API's thinking toggle defines T1/T2.** The lab spec imagined
  three model tiers; the live API has two models and a thinking flag.
  `TIER_THINKING` in `llm/llm_client/tiers.py` is now the single source
  of truth for the mapping.
- **Pricing is verified, with a nuance.** The price table was checked
  against the [official pricing page](https://api-docs.deepseek.com/quick_start/pricing)
  (2026-07-20): flash matches spec §7.5 exactly; pro is cached
  $0.003625 / miss $0.435 / out $0.87 per 1M — NOT the spec's implied
  flat 3× (real: cached 1.29×, miss/out 3.1×). The spec's T3 worked
  example still lands at $0.0026/call. See
  `docs/spec-notes/2026-07-20-l1-deepseek-v4-pricing.md`.
- **Cached-token accounting uses `prompt_cache_hit/miss_tokens`** from
  the usage block (verified present); cache hits land in
  `cached_input_tokens` in the cost schema, which is what L2's
  prefix-cache discipline will optimize.
