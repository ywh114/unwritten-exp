# Ara module mapping

Source: design spec §10.4. Ara lives at `conversations/llmconv/` (reference
checkout, git-ignored). Recycled code carries `# ARA: <module>` provenance
comments (lab spec §7).

| Ara module | Becomes | Notes |
|---|---|---|
| `fortune/` (rolls, distributions, I-Ching, grammars) | Sampling/omen/content layer | Lift wholesale; simulation-agnostic |
| `memory/wiki.py` (trust scores, importance, distance cap, querier reframing) | Wiki/graveyard store (**K7**) | Add typed-promise schema + temporal validity metadata; `invented_fact_NNN` IDs → entity-stable UUIDs |
| `world/summarizer.py` (block format: FACT/TRUST/SOURCE, location finalization, keyword prefetch) | Backfill worker + commit message schema (**C2**) | The location-change classifier → terrain-diff commit gate |
| `llm/context.py` (per-entity visibility slices, hidden rules, branch/KV discipline) | Observation-log reader; prefix-stability patterns (**L2**) | Strip to visibility core |
| `world/orchestrator.py` (dynamic enum schemas, strict JSON, retries, fallback, tool loop) | Orchestrator service plumbing (**L1**, **C4**) | Rebuild loop around event triggers; keep schema/retry patterns |
| `spawn_anonymous` | Degenerate summon (Tier-2 NPCs) (**C5**) | Generalize upward to z-vector summons |
| `memory/knowledge.py` (scratchpads, per-character RAG) | NPC internal state + memory (**C3**) | Goals become Chekhov-seed soft promises |
| `prompts/orchestrator.py` (binding rolls, player-freedom guarantees, invisible steering) | Orchestrator system-prompt lineage (**C4**) | Add promise-tool instructions, intent rules, audit logging |

Not recycled: VN surface (sprites, webclient), scene graph / authored plots,
per-turn orchestration rhythm.
