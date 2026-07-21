"""L1 — llm_client: DeepSeek V4 wrapper with tier routing, strict-JSON
structured output, cassette record/replay, and cost logging.

Promoted from exp/l1_llm_client (2026-07-20, verdict: works).  The exp/
directory keeps the demo, fixtures, tests, and committed cassettes as
living documentation.
"""

from llm.llm_client.tiers import Tier, MODEL_IDS, TIER_THINKING, PRICE_TABLE
from llm.llm_client.client import LLMClient, CallResult, SchemaError
from llm.llm_client.cassette import CassetteStore, CassetteMiss
from llm.llm_client.costlog import CostEntry, CostLog, compute_cost
from llm.llm_client import grammar

__all__ = [
    "Tier", "MODEL_IDS", "TIER_THINKING", "PRICE_TABLE",
    "LLMClient", "CallResult", "SchemaError",
    "CassetteStore", "CassetteMiss",
    "CostEntry", "CostLog", "compute_cost", "grammar",
]
