# 2026-07-20 — L1 write-back: DeepSeek V4 pricing verified

**Amends:** engine spec §7.5 (cost model) — confirms flash rates,
corrects the implied Pro rates.
**Source:** [DeepSeek API pricing page](https://api-docs.deepseek.com/quick_start/pricing),
fetched 2026-07-20; encoded in `llm/llm_client/tiers.py` `PRICE_TABLE`.

## Numbers (per 1M tokens)

| model | input (cache hit) | input (cache miss) | output |
|---|---|---|---|
| deepseek-v4-flash | $0.0028 | $0.14 | $0.28 |
| deepseek-v4-pro | $0.003625 | $0.435 | $0.87 |

## Findings

1. **Flash rates match spec §7.5 exactly** — the per-minute worked
   example (~$0.00017, ~$0.01/hr) stands as written.
2. **Pro is not a flat 3× flash** (L1's initial inference): cache-hit
   input is only 1.29× flash, miss/output 3.1×. Cached prefixes are
   disproportionately cheap on Pro, which *strengthens* the spec's
   prefix-discipline argument for T3 chapter planning.
3. **The spec's T3 example still lands**: 6k cached + 2k uncached + 2k
   out on Pro = $0.00263/call ≈ the spec's $0.0026 — no amendment to
   the hourly envelope needed (still 1–5¢/hour).
4. **Model-tier reality check** (also in the L1 README): the API
   exposes two models and a thinking flag, not three models.
   `deepseek-chat`/`deepseek-reasoner` aliases deprecate 2026-07-24;
   the lab uses the `deepseek-v4-*` ids directly.
5. Prices drift — L2's prefix_bench should re-verify before amending
   §7.5's envelope.
