# 2026-07-20 — L2 verdict: prefix-cache mechanics and the §7.5 envelope

**Amends:** engine spec §7.2/§7.5 (cache discipline, cost model) —
confirms the envelope, adds provider-mechanics detail the spec did not
have.
**Source:** live probes + the L2 bench (`exp/l2_prefix_bench`), seed 1,
V4-Flash rates per `docs/spec-notes/2026-07-20-l1-deepseek-v4-pricing.md`.

## Probed mechanics

Three identical calls (1,638-token prompt, thinking disabled):

| call | prompt | cache hit | miss |
|---|---|---|---|
| 0 | 1638 | 0 | 1638 |
| 1 | 1638 | **1536** | 102 |
| 2 | 1638 | **1536** | 102 |

1536 = 12 × 128. **The cache works on 128-token blocks of any shared
prefix** — not whole requests, and the sub-128 remainder never caches.
TTL: survives at least minutes (bench ran ~1 min, hits throughout);
not measured beyond that.

## Consequences for the discipline (§7.2)

1. **A stable system block is already half the win.** The naive bench
   mode (stable system prompt, varying digest after it) still got 77%
   cache hits. What an unstable prefix kills is only everything *after
   the divergence point*.
2. **Keep the prefix a multiple of 128 tokens** where practical — the
   remainder below the block boundary is never cached. Pad with useful
   content (schema docs, style rules), not whitespace.
3. **Batching is the biggest lever**, bigger than cache rate:
   disciplined mode's hit rate (80%) barely beat naive (77%), but 10
   calls vs. 40 cut total cost 2.6×. Output tokens dominate (§7.5 said
   this; now measured).

## §7.5 envelope: confirmed

One hour of play (40 events, ~1.6k-token prefix):

| mode | calls | hit rate | cost/hour |
|---|---|---|---|
| naive | 40 | 77% | $0.0019 |
| disciplined | 10 | 80% | $0.00076 |

Spec model: $0.0099/hr; claim: 1–5¢/hr. **Confirmed with margin** —
even the undisciplined baseline lands 5× under the model. The spec's
assumptions (4k prefix, 1 call/min) are conservative relative to what
the discipline achieves. No envelope revision needed; the risk §7.5
named (prefix-stability discipline, not price) is the correct risk.
