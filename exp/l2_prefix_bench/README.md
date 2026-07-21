# L2 — prefix_bench

## Goal

The cache-discipline harness. Two deliverables (lab spec §3 L2
done-when): a reusable **`PromptBuilder`** encoding the
`[system+schemas+digest+intents] → [event tail]` layout, and
confirmation/revision of the engine spec §7.5 cost envelope with real
numbers.

## API

Library home: `llm.prefix_bench` (promoted 2026-07-20 per lab spec §6).

- **`PromptBuilder(system, schemas=())`** — epoch-stable prefix +
  batched event tail. `begin_epoch(digest_state, intents=())` (digest
  serialized via `canonical_digest` — sort-keys, byte-stable; pending
  tail survives epoch changes), `add_event(text)`, `build_messages()`,
  `flush()`, `prefix_bytes()` (stability check). Prefix changes ONLY at
  epoch boundaries — that is the whole discipline.
- **Flush policies** — `EveryN(n)`, `TokenBudget(budget)`,
  `OnPriority(level)`; urgent events always flush immediately.
  `estimate_tokens(text)` (~4 chars/token).
- **`run_bench(client, events, mode, *, system, digest_state, builder,
  policy) -> BenchResult`** — drives an event stream through an L1
  client in `naive` (per-event calls, digest embeds the event) or
  `disciplined` mode, returns measured tokens/cost and
  `cache_hit_rate`.
- **`FakeCacheTransport`** — API-free provider-cache simulation for
  tests: reports cache hits only for byte-identical shared prefixes, so
  hits are earned, not asserted.

## Demo

`uv run python -m exp.l2_prefix_bench demo --seed 1 [--json] [--replay]`

One scripted hour of play (40 events, 3 urgent) through both modes with
a realistic ~1.6k-token prefix. Measured (recorded cassette, seed 1):

| mode | calls | input tokens | cached | hit rate | cost/hour |
|---|---|---|---|---|---|
| naive | 40 | 31,777 | 24,320 | 77% | $0.001946 |
| disciplined | 10 | 8,046 | 6,400 | 80% | $0.000758 |

Spec §7.5 model: $0.0099/hr; envelope claim 1–5¢/hr. **Both modes land
an order of magnitude under the model** — the envelope holds, with
margin, because the fixture prefix (~1.6k tokens) is smaller than the
spec's assumed 4k and batching cuts call count 4×.

## Verdict

**works** (2026-07-20). 15 API-free tests: prefix byte-stability within
epochs and invalidation across, canonical-digest key-order independence,
flush semantics (clear-on-flush, empty-raises, tail survives epoch
change), all three policies + urgent override, naive-never-caches and
disciplined-earns-hits through `FakeCacheTransport`, disciplined cheaper
than naive, urgent immediate flush, final partial batch, fixture shape.
Live bench + replay byte-identical with the API key unset.

## Spec-notes

See `docs/spec-notes/2026-07-20-l2-prefix-cache-mechanics.md`. The
headline: **the provider caches shared prefixes in 128-token blocks —
any shared prefix, not just whole requests** (probed live). Naive mode
already got 77% hits; the disciplined win is 4× fewer calls and a fully
stable prefix, not zero-vs-nonzero caching. Discipline rules: keep the
prefix a multiple of 128 tokens where practical, treat anything after
the first divergence point as dead cache, and remember output tokens
dominate cost — batching is the biggest lever.
