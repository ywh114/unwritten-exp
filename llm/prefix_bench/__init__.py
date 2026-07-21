"""L2 — prefix_bench: cache discipline harness.

`PromptBuilder` enforces the [system+schemas+digest+intents] → [event
tail] layout with epoch-stable prefixes; flush policies decide when the
tail ships; `run_bench` measures naive vs. disciplined token/cost over
an event stream.  Provider reality (probed 2026-07-20): shared prefixes
cache in 128-token blocks — see
docs/spec-notes/2026-07-20-l2-prefix-cache-mechanics.md.

Promoted from exp/l2_prefix_bench (2026-07-20, verdict: works).  The
exp/ directory keeps the demo, fixtures, tests, and cassettes as living
documentation.
"""

from llm.prefix_bench.builder import PromptBuilder, canonical_digest
from llm.prefix_bench.policies import EveryN, OnPriority, TokenBudget, estimate_tokens
from llm.prefix_bench.bench import BenchResult, FakeCacheTransport, run_bench

__all__ = [
    "PromptBuilder", "canonical_digest",
    "EveryN", "OnPriority", "TokenBudget", "estimate_tokens",
    "BenchResult", "FakeCacheTransport", "run_bench",
]
