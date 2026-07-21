"""K7 — wiki_store: trust-scored facts and the promise graveyard.

Content-addressed facts with world-POV trust (no inversion, never
per-character belief), temporal validity, archive-instead-of-delete,
deterministic vector recall behind a `VectorIndex` swap point, and a
dry-register chronicle of the graveyard.  Partial port of Ara's
`memory/wiki.py` (no LLM subagent, no TOML ingestion, no ChromaDB).

Promoted from exp/k7_wiki (2026-07-20, verdict: works).  The exp/
directory keeps the demo, fixtures, and tests as living documentation.
"""

from kernel.wiki_store.facts import Fact, FactState, close, make_fact
from kernel.wiki_store.index import HashedIndex
from kernel.wiki_store.store import QuerierContext, WikiStore

__all__ = [
    "Fact", "FactState", "close", "make_fact",
    "HashedIndex", "QuerierContext", "WikiStore",
]
